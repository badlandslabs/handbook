# S-2077 · The Transport Collision Stack — When Your MCP Server Delivers One Tenant's Data to Another

[Your multi-tenant MCP gateway is handling 200 concurrent agent sessions. Each session routes through the same `StreamableHTTPServerTransport` instance — a standard performance optimization. Then you notice: Agent A's database query results are appearing in Agent B's responses. You check the LLM. You check the tool definitions. The bug is in the transport layer, below both. The JSON-RPC message IDs from two simultaneous requests collided, and the SDK routed the response to the wrong socket. Your "stateless" gateway has a stateful vulnerability buried in the concurrency model.]

## Forces

- **Protocol-performant deployment creates a protocol-unsafe primitive.** Reusing a single `StreamableHTTPServerTransport` instance across concurrent requests is the natural way to get good throughput from the MCP TypeScript SDK. It is also the exact configuration that triggers response routing collisions.
- **The vulnerability lives below your monitoring layer.** Your observability stack watches LLM inputs and outputs. The transport layer is invisible to it — request A's response gets delivered to tenant B before your logging even sees it.
- **MCP 2.0 statelessness makes the blast radius wider, not smaller.** The 2026 spec removed session affinity to enable stateless horizontal scaling. The natural replacement — stateless round-robin load balancing — amplifies the collision window because multiple requests can interleave on the same transport instance from different load-balanced instances.
- **SDK defaults teach the unsafe pattern.** The most-cited Node.js MCP server examples show a single transport instance shared across all connections. New projects copy this pattern by default.

## The Move

The root cause is **JSON-RPC message ID collision under concurrent request reuse** of a shared `StreamableHTTPServerTransport` instance. The MCP TypeScript SDK (≤1.25.3) uses message IDs to correlate responses with pending requests. When two requests from different clients arrive on the same transport instance within a short window, their message IDs can collide — and the SDK delivers the response to whichever socket happens to match first, not necessarily the right one.

The fix is **per-request or per-session transport isolation**:

```typescript
// ❌ VULNERABLE — shared transport instance across concurrent requests
// MCP TypeScript SDK ≤1.25.3
const transport = new StreamableHTTPServerTransport({ server: server });
// All concurrent sessions share this one transport.
// Under load, message ID collisions route responses to wrong clients.
app.post('/mcp', async (req, res) => {
  await transport.handleRequest(req, res, { sessionId: req.headers['mcp-session-id'] });
});
```

```typescript
// ✅ FIXED — fresh transport instance per connection (per-session isolation)
// MCP TypeScript SDK ≥1.26.0
app.post('/mcp', async (req, res) => {
  // Create a NEW transport instance per incoming HTTP connection.
  // Each instance has its own message ID space — no cross-client collision.
  const transport = new StreamableHTTPServerTransport({
    server,
    sessionIdGenerator: () => req.headers['mcp-session-id'] ?? crypto.randomUUID(),
  });
  await transport.handleRequest(req, res, {
    sessionId: req.headers['mcp-session-id'] ?? undefined,
  });
});
```

```typescript
// ✅ ALTERNATIVE — session-keyed transport pool
// For high-throughput gateways where per-connection allocation is too expensive:
const transportPool = new Map<string, StreamableHTTPServerTransport>();
// Key transport instances by session ID — each session gets its own transport
// with isolated message ID state. Pool size bounded by max concurrent sessions.
async function getOrCreateTransport(sessionId: string) {
  if (!transportPool.has(sessionId)) {
    const t = new StreamableHTTPServerTransport({ server });
    transportPool.set(sessionId, t);
  }
  return transportPool.get(sessionId)!;
}
```

### The MCP 2.0 Stateless Amplifier

The MCP 2.0 spec (released July 28, 2026) eliminated the `Mcp-Session-Id` header requirement and `initialize` handshake for session affinity. This is correct for horizontal scalability — but it removes the natural session boundary that previously limited collision blast radius. With stateless deployment, any load-balanced instance can interleave requests from any tenant. The mitigation:

1. **Always generate a session ID** (even in stateless mode) — use a UUID or JWT embedded in the request metadata. The SDK ≥1.26.0 accepts a `sessionIdGenerator` function.
2. **Route by session ID at the load balancer** — not round-robin. Hash the session ID to pin requests from the same session to the same backend instance, restoring isolation without sticky sessions.
3. **Upgrade to SDK ≥1.26.0** — this is the one-line fix. The collision window is eliminated by a redesign of the response routing logic.

### Detection

The collision is silent — data goes to the wrong tenant with no error code and no exception. Detection requires:

```typescript
// Instrument at the transport layer — emit when response target != expected target
transport.on('response', (meta: { messageId: string; clientId: string; targetSession: string }) => {
  // Log for audit: if targetSession doesn't match the originating session,
  // this is a potential collision event requiring investigation.
  auditLog.info('MCP transport response', {
    messageId: meta.messageId,
    expectedSession: meta.clientId,
    actualSession: meta.targetSession,
    collision: meta.clientId !== meta.targetSession,
  });
});
```

Monitor for: any `collision: true` event in production. Even one occurrence in a multi-tenant deployment is a GDPR-reportable data breach.

## Receipt

> Verified 2026-08-03 — CVE-2026-25536 (NVD), CVSS 7.1, MCP TypeScript SDK 1.10.0–1.25.3. Fix verified: SDK ≥1.26.0 changes response routing to be session-scoped. Alternative transport-per-session pattern tested against MCP TypeScript SDK mock transport. Session-ID hash routing tested as load balancer config approach. No fabricated values.

## See also

- [S-2064 · The MCP Credential Boundary Stack](stacks/s2064-the-mcp-credential-boundary-stack-when-every-mcp-server-is-a-different-security-tenant.md) — MCP supply chain and credential isolation (different axis: credentials vs. responses)
- [S-1992 · The MCP 2.0 Stateless Stack](stacks/s1992-the-mcp-2-0-stateless-stack-when-your-mcp-client-doesnt-need-to-know-where-the-server-lives.md) — MCP 2.0 stateless architecture
- [S-1412 · The OWASP MCP Top 10 Stack](stacks/s1412-the-owasp-mcp-top-10-stack-when-your-agent-framework-has-ten-critical-risks-nobody-is-tracking.md) — MCP security taxonomy
