# S-1949 · The Shadow MCP Stack — When Your Attack Surface Lives on Every Developer's Laptop

Your security team just completed an audit of your agent infrastructure. 12 MCP servers, all approved, all in the registry. What they missed: the 4 MCP servers each developer installed on their laptop last week — the GitHub server for PR summaries, the AWS server for cost queries, the Notion server for doc lookups. Each one has a live OAuth token. None of them are in the vault. None of them were reviewed. Your attack surface isn't in your cloud — it's on 47 laptops in engineering, and you didn't know it existed.

This is the **Shadow MCP** problem: the Model Context Protocol deploys bottom-up, per-user, and bypass-resistant. MCP's install pattern — developer installs a server so their Cursor agent can read pull requests — creates credential sprawl that IT and security teams cannot see, audit, or control through traditional means.

## Forces

- **Bottom-up beats top-down.** MCP servers install via npm, pip, or a config file edit. No deployment ticket. No architecture review. The developer adds it in 30 seconds and it works. Security finds out months later, if at all.
- **Each MCP server is an agent with a production credential.** It's not a developer convenience tool. It's a model with a GitHub OAuth token, an AWS session token, or a Notion API key, running in the context of the user's identity and permissions.
- **The registry is exploding.** The public MCP server registry crossed several thousand entries in H1 2026. The install velocity is faster than any security team's review velocity.
- **Credential inventory is near-zero.** Across 12 enterprise engagements, researchers found median 4 MCP servers per engineering laptop, max 19. Almost none of the credentials in those configs appeared in the org's secrets vault.
- **Traditional security controls don't reach laptops.** Network perimeter controls, cloud IAM, and secrets management platforms were not designed for per-user tool installations on developer workstations.

## The move

### 1. Discover the fleet (shadow inventory)

You cannot secure what you cannot see. Run a discovery scan before any other control:

```bash
# Find all MCP server configs across the fleet
# MCP configs live at ~/.config/mcp/ (Linux/macOS) or %APPDATA%/mcp/ (Windows)
find ~ -name "mcp.json" -o -name "mcp_servers.json" 2>/dev/null \
  | xargs grep -l '"http"' 2>/dev/null

# List installed MCP servers via CLI
mcp --list 2>/dev/null || npx @modelcontextprotocol/cli list 2>/dev/null

# Scan for credential patterns in MCP configs
grep -rE '"(bearer|token|key|secret|oauth)"' ~/.config/mcp/ 2>/dev/null
```

The output is your shadow inventory. Treat it as a real finding, not a compliance artifact.

### 2. Classify by blast radius

Not all shadow MCP servers are equal. Score each on:

| Factor | Low Risk | High Risk |
|--------|----------|-----------|
| Credential type | Read-only API key | OAuth with write access |
| Target system | Public data | Production database, CI/CD |
| Isolation | User-scoped | Admin/org-level access |
| Rotation | Recent | >90 days old |

High-blast-radius servers on laptops need immediate action regardless of org policy.

### 3. Enforce a credential gateway

Route all MCP server credentials through a managed gateway layer:

```typescript
// MCP credential gateway — all servers register through here
interface MCPCredential {
  serverName: string;
  target: string;
  scope: 'read' | 'read-write' | 'admin';
  owner: string;          // laptop/user
  approvedBy?: string;
  expiresAt: Date;
  rotationSchedule: string;
}

// MCP server config that replaces raw credentials
// Instead of: { "github": { "auth": "bearer", "token": "gho_..." } }
// Use:
{
  "github": {
    "gateway": "https://mcp-gateway.internal.co",
    "serverId": "github-production-read",
    "scopedTo": "user-id-from-idp"
  }
}
```

The gateway issues short-lived, scoped tokens and logs every tool invocation. It enforces the principle that the MCP server never holds a raw credential — it holds a session managed by the gateway.

### 4. Scoped least-privilege per server

Review every MCP server's actual requirements and reduce scope:

```json
// Before: GitHub MCP server with full repo access
{
  "token": "ghp_xxxxxxxxxxxxxxxxxxxx",
  "scopes": ["repo", "admin:org", "workflow"]
}

// After: Read-only, user-scoped
{
  "gatewayToken": "gw_xxxxxxxx",
  "scopes": ["issues:read", "pulls:read", "contents:read"],
  "rateLimit": "100/hour"
}
```

### 5. Establish an install registry (even if you can't block installs)

If you can't prevent bottom-up installs, at least make them auditable:

```bash
# In your MDM/deployment tooling, scan for MCP configs on enrollment
# Flag any server not in the approved registry
#!/bin/bash
APPROVED=$(cat /etc/mcp/approved-servers.json | jq -r '.[].name')
INSTALLED=$(jq -r 'keys[]' ~/.config/mcp/mcp_servers.json 2>/dev/null)

for server in $INSTALLED; do
  if echo "$APPROVED" | grep -q "$server"; then
    echo "APPROVED: $server"
  else
    echo "UNREVIEWED: $server — escalate"
  fi
done
```

## Receipt

> Verified 2026-08-01 — Research synthesis: Nomad Security (May 9, 2026) across 12 engagements: median 4 MCP servers per engineering laptop, max 19, near-zero credential inventory in secrets vault. Microsoft Security (2026): MCP has become the default agent-tool bridge, with OWASP Agentic AI Security (ASI) Top 10 released June 2026. The install pattern (Cursor/Claude Desktop user installs GitHub MCP for PR summaries) creates an OAuth token on a personal workstation that bypasses IT review entirely. Control: discover → classify → gateway → scope → register. The attack is structural (bottom-up install pattern), not a configuration mistake — controls must match the deployment velocity.

## See also

- [S-1458 · Policy-Kernel Agent Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — enforcement layer for the MCP ecosystem
- [S-1006 · Agent Toolbelt Problem](stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — tool cardinality and permission blast radius
- [S-1318 · Ephemeral Identity Stack](stacks/s1318-the-ephemeral-identity-stack-when-your-agent-wears-the-master-key.md) — what happens when credentials outlive their context
- [S-1017 · Transitive Framework Stack](stacks/s1017-the-transitive-framework-stack-when-your-agent-server-is-owned-through-a-dependency-you-didnt-know-you-had.md) — the other attack surface hiding in your dependency tree
