# S-870 · The MCP Session Architecture Stack — When the Protocol Was Built for Demos and You're in Production

Your MCP agent works beautifully on your laptop. You deploy it to production and it handles 3 concurrent users fine. At 50, it starts dropping connections. At 200, it starts returning other users' data. The MCP SDK was built for single-user, single-session, local-first use. Enterprise production requires something different: stateless sessions, external state stores, and connection pooling. This is the MCP session architecture gap.

## Forces

- **The SDK defaults couple you to a process lifetime.** MCP's official SDKs default to in-process session management — one server process owns one session. Scale that to 200 concurrent agents and you have 200 processes, none sharing state, all competing for file descriptors and memory. One OOM kills a session with no recovery path.
- **Sessions carry state you can't afford to lose.** MCP session state includes tool call history, resource subscriptions, and pending notifications. If your agent process crashes mid-task, the session — and all its work — is gone. The protocol has no native recovery mechanism.
- **Horizontal scaling breaks session affinity.** Load balancers route MCP connections across instances. Without shared session state, a multi-step task starts on instance A, the second tool call routes to instance B, and instance B has no knowledge of what instance A did. The task silently degrades.
- **The 2026 spec roadmap acknowledges this.** The March 2026 MCP roadmap explicitly shifted focus from "simple connectivity" to "transport scalability, governance, and stateless core architectures." The community is aware; production teams are still catching up.

## The move

### 1. Externalize session state immediately

The session is not the process. Move session state to an external store (Redis, Postgres, SQLite on a network volume):

```python
import redis, json
from mcp.server import McpServer

class ExternalSessionStore:
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)
        self.ttl = 3600  # 1-hour session expiry

    async def save(self, session_id: str, state: dict):
        self.redis.setex(
            f"mcp:session:{session_id}",
            self.ttl,
            json.dumps(state)
        )

    async def load(self, session_id: str) -> dict | None:
        raw = self.redis.get(f"mcp:session:{session_id}")
        return json.loads(raw) if raw else None

    async def extend(self, session_id: str):
        self.redis.expire(f"mcp:session:{session_id}", self.ttl)

# Wrap the standard server with external session persistence
server = McpServer(session_store=ExternalSessionStore("redis://redis:6379"))
```

This single change enables session recovery after process restarts, horizontal scaling with sticky sessions at the load balancer, and shared session state across instances.

### 2. Use a connection pool, not a process-per-session

MCP's default creates a new transport channel per session. Production requires a pool:

```python
from mcp.client import ClientPool, PoolConfig

pool = ClientPool(
    PoolConfig(
        max_connections=100,      # total pool capacity
        max_per_host=10,          # per MCP server limit
        keepalive=60,             # seconds before idle prune
        connection_timeout=10.0,
    )
)

async def get_session(server_id: str) -> MCPClient:
    # Borrowing from the pool avoids the per-session process overhead
    return await pool.acquire(f"mcp://{server_id}/mcp")
```

### 3. Implement session resume, not session restart

When a connection drops, the client should resume — not replay from scratch:

```python
async def resume_or_start(
    client: MCPClient,
    session_id: str,
    store: ExternalSessionStore,
) -> MCPClient:
    state = await store.load(session_id)
    if state:
        # Rehydrate the session from external state
        await client.resume_session(
            history=state["tool_call_history"],
            subscriptions=state["active_subscriptions"],
        )
        await store.extend(session_id)
        return client

    # Cold start — register the new session
    await store.save(session_id, {
        "tool_call_history": [],
        "active_subscriptions": [],
        "created_at": time.time(),
    })
    return client
```

### 4. Route tool calls idempotently

Without idempotency, retry logic re-executes tool calls on session resume:

```python
from mcp.types import ToolCall, tool_call_id

async def safe_invoke(client, tool: ToolCall, session_id: str):
    idempotency_key = f"{session_id}:{tool_call_id(tool)}"

    # Check: did this call already succeed?
    if await redis.exists(f"mcp:done:{idempotency_key}"):
        return await redis.get(f"mcp:result:{idempotency_key}")

    result = await client.call_tool(tool.name, tool.arguments)
    await redis.setex(
        f"mcp:done:{idempotency_key}", 86400, "1"
    )
    await redis.setex(
        f"mcp:result:{idempotency_key}", 86400, json.dumps(result)
    )
    return result
```

### 5. Name your sessions explicitly — don't let the SDK auto-generate

Auto-generated session IDs collide under high concurrency. Use a deterministic, collision-free ID:

```python
import uuid
from hashlib import sha256

def make_session_id(agent_id: str, user_id: str, task_id: str) -> str:
    """Stable, unique, human-debuggable session ID."""
    raw = f"{agent_id}:{user_id}:{task_id}"
    return sha256(raw.encode()).hexdigest()[:16]
```

## See also

- [S-830 · The MCP Transport Resilience Stack](s830-the-mcp-transport-resilience-stack-when-the-protocol-survives-the-connection.md) — transport-layer survival when connections drop
- [S-737 · The Protocol Layer: MCP and A2A Are Becoming the Wires of Agentic Systems](s737-the-protocol-layer-mcp-and-a2a-are-becoming-the-wires-of-agentic-systems.md) — where MCP fits in the broader protocol stack
- [S-261 · MCP Security: The Attack Surface You Inherited](s261-mcp-security-attack-surface.md) — the trust model when connecting to third-party MCP servers
- [S-444 · The 97-12 Gap: Agent Governance Discovery](s444-the-97-12-gap-agent-governance-discovery.md) — the governance layer that sits above session management
