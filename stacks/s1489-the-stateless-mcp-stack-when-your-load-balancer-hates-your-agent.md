# S-1489 · The Stateless MCP Stack — When Your Load Balancer Hates Your Agent

You deployed MCP in production. It works fine with one server instance. Then you add a second instance behind the load balancer and your agent starts failing 40% of requests — silent failures, no errors in your logs, just empty tool responses. The culprit: `Mcp-Session-Id` headers, a stateful protocol design that pins every MCP client to exactly one server instance. The July 2026 MCP specification (RC) eliminates this entirely. This is the Stateless MCP Stack — how to migrate, what breaks, and what the stateless paradigm unlocks.

## Forces

- **Session affinity was always a deployment smell.** The original MCP design required `Mcp-Session-Id` headers after `initialize`, forcing you to pin clients to instances. Horizontal scaling was bolted on with shared session stores — a Redis dependency that became a blast radius.
- **Every breaking change in the MCP RC has a migration path.** The 2026-07-28 spec is the largest revision since launch. It removes sessions, introduces MCP Apps (SEP-1865), formalizes the Extensions framework, and aligns authorization with OAuth 2.1 / OpenID Connect. The changes are breaking but documented.
- **MCP Apps (SEP-1865) turn servers into UI endpoints.** The Skills primitive lets MCP servers return interactive HTML — your agent's `send_email` tool can now render a compose form inside the AI host. This collapses the tool/UI boundary and introduces new security considerations around rendered content.
- **Authorization is now first-class, not bolted-on.** The old spec had no standard auth model. The RC introduces structured identity propagation, `Authorization` header passthrough, and alignment with OAuth 2.1. For agents that act across MCP servers with different privilege levels, this is a foundational shift.

## The move

### 1. Audit your current session-store dependency

Before upgrading, find every place your stack assumes session persistence:

```python
# Old (stateful): requires shared session store
# MCP client pins to instance via Mcp-Session-Id
# Redis/DB session store becomes a hard dependency

# Find it in your config
grep -r "Mcp-Session-Id\|session_id\|session_store" ./mcp/
```

If your MCP client or server code references session IDs after `initialize`, you're stateful. The RC makes these optional — the absence of `Mcp-Session-Id` in responses signals stateless mode.

### 2. Migrate to stateless: the three changes

**a) Remove session-store infrastructure.** The Redis/SQLite session store you added for horizontal scaling is now deprecated. Drop the `session-store` dependency from your MCP server config.

**b) Ensure all requests are self-contained.** Every request must carry what it needs:
- The `protocolVersion` in `params` (required)
- All required context in the request body (no server-side session)
- `id` field on every JSON-RPC request/response for correlation

```python
# Old (stateful): session carries state across requests
# POST /mcp → Server returns Mcp-Session-Id → all future requests include it

# New (stateless): every request is self-contained
POST /mcp HTTP/1.1
Content-Type: application/json
{
  "jsonrpc": "2.0",
  "id": 42,
  "method": "tools/call",
  "params": {
    "protocolVersion": "2026-07-28",
    "name": "search_db",
    "arguments": {"query": "active users"},
    # no session_id — it's implicit in stateless mode
    "context": {"request_id": "req-abc123"}  # optional correlation
  }
}
```

**c) Update your load balancer.** Stateless mode means any instance can handle any request. Configure your LB for round-robin or least-connections — no sticky sessions needed.

### 3. Handle the MCP Apps (SEP-1865) skill primitive

MCP Apps let servers return structured UI components alongside data:

```json
// Server returns a "skill" — interactive HTML embedded in the AI host
{
  "skills": [{
    "id": "skill-email-compose",
    "name": "Email Composer",
    "description": "Renders an email compose form",
    "capabilities": ["read_draft", "send", "attach"],
    "inputSchema": { "type": "object", "properties": {...} }
  }]
}
```

**Security consideration:** A server returning HTML via MCP Apps gives the agent a rendering surface inside the AI host. Treat MCP App responses with the same origin isolation you apply to web content. Key mitigations:
- CSP headers on MCP App responses
- Validate `capabilities` array before rendering
- Restrict skill access to explicitly trusted servers
- Audit which servers ship MCP App skills — a compromised server can render arbitrary content in your agent's context window

### 4. Lock down authorization with OAuth 2.1 / OIDC alignment

The RC formalizes `Authorization` header passthrough and structured identity:

```python
# RC-compliant: structured identity propagation
# Server receives identity context without decoding JWTs
class MCPAuthorizationContext:
    principal_id: str        # from OIDC ID token subject
    scopes: list[str]        # from token scope claim
    server_id: str           # which MCP server is being accessed
    tool_name: str           # which tool is being invoked

# Policy decision at the proxy/gateway layer
def authorize_mcp_call(ctx: MCPAuthorizationContext, tool: str) -> bool:
    if tool in HIGH_STAKES_TOOLS and "admin:write" not in ctx.scopes:
        raise PermissionError(f"Principal {ctx.principal_id} lacks admin:write for {tool}")
```

Align your MCP gateway with the RFC 9396 OAuth 2.0 Rich Authorization Requests pattern. The key insight: authorization decisions should happen at the MCP gateway, not inside the agent or individual servers.

### 5. Validate the Extensions framework

The RC formalizes the Extensions framework for protocol extensions that don't require a full spec revision:

```json
// Server declares extensions
{
  "capabilities": {
    "extensions": {
      "tracing": {"version": "1.0"},
      "experiments": ["streaming-results"]
    }
  }
}
```

Check your MCP SDK version before upgrading. The Python and TypeScript SDKs (v0.9+) have RC support; older versions may silently fall back to 2025-11-25 behavior with degraded features.

### 6. The deprecation policy is now formal

The RC introduces a 12-month minimum support window per spec version:

```
Spec version N → N-1 supported for ≥12 months
Spec version N → N-2: security fixes only
Spec version N → N-3: end of life
```

Track spec versions in your `clientInfo` / `serverInfo` and implement version probing. If a remote MCP server doesn't advertise a `protocolVersion`, assume the oldest supported version and test incrementally.

## References

- [MCP 2026-07-28 Release Candidate](https://blog.modelcontextprotocol.io/posts/2026-07-28-release-candidate/) — David Soria Parra, Den Delimarsky
- [MCP 2026 Roadmap](https://blog.modelcontextprotocol.io/posts/2026-03-09-roadmap/) — Working Groups: Transport & Scaling, Identity & Trust, Discovery & Registry, SDK, Security
- [SMCP: Secure Model Context Protocol](https://arxiv.org/abs/2602.01129) — Hou et al., arXiv:2602.01129 (cs.CR), Feb 2026
- [Ginger Labs: MCP 2026 Roadmap Explained](https://gingerlabs.ai/blog/mcp-2026-roadmap-stateless-transport-agent-communication-enterprise-authentication)
