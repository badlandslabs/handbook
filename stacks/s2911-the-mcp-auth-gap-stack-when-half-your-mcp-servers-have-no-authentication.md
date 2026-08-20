# [S-2911] · The MCP Auth Gap Stack — When 50% of Your MCP Servers Have No Authentication and You're Already in Production

You have 12 MCP servers in production. Three of them expose tools that can read customer records, send emails, and provision cloud resources. You know this because you read the schema. The problem: you have no idea who can call them, because none of those servers have authentication configured. The spec doesn't mandate it. The SDK doesn't require it. The blog post that taught you how to build your first MCP server didn't mention it. You shipped anyway.

This is the **MCP Auth Gap**: the structural hole between MCP's protocol-first design and the reality that production tool access requires both authentication *and* authorization — and neither ships by default.

## Forces

- **MCP was designed to be protocol-first, security-later.** The specification defines transport and message formats; authentication and authorization are explicitly left to implementors. This made adoption fast. It made production unsafe.
- **Credential mismanagement is the #1 MCP vulnerability (OWASP MCP Top 10, beta — MCP01).** Analysis of 5,200 open-source MCP servers found 88% require credentials, but only 8.5% use OAuth. 53% rely on static API keys or PATs, and 79% of those keys are passed through plain environment variables — visible in process listings, leaked through log aggregation, and impossible to revoke per-session.
- **Security is the #1 blocker for MCP production adoption.** Zuplo's State of MCP Report (2026): 50% of respondents cite security and access control as their top challenge; 38% say security concerns are *actively blocking* adoption. 25% of MCP servers have no authentication whatsoever.
- **Authentication without authorization grants every verified identity full tool access.** Teams implement OAuth, get a green checkmark, and then grant every authenticated agent access to every tool on every server. A prompt injection on the agent side then invokes any tool the agent can name — the auth server verified the agent's identity, not its intent.

## The move

### Gate 1: Authentication — who is this agent?

Authentication answers "who is connecting." Three patterns in production, roughly ordered by maturity:

**Static API key (legacy, common, fragile):**
```
# Passed as env var — visible in ps aux, leaked by log aggregation
MCP_API_KEY=sk-live-...
```
Problem: Long-lived, no per-session revocation, no audit trail of which agent session used it, logs it everywhere.

**OAuth 2.0 with short-lived tokens (recommended for production):**
```
# Agent authenticates → receives scoped, time-limited access token
# Token expires in minutes, not months
POST /oauth/token
  grant_type=client_credentials
  scope=mcp:read,customer_db:query
# Returns: { "access_token": "eyJ...", "expires_in": 300 }
```
Problem: Requires an OAuth provider. More complexity upfront. Worth it.

**MCP-native bearer tokens via the auth/scheme endpoint (emerging):**
```
# Server declares its auth requirements
HTTP GET /auth/scheme
# → { "type": "bearer", "header": "Authorization", "token_endpoint": "/auth/token" }
```
The Linux Foundation now governs the MCP spec (incorporated late 2025), and auth/scheme is the emerging standard for servers to declare their requirements to clients — solving the discovery problem that plagued early MCP deployments.

### Gate 2: Authorization — what is this agent permitted to do?

Authentication without authorization is a lobby with a badge scanner but no doors. The authorization question is granular: *which agent, requesting which tool, with which arguments, in which session, for which task?*

**Role-based access (RBAC) on the server side:**
```python
# MCP server authorization middleware
ALLOWED_TOOLS = {
    "email_agent":    ["send_email", "read_inbox"],
    "data_agent":     ["customer_db:query", "customer_db:read"],
    "code_agent":     ["execute_code", "read_file"],
    "admin_agent":    ["*"],  # deny this in production
}

def authorize(agent_id: str, tool: str) -> bool:
    allowed = ALLOWED_TOOLS.get(agent_id, [])
    return tool in allowed or "*" in allowed
```

**Scope-limited tokens (defense in depth):**
```python
# Token carries its own permissions — MCP server enforces, not just trusts
token_payload = jwt.decode(token, SECRET, algorithms=["RS256"])
# token_payload["scope"] = "customer_db:query,read_inbox"
# token_payload["agent_id"] = "data_agent_01"
# token_payload["session_id"] = "sess_abc123"

def call_tool(tool: str, args: dict, token_scope: list[str]) -> dict:
    required_scope = f"{tool}:{args.get('_mode', 'execute')}"
    if required_scope not in token_scope and tool not in token_scope:
        raise PermissionError(f"Token scope {token_scope} does not cover {tool}")
    return execute_tool(tool, args)
```

**Policy engine at the MCP gateway (enterprise — S-1458 extends this):**
```python
# OPA (Open Policy Agent) at the MCP gateway
# Decides per-call, not per-connection
def mcp_gateway_policy(request: MCPRequest, context: AgentContext) -> Decision:
    return {
        "allow": context.agent_trust_level >= MIN_TRUST_LEVEL
                 and request.tool not in HIGH_IMPACT_TOOLS
                 and request.args["_mode"] != "bulk"
    }
```

### The two-gate failure mode nobody catches

The most dangerous pattern: **HTTP 200 on auth, wildcard on authorization.**

```python
# Looks like security. Isn't.
@app.post("/mcp/call")
def call_tool(request: MCPRequest):
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not verify_token(token):  # Gate 1: ✓
        return {"error": "unauthorized"}
    # Gate 2: ✗ — authenticated? everything is allowed.
    return execute(request.tool, request.params)
```

The fix is a deny-by-default authorization table on every server, separate from the authentication layer.

### Tool-level audit logging

Every MCP call — allowed or denied — gets written to an immutable audit log with the agent identity, session ID, tool, arguments, timestamp, and decision:

```json
{
  "ts": "2026-08-20T14:32:01Z",
  "agent_id": "data_agent_01",
  "session_id": "sess_abc123",
  "tool": "customer_db:query",
  "args": {"table": "users", "filters": {"id": "cu_9473"}},
  "decision": "ALLOW",
  "auth_method": "oauth_scoped_token",
  "token_scope": ["customer_db:query"],
  "mcp_server": "db-server-prod-03"
}
```

Without this log, you cannot answer: *which agent accessed this record, when, and why?* — the question your compliance team and your incident responders will ask simultaneously.

## Receipt

> Receipt pending — [2026-08-20] — Based on: Zuplo State of MCP Report (2026, n=survey respondents), Astrix Security analysis of 5,200 open-source MCP servers (2026), OWASP MCP Top 10 beta (MCP01), Practical DevSecOps MCP Auth Guide (Varun Kumar, May 2026), CSA/Strata Identity survey (March 2026), Linux Foundation MCP governance update (late 2025).

## See also

- [S-2847 · The Non-Human Identity Void](stacks/S-2847-the-non-human-identity-void-stack-when-your-agent-has-no-birth-certificate-no-passport-and-full-admin-access.md) — NHI is the identity problem; this is the auth-stack solution for MCP specifically
- [S-1458 · The Policy Kernel](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — policy kernel extends the authorization gate into multi-agent orchestration
- [S-1145 · The Two-Layer Guard Stack](stacks/s1145-the-two-layer-guard-stack-when-your-prompt-guardrail-cant-see-the-tool-call-that-breaks-you.md) — prompt guardrails can't enforce MCP-layer auth; this stack adds the enforcement that sits below the model
- [S-2910 · The MCP Fault Taxonomy](stacks/S-2910-the-mcp-fault-taxonomy-stack-when-your-mcp-server-runs-but-your-agent-breaks.md) — same MCP server, different failure mode: the server answers every request but the wrong one
