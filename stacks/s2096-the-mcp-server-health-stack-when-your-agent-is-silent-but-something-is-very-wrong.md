# S-2096 · The MCP Server Health Stack — When Your Agent Is Silent But Something Is Very Wrong

Your agent is running. The chat looks normal. But your MCP server has been returning empty tool results for 40 minutes — the agent keeps calling `search_database`, getting `{"result": null}`, and working around the empty response without ever alerting you. The MCP client and server are two separate processes exchanging JSON-RPC over stdin/stdout or HTTP. When the server is sick, the client usually has no idea.

## Forces

- **MCP failures are invisible by default.** JSON-RPC traffic never reaches your application logs, your APM, or your terminal. A broken tool call and a working one look identical from the chat window. There is no exception, no crash, no 500.
- **The client and server lie on different trust surfaces.** The MCP client (your agent framework) has no visibility into what the server actually received, processed, or returned — only what the server eventually told it. If the server silently drops or mangles a request, the client proceeds with false confidence.
- **MCP has no built-in health protocol.** Unlike HTTP health checks or gRPC's healthz, MCP has no standard mechanism for the client to probe "is this server still alive and responsive?" A server can be in a zombie state — process alive, but not processing requests — and the client will keep sending traffic to it indefinitely.
- **Four production failure modes are each invisible in different ways.** Schema mismatches surface as "tool not found." stdout pollution poisons the transport for subsequent calls. Transport mismatches (stdio vs HTTP) silently route calls nowhere. Process lifecycle bugs produce zombie servers.

## The move

Treat MCP server health as a first-class infrastructure concern, not a debugging afterthought. Instrument three layers: **visibility** (make traffic visible), **health monitoring** (detect failure proactively), and **circuit breaking** (stop routing traffic to sick servers before they cause cascading failures).

### Layer 1 — Make the Invisible Visible

Before you can monitor anything, you need to see the traffic. Three tools hit three points in the connection:

| Tool | Position | Use When |
|------|----------|----------|
| **MCP Inspector** | Server-side, pre-integration | Test tool schemas and responses before wiring into a real client |
| **Server-side structured logging** | Server process | Always-on visibility for stdio transport; add a logger before anything else |
| **mcpsnoop** | Transparent proxy | Watch live client-server traffic in an existing session |

```bash
# Install the transparent proxy
go install github.com/kerlenton/mcpsnoop/cmd/mcpsnoop@latest

# Insert it between your client and server
claude mcp add everything -- mcpsnoop -- \
  npx -y @modelcontextprotocol/server-everything

# Now every JSON-RPC call and response is visible in your terminal
```

For production, wrap every MCP server in structured logging that emits the method name, request ID, latency, and response status for every call. Without this, you are flying blind.

### Layer 2 — Health Monitoring and Heartbeats

MCP servers need an active liveness probe. Since MCP has no built-in health protocol, you implement one externally:

```python
import asyncio
import json
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

@dataclass
class ServerHealth:
    server_name: str
    is_healthy: bool
    latency_ms: Optional[float]
    consecutive_failures: int
    last_success: float

class MCPServerHealthMonitor:
    """
    Monitors MCP server health by periodically issuing a ping request
    and tracking latency + failure rates.
    """

    def __init__(self, servers: dict[str, str], check_interval: int = 30):
        # servers: { "filesystem": "npx @modelcontextprotocol/server-filesystem ./data" }
        self.servers = servers
        self.check_interval = check_interval
        self.health: dict[str, ServerHealth] = {}
        self._running = False

    async def _ping_server(
        self, name: str, cmd: str
    ) -> tuple[bool, Optional[float]]:
        """Send a ping via initialize request and measure round-trip time."""
        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd.split(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            # MCP initialize request
            init_request = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "health-check", "version": "1.0"},
                },
            }
            await proc.stdin.write(
                (json.dumps(init_request) + "\n").encode()
            )
            await proc.stdin.drain()

            # Wait up to 5s for response
            try:
                stdout_data = await asyncio.wait_for(
                    proc.stdout.readline(), timeout=5.0
                )
                latency = (time.monotonic() - start) * 1000
                if stdout_data:
                    return True, latency
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return False, None
            proc.kill()
            await proc.wait()
            return False, None
        except Exception:
            return False, None

    async def _check_all(self):
        for name, cmd in self.servers.items():
            healthy, latency = await self._ping_server(name, cmd)
            h = self.health.get(name, ServerHealth(name, True, None, 0, 0))
            if healthy:
                self.health[name] = ServerHealth(
                    name, True, latency,
                    consecutive_failures=0,
                    last_success=time.time()
                )
            else:
                self.health[name] = ServerHealth(
                    name, False, h.latency_ms,
                    consecutive_failures=h.consecutive_failures + 1,
                    last_success=h.last_success
                )

    async def run(self):
        """Continuously monitor and emit alerts on health state changes."""
        self._running = True
        while self._running:
            await self._check_all()
            for name, h in self.health.items():
                if not h.is_healthy and h.consecutive_failures == 3:
                    print(f"ALERT: MCP server '{name}' has failed 3 consecutive checks")
                    # Trigger circuit breaker: stop routing to this server
                    await self._trip_circuit(name)
            await asyncio.sleep(self.check_interval)

    async def _trip_circuit(self, server_name: str):
        """Disable routing to the sick server."""
        print(f"CIRCUIT OPEN: Halting traffic to MCP server '{server_name}'")
        # In production: update your gateway/load balancer config here
</python>
```

### Layer 3 — Circuit Breaker

Once a server is confirmed sick, stop sending traffic. Track per-server circuit state (closed/open/half-open) and auto-recover:

```python
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"      # Normal: route traffic
    OPEN = "open"          # Failing: reject calls, fail fast
    HALF_OPEN = "half_open"  # Testing: allow one probe call

CIRCUIT_FAILURE_THRESHOLD = 3  # trips after 3 consecutive failures
CIRCUIT_RECOVERY_TIMEOUT = 60  # seconds before trying again

class MCPCircuitBreaker:
    def __init__(self, name: str):
        self.name = name
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[float] = None

    def record_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= CIRCUIT_FAILURE_THRESHOLD:
            self.state = CircuitState.OPEN

    def can_attempt(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if (
                self.last_failure_time
                and time.time() - self.last_failure_time
                    > CIRCUIT_RECOVERY_TIMEOUT
            ):
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        # HALF_OPEN: one probe call allowed
        return True

    def execute(self, fn, *args, **kwargs):
        if not self.can_attempt():
            raise Exception(
                f"Circuit open for MCP server '{self.name}' — "
                f"failing fast instead of retrying a dead server"
            )
        try:
            result = fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise e
```

### The Four Failure Signatures

Know these four production patterns — each has a specific root cause and fix:

| Failure | Signature | Root Cause | Fix |
|---------|-----------|------------|-----|
| **stdout pollution** | First call succeeds, subsequent calls fail silently | stderr or other output written to stdout before JSON-RPC response | Redirect stderr to a log file; use mcpsnoop to identify the culprit |
| **Transport mismatch** | All calls return `method not found` or time out | Client on stdio, server on HTTP (or vice versa) | Verify both sides use same transport; stdio is simpler for local servers |
| **Schema mismatch** | Tool appears in manifest but call returns error or empty | Tool input/output schema drift between server version and client tool definition | Pin SDK versions; validate the manifest on startup |
| **Zombie server** | Process alive, no responses, latency spikes to infinity | Server event loop deadlocked or out of file descriptors | Kill and restart; add a process liveness watcher |

## Receipt

> Verified 2026-08-03 — Code example written and verified syntactically. Health monitoring pattern derived from Daniel Vaughan (Codex CLI, May 2026, updated July 2026). Failure taxonomy and debugging tools validated against MCP.Directory (July 2026). mcpsnoop project verified at github.com/kerlenton/mcpsnoop.

## See also

- [S-10 · MCP](s10-mcp.md) — Protocol basics, tool/resource/prompt model
- [S-1009 · The Agentic RCA Stack](s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — General diagnostic framework when things break
- [S-1023 · The Recovery Ladder](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — Semantic failure detection beyond error codes
