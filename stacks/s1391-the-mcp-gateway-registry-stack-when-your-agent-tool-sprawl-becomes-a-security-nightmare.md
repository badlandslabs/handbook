# S-1391 · The MCP Gateway Registry Stack — When Your Agent Tool Sprawl Becomes a Security Nightmare

Every developer wires their own MCP server credentials into their dotfile. Each agent instance gets its own set of API keys. Nobody knows which tools exist, which credentials are live, or who accessed what. One exposed key later, your production database is in a commit log.

## Forces

- MCP's decentralized model — any server, any tool, anywhere — is great for demos; it becomes a governance nightmare at scale
- Credential sprawl across per-user MCP configs means no audit trail, no rotation, no revocation
- Agents need dynamic tool discovery at runtime, but naive discovery exposes every registered capability indiscriminately
- The moment an agent can discover tools autonomously, you've moved from "access control" to "capability enumeration attack surface"
- Enterprise identity providers (Entra ID, Okta, Keycloak) are separate from the agent runtime — bridging them requires a proxy layer

## The move

Introduce an **MCP Gateway & Registry** as the single governed entry point for all MCP servers, tools, and agent-to-agent communication. It collapses three concerns into one control plane:

### 1. Credential Consolidation

All MCP server credentials live in the registry, not in individual developer machines or agent configs. The gateway owns the secrets; agents receive scoped, short-lived tokens.

```yaml
# Registry: one source of truth for all tool credentials
# agents/agents.yaml
- agent_id: triage-agent
  name: "Triage Agent v2"
  mcp_tools:
    - server: jira-mcp-prod
      allowed_tools: [get_issue, create_subtask]
      token_ttl: 3600  # short-lived, rotated by gateway
    - server: slack-mcp
      allowed_tools: [send_message]
      token_ttl: 7200
  oauth_provider: entra-id
  audit: true
```

### 2. Dynamic Tool Discovery with Access Control

The gateway exposes a semantic search endpoint over registered tool schemas. Agents query it with natural language, the gateway returns only tools the agent's identity is authorized to use.

```python
# Agent requests: "find tools for creating a support ticket in Jira"
# Gateway flow:
# 1. Embed query with sentence transformer
# 2. Vector search over registered tool schemas
# 3. Filter results by agent's allowed_tools (from registry)
# 4. Return only authorized matches with discovery receipt

import httpx

async def discover_tools(query: str, agent_id: str, auth_token: str):
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{GATEWAY_URL}/api/v1/discover",
            json={"query": query, "agent_id": agent_id},
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        results = resp.json()["tools"]
        # Each result includes a "discovery_receipt" showing
        # which tools were filtered and why (governance, not magic)
        return [t for t in results if t["authorized"]]
```

### 3. Audit and Governance Layer

Every tool invocation through the gateway is logged with: agent identity, tool called, parameters (scrubbed of secrets), timestamp, and outcome. Logs forward to SIEM.

```yaml
# Gateway audit log entry (forwarded to SIEM)
---
event: mcp_tool_invocation
agent_id: triage-agent-v2
tool: jira-mcp-prod/create_subtask
parameters:
  summary: "[REDACTED - contains ticket data]"
  assignee: "support-queue@corp.com"
outcome: success
duration_ms: 1247
gateway_policy: allowed  # vs "blocked - not in allowed_tools"
```

### 4. Idempotent Tool Invocation

The gateway assigns idempotency keys to tool calls so retries don't create duplicate side effects:

```python
idempotency_key = f"{agent_id}:{tool_name}:{hash(request_params)}"

response = await gateway.forward(
    tool=tool_name,
    params=request_params,
    idempotency_key=idempotency_key,
    timeout=30
)
# If the same idempotency_key arrives within the TTL window,
# the gateway returns the cached response instead of re-calling the MCP server
```

## Architecture

```
Users / Agents
    │
    ▼
┌─────────────────────────┐
│  nginx reverse proxy    │  ← TLS termination, auth header validation
│  (data plane)           │
└────────────┬────────────┘
             │
┌────────────▼─────────────────────────┐
│  Registry + Gateway (FastAPI)        │  ← Control plane
│  ├─ OAuth2/OIDC (Keycloak/Entra/Okta)│
│  ├─ Tool inventory + embeddings      │
│  ├─ Access policy engine              │
│  ├─ Audit log → SIEM                 │
│  └─ Idempotency key store (Redis)    │
└─────┬───────────────────────┬────────┘
      │                       │
      ▼                       ▼
  MCP Server A            MCP Server B
  (Jira)                  (Slack)
```

## See also

[S-10](s10-mcp.md) · [S-20](s20-agent-skills.md) · [S-889](s889-mcp-ambient-authority-capability-bucketing-against-session-scoped-token-chains.md) · [S-1089](s1089-the-tool-description-drift-stack-when-your-agent-routes-to-the-wrong-tool-because-the-schema-changed.md) · [F-194](f194-agentjacking-mcp-tool-response-poisoning.md)
