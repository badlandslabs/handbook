# S-2240 · The MCP Tool Cost Stack — When Your Agent Runs Up a Tab on Every Tool

Every MCP tool call your agent makes has a price tag attached — not just the LLM inference cost, but the token cost of loading tool schemas, the token cost of injecting results, and the downstream API costs the tool itself fires. Nobody tracks this. Most teams don't even know it exists. Then the monthly bill arrives and nobody can explain why a simple task ran 40,000 tokens through the MCP layer before a single tool was called.

## Forces

- **Tool richness vs. cost linearity** — More MCP servers = more tool capabilities = more schema tokens per call. There's no free lunch.
- **The schema load tax is invisible** — `tools/list` fetches the full tool surface of every connected server before the agent decides which tool to call. With 10 servers × 20 tools, that's 50k+ tokens burned before the first tool fires.
- **Result injection compounds** — A 10-step workflow where each tool returns 2,000 tokens adds 20,000 tokens to your bill that never appeared in any cost dashboard.
- **Multi-tenant collapse** — When one shared MCP server serves multiple clients, the tool call costs blur together. No per-client breakdown means no chargeback, no margin visibility, no way to answer "which client is actually profitable."

## The Move

**1. Isolate per-server token budgets, not just global budgets.**

MCP servers are the new microservices — each one has its own call frequency, response size, and upstream cost. Budget the MCP layer separately from LLM inference:

```python
# Per-MCP-server budget guard (simplified)
from dataclasses import dataclass
from typing import Optional
import time

@dataclass
class MCPServerBudget:
    name: str
    max_tokens_per_hour: int
    current_tokens: int = 0
    window_start: float = field(default_factory=time.time)

    def check(self, tokens: int) -> bool:
        """Returns True if within budget."""
        if time.time() - self.window_start > 3600:
            self.current_tokens = 0
            self.window_start = time.time()
        if self.current_tokens + tokens > self.max_tokens_per_hour:
            return False
        self.current_tokens += tokens
        return True

# Server budgets
SERVER_BUDGETS = {
    "github-production": MCPServerBudget("github-production", max_tokens_per_hour=500_000),
    "postgres-readonly": MCPServerBudget("postgres-readonly", max_tokens_per_hour=200_000),
    "web-search": MCPServerBudget("web-search", max_tokens_per_hour=100_000),
}

def mcp_tool_call(server: str, tool: str, args: dict) -> dict:
    budget = SERVER_BUDGETS.get(server)
    est_tokens = estimate_tool_result_tokens(server, tool, args)
    if budget and not budget.check(est_tokens):
        raise MCPServerQuotaExceeded(f"{server} over budget for this hour")
    result = execute_mcp_tool(server, tool, args)
    # Track actual for reconciliation
    record_tool_cost(server, tool, actual_tokens(result), cost_usd(result))
    return result
```

**2. Lazy-load the tool schema, not the kitchen sink.**

On startup, don't call `tools/list` on every connected server. Instead, maintain a lightweight **tool manifest** — just `{tool_name: server_name}` — and only fetch the full schema when the agent has narrowed down what it needs:

```python
# Lightweight manifest (fetched once, cached cheaply)
TOOL_MANIFEST = {
    # server: github-production
    "create_issue": "github-production",
    "list_prs": "github-production",
    "add_review": "github-production",
    # server: postgres-readonly
    "run_query": "postgres-readonly",
    "get_schema": "postgres-readonly",
}

# Full schema fetched only when needed
SCHEMA_CACHE: dict[str, dict] = {}

def get_tool_schema(server: str, tool: str) -> dict:
    cache_key = f"{server}:{tool}"
    if cache_key not in SCHEMA_CACHE:
        # This is where the token spend happens — gate it
        with mcp_token_budget(server, budget=5_000):
            SCHEMA_CACHE[cache_key] = fetch_full_schema(server, tool)
    return SCHEMA_CACHE[cache_key]
```

**3. Tag every tool call for multi-tenant attribution.**

Ingest a `client_id` and `request_id` into every MCP call context so the cost flows to the right bucket:

```python
# Propagation via MCP session context
CONTEXT_STACK = contextvars.ContextVar[dict] = contextvars.ContextVar("mcp_context", default={})

def tool_call(server: str, tool: str, args: dict) -> dict:
    ctx = CONTEXT_STACK.get()
    # Stamp the cost record with client + request for billing
    cost_record = {
        "client_id": ctx.get("client_id", "unknown"),
        "request_id": ctx.get("request_id", ""),
        "server": server,
        "tool": tool,
        "timestamp": time.time(),
    }
    result = _execute(server, tool, args)
    cost_record["tokens"] = result.token_count
    cost_record["cost_usd"] = result.cost_usd
    emit_cost_event("mcp_tool_call", cost_record)
    return result
```

**4. Cache tool results at the schema level, not the logic level.**

If two agents call `list_issues` on the same repo within 5 minutes, the MCP layer should de-duplicate the call and return a cached result — not re-execute. This is distinct from semantic caching (where you compare query similarity):

```python
from functools import lru_cache
import hashlib

@lru_cache(maxsize=1000)
def cached_tool_result(server: str, tool: str, args_hash: str, ttl: int = 300):
    """Cache tool results for TTL seconds by exact args hash."""
    if is_readonly_tool(tool) and time.time() - cached_at(args_hash) < ttl:
        return get_cached(args_hash)
    result = execute_mcp_tool(server, tool, args)
    return result
```

## Receipt

> Verified 2026-08-06 — TokenFence (2026-03-21): Tool description tokens = 2,000–5,000 per call for 10-tool server; tool result tokens = 1,000–10,000+ per result; multi-step 5–15 tool chains accumulate 20,000–50,000+ tool-layer tokens. Keito MCP cost tracking: per-client/project attribution is the primary missing piece in production MCP deployments. GitHub vanthienha199/agent-cost-mcp (real project, active): real-time per-message cost tracking across Claude Code, Cursor, Windsurf, Codex, Gemini CLI. MintMCP (2026-02-04): single runaway agent loop fired 127,000 API calls in ~8 hours, costing ~$47,000. MCP registry discovery (S-1254): tool catalog fetches can cost 55,000+ tokens before the conversation starts — confirming the schema-load tax is a real and common problem.

## See also

- [S-1890 · The Difficulty-Aware Escalation Stack](stacks/s1890-the-difficulty-aware-escalation-stack-when-static-tiers-hit-their-ceiling.md) — Dynamic routing and budget management across tiers
- [S-2186 · The Agent Budget Guard Stack](stacks/s2186-the-agent-budget-guard-stack-when-your-agent-is-your-biggest-monthly-expense.md) — Token budget enforcement at the agent level
- [S-2234 · The Agent Governance Readiness Stack](stacks/s2234-the-agent-governance-readiness-stack-when-your-pilot-wins-but-production-fails.md) — Multi-tenant accountability and audit trails
- [S-1254 · The MCP Registry Discovery Collapse](stacks/s1254-the-mcp-registry-discovery-collapse-when-your-tool-catalog-costs-55k-tokens-before-the-conversation-starts.md) — Tool catalog token cost at startup
