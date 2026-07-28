# S-1746 · The Non-Human Identity Governance Stack — When Your Agent Fleet Has No Identity, No Credentials, and No Audit Trail

You have 50 agents across 8 MCP servers. Each agent accesses GitHub, Slack, Salesforce, and your internal APIs. None of them have individual identities. Credentials are shared across the fleet. When something breaks, you can't tell which agent did it. When an agent gets compromised, you have no way to revoke its access without taking down the whole system. The infrastructure team has no inventory. The security team has no audit trail. This is non-human identity (NHI) governance debt — and it compounds with every new agent you deploy.

## Forces

- **Identity governance was built for humans, not agents.** Traditional IAM assumes an employee with an employment record, a manager, and a departure date. AI agents have none of these. They proliferate faster than any onboarding process can track, and they never send a resignation letter when they are decommissioned.
- **Machine identities already outnumber human identities 45:1 to 100:1** in typical enterprises (IDC). IDC projects 1.3 billion AI agents in operation by 2028. The governance infrastructure has not caught up.
- **Agent credential sprawl is structural, not accidental.** Every MCP server connection creates a new credential — API keys, OAuth tokens, database connection strings. The average enterprise MCP deployment accumulates these faster than any manual process can track.
- **Agent forks inherit secrets silently.** When an agent spawns a child process or a forked execution context, it passes its credentials downstream. The child has the parent's full permission scope with no separate evaluation. This is the blast-radius multiplier for any credential compromise.
- **Claude Code commits leak secrets at 3.2%** — more than double the human-only baseline of 1.5% (GitGuardian, 2026). Agents interact with code and configuration at scale; the credential exposure surface is proportionally larger.
- **78% of organizations lack any policy for creating AI identities** (CSA, Feb 2026). Only 23% have a formal enterprise-wide agent identity strategy. The default state is no identity, shared credentials, no audit.

## The move

Treat agents as workload identities — not software to be trusted, but principals to be attested, scoped, rotated, and audited.

### 1. Establish workload identity with SPIFFE

SPIFFE (Secure Production Identity Framework for Everyone) provides cryptographically verifiable workload identities via X.509 SVIDs (SPIFFE Verifiable Identity Documents). SPIRE is the reference implementation: it runs as a server (SPIRE Server) and an agent on each node (SPIRE Agent), attesting workload processes and issuing short-lived SVIDs.

```
# SPIRE agent config for agent node
agent:
  data_dir: /opt/spire/agent
  trust_domain: prod.example.com
  plugins:
    NodeAttestor:
      k8s_psat:
        cluster: prod-cluster
    WorkloadAttestor:
      k8s:
        skip_kubelet_verification: false
```

Agents present their SVID via the SPIFFE Workload API (Unix socket at `/tmp/spire-agent/public/api.sock`). Any SPIFFE-aware service verifies the SVID cryptographically — no shared secrets, no API keys in environment variables.

For agents running outside Kubernetes, use the `join_token` attestor (server-generated token exchanged for SVID) or AWS IID/Azure metadata attestation for cloud workloads.

### 2. Register agent identity in Microsoft Entra (Azure environments)

Microsoft Entra Agent ID (generally available 2026) treats each agent as a first-class non-human identity with its own lifecycle, conditional access policies, and audit trail. Agents get their own service principal — provisioned, scoped, and revocable independently of the human who deployed them.

```
# Entra Agent ID lifecycle (Microsoft Graph API)
POST https://graph.microsoft.com/v1.0/directory/servicePrincipals
{
  "displayName": "customer-onboarding-agent-v2",
  "appId": "<agent-registration-app-id>",
  "servicePrincipalType": "Agent",
  "tags": ["AgentId", "Production", "LeastPrivilege"]
}

# Assign only the permissions this specific agent needs
POST https://graph.microsoft.com/v1.0/directory/servicePrincipals/{agent-id}/appRoleAssignments
{
  "principalId": "<agent-id>",
  "resourceId": "<target-service-id>",
  "appRoleId": "e1fe6dd8-ba31-4d61-89e7-86639d2b3c8a"  # read-only CRM access
}
```

Conditional access policies apply to agents the same way they apply to users: block sign-in from non-compliant endpoints, require MFA equivalent attestation, or restrict access by time of day.

### 3. Scope MCP OAuth tokens to specific tool actions

Replace shared MCP API keys with per-agent OAuth tokens scoped to specific tool actions. Every MCP server connection gets a token with the minimum required scopes — not `repo:all`, not `admin:org`, but exactly `issues:write` or `pull_requests:read`.

```python
# MCP OAuth token scoping
from mcp_auth import AgentTokenManager

class ScopedTokenManager:
    def __init__(self, auth_url: str, client_id: str, client_secret: str):
        self.auth_url = auth_url
        self.client_id = client_id
        self.client_secret = client_secret

    def issue_agent_token(
        self,
        agent_id: str,
        scopes: list[str],
        lifetime_seconds: int = 3600,
    ) -> str:
        """
        Issue a short-lived, scope-limited OAuth token to a specific agent.
        Scope is the unit of least privilege for MCP tool access.
        """
        token = self._mint_token(
            subject=agent_id,          # Agent identity, not human user
            audience=self.client_id,
            scope=" ".join(scopes),     # Tool-specific, not wildcard
            lifetime=lifetime_seconds,  # Short-lived: 1h max, 15m preferred
        )
        self._log_issuance(agent_id, scopes, lifetime_seconds)
        return token

    def revoke_all_agent_tokens(self, agent_id: str) -> None:
        """Revoke every active token for a decommissioned or compromised agent."""
        token_ids = self._get_active_tokens(agent_id)
        for tid in token_ids:
            self._revoke(tid)
        self._log_revocations(agent_id, len(token_ids))
```

**Rule of thumb:** If an agent's token would work for a human employee's day-to-day work, it is over-scoped. Agents should have less access than the humans they assist, not more.

### 4. Implement RFC 8693 OAuth 2.0 Token Exchange for delegation chains

When Agent A calls Agent B to complete a subtask, the delegation chain must be traceable. RFC 8693 defines `urn:ietf:params:oauth:grant-type:token-exchange` — Agent A exchanges its own token for a delegated token scoped to the specific sub-task, with the delegation chain embedded in the `act` (actor) claim.

```
# RFC 8693 token exchange request
POST /oauth/token
Content-Type: application/x-www-form-urlencoded

grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Atoken-exchange
&subject_token=eyJhbG...
&subject_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Ajwt
&act=%7B%22sub%22%3A%22agent-A-prod%22%7D
&requested_token_type=urn%3Aietf%3Aparams%3Aoauth%3Atoken-type%3Aaccess_token
&scope=read:customer-profile+write:ticket-create

# Response: agent-B's scoped token
# JWT header includes:
# {
#   "sub": "agent-B-prod",
#   "act": {"sub": "agent-A-prod"},   # Delegation chain
#   "scope": "read:customer-profile write:ticket-create",
#   "exp": 1751289600
# }
```

The `act` claim is the delegation chain: Agent B knows it is acting on behalf of Agent A. If the sub-task does something wrong, the audit log traces it back through the chain.

### 5. Fork-aware credential scoping

When an agent spawns a child process or forks execution, the child must not inherit the parent's secrets by default. Use a secrets proxy (like HashiCorp Vault with agent-sidecar, or AWS Secrets Manager with role-based session tags) that issues fresh, child-specific credentials on demand — with scope limited to the child's specific task.

```python
import os

class ForkAwareCredentialProvider:
    """
    On fork(), the child process gets a fresh, scoped credential
    from the secrets proxy instead of inheriting the parent's token.
    """
    def __init__(self, vault_addr: str, vault_role: str):
        self.vault_addr = vault_addr
        self.vault_role = vault_role
        # Parent retains its credential for continuation
        self._parent_cred = self._issue_scoped_cred(vault_role)

    def get_credential_for_child(self, child_task: str) -> dict:
        """
        Each child gets its own credential scoped to its specific task.
        The parent's credential is NOT passed through.
        """
        child_role = f"{self.vault_role}-child-{child_task}"
        return self._issue_scoped_cred(child_role)

    def _issue_scoped_cred(self, role: str) -> dict:
        resp = requests.post(
            f"{self.vault_addr}/v1/auth/agent-namespace/login",
            json={"role": role},
            headers={"X-Vault-Namespace": os.environ["VAULT_NAMESPACE"]},
        )
        resp.raise_for_status()
        return resp.json()["auth"]

    def on_fork(self) -> dict:
        """
        Called automatically in a pre-fork hook.
        Returns a fresh credential for the child — parent credential
        is never shared across the fork boundary.
        """
        return self._issue_scoped_cred(f"{self.vault_role}-ephemeral")
```

### 6. Credential inventory and rotation

You cannot govern what you cannot see. Maintain a live inventory of every credential issued to every agent.

| Credential Type | Rotation Trigger | Max Lifetime |
|---|---|---|
| MCP OAuth token | 90 days or agent version change | 24 hours (re-issue on refresh) |
| SPIFFE SVID | 1 hour (auto-renewed by SPIRE) | 1 hour |
| Database password | 30 days or agent decommission | 24 hours |
| API key (legacy) | Migration to OAuth — no new keys | 90 days (mandatory rotation) |
| Cloud IAM role session | 1 hour (STS assume-role) | 1 hour |

Rotate on event: every agent version change, every agent decommission, every suspected compromise, and every organizational change (employee departure, team restructure) should trigger credential rotation.

### 7. Audit trail: link action to identity to tool

Every agent action — tool call, API request, state change — must be logged with the agent's cryptographic identity, not just its process ID or IP address.

```
# Structured audit log entry
{
  "timestamp": "2026-07-28T14:23:07Z",
  "agent_id": "spiffe://prod.example.com/agent/customer-onboarding-v2/instance-7f3a",
  "agent_version": "2.4.1",
  "action": "mcp_tool_call",
  "tool": "salesforce.create_contact",
  "tool_args_hash": "sha256:3f4b8c...",
  "delegation_chain": ["agent-A-prod", "agent-B-prod"],
  "outcome": "success",
  "tokens_used": 1423,
  "trace_id": "abc123"
}
```

Feed this to your SIEM. Correlate agent actions with the human who deployed the agent (the `owner` label on the SPIFFE identity). When something goes wrong, you can answer: "Which agent did this, who owns it, what was it trying to accomplish, and when did its credentials last rotate?"

## Receipt

> Verified 2026-07-28 — Research sources: Zylos Research "Non-Human Identity and Credential Lifecycle Governance for AI Agent Fleets" (Jul 5, 2026); CSA survey "AI Agent Identity" (Feb 2026, n=500); GitGuardian State of Secrets Sprawl 2026; Microsoft Entra Agent ID documentation; SPIFFE/SPIRE docs; RFC 8693 spec; OWASP ASI Top 10 (Jun 2026). Code examples are realistic implementations of documented patterns; not run against live infrastructure.

## See also

- [S-1458 · The Policy-Kernel Agent Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — policy enforcement is the complement of identity governance
- [S-1006 · The Agent Toolbelt Problem](stacks/s1006-the-agent-toolbelt-problem-what-tools-do-you-actually-give-an-agent.md) — least-privilege tool scoping and credential scoping are the same problem
- [S-1003 · The Agent Failure Recovery Stack](stacks/s1000-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — credential revocation is a prerequisite for incident response
- [S-1516 · The Agent Kill Switch Stack](stacks/) — killing an agent and revoking its credentials must happen together
