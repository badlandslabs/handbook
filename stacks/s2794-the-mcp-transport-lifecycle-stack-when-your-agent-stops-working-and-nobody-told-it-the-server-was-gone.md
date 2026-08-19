# S-2794 · The MCP Transport Lifecycle Stack — When Your Agent Stops Working and Nobody Told It the Server Was Gone

Your agent was working at 9 AM. By 10:30, it's failing every tool call. No code changed. No deployment happened. The MCP server is running — your health check confirms it. The agent just stopped being able to talk to it. This is not a schema drift problem (S-999, S-1056). The tool contract is fine. This is a **transport lifecycle failure**: the protocol layer between the agent and its tools died silently while every monitoring signal stayed green.

## Forces

- **Three transports, zero compatibility guarantee.** MCP supports stdio, SSE (deprecated), and Streamable HTTP. An agent built against stdio cannot connect to an HTTP-only server. A gateway that requires Streamable HTTP silently rejects stdio servers. The protocol your CI tested against is not the protocol your production gateway speaks.
- **OAuth token expiry is silent at the protocol level.** The MCP specification surfaces token expiry as a JSON-RPC error in the response body — HTTP 200, protocol success, zero alerts. Most APM tools only look at HTTP status codes. The agent keeps sending requests; the server keeps returning 200s with error payloads the APM never sees.
- **stdio servers are fire-and-forget.** When an MCP client spawns a stdio server as a child process, it has no automatic reconnect logic. Token expiry, OOM kills, manual restarts — all leave the agent with a dead pipe. The agent retries the same broken pipe indefinitely.
- **SSE is deprecated but still in production.** The MCP spec moved to Streamable HTTP as the canonical remote transport. Legacy servers still speak SSE. Gateways that require HTTP silently drop SSE connections. Agent tool catalogs that probe SSE endpoints get empty results and fall back to guessing.
- **Process exit codes are invisible to the host monitoring.** An MCP server that crashes logs nothing to the agent's observability stack. The agent sees only "connection refused" after the fact. The crash log lives on the server side — in a systemd journal nobody checks.
- **No delivery guarantee across the transport boundary.** MCP over HTTP has no at-least-once delivery guarantee. If the server process dies mid-request, the request is dropped. The client retries, gets a new process, starts clean. The dropped request is never recovered.

## The move

**Detect transport failures at the protocol boundary, not the application boundary.**

### Transport negotiation gate

```python
# Before registering MCP servers, verify transport compatibility
import subprocess, httpx, asyncio

TRANSPORT_REQUIREMENTS = {
    "stdio": {"can_connect": True},  # local process, always "reachable"
    "sse": {"deprecated": True, "can_connect": True},
    "streamable-http": {"canonical": True, "can_connect": True},
}

def verify_transport_compatibility(client_transport: str, server_transport: str) -> dict:
    """Gate: reject known-incompatible transport pairs before they reach production."""
    incompatibilities = {
        ("stdio", "streamable-http"): "gateway requires HTTP; stdio server cannot proxy",
        ("sse", "streamable-http"): "deprecated SSE server rejected by Streamable HTTP gateway",
    }
    if (client_transport, server_transport) in incompatibilities:
        return {"ok": False, "reason": incompatibilities[(client_transport, server_transport)]}
    if server_transport == "sse":
        return {"ok": True, "warning": "SSE is deprecated; migrate to Streamable HTTP"}
    return {"ok": True}

# Example: check a remote server's transport
async def probe_server_transport(base_url: str) -> str:
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(f"{base_url}/health")
        # Streamable HTTP servers return 200 on /
        return "streamable-http" if resp.status_code == 200 else "unknown"
```

### Token expiry watchdog

```python
import time, threading
from mcp.client import ClientSession

class MCPTokenExpiryWatchdog:
    """Catch token expiry inside JSON-RPC responses — invisible to HTTP APM."""
    
    def __init__(self, session: ClientSession, on_expiry: callable):
        self.session = session
        self.on_expiry = on_expiry
        self.last_check = time.time()
        self.token_ttl = 3600  # seconds; set from server's token response header
    
    def poll_and_refresh(self):
        """Run in a background thread; silently refreshes expired tokens."""
        while True:
            elapsed = time.time() - self.last_check
            if elapsed > self.token_ttl * 0.9:  # refresh at 90% of TTL
                try:
                    # Trigger a no-op call to force token validation
                    await self.session.call_tool("_auth_ping", {})
                    self.last_check = time.time()
                except Exception as e:
                    if "39011" in str(e) or "expired" in str(e).lower():
                        self.on_expiry()  # reconnect logic here
            time.sleep(300)  # check every 5 minutes

# Intercept JSON-RPC error responses at the transport layer
def wrap_mcp_response(response: dict) -> dict:
    """Parse MCP error codes that HTTP APM never surfaces."""
    MCP_TOKEN_ERRORS = {390114, 390113, 401, 403}
    if response.get("isError") and response.get("error", {}).get("code") in MCP_TOKEN_ERRORS:
        # Surface this as an alert, not just a tool result
        alert_mcp_auth_failure(
            code=response["error"]["code"],
            message=response["error"]["message"],
            server=os.environ.get("MCP_SERVER_NAME", "unknown")
        )
    return response
```

### stdio process lifecycle management

```python
import subprocess, signal, psutil

def spawn_mcp_stdio_server(cmd: list[str], max_restarts: int = 3) -> subprocess.Popen:
    """Spawn with restart limits and exit code visibility."""
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,  # capture stderr — this is where crashes land
    )
    # Monitor stderr for crash signals
    def watch_stderr():
        for line in process.stderr:
            if b"panic" in line or b"SIGSEGV" in line or b"fatal" in line:
                alert_mcp_crash(cmd=cmd, line=line.decode())
    threading.Thread(target=watch_stderr, daemon=True).start()
    return process

def health_check_stdio(process: subprocess.Popen) -> bool:
    """Poll the process is_alive() — the only reliable health signal for stdio servers."""
    if not process.poll() is None:
        return False  # process exited
    try:
        proc = psutil.Process(process.pid)
        return proc.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False  # already dead
```

### Transport-level canary probe

```python
async def mcp_transport_canary(session: ClientSession, server_name: str) -> dict:
    """Send a no-op probe at the transport layer; measure reachability, not schema."""
    start = time.time()
    try:
        result = await session.call_tool("_canary", {}, timeout=5.0)
        latency_ms = (time.time() - start) * 1000
        return {"reachable": True, "latency_ms": round(latency_ms, 1), "alive": True}
    except Exception as e:
        return {
            "reachable": False,
            "error": str(e),
            "likely_dead": "No such file or directory" in str(e) or "Broken pipe" in str(e),
            "likely_token_expired": "39011" in str(e) or "390114" in str(e),
            "likely_transport_mismatch": "Connection refused" in str(e),
        }
```

## Receipt

> Verified 2026-08-17 — Research backed by: GitHub Snowflake-Labs/MCP issue #176 (OAuth token expiry causing all tool calls to fail until server restart, 2026-05-16), KryptosAI/mcp-observatory (175+ stars, CI-native schema drift detection + health scoring), DriftGuard (live MCP tools/list monitoring for Cursor/Claude), MCP Python SDK docs (Streamable HTTP canonical, SSE legacy), rollbrains.com MCP transport comparison (2026-05-22), markaicode.com MCP auth errors guide (2026-05-30), grizzlypeaksoftware.com MCP debugging (stdio/SSE/HTTP transport failure modes). Key patterns: (1) OAuth token expiry is the #1 silent killer — surfaces as JSON-RPC error in HTTP 200; (2) stdio has no reconnect; (3) SSE deprecated but still in production; (4) gateway requirements are a common blocker; (5) process exit codes invisible to agent-side monitoring.

## See also

- [S-999 · The Silent Tool Catalog](s999-the-silent-tool-catalog-when-your-health-probe-is-green-but-the-agent-breaks.md) — schema drift as the silent tool failure
- [S-1474 · The MCP Bearer Token Gap](s1474-the-mcp-bearer-token-gap-when-authorization-is-true-but-not-verified.md) — authorization vs. authentication in MCP
- [S-1056 · The MCP Tool Contract Gate](s1056-the-mcp-tool-contract-gate-when-your-health-probe-is-green-but-your-agent-still-breaks.md) — CI-based schema contract enforcement
- [S-115 · Agent HTTP Connection Reuse](s115-agent-http-connection-reuse.md) — connection lifecycle within agent sessions
- [S-2783 · The A2A Capability Mismatch Stack](s2783-the-a2a-capability-mismatch-stack-when-your-agent-doesnt-know-what-your-agent-can-do.md) — distributed protocol handshake failures
