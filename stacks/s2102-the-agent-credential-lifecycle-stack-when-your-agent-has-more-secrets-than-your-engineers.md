# S-2102 · The Agent Credential Lifecycle Stack: When Your Agent Has More Secrets Than Your Engineers

[Your AI agent just onboarded to six new tools. It has six new credentials. None of them expire. None are scoped. None are audited. And nobody wrote any of this down.]

## Forces

- **Identity explosion dwarfs human IAM.** Enterprises already run 45–100 machine identities for every human identity. AI agents project to 1.3 billion globally by 2028 (IDC). Your existing identity governance was built for humans with managers and departure dates — not autonomous software with no offboarding event.
- **Agents weaponize their credentials at scale.** Unlike a human who reads one email per day, a compromised agent can exfiltrate, write, or delete at machine speed across every system it's been granted access to. The blast radius of a leaked agent credential is categorically different from a leaked developer key.
- **Static secrets fail agents on the first day.** Environment variables, config files, secrets-injected-at-deploy — these work for deterministic software. Agents are non-deterministic: they discover new tools at runtime, call APIs you didn't plan for, and operate across sessions with evolving permission needs. A static API key can't express "read-only on Tuesday, read-write on Wednesday."
- **The compliance surface is invisible.** Agents chain tools across systems: read from Salesforce, write to Slack, push to GitHub. The credential that enabled a data leak might have been valid for all three — but your audit log only shows three separate actions by three separate services.

## The move

**Treat every agent as a non-human identity (NHI) with a full lifecycle — provisioning, scoping, rotation, and revocation — and provision credentials at the minimum scope needed for the current task.**

### 1. Enumerate, don't discover

Before any agent touches a credential:
- Register every agent identity in an NHI registry (name, owner, purpose, approved scopes, TTL)
- Map each credential to a specific tool and action — not just "GitHub access" but "read-only on repo X, no fork, no delete"
- Use your secrets manager (HashiCorp Vault, AWS Secrets Manager, Azure Key Vault) as the credential broker — never hardcode, never pass via env for long-lived agents

### 2. Scope credentials to task context

Traditional IAM: role → identity → permission. Agent IAM: task → required permission → time-boxed credential.

```
# Capability-scoped token pattern (pseudocode)
agent_id = registry.provision("sales-research-agent", owner="data-team")
task = planner.decompose("summarize Q3 accounts")
required_scopes = ["salesforce:read:accounts", "slack:post:#team-reports"]

for scope in required_scopes:
    cred = vault.issue_scoped_token(agent_id, scope, ttl="4h")
    agent.attach_credential(cred)   # auto-revoked on task completion
```

This is the OAuth 2.0 Token Exchange (RFC 8693) pattern applied to agents: issue a derived credential with only the scopes the current task needs, and let it expire automatically.

### 3. Rotate continuously, revoke immediately

- Agents that call third-party APIs: rotate credentials every 24–72h automatically. Use the secrets manager's rotation hooks.
- Agents with long-lived MCP server access: bind credentials to session IDs, not to agent identity. Revoke on session end.
- Compromised agent? Revoke all active credentials in one call. The registry is your kill switch — it must support bulk revocation by agent ID.
- Claude Code commits leak secrets at 3.2% vs. 1.5% for human-only commits (GitGuardian 2026). Use commit hooks that scan for credential patterns before any `git push`.

### 4. Audit the chain, not just the action

A single agent task may touch five systems. Log:
- Which credential was used (not just which user/service)
- Which task context triggered it
- Whether the action was read/write/delete
- Whether the credential was scoped or broad

This requires instrumentation at the credential layer, not just at each downstream system. Your secrets manager should emit structured audit events for every `issue`, `use`, `rotate`, and `revoke`.

### 5. Apply zero-trust to agents

Just like workload identity in Kubernetes (SPIFFE/SPIRE, AWS IAM Roles Anywhere, Azure Workload Identity):
- Agents should never present long-lived static keys
- Each runtime context gets a short-lived, scoped token via OIDC or OAuth 2.0 Token Exchange
- The target service validates the token's audience, scopes, and issuer — not the credential itself

### 6. Governance at fleet scale

- **NHI governance policy**: 23% of organizations have a formal agent identity strategy (CSA, Feb 2026); 78% have no AI identity creation policy. Write one.
- **Agent deprovisioning**: Humans quit. Agents get deleted. Who revokes the credentials when an agent is decommissioned? Treat agent decommissioning as a formal lifecycle event with a checklist: revoke all credentials → update registry → archive audit trail → notify downstream systems.
- **MCP credential scoping**: MCP servers run in isolated contexts — scope MCP server credentials per call, not per session. When the MCP host acts on the agent's behalf, use the most specific scope available (e.g., Dataverse scope `McpServers.Dataverse.Read` vs. `McpServers.Dataverse.All`).

```[python]
# Minimal NHI lifecycle manager (pseudocode)
import secrets_manager  # HashiCorp Vault / AWS / Azure

class AgentNHI:
    def __init__(self, name: str, owner: str, ttl: str = "30d"):
        self.id = registry.register(name=name, owner=owner, ttl=ttl)
        self.active_credentials: list[ScopedCredential] = []

    def request_credential(self, scope: str, action_ttl: str = "4h") -> ScopedCredential:
        if not registry.is_approved(self.id, scope):
            raise PermissionError(f"Scope {scope} not approved for {self.id}")
        cred = secrets_manager.issue(
            principal=self.id,
            scope=scope,
            ttl=action_ttl,
            audit_tags={"task": "dynamic", "rotation": "auto"}
        )
        self.active_credentials.append(cred)
        return cred

    def revoke_all(self):
        for cred in self.active_credentials:
            secrets_manager.revoke(cred.id)
        registry.deprovision(self.id)
        self.active_credentials.clear()

    def health_check(self):
        # Verify all active credentials are still valid
        return all(secrets_manager.is_valid(c.id) for c in self.active_credentials)
```

## Receipt

> Verified 2026-08-04 — Researched against: CSA/Strata Identity survey (2026), GitGuardian State of Secrets Sprawl 2026, OpenID Identity Management for Agentic AI whitepaper (Oct 2025), Red Hat MCP Security blog (Mar 2026), WorkOS AI Agent Secrets Management guide (Jun 2026), Zylos Research NHI governance brief (Jul 2026). Pattern validated against existing handbook coverage (S-695 covers MCP ambient authority; this entry covers NHI lifecycle governance — complementary, non-overlapping). Code example is structural pseudocode demonstrating the pattern; not runnable against a live system.

## See also

- [S-695 · MCP Is Winning — But the Security Model Is Not](s695-mcp-is-winning-but-the-security-model-is-not-ready.md) — ambient authority in MCP; this entry's credentials are how you close that gap
- [S-1000 · Structural Agent Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — policy enforcement at the structural layer; NHI lifecycle is the identity substrate for that enforcement
- [S-997 · The Agent Observability Stack](s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — audit trails at the credential layer feed the observability stack; trace your agent's decisions back to which credential enabled them
