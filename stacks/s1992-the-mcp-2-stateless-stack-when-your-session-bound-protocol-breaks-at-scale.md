# S-1992 · The MCP 2.0 Stateless Stack

*When your production agent cluster worked fine with one server — then silently broke the moment you added a second, because the MCP handshake pinned every client to one instance. The protocol that was supposed to connect your agent to the world just became your scaling ceiling. MCP 2.0 fixes this at the protocol level, and if you're running remote MCP servers today, you need to migrate before your clients stop negotiating.*

## Forces

- **Sessions were a local-use artifact that became a production liability.** MCP shipped with an `initialize` handshake and `Mcp-Session-Id` header. That made sense for a desktop AI app talking to a local server over stdio. It breaks the moment you put a load balancer in front of two pods — Pod A handled the handshake, Pod B knows nothing about that session, and the agent gets a 404 on every subsequent call.

- **Scaling and reliability are in tension with session affinity.** Teams running MCP servers in Kubernetes or behind any HTTP infrastructure needed sticky sessions, shared session stores, or deep packet inspection just to keep the protocol alive. The operational overhead was a silent tax on every production deployment.

- **The migration window is now.** The RC shipped May 21, 2026; the final spec landed July 28, 2026. The 12-month minimum deprecation window has started. Clients and registries will begin enforcing the new spec within months — not years.

- **Authorization hardening arrives alongside statelessness.** Six SEPs converge on this release, including SEP-2468: per-request `iss` validation against RFC 9207 to block OAuth mix-up attacks. This was not a minor security patch — it's a structural hardening of how agents trust MCP servers.

## The move

MCP 2.0 eliminates session affinity as a protocol requirement. Every request is now self-contained:

### What disappeared

```
BEFORE: Session-based (2025-11-25)
1. Client → Server: POST /mcp + initialize handshake
2. Server → Client: Mcp-Session-Id header
3. Client → Server: All subsequent calls include Mcp-Session-Id
4. Proxy requirement: sticky sessions or shared session store
5. Reconnection: client must re-establish session after drop

AFTER: 2026-07-28 — Stateless
1. Client → Server: POST /mcp with _meta envelope
   (protocol version, client identity, capabilities in every request)
2. Server → Client: No session ID, no handshake required
3. Proxy: plain round-robin load balancer works
4. Reconnection: just retry; no session state to rebuild
```

### The three required headers

Every request must now carry:

```http
Mcp-Method: <method being called>
Mcp-Name: <server or client identifier>
traceparent: <W3C trace context>
```

These replace session affinity with header-based routing, observability, and identity — all of which were impossible or fragile before.

### Authorization hardening (most urgent SEP)

SEP-2468 validates the `iss` (issuer) parameter per RFC 9207 on every request. Without this, an attacker can proxy an MCP server and present a different issuer, silently intercepting tool calls and responses. This is a mix-up attack that session-based MCP was vulnerable to.

### Migration checklist

```bash
# Before migration (old spec)
# - Sticky sessions configured at load balancer
# - Shared session store (Redis, etc.) running
# - Deep packet inspection for Mcp-Session-Id at gateway

# After migration (2026-07-28)
# 1. Update SDK: ensure you have a stateless-capable client
# 2. Remove sticky-session configuration
# 3. Decommission session store
# 4. Add three headers to every outbound MCP request
# 5. Implement SEP-2468 issuer validation on server side
# 6. Update client/server capability negotiation (no more initialize/initialized)
# 7. Update tool caching logic: use server's ttlMs directive
# 8. Test reconnection behavior — stateless retries should be idempotent
```

### MCP Apps and Tasks (extension layer)

The stateless core enables two new first-class features built on top:

- **MCP Apps**: server-rendered UIs injected into the client. Requires stateless transport to route correctly.
- **Tasks**: a structured protocol for multi-round-trip work without a long-lived SSE stream. The server can initiate work without maintaining connection state.

### Extensions framework

The new Extensions framework allows vendors to extend MCP without forking the protocol. This matters for enterprise deployments where custom auth, logging, or quota mechanisms need to hook into the transport layer without breaking compatibility.

## Receipt

> Verified 2026-08-01 — Researched against MCP blog (modelcontextprotocol.io/posts/2026-07-28-release-candidate/), BOVO Digital analysis (bovo-digital.tech/en/blog/mcp-2026-specification-stateless-enterprise-agents), luismori.dev migration guide, and byteiota breaking changes analysis. Architecture confirmed: session elimination, three required headers (_meta envelope), SEP-2468 OAuth hardening. Migration window: 12 months minimum per formal deprecation policy.

## See also

- [S-1000 · Structural Agent Governance Stack](stacks/s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — authorization hardening connects to trust boundary enforcement
- [S-1987 · The Tool Surface Design Stack](stacks/s1987-the-tool-surface-design-stack-when-your-agent-has-every-tool-but-cant-decide.md) — MCP proliferation makes tool selection the next frontier
- [S-03 · Tool Use](stacks/s03-tool-use.md) — foundational pattern for how agents invoke external capabilities
- [S-1990 · The GenAI Semantic Convention Stack](stacks/s1990-the-genai-semantic-convention-stack-when-your-agent-traces-are-in-the-right-format-but-nobody-elses-tool-can-read-them.md) — the `traceparent` header is how MCP 2.0 fits into the observability standards ecosystem
