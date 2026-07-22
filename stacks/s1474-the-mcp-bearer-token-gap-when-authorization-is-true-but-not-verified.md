# S-1474 · The MCP Bearer Token Gap — When Authorization Is "True" But Not Verified

Authorization is declared. Session is hijacked.

## Situation

Your MCP server has `--auth=true`. The bearer token is present. The agent holds a valid credential. Yet an attacker injects JSON-RPC messages into a live session — reading sensitive tool outputs, poisoning retrieval results, or escalating privileges — because the transport verified the bearer token but never checked whether the *requesting principal* matches the *session owner*.

## Forces

- MCP's HTTP transports (SSE and Streamable HTTP) route requests to sessions using `session_id` alone — no principal verification across the auth boundary
- Bearer token validation is optional and decoupled from session routing, so a valid token proves identity to the server but not ownership of the session
- This is not a configuration error — it is the default behavior across all affected versions (SSE: all versions; Streamable HTTP: ≥1.8.0, patched at 1.27.2)
- The gap is invisible: auth passes, the agent proceeds, and the session quietly belongs to whoever knows the ID

## The Move

### Detect the gap

```bash
# Check if you're on a vulnerable version
pip show mcp | grep Version
# Affected: < 1.27.2 on SSE or Streamable HTTP transports

# Verify session isolation in your transport config
# If you're passing bearer tokens but NOT binding them to session ownership,
# you have the gap — even with auth middleware enabled
```

### Patch immediately

```bash
pip install --upgrade "mcp>=1.27.2"
```

### Audit transport-level session binding (if patch is delayed)

The vulnerable pattern: session lookup by ID alone, regardless of token.

```python
# VULNERABLE — fixed in 1.27.2
async def route_request(session_id: str, token: str) -> Session:
    session = await get_session(session_id)  # session_id only
    await verify_token(token)                  # token verified, but NOT bound to session
    return session

# SAFE — bind bearer token to session principal
async def route_request(session_id: str, token: str) -> Session:
    session = await get_session(session_id)
    token_principal = await verify_token(token)
    if session.principal_id != token_principal:
        raise AuthenticationError("Bearer token does not own this session")
    return session
```

### Harden the transport perimeter

1. **Rotate session IDs** on privilege changes (tool additions, permission escalation)
2. **Bind sessions to origin** — add `Origin` / `X-Forwarded-For` validation per session
3. **Audit session creation logs** — every `initialize` should emit `session_id + principal + timestamp`
4. **Scope bearer tokens tightly**: tool-level scopes, not blanket server access

### Zero-trust the MCP boundary

```
┌─────────────────────────────────────────────────────────┐
│  Agent Runtime                                           │
│  Bearer token: eyJhbG... (valid, verified)              │
└──────────┬──────────────────────────────────────────────┘
           │ POST /mcp/sse?session_id=abc123
           │ Authorization: Bearer eyJhbG...
           ▼
┌─────────────────────────────────────────────────────────┐
│  MCP Transport (vulnerable ≤1.27.2)                      │
│  Route: session_id=abc123 → session[owner=alice]         │
│  Auth:  bearer token verified as bob                     │
│  Result: bob sends JSON-RPC as alice's session  ← GAP   │
└─────────────────────────────────────────────────────────┘

FIX: Session principal must match token principal on every request
```

## Verification

```bash
# 1. Confirm patched version is running
pip show mcp | grep Version
# Must be ≥ 1.27.2

# 2. Smoke-test session isolation
# Start session as principal-A, attempt request as principal-B with same session_id
# Expect: 401 — "Bearer token does not own this session"

# 3. Review transport logs for session_id lookups without principal binding
grep -E "session.*route|session.*auth|401.*session" mcp_transport.log

# 4. NSA guidance: U/OO/6030316-26 (May 2026)
#    CVE: CVE-2026-52869 (July 15, 2026) — CVSS 7.1
```

---

**Sources:** NSA Cybersecurity Information Sheet U/OO/6030316-26 | PP-26-1834 (May 2026); CVE-2026-52869 — MCP Python SDK session hijacking, published 2026-07-15; Hermes Agent MCP-config persistence campaign (June 2026).
