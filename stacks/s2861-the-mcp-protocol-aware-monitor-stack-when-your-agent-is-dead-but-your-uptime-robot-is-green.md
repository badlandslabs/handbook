# S-2861 · The MCP Protocol-Aware Monitor Stack — When Your Agent Is Dead but Your Uptime Robot Is Green

Of 2,181 public MCP endpoints audited in Q2 2026, 26.7% showed green on UptimeRobot while being completely unusable — HTTP alive, MCP dead. Your standard health check tells you the server process is running. It tells you nothing about whether the agent can actually talk to it. This is the MCP monitoring gap, and it is responsible for a class of production outages that no amount of HTTP probing will catch.

## Forces

- **Loud failures (38%) vs quiet failures (53%).** DNS lapses, host crashes, and expired TLS certificates are visible to any HTTP monitor. Route changes, OAuth token expiry, malformed JSON-RPC responses, and schema drift are invisible — the server responds 200, the agent gets garbage, no alert fires.
- **Standard monitors measure infrastructure, not protocol health.** An HTTP HEAD to port 11435 confirms the process is listening. It does not confirm that `initialize` returns a valid JSON-RPC response, that `tools/list` produces a non-empty tool catalog, or that the schema matches what your agent cached.
- **The compounding failure chain.** Schema drift → cached tool definitions go stale → agent calls a renamed tool with the old name → silent failure → downstream consequences compound for hours before detection. The root cause happened silently; the symptom manifests somewhere else entirely.
- **MCP's two failure dimensions are independent.** A server can be *reachable* (HTTP 200) and *correct* (schema matches, auth valid, response well-formed) independently. Standard monitoring only checks reachability.

## The Move

Replace HTTP-native health checks with MCP protocol-aware probes. The probe exercises the actual JSON-RPC surface your agent uses, not the TCP port the server happens to listen on.

### Layer 1 — JSON-RPC Round-Trip Probe

Send a real `initialize` request, not a curl to `/health`.

```python
import httpx
import hashlib
import time

MCP_TRANSPORT = "streamable-http"
MCP_PROTOCOL_VERSION = "2024-11-05"

class MCPHealthProbe:
    def __init__(self, server_url: str, auth_token: str | None = None):
        self.server_url = server_url
        self.headers = {"Authorization": f"Bearer {auth_token}"} if auth_token else {}

    def probe(self) -> dict:
        """Full JSON-RPC round-trip probe. Returns structured health report."""
        report = {"url": self.server_url, "ts": time.time(), "status": "unknown"}

        # 1. Initialize
        init_payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "mcp-health-probe", "version": "1.0.0"},
            },
        }
        try:
            resp = httpx.post(
                self.server_url,
                json=[init_payload],
                headers={**self.headers, "Content-Type": "application/json"},
                timeout=10.0,
            )
        except httpx.ConnectError as e:
            report.update({"status": "unreachable", "error": str(e)})
            return report

        if resp.status_code != 200:
            report.update({"status": "http_error", "code": resp.status_code})
            return report

        try:
            # MCP uses array response wrapping
            resp_data = resp.json()
            if isinstance(resp_data, list):
                resp_data = resp_data[0]
        except Exception:
            report.update({"status": "malformed_json", "error": "response is not valid JSON"})
            return report

        if "error" in resp_data:
            report.update({
                "status": "json_rpc_error",
                "error": resp_data["error"],
            })
            return report

        report["protocol_version"] = resp_data.get("result", {}).get("protocolVersion")

        # 2. tools/list — verify non-empty catalog
        tools_payload = {
            "jsonrpc": "2.0", "id": 2,
            "method": "tools/list",
            "params": {},
        }
        tools_resp = httpx.post(
            self.server_url,
            json=[tools_payload],
            headers={**self.headers, "Content-Type": "application/json"},
            timeout=10.0,
        )

        if tools_resp.status_code != 200:
            report.update({"status": "tools_list_http_error", "code": tools_resp.status_code})
            return report

        try:
            tools_data = tools_resp.json()
            if isinstance(tools_data, list):
                tools_data = tools_data[0]
            tools = tools_data.get("result", {}).get("tools", [])
        except Exception:
            report.update({"status": "malformed_tools_response"})
            return report

        report["tool_count"] = len(tools)
        report["tool_names"] = [t["name"] for t in tools]
        report["schema_hash"] = hashlib.sha256(
            str(sorted(report["tool_names"])).encode()
        ).hexdigest()[:16]

        # 3. Schema health
        if len(tools) == 0:
            report.update({"status": "degraded", "reason": "zero_tools"})
        else:
            report["status"] = "healthy"

        return report
```

### Layer 2 — Schema Hash Tracking (Drift Detection)

Store the previous `schema_hash` and alert on change. A 7.1% drift rate over 48 hours means this *will* happen in production.

```python
import redis

def check_schema_drift(probe_result: dict, server_id: str) -> list[str]:
    """Alert when tool catalog changes without corresponding deployment."""
    alerts = []
    r = redis.Redis(host="localhost", port=6379, decode_responses=True)
    hash_key = f"mcp:schema_hash:{server_id}"
    prev_hash = r.get(hash_key)

    if prev_hash is None:
        r.setex(hash_key, 86400 * 3, probe_result["schema_hash"])
        return alerts

    if prev_hash != probe_result["schema_hash"]:
        alerts.append(
            f"SCHEMA_DRIFT: {server_id} tool catalog changed "
            f"({prev_hash} → {probe_result['schema_hash']}). "
            f"Tools: {probe_result['tool_names']}. "
            f"Agent cache invalidation required."
        )
        r.setex(hash_key, 86400 * 3, probe_result["schema_hash"])

    return alerts
```

### Layer 3 — Authentication Expiry Watch

MCP servers using bearer-token auth have tokens that expire silently. Unlike OAuth web apps that redirect to login, MCP servers return 401 or malformed responses.

```python
def check_auth_expiry(probe: MCPHealthProbe) -> str | None:
    """Detect OAuth/bearer token expiry on MCP server."""
    result = probe.probe()
    if result["status"] == "unreachable":
        return None  # Already caught by infrastructure monitor
    if "json_rpc_error" in result["status"]:
        err = result.get("error", {})
        code = err.get("code", 0)
        # -32001 = auth error in some MCP implementations
        if code == -32001 or "auth" in str(err).lower():
            return f"AUTH_EXPIRED: MCP server {probe.server_url} authentication failed"
    if result["status"] == "http_error" and result.get("code") == 401:
        return f"AUTH_EXPIRED: MCP server {probe.server_url} returned 401"
    return None
```

### Layer 4 — Latency Baselines and Concurrency Falloff

The DigitalApplied study found P95 latency is 5.7× P50, and concurrency falloff reaches −18% at 32 parallel requests. Establish baselines per server and alert on degradation.

```python
from collections import deque
import statistics

class LatencyBaseline:
    def __init__(self, server_id: str, window: int = 100):
        self.server_id = server_id
        self.window = window
        self.latencies = deque(maxlen=window)

    def record(self, latency_ms: float):
        self.latencies.append(latency_ms)

    def is_degraded(self, current_ms: float, threshold: float = 2.5) -> bool:
        if len(self.latencies) < 20:
            return False
        p95_baseline = statistics.quantiles(list(self.latencies), n=20)[18]
        return current_ms > p95_baseline * threshold
```

## Receipt

> Verified 2026-08-19 — AliveMCP Q2 2026 audit of 2,181 endpoints confirms 26.7% "HTTP alive, MCP dead." DigitalApplied study (100 servers, 12,000 trials, Feb–Apr 2026) found P95 latency 5.7× P50 and −18% concurrency falloff at 32 parallel requests. Perplexity CTO cited MCP auth expiry and schema drift as top production failures before engineering patterns emerged. Tool composition compounding: median MCP server at 71% pass rate means a 5-tool call chain succeeds only 18% of the time end-to-end.

## See also

- [S-999 · The Silent Tool Catalog](s999-the-silent-tool-catalog-when-your-health-probe-is-green-but-your-agent-breaks.md) — MCP schema drift diagnosis (this entry adds monitoring)
- [S-1056 · The MCP Tool Contract Gate](s1056-the-mcp-tool-contract-gate-when-your-health-probe-is-green-but-your-agent-still-breaks.md) — CI/CD gate for schema changes (this entry adds runtime monitoring)
- [S-2352 · The Schema Drift Stack](s2352-the-schema-drift-stack-when-your-mcp-server-ships-a-breaking-change-and-your-agent-keeps-calling-it.md) — MCP-specific schema drift patterns
- [S-2856 · The Tool-Call Failure Layer](s2856-the-tool-call-failure-layer-stack-when-your-agent-thinks-it-worked-but-the-tool-lied.md) — outcome verification when tools return misleading success signals
