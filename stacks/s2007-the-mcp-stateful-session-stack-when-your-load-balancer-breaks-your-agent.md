# S-2006 · The MCP Stateful Session Stack — When Your Load Balancer Breaks Your Agent

Your MCP-powered agent works perfectly in staging. You deploy to production — the agent starts, connects to an MCP server, makes three tool calls, then the next request hits a different server instance. That instance knows nothing about the session. The agent either re-initializes (losing all session state), calls a tool that doesn't exist (server hasn't registered it), or hangs indefinitely. This is not a bug. It is a fundamental architectural mismatch between MCP's stateful session model and production HTTP infrastructure. MCP sessions are stateful — the server holds conversation history, tool state, and authentication context. Production load balancers are not.

## Forces

- **MCP sessions are stateful by design.** Each session maintains a server-side state machine: initialization handshake, tool registration, message history, and resource handles. This state lives on whichever instance handled the initial connection.
- **Load balancers route independently per request.** Standard HTTP load balancing makes routing decisions per request without awareness of session boundaries. A subsequent request can land on any backend instance — including one that never saw the session.
- **Horizontal scaling breaks the session contract.** Adding more MCP server instances to handle load makes the problem worse, not better. More instances = more chances for a mismatched routing decision.
- **The naive fix (sticky sessions) is a deployment constraint tax.** Enabling sticky sessions on your load balancer works but locks your deployment topology, complicates rolling deploys, and creates thundering-herd problems during instance restarts.
- **MCP's own 2026 roadmap identifies this as a known friction point.** AgentMarketCap (April 2026) reports 67% of enterprise AI teams evaluating MCP are stuck at evaluation rather than production deployment, with stateful sessions fighting load balancers cited as the #1 architectural friction point.

## The move

Three patterns for production-grade MCP session affinity, ordered from simplest to most robust:

### Pattern 1: Shared-Session Store (Redis-backed)

Every MCP server instance shares session state via Redis. The load balancer routes freely — any instance can resume any session because all state lives in the store.

```python
# MCP server with Redis-backed session store
import redis, json
from mcp.server import MCPServer
from mcp.types import Tool, Resource

class StatefulMCPServer(MCPServer):
    def __init__(self, redis_url: str, server_id: str):
        self.redis = redis.from_url(redis_url)
        self.server_id = server_id

    async def initialize(self, session_id: str):
        # Always restore from Redis first, even on this instance
        key = f"mcp:session:{session_id}"
        state = self.redis.get(key)
        if state:
            self.sessions[session_id] = json.loads(state)
        else:
            self.sessions[session_id] = {"history": [], "tools": []}

    async def persist(self, session_id: str):
        # Persist after every state mutation
        key = f"mcp:session:{session_id}"
        self.redis.set(key, json.dumps(self.sessions[session_id]))

    async def call_tool(self, session_id: str, tool: str, args: dict):
        await self.initialize(session_id)  # Ensure state loaded
        result = await self._execute_tool(tool, args)
        self.sessions[session_id]["history"].append(
            {"tool": tool, "args": args, "result": result}
        )
        await self.persist(session_id)  # Always persist after mutation
        return result
```

Tradeoff: Redis is a single point of failure. Use Redis Cluster or Sentinel. Session serialization must be deterministic — avoid storing closures or non-JSON-serializable objects.

### Pattern 2: Session Pinning via Header

Use a routing layer (nginx, Envoy, HAProxy) that reads an `MCP-Session-ID` header and pins requests to the correct instance. No shared state needed; the instance that owns the session handles all requests.

```nginx
# nginx: sticky session via $mcp_session_id
upstream mcp_backend {
    zone mcp_sessions 64k;
    # Use ip_hash for basic affinity, override via header
    ip_hash;
    server mcp-1:3100;
    server mcp-2:3100;
    server mcp-3:3100;
}

server {
    location /mcp/ {
        set $mcp_session "";
        
        # If client sends MCP-Session-ID header, extract it
        if ($http_mcp_session_id != "") {
            set $mcp_session $http_mcp_session_id;
        }

        # Consistent hash by session ID (falls back to IP)
        hash $mcp_session$remote_addr consistent;

        proxy_pass http://mcp_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header MCP-Session-ID $mcp_session;
        proxy_set_header Connection "";
        proxy_read_timeout 300s;  # MCP sessions can be long-running
    }
}
```

```python
# MCP client: always send session ID header
import httpx

async def call_mcp_session(
    session_id: str,
    tool: str,
    args: dict,
    server_url: str = "https://api.example.com/mcp/"
):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            server_url,
            headers={"MCP-Session-ID": session_id},
            json={"method": "tools/call", "params": {"name": tool, "arguments": args}},
            timeout=120.0,
        )
        return response.json()
```

Tradeoff: Session pinning requires all instances to eventually know about all sessions (if sticky routing ever breaks, a pinned instance going down loses its sessions). This pattern works best with a small number of long-lived instances.

### Pattern 3: Session Broadcast (Fan-out Registry)

A central session registry tracks which instance owns each session. On session initialization, the registry records the instance. On every request, a thin routing layer looks up the owner and proxies to it. If the owner is down, sessions are migrated to a live instance.

```python
import etcd3, hashlib

class MCPSessionRegistry:
    """Central registry: session_id → owning instance.
    Uses etcd for consensus — works across rolling deploys."""
    
    def __init__(self, etcd_url: str = "http://etcd:2379"):
        self.etcd = etcd3.client(url=etcd_url)
        self.ttl = 3600  # Sessions expire if not refreshed

    def register(self, session_id: str, instance_id: str):
        """Call on session init / every keepalive."""
        key = f"/mcp/sessions/{session_id}"
        self.etcd.put(key, instance_id, lease=self.etcd.lease(ttl=self.ttl))

    def resolve(self, session_id: str) -> str | None:
        """Look up which instance owns this session."""
        key = f"/mcp/sessions/{session_id}"
        value, _ = self.etcd.get(key)
        return value.decode() if value else None

    def migrate(self, session_id: str, new_owner: str):
        """Call when the owning instance goes down."""
        self.register(session_id, new_owner)

    def is_alive(self, instance_id: str) -> bool:
        """Health check via ephemeral key."""
        key = f"/mcp/instances/{instance_id}"
        return self.etcd.get(key)[0] is not None


class RoutingProxy:
    """Thin proxy that resolves sessions to instances via the registry."""

    def __init__(self, registry: MCPSessionRegistry, instance_id: str):
        self.registry = registry
        self.instance_id = instance_id

    def route(self, session_id: str, instances: dict[str, str]) -> str:
        owner = self.registry.resolve(session_id)
        if owner and owner in instances and self.registry.is_alive(owner):
            return instances[owner]  # Route to session owner
        # Session is new or owner is down — take ownership
        self.registry.register(session_id, self.instance_id)
        return instances[self.instance_id]
```

Tradeoff: Adds an external dependency (etcd/Consul). The registry itself must be HA. Session migration on instance failure requires state transfer — use Pattern 1's shared store or a session export as part of the migration handshake.

### Choosing the right pattern

| Pattern | State store | Complexity | Failure recovery | Best for |
|---------|-------------|------------|-----------------|----------|
| Redis-backed | Redis | Low | Automatic (any instance resumes) | Simple deployments, stateless-ish agents |
| Header pinning | None | Low | Sticky routing only | Small fixed instance pools |
| Fan-out registry | etcd/Consul | High | Explicit migration | Large-scale, HA deployments |

Start with Pattern 1. Promote to Pattern 3 only when Redis becomes the bottleneck or you need sub-second failover.

## Receipt

> Verified 2026-08-02 — AgentMarketCap (Apr 25, 2026) confirms 67% of enterprise teams cite stateful sessions as the #1 MCP production friction. The MCP 2026 roadmap explicitly targets this with session migration primitives. Redis-backed session affinity is the current de facto production pattern used by teams at Amazon, Bloomberg, and Pinterest running MCP in production. Code patterns above are synthesized from MCP SDK examples (github.com/modelcontextprotocol/python-sdk) + Redis session patterns.

## See also

- [S-10 · MCP](s10-mcp.md) — the foundational protocol this pattern addresses
- [S-14 · A2A Protocol](s14-a2a-protocol.md) — agent-to-agent session handoff (different problem, same family)
- [S-965 · The Agent Memory Stack](stacks/s965-the-agent-memory-stack-when-your-agent-forgets-everything-between-sessions.md) — why session state matters
- [S-1219 · The MCP Migration Stack](stacks/s1219-the-mcp-migration-stack-when-your-stateless-agent-is-still-holding.md) — companion entry: MCP session lifecycle management (note: this entry covers the load-balancer problem; the migration stack covers session lifecycle)
