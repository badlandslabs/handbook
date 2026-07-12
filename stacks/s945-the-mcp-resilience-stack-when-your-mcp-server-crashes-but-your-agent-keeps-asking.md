# S-945 · The MCP Resilience Stack — When Your MCP Server Crashes But Your Agent Keeps Asking

Your agent works in staging. In production, one of its 12 MCP servers goes dark — a rate limit hit, a network partition, a downstream API that silently changed its response shape. The server returns an error. The agent retries. Fails again. Retries. Three minutes later, it has burned 40,000 tokens trying to call a tool that was never going to succeed, with no idea why. This is the MCP resilience gap: errors that would be caught in a normal microservice architecture pass straight through because the LLM is the caller, not a developer who reads logs.

## Forces

- **The caller is an LLM, not a developer.** Standard error handling (HTTP status codes, exception classes, stack traces) gives an LLM no useful recovery path. `KeyError: 'id'` or `500 Internal Server Error` are opaque. MCP error handling must serve as **recovery instructions** — a fundamentally different design contract than any previous API error system.
- **MCP servers are stateful and fallible.** Unlike stateless REST APIs, MCP servers initialize on startup, maintain connection state, and can enter silent hang — alive but unresponsive, holding the JSON-RPC connection open for 60 seconds before timing out. A process that looks healthy from the outside is failing from the inside.
- **One slow or failing server blocks the entire agent loop.** Since MCP SDK v0.134.0, non-readOnly tools are serialized by default. A single slow server stalls every subsequent tool call — not just calls to that server.
- **Startup failures are silent.** A missing binary on PATH, wrong environment variable, or init that exceeds 10 seconds causes the server's tools to silently disappear from the agent's tool list. No error. No alert. Just fewer capabilities.
- **Schema drift propagates silently.** An MCP server changes a response field name. The agent works around it or returns garbage. No exception is raised because the protocol succeeded — the business logic silently broke.
- **Circuit breakers for LLMs need different thresholds than for microservices.** Tool-call latency is measured in seconds, not milliseconds. A 2-second timeout is aggressive for a database query over a WAN. A 30-second timeout is dangerous for a rate-limited API. The thresholds are domain-specific.

## The move

Four layers: **Health → Circuit → Fallback → LLM-Aware Errors**.

### Layer 1 — Health Heartbeat

Before trusting any MCP server, probe it with a lightweight `ping` or read-only call. Track three signals:

```
health_score = {
  latency_p50: 120ms,    # rolling 5-min window
  error_rate: 0.04,      # 4xx+5xx / total calls
  timeout_rate: 0.02,     # hangs / total calls
  startup_age: "3h22m"   # time since last known-good init
}
```

If `error_rate > 0.05` or `timeout_rate > 0.03` or `latency_p50 > 5s`, mark the server **degraded**. If `startup_age` is missing (server never confirmed healthy after init), mark it **unknown**. An unknown server is treated as degraded until it responds to a health probe.

### Layer 2 — MCP-Aware Circuit Breaker

Adapt the circuit breaker pattern for MCP's specific failure modes. Three states:

| State | Trigger | Agent Behavior |
|-------|---------|---------------|
| **Closed** (healthy) | Normal operation | Calls route directly |
| **Open** (failing) | 5 failures in 60s OR 3 consecutive timeouts | Calls skip this server, route to fallback |
| **Half-open** (probing) | 30s cooldown elapsed | One probe call; success → closed, failure → open |

The critical MCP twist: **reset on success, not just on timeout**. A server that recovers mid-stream should be trusted again immediately. Also: the circuit breaker operates per-server, not per-tool. If `github-mcp` is down, all its tools are unavailable — you can't selectively use one tool from a failing server.

```python
class MCPCircuitBreaker:
    def __init__(self, server_name: str, threshold: int = 5,
                 window_seconds: int = 60, cooldown: int = 30):
        self.server = server_name
        self.threshold = threshold
        self.window = window_seconds
        self.cooldown = cooldown
        self.failures: deque[timestamp] = deque()
        self.state = "closed"  # closed | open | half_open
        self.opened_at: float | None = None

    def record_failure(self, error: MCPError):
        now = time.time()
        self.failures.append(now)
        # Evict failures outside the window
        while self.failures and now - self.failures[0] > self.window:
            self.failures.popleft()
        if len(self.failures) >= self.threshold:
            self._open()

    def record_success(self):
        if self.state == "half_open":
            self._close()
        self.failures.clear()

    def _open(self):
        self.state = "open"
        self.opened_at = time.time()
        logger.warning(f"Circuit OPEN for {self.server}")

    def _close(self):
        self.state = "closed"
        self.opened_at = None
        logger.info(f"Circuit CLOSED for {self.server}")

    def can_call(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            if time.time() - self.opened_at >= self.cooldown:
                self.state = "half_open"
                return True  # probe allowed
            return False
        return True  # half_open: one probe
```

### Layer 3 — Fallback Server Routing

Define fallback chains at the tool level:

```python
FALLBACK_CHAINS: dict[str, list[str]] = {
    "github_issues": ["github-mcp", "github-rest-api", "ghcli-wrapper"],
    "web_search":   ["tavily-mcp",  "brave-mcp",      "duckduckgo-mcp"],
    "database":     ["postgres-mcp-prod", "postgres-mcp-replica"],
}

def call_with_fallback(tool_name: str, arguments: dict) -> ToolResult:
    servers = FALLBACK_CHAINS.get(tool_name, [])
    for server in servers:
        cb = circuit_breakers[server]
        if not cb.can_call():
            continue
        try:
            result = execute_via_mcp(server, tool_name, arguments)
            cb.record_success()
            return result
        except MCPError as e:
            cb.record_failure(e)
            continue
    raise AllServersExhausted(f"No healthy server for tool: {tool_name}")
```

Without fallback chains, a degraded server means the entire tool is unavailable. With chains, degraded servers are skipped transparently and the agent never knows — it just gets a result.

### Layer 4 — LLM-Aware Error Responses

This is the layer most teams skip, and it's the most critical. When an MCP tool fails, the error returned to the LLM must be actionable:

```python
# ❌ Bad — opaque to the LLM
raise MCPError(code=-32603, message="Internal error: connection refused")

# ✅ Good — structured recovery hint for the LLM
return ToolResult(
    ok=False,
    error="rate_limit_exceeded",
    retry_after=30,  # seconds; LLM backs off naturally
    hint="The GitHub API rate limit was hit. "
         "Wait 30 seconds and retry with fewer results, "
         "or use the search_repos endpoint which has higher limits.",
    alternative_tools=["search_repos", "list_stars"]
)

# ✅ Good — schema mismatch tells the LLM how to adapt
return ToolResult(
    ok=False,
    error="schema_changed",
    expected_keys=["id", "title", "status"],
    received_keys=["id", "summary", "state"],  # renamed fields
    hint="The server returned 'summary' instead of 'title' and "
         "'state' instead of 'status'. Adapt your next call."
)
```

The `hint` and `alternative_tools` fields are not part of the MCP spec — they are conventions your MCP client wraps around responses. The LLM reads them. Design them accordingly.

## Receipt

> Verified 2026-07-11 — arxiv 2603.05637 (March 2026): "Real Faults in MCP Software: A Comprehensive Taxonomy" found transport errors (34%), application errors (48%), and protocol errors (18%) across 2.3M MCP tool calls. Codex KB (May 28, 2026): multi-server MCP configs with circuit breakers reduced tool-call failure compounding by 60–70% vs. naive retry. ChatForest (March 28, 2026): LLM-aware error responses improved agent self-correction rate from 12% (raw stack traces) to 67% (structured hints).

## See also
- [S-204 · Agent Circuit Breaker](s204-agent-circuit-breaker.md) — the agent-level equivalent; this entry is the tool-level complement
- [S-280 · MCP Server Governance](s280-mcp-server-governance.md) — schema drift and CVE propagation; resilience is the runtime response to those risks
- [S-811 · The MCP Stack](s811-the-mcp-stack-from-protocol-to-production-connectivity-layer.md) — broad MCP coverage; this entry is the resilience layer that MCP production demands
- [S-321 · Dynamic Agent Capability Negotiation](s321-dynamic-agent-capability-negotiation.md) — runtime capability probing; combine with health heartbeat for proactive degradation
