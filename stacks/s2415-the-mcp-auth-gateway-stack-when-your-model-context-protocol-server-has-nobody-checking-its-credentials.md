# [S-2415] · The MCP Auth Gateway Stack — When Your Model Context Protocol Server Has Nobody Checking Its Credentials

Your MCP server runs in production. It has credentials. Those credentials are a long-lived static token sitting in an environment variable, or worse, embedded in a config file that your entire team shares. Nobody rotates them. Nobody audits who uses them. Nobody knows when they were last reviewed. The protocol is OAuth 2.1 for remote servers — and you are not doing it.

This is the MCP Auth Gateway problem: the gap between what the MCP spec mandates for remote server authentication and what production deployments actually implement. It is also the gap where CVE-2025-54136 lives.

## Forces

- **88% of MCP servers require credentials** — but **53% of deployments use static, long-lived secrets** instead of short-lived tokens. The credential is the perimeter, and the perimeter is a shared secret.
- **Only 8.5% of MCP servers currently implement OAuth 2.1** — despite it being the protocol's mandatory security standard for remote deployments. The spec mandates it; production hasn't caught up.
- **AI agents are public clients that cannot store secrets.** Standard OAuth flows that rely on client credentials — a secret the app keeps — don't work when your "client" is an autonomous agent with no secure storage.
- **Enterprise MCP deployments face consumer OAuth's structural failure:** 50 engineers × 8 MCP servers = 400+ manual consent flows, zero IT visibility, no revocation path when employees leave.
- **The MCP registry grew from ~1,200 to 9,400+ servers in 14 months** (Q1 2025 → April 2026). The attack surface grew 7× faster than governance programs could track it.
- **MCP's remote transport is a different security domain than stdio.** Local stdio passes environment variables; remote HTTP exposes network endpoints. Every endpoint is an attack surface.

## The Move

### 1. Know what the spec actually mandates

The MCP authorization specification (revision 2025-11-25) requires OAuth 2.1 with PKCE for any MCP server handling authenticated requests. The compliant stack:

| Standard | Purpose |
|----------|---------|
| **OAuth 2.1 + PKCE** | Required auth flow; S256 code challenge mandatory; implicit grant removed |
| **RFC 9728** — Protected Resource Metadata | Server advertises capabilities via `/.well-known/resource-metadata.json` |
| **RFC 8707** — Resource Indicators | Scopes MCP tools/resources with fine-grained audience values |
| **RFC 8693** — Token Exchange | Zero-touch delegation; agents exchange tokens without re-authenticating |

Token passthrough — forwarding tokens through your MCP server to backend services — is the most dangerous anti-pattern. Validate tokens directly with the authorization server. Use token exchange when accessing downstream services.

### 2. Map the three MCP auth properties

Traditional OAuth and MCP OAuth operate on different trust models:

| Property | Traditional Model | MCP Model |
|----------|-------------------|-----------|
| **Server role** | May issue tokens | Is a resource server; never issues tokens |
| **Token scope** | App-level | Per-tool, per-resource, per-call |
| **Client type** | Confidential (has a secret) | Public (no secure storage; agents) |

Because MCP clients (agents) are public clients, the only viable flow is **Authorization Code + PKCE**. The agent generates a code verifier, sends a challenge derived from it, and the auth server confirms the challenge matches on callback.

### 3. Implement zero-touch enterprise OAuth

Consumer OAuth — one consent prompt per server per user — breaks at enterprise scale. The `io.modelcontextprotocol/enterprise-managed-authorization` extension (shipped June 18, 2026) solves this:

- **IT pre-authorizes MCP servers** at the organization level; agents inherit the org's consent silently
- **Token audience binding** scopes tokens to the specific MCP server + resource, not a generic bearer
- **Dynamic Client Registration** (RFC 7591) is deprecated in favor of **Client ID Metadata Documents** — clients fetch their registration from a well-known endpoint instead of registering blindly
- **Keycloak / Entra ID integration** for MCP gateway deployments: agents authenticate via the enterprise IdP, receive short-lived (5–15 minute) scoped tokens, and present them per-call

```python
# MCP server token validation (Python / FastAPI)
# Validates bearer token against Keycloak token introspection endpoint
# before executing any tool call

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import httpx

security = HTTPBearer()

async def validate_mcp_token(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials
    async with httpx.AsyncClient() as client:
        # Introspect token against authorization server
        response = await client.post(
            f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token/introspect",
            data={
                "token": token,
                "token_type_hint": "access_token",
            },
            auth=(MCP_SERVER_CLIENT_ID, MCP_SERVER_CLIENT_SECRET),
        )
    payload = response.json()
    if not payload.get("active"):
        raise HTTPException(status_code=401, detail="Token not active")
    # Enforce audience: token must be scoped to this MCP server
    expected_audience = f"mcp://{MCP_SERVER_ID}"
    if expected_audience not in payload.get("aud", []):
        raise HTTPException(status_code=403, detail="Token audience mismatch")
    return payload


@app.post("/v1/tools/{tool_name}")
async def execute_tool(
    tool_name: str,
    params: dict,
    token_payload: dict = Depends(validate_mcp_token),
):
    # token_payload['scope'] contains per-tool scopes granted by enterprise policy
    allowed_tools = token_payload.get("scope", "").split()
    if tool_name not in allowed_tools:
        raise HTTPException(
            status_code=403,
            detail=f"Token does not grant access to tool: {tool_name}",
        )
    result = await dispatch_tool(tool_name, params)
    return {"result": result}
```

### 4. Defend the MCP config file supply chain

CVE-2025-54136 (CVSS 7.2, August 2025): Cursor IDE versions ≤1.2.4 accepted silent server swaps in shared MCP config files. A collaborator adds a benign MCP server, the attacker later edits the config to swap the binary for a malicious one — no warning, no re-approval. This attack works because the trust model is file-level, not content-level.

Defense layers:

- **Content-hash pinning**: store SHA-256 digests of approved MCP server binaries; verify on every invocation
- **Signed manifests**: MCP server operators sign their releases (SLSA / Sigstore); clients verify signatures before loading
- **Config file integrity monitoring**: alert on any modification to MCP config files that doesn't come from your approved CI/CD pipeline
- **Enterprise MCP gateway as enforcement point**: all MCP server connections route through a governed gateway that validates server identity, enforces auth, and logs every tool invocation — instead of allowing agents to connect directly to remote servers

### 5. Build the MCP governance foundation

MCP Ambassador (mcpambassador.ai) and the MCP Gateway Registry (agentic-community/mcp-gateway-registry) provide self-hosted governance proxies with:

- **Centralized auth**: all agents authenticate to the gateway; the gateway handles per-server OAuth flows
- **Audit trail**: every tool invocation logged with agent identity, tool name, parameters, and timestamp
- **Access control**: per-agent, per-server, per-tool authorization policies
- **Scope narrowing**: tokens received by the agent carry only the minimum permissions for the current task

```yaml
# MCP gateway policy: minimal tool access per agent role
# agent role → allowed servers → allowed tools
policies:
  - agent_role: data-analyst
    servers:
      - mcp://warehouse-db
    tools: [query, schema_inspect]
    token_ttl_minutes: 15
    require_reauthorization_on_scope_change: true

  - agent_role: code-review
    servers:
      - mcp://github-enterprise
      - mcp://security-scanner
    tools: [list_pull_requests, get_diff, run_static_analysis]
    token_ttl_minutes: 30

  - agent_role: incident-runbook
    servers:
      - mcp://pagerduty
      - mcp://jira
    tools: [list_incidents, get_runbook, create_ticket]
    token_ttl_minutes: 60
```

## Receipt

> Receipt pending — 2026-08-10. The Python validation snippet was written against the MCP authorization spec (RFC 8707 / RFC 9728) and Keycloak token introspection patterns. Run against a real Keycloak instance by configuring `KEYCLOAK_URL`, `REALM`, `MCP_SERVER_CLIENT_ID`, and `MCP_SERVER_CLIENT_SECRET` as environment variables. Validate the gateway policy YAML against your IdP's scope model.

## See also

- [S-365 · MCP Supply Chain: From `npx` to Production Catalog](stacks/s365-the-mcp-supply-chain-from-npx-to-production-catalog.md) — SBOM, artifact pinning, signed digests (the artifact security layer this entry's signing defenses build on)
- [S-427 · MCP Schema Contracts](stacks/s427-the-mcp-schema-contracts-stack-when-your-tool-description-changes-and-nobody-notices.md) — schema versioning and drift detection for MCP tools
- [S-420 · Agent Identity Governance: The AI-Principal Paradigm](stacks/s420-the-agent-identity-governance-stack-when-your-agent-is-a-principal-with-no-identity-card.md) — NHI, capability contracts, and zero-trust agent identity (the authentication layer agents use to authenticate to the gateway)
- [S-2290 · The A2A Credential Propagation Stack](stacks/s2290-the-a2a-credential-propagation-stack-when-your-delegation-chain-hands-out-the-keys.md) — least-privilege delegation across agent-to-agent hops
