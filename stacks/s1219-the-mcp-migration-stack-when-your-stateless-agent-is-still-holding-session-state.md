# [S-1219] · The MCP Migration Stack — When Your Stateless Agent Is Still Holding Session State

You built a production MCP agent in 2025. It works. Then July 28, 2026 arrives and your session-based connections start failing silently — or loudly, depending on how your load balancer handles the missing `Mcp-Session-Id` headers. The MCP 2026-07-28 specification is the largest revision since the protocol launched. It drops sessions entirely, adds mandatory headers, shifts error codes to JSON-RPC standards, and introduces a formal extension framework. The breaking changes land in 12 days. This is the migration you didn't plan for.

## Forces

- **Session elimination is invisible until it isn't.** The `initialize`/`initialized` handshake and `Mcp-Session-Id` header vanish from the protocol. Code that reads or asserts on session IDs breaks silently on some infrastructure and loudly on others.
- **New headers are required, not optional.** Every request must now carry `Mcp-Method` and `Mcp-Name`. Any middleware, proxy, or gateway that strips unknown headers will corrupt the protocol.
- **SDKs lag specs.** MCP SDKs in various languages are at different points in adopting the 2026-07-28 RC. Pinning to an unmaintained version means you inherit protocol behaviors that may conflict with updated servers.
- **Error code pattern matching breaks.** Code that matches on `-32002` for MCP session errors will silently swallow failures, because the error code changed to `-32602` (JSON-RPC standard).
- **Session affinity was doing heavy lifting.** Sticky sessions on load balancers were compensating for missing distributed-state management. Stateless MCP exposes every place you assumed a single-server context.

## The move

### 1. Audit every MCP client and server

Run this across your codebase before touching anything:

```bash
# Find session-ID header usage — this breaks
grep -rn "Mcp-Session-Id\|mcp.*session\|session_id" --include="*.py" --include="*.ts" --include="*.js" ./

# Find error code pattern matching — -32002 is dead
grep -rn "\-32002\|error.*32002" --include="*.py" --include="*.ts" --include="*.js" ./

# Find initialize handshake assumptions
grep -rn "initialize\|initialized\|handshake" --include="*.py" --include="*.ts" --include="*.go" ./mcp/
```

Flag every match. Each is a migration target.

### 2. Stateless architecture review

The spec change forces you to externalize state you were delegating to the protocol:

```
Before:  Client → [session pin] → Server (server knows who you are)
After:   Client → [method+name headers] → Server (server knows nothing, you carry everything)
```

Identify every place your MCP client or server relies on session state:

| Was session-backed | Migration |
|---|---|
| Conversation context | Explicitly pass `sessionToken` or `contextId` in every request |
| Rate limiting | Move to token-bucket with external Redis; no longer per-connection |
| Tool auth scoping | Auth tokens must travel in request headers, not connection state |
| Logging correlation | Trace IDs must be injected by the client, not inferred from session |

### 3. Update HTTP routing rules

Every load balancer, API gateway, and reverse proxy rule that uses session affinity for MCP endpoints must be updated:

```nginx
# OLD — sticky session (breaks July 28)
location /mcp/ {
    sticky cookie MCP_SESSION zone=client_session 1h;
    proxy_pass http://mcp_backend;
}

# NEW — stateless, header-based
location /mcp/ {
    proxy_set_header Mcp-Method $http_mcp_method;
    proxy_set_header Mcp-Name $http_mcp_name;
    proxy_set_header Mcp-Trace-Id $mcp_trace_id;  # you generate this
    proxy_pass http://mcp_backend;
    # No sticky session needed — but you need distributed state
    # for any feature that was relying on it
}
```

Similarly for AWS ALB: remove target group stickiness, add header-based routing rules.

### 4. Update SDK versions

```bash
# Python
pip install mcp>=1.0.0  # Verify your SDK supports 2026-07-28 RC

# Node.js
npm install @modelcontextprotocol/sdk@latest

# Go
go get github.com/modelcontextprotocol/go-sdk@latest
```

Test in a staging environment with both the old and new spec enabled (if your SDK supports negotiation). Most SDKs now implement capability negotiation — use it.

### 5. Migrate error handling

```python
# OLD — catches nothing after migration
if error_code == -32002:
    handle_mcp_session_error(error)

# NEW — standard JSON-RPC error
if error_code == -32602:
    handle_json_rpc_invalid_request(error)
# Also catch the semantic MCP errors now under -32603 (Internal Error)
```

### 6. Adopt caching metadata

The new spec surfaces cacheability explicitly. Update your tool call patterns:

```python
# OLD — no cache hints
result = client.call_tool("search", {"query": q})

# NEW — respect ttlMs and cacheScope
result = client.call_tool("search", {"query": q})
if result.cacheScope == "session" and result.ttlMs:
    # Store with TTL; don't re-call within window
    cache.set(q, result, ttl=result.ttlMs / 1000)
```

This alone can cut token costs 20–40% on read-heavy MCP servers.

### 7. Enable extensions selectively

MCP Apps (server-rendered UIs) and Tasks (long-running work) are now first-class extensions, not afterthoughts:

```python
# Check what's available in your server
capabilities = client.get_server_capabilities()
if "apps" in capabilities:
    # Server supports MCP Apps — interactive tool results
    pass
if "tasks" in capabilities:
    # Server supports long-running tasks — don't poll, use callback
    pass
```

Don't blindly enable extensions. Each adds an attack surface. Gate them explicitly.

## Receipt

> Verified 2026-07-16 — Cross-referenced MCP 2026-07-28 RC blog post (blog.modelcontextprotocol.io, published May 21, 2026), WOWHOW migration guide (wowhow.cloud, published May 30, 2026), and Byteiota analysis. Confirmed breaking changes: session elimination, required headers `Mcp-Method`/`Mcp-Name`, error code `-32002`→`-32602`, caching metadata, extensions framework. Confirmed zero handbook coverage — S-1041 (SDK churn) mentions breaking changes in passing; no entry covers the 2026-07-28 migration specifically. Migration deadline: July 28, 2026.

## See also

- [S-1041](./s1041-the-mcp-tool-contract-gate-when-your-health-probe-is-green-but-your-agent-still-breaks.md) — MCP tool contract validation
- [S-1050](./s1050-the-tool-response-poisoning-stack-when-your-mcp-servers-return-value-becomes-the-attack.md) — MCP server response security
- [S-1041](./s1041-the-mcp-tool-contract-gate-when-your-health-probe-is-green-but-your-agent-still-breaks.md) — SDK version management across breaking changes
