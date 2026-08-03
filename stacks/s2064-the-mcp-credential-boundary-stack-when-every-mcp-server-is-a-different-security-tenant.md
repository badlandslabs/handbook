# S-2064 · The MCP Credential Boundary Stack — When Every MCP Server Is a Different Security Tenant

Your coding agent needs to read GitHub PRs and post Slack messages. You connect two MCP servers. Both ask for credentials. Both say "read-only." You approve both. What you just did: gave two independent third-party codebases, neither of which you've audited, access to your entire GitHub organization and your company's Slack workspace — simultaneously, with no isolation between them. One of them has a CVE from January. One of them will have a CVE in three months. The blast radius of each is your entire credential scope. This is the MCP credential boundary problem, and it is not a configuration mistake — it is a structural flaw in how the protocol handles identity and scope.

## Forces

- **MCP servers are third-party code running at your agent's privilege level.** Unlike traditional APIs where you write the integration, MCP servers are pre-built binaries or packages you connect to your agent's context. Their permission model is inherited from the agent — not sandboxed by it.
- **Credentials are shared, not scoped.** When you authenticate an MCP server, you hand it a credential (OAuth token, API key, PAT) that has the same scope as your agent's session. If the server needs read-only GitHub access, you give it a read-only PAT — but that PAT can be cloned, replayed, or exfiltrated by the server itself.
- **Protocol lacks credential boundary enforcement.** MCP's STDIO transport and the reference SDKs provide no mechanism for per-server credential isolation. A single compromised server inherits all credentials the agent holds.
- **The skills layer amplifies this.** Skills install additional MCP servers or extend existing ones. A skill from a registry can silently add a new server connection with its own credential requirements. The agent's credential surface grows organically, without human review.
- **CVEs are accelerating.** 30+ CVEs filed against MCP servers in a single 60-day window in early 2026 (multiple researchers). 13 of 30 were command-injection patterns. The protocol solves tool integration — it does not solve tool security.

## The move

**Treat every MCP server as an external service with its own security policy.** Do not grant MCP servers access to your agent's runtime credentials. Instead, use scoped, revocable, instrumented credentials per server.

### 1. Credential-per-server isolation

Instead of giving one GitHub PAT to the agent and letting all MCP servers use it, create separate read-only PATs per server. Limit scope to exactly what that server needs — no more.

```python
# Credential registry: each MCP server gets a scoped, revocable credential
from mcp_credential_boundary import ServerCredential, CredentialGrant

credential_registry = {
    "github-pr-reader": ServerCredential(
        pat="ghp_xxxxxxxxxxxx",
        scopes=["pull_requests:read", "issues:read"],
        mcp_server="github-pr-mcp",
        audit_tag="s2064",
    ),
    "slack-notifier": ServerCredential(
        token="xoxb-xxxxxxxxxxxx",
        scopes=["chat:write"],
        mcp_server="slack-mcp",
        audit_tag="s2064",
    ),
}

# MCP server config: explicit credential binding
mcp_config = {
    "mcpServers": {
        "github-pr-mcp": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {
                "GITHUB_PERSONAL_ACCESS_TOKEN": credential_registry["github-pr-reader"].pat,
            }
        },
        "slack-mcp": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-slack"],
            "env": {
                "SLACK_BOT_TOKEN": credential_registry["slack-notifier"].token,
            }
        }
    }
}
```

### 2. Runtime credential audit log

Every MCP server invocation should be logged with the credential used, the data accessed, and the server version. Rotate credentials on a schedule and on every MCP server version update.

```python
import httpx
from datetime import datetime, timedelta
from typing import Literal

class ScopedCredential:
    def __init__(self, name: str, token: str, scopes: list[str], mcp_server: str):
        self.name = name
        self.token = token
        self.scopes = scopes
        self.mcp_server = mcp_server
        self.created_at = datetime.utcnow()
        self.rotation_interval_days = 90

    def should_rotate(self) -> bool:
        return datetime.utcnow() - self.created_at > timedelta(days=self.rotation_interval_days)

    def audit_log(self, action: str, resource: str, outcome: Literal["allow", "deny"]):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "server": self.mcp_server,
            "credential_name": self.name,
            "scopes": self.scopes,
            "action": action,
            "resource": resource,
            "outcome": outcome,
        }
        # Ship to your SIEM / audit trail
        print(f"[S2064 AUDIT] {log_entry}")
        return log_entry

    def revoke(self):
        print(f"[S2064] Revoking credential {self.name} for server {self.mcp_server}")
        self.token = None
```

### 3. MCP server registry pinning

Never fetch MCP servers at runtime from a public registry without pinning. Lock to a specific version, verify the package hash, and require manual approval for version upgrades.

```yaml
# mcp-servers.yaml — version-controlled, hash-verified
mcpServers:
  github-pr-mcp:
    package: "@modelcontextprotocol/server-github@1.4.0"
    sha256: "a3f5c8d9e1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8"
    auto_update: false
    requires_approval: ["security-team"]
  slack-mcp:
    package: "@modelcontextprotocol/server-slack@2.1.0"
    sha256: "b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5"
    auto_update: false
    requires_approval: ["security-team"]
```

### 4. Least-agency permission model

Apply OWASP ASI04's least-agency principle at the protocol level. The agent should only have the minimum agency required for the current task — and each MCP server should only receive the minimum credential scope required for its specific function. When a server needs elevated access, require explicit task-level authorization, not session-level grant.

## Receipt

> Verified 2026-08-03 — Research confirmed: OX Security April 2026 disclosure (150M+ MCP SDK downloads, 7,000+ public servers, systemic STDIO RCE architectural flaw across all language SDKs); Docker MCP Horror Stories analysis (CVE-2025-6514, 30+ CVEs in 60-day window early 2026); OWASP ASI04 (Least Agency), ASI10 (Unmaintained Components), and AST10 (Agentic Skills Top 10) framework convergence. MCP credential boundary problem is a structural protocol gap, not a configuration error. Receipt pending — production implementation example not yet run.

## See also

- [S-1517 · The Compromised MCP Server Stack](s1517-the-compromised-mcp-server-stack-when-the-tool-you-trusted-becomes-the-attack-surface.md) — focuses on the compromised server; S-2064 focuses on the credential boundary problem *before* compromise
- [S-1960 · The Agentic Skills Top 10 Stack](S-1960-the-agentic-skills-top-10-stack-when-your-agent-installs-brittle-code-from-a-stranger.md) — skills-as-packages attack surface; S-2064 is the credential-layer root cause
- [S-2046 · The Infra Blast-Radius Stack](s2046-the-infra-blast-radius-stack-when-your-agent-deletes-the-database-without-asking.md) — credential blast radius; S-2064 is the protocol-level boundary that determines blast radius size
