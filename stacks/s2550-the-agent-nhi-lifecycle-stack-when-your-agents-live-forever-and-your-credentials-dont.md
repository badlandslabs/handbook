# S-2550 · The Agent NHI Lifecycle Stack — When Your Agents Live Forever and Your Credentials Don't

An AI agent needs access to enterprise systems — email, CRM, databases, internal APIs. You give it a service account. The service account has the same access it had three engineers and two org restructures ago. The agent's task changed. The credential didn't. The credential now has access the agent no longer needs, and nobody knows it's there. Meanwhile, the agent that was decommissioned six months ago still holds a valid OAuth token. This is the NHI (Non-Human Identity) lifecycle crisis: the gap between how enterprises manage human identities and how they manage agent identities — a gap that widens with every deployment.

## Forces

- **Agents are permanent. Credentials are ephemeral.** Human identities follow a joiner/mover/leaver lifecycle enforced by HR systems. AI agents are created ad-hoc, never linked to a departure event, and their credentials outlive the agent's useful life. An agent spun up for a 2-week data migration still has a valid API key 18 months later.
- **The provisioning event is not the security event.** The moment an agent is provisioned with a credential, it becomes a persistent, unattended principal. Unlike a human who re-authenticates daily, an agent's credential is a static key that works indefinitely unless manually revoked. Every credential issued to an agent is a standing privilege until someone actively retires it.
- **Agent decommissioning is an afterthought — if it exists at all.** Human offboarding is a process with deadlines and sign-offs. Agent offboarding is an asterisk. When a project ends, the agent's credentials are rarely tracked, audited, or revoked. Shadow NHI compounds: old agents accumulate in systems, and nobody knows which credentials are live versus ghosted.
- **Credential rotation breaks running agents.** Revoking and rotating a static API key or OAuth token takes down any agent using it. Unlike human SSO, which re-prompts transparently, credential rotation for agents requires code changes, deployment cycles, and testing. This creates a structural incentive to never rotate — and to over-provision scope to avoid the next rotation event.
- **Discovery is harder than for human identities.** NHIs leave different traces: MCP client connections, API keys in secret managers, OAuth app registrations, service account grants. There is no unified "NHI inventory" in most identity providers, and agents don't appear in org charts.

## The move

### 1. Treat agent provisioning as an identity event, not a deployment event

Every agent that accesses enterprise resources needs a named identity registered in your identity provider — not just a shared API key. Use platform-native solutions:

- **Microsoft Entra ID** (GA April 2026): each agent gets an object/app ID; authenticate via Federated Identity Credentials, no passwords
- **Google Workspace**: Workload Identity Federation for GCP-bound agents
- **Generic**: OAuth 2.0 client credentials with scoped grants, issued per-agent not per-deployment

The credential is bound to the agent identity, not to the agent's code or infra.

```python
# Provision an agent identity via Microsoft Graph API
import requests

TENANT_ID = "your-tenant-id"
CLIENT_ID = "your-app-id"
CLIENT_SECRET = "your-client-secret"

# 1. Register the agent as an app in Entra ID
app_payload = {
    "displayName": "crm-data-migration-agent",
    "signInAudience": "AzureADMyOrg",
    "requiredResourceAccess": [
        {
            "resourceAppId": "00000003-0000-0000-c000-000000000000",  # Graph API
            "resourceAccess": [
                {"id": "e1fe6dd8-ba31-4d61-89e7-8661c21aae34", "type": "Scope"}  # User.Read
            ]
        }
    ],
    "optionalClaims": {
        "accessToken": [{"name": "idp", "essential": True}]
    }
}

token_resp = requests.post(
    f"https://login.microsoftonline.com/{TENANT_ID}/oauth2/v2.0/token",
    data={
        "grant_type": "client_credentials",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "https://graph.microsoft.com/.default"
    }
)
graph_token = token_resp.json()["access_token"]

app_resp = requests.post(
    "https://graph.microsoft.com/v1.0/applications",
    headers={"Authorization": f"Bearer {graph_token}"},
    json=app_payload
)
agent_app = app_resp.json()
agent_id = agent_app["id"]
print(f"Agent NHI registered: {agent_id}")
```

### 2. Enforce a bounded, time-scoped credential lifecycle

Never issue indefinite credentials. Every agent credential gets:

- **Max lifetime**: 24h–7d for long-running agents (renewable via rotation)
- **Purpose-tagged scope**: least-privilege to the specific resource action, not the service account default
- **Expiration bound to project end date**: stored as metadata in the identity registry

```python
from datetime import datetime, timedelta
from typing import Protocol

class NHIProvisioner(Protocol):
    def provision(self, agent_id: str, scopes: list[str], ttl_days: int) -> str: ...
    def revoke(self, agent_id: str) -> None: ...
    def rotate(self, agent_id: str) -> str: ...

class BoundedNHIProvisioner:
    def provision(self, agent_id: str, scopes: list[str], ttl_days: int) -> str:
        # Issue a scoped, time-bounded credential
        issued_at = datetime.utcnow()
        expires_at = issued_at + timedelta(days=ttl_days)
        credential = self._issue_oauth_credential(
            client_id=agent_id,
            scopes=scopes,
            issued_at=issued_at,
            expires_at=expires_at,
        )
        # Register in NHI inventory for tracking
        self._inventory.add(
            nhi_id=agent_id,
            credential_id=credential["id"],
            issued_at=issued_at,
            expires_at=expires_at,
            project_end_date=self._get_project_end(agent_id),
            status="active",
        )
        print(f"[NHI] Provisioned {agent_id} — expires {expires_at.date()}")
        return credential["access_token"]

    def revoke(self, agent_id: str) -> None:
        creds = self._inventory.list_active(agent_id)
        for cred in creds:
            self._revoke_oauth_credential(cred["id"])
            self._inventory.update(cred["id"], status="revoked")
            print(f"[NHI] Revoked credential {cred['id']} for {agent_id}")

    def schedule_decommission(self, agent_id: str) -> None:
        """Link agent identity to project end date — trigger auto-revocation."""
        project_end = self._get_project_end(agent_id)
        self._inventory.update(agent_id, target_revoke_date=project_end)
        print(f"[NHI] {agent_id} scheduled for decommission {project_end.date()}")
```

### 3. Auto-discover and audit your NHI inventory

Most organizations don't know how many NHIs they have. Run continuous discovery:

```python
import subprocess

def discover_mcp_connections() -> list[dict]:
    """Enumerate active MCP client connections as NHI surface indicators."""
    result = subprocess.run(
        ["mcp", "inspect", "--format", "json"],
        capture_output=True, text=True
    )
    clients = json.loads(result.stdout)
    return [
        {"client_id": c["client_id"], "server": c["server"],
         "last_seen": c["last_activity"], "scopes": c["granted_scopes"]}
        for c in clients
    ]

def audit_nhi_inventory(provisioner: BoundedNHIProvisioner) -> list[str]:
    """Flag NHIs past project end date — candidates for revocation."""
    stale = []
    now = datetime.utcnow()
    for nhi in provisioner._inventory.list_all():
        if nhi["status"] != "active":
            continue
        if nhi.get("project_end_date") and nhi["project_end_date"] < now:
            stale.append(nhi["nhi_id"])
            print(f"[AUDIT] STALE NHI: {nhi['nhi_id']} — past project end {nhi['project_end_date'].date()}")
    return stale
```

### 4. Build revocation into the agent termination path

Agent termination must include credential revocation — not just stopping the process:

```python
# In your agent supervisor / orchestration layer
def terminate_agent(agent_id: str, provisioner: BoundedNHIProvisioner):
    # 1. Stop the agent process
    subprocess.run(["docker", "stop", f"agent-{agent_id}"])
    # 2. Revoke all credentials
    provisioner.revoke(agent_id)
    # 3. Update NHI inventory
    provisioner._inventory.update(agent_id, status="decommissioned")
    # 4. Emit lifecycle event for SIEM
    emit_audit_event("agent.decommissioned", {"agent_id": agent_id, "ts": datetime.utcnow()})
    print(f"[LIFECYCLE] Agent {agent_id} fully terminated and credentials revoked")
```

### 5. Connect NHI lifecycle to your SIEM

Every NHI event — provision, rotation, revocation, expiration — is a security signal:

| Event | Alert threshold |
|-------|----------------|
| Provision without project end date | Warning |
| Credential active past project end | **Critical** — auto-alert SOC |
| Credential never rotated in 90 days | Medium — schedule rotation |
| Revocation event from unexpected source | **Critical** — potential compromise |
| Agent still running after revocation | **Critical** — bypass attempt |

## Receipt

> Verified 2026-08-12 — Sources: Microsoft Entra Agent ID GA (April 2026, techcommunity.microsoft.com); IETF draft-klrc-aiagent-auth-00 (AI Agent Authentication/Authorization using OAuth 2.0 + WIMSE); identitychallengecard.avatier.com agentic authentication guide (June 2026); IBM/UC Berkeley MAP study (arXiv:2512.04123, 86 deployed systems, 306 practitioners). Code reflects standard OAuth 2.0 client credentials + Entra ID Graph API patterns. MCP `mcp inspect` command is illustrative — verify against your MCP server version.

## See also

- [S-1075 · The Ephemeral Delegation Stack](stacks/s1075-the-ephemeral-delegation-stack-when-your-agent-hands-its-credentials-to-a-stranger.md) — credential handing to sub-agents
- [S-1041 · The Agent Shadow IT Stack](stacks/s1041-the-agent-shadow-it-stack-when-82-percent-of-your-ai-agents-are-running-without-your-security-team-knowing.md) — discovering agents you didn't know existed
- [S-1065 · The Inter-Agent Trust Escalation Stack](stacks/s1065-the-inter-agent-trust-escalation-stack-when-your-agent-takes-instructions-from-an-agent-and-bypasses-every-security-control.md) — permission chains across agent handoffs
- [S-1458 · The Policy Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — enforcement at the infrastructure layer
