# S-2052 · The NHI Governance Stack — When Your Agent Holds Credentials That Outnumber Your Employees 82-to-1

Your agent can read your CRM, write to your database, and email your customers. It does all three with credentials provisioned by a developer who set them up during the pilot and forgot about them six months ago. Those credentials have never rotated. They have admin scope. They live in an MCP config file that got committed to a repo — which GitGuardian found last Tuesday. Meanwhile, your identity team manages 47 human employees and 3,864 non-human identities. This is the NHI governance crisis: agents hold credentials at a scale and autonomy that traditional IAM was never designed to handle.

## Forces

- **Agents proliferate credentials faster than any process can track.** A single agent with 6 tools needs 6 credential sets. A fleet of 50 agents connecting to 8 external systems creates 400 credential pairs. Humans get hire and termination events that trigger provisioning and deprovisioning. Agents get deployed, modified, and abandoned with no equivalent lifecycle signal.
- **Runtime credential access is invisible to traditional IAM.** When an agent reads an API key from an environment variable at runtime, your identity provider doesn't see a login event. There's no MFA challenge, no session token, no "last authenticated" log — just a running process that happens to hold a secret. Your SIEM sees the API call, not the credential that made it.
- **Over-privileged by default, under-governed by habit.** Every NHI survey since 2024 finds the same pattern: 95%+ of service credentials carry more scope than the workload needs. Agents amplify this because the fastest way to get an agent working is to give it broad access, and "working" is easier to measure than "least-privilege."
- **Credential sprawl is compounding.** GitGuardian's 2026 report found 28.65 million secrets committed to public GitHub in 2025 (+34% YoY). AI-service credential leaks surged 81%. Claude Code co-authored commits leak secrets at 3.2% — double the human-only baseline of 1.5%. Agents create secrets faster than governance can keep up.

## The move

NHI governance for AI agents is a five-phase lifecycle. Each phase has the same structure as human IAM but operates at higher velocity and with fundamentally different failure modes.

### Phase 1 — Provisioning: Request Before Access

Every credential an agent needs goes through an approval workflow that specifies: which agent, which tool, which resource, which scope, and which duration.

```python
# Credential request with scope declaration
class AgentCredentialRequest:
    agent_id: str          # "support-agent-prod-v3"
    tool_name: str         # "salesforce_read"
    resource_arn: str      # "arn:aws:iam::123456:role/crm-read-only"
    requested_scope: list[str]  # ["read:contacts", "read:opportunities"]
    duration_hours: int    # 720  # 30-day max, then mandatory rotation
    justification: str     # "Read customer records to personalize email drafts"
    risk_level: str        # "low" | "medium" | "high"

    # Automatic scope reduction
    def approved_scope(self) -> list[str]:
        if "admin" in self.requested_scope:
            raise OverprivilegedError(
                f"Agent {self.agent_id} requested admin scope for {self.tool_name}. "
                f"Request was auto-rejected. Refile with minimum required permissions."
            )
        return self.requested_scope
```

The key NHI-specific rule: **credential scope must be narrower than the agent's full capability surface.** An agent that can read 10 CRM object types should not hold credentials scoped to all 10 — only the ones the active task requires.

### Phase 2 — Rotation: Continuous, Not Periodic

Traditional rotation is annual. Agent rotation must be continuous because agents change faster and leave more invisible blast radius.

```python
from datetime import datetime, timedelta

class AgentCredential:
    def __init__(self, request: AgentCredentialRequest):
        self.credential_id = generate_credential_id()
        self.created_at = datetime.utcnow()
        self.max_age = timedelta(hours=request.duration_hours)
        self.last_rotated = self.created_at
        self.status = "active"
        self.usage_count = 0

    @property
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.created_at + self.max_age

    @property
    def rotation_due(self) -> bool:
        # Rotate if: expired OR >90 days old OR agent version changed
        age_days = (datetime.utcnow() - self.last_rotated).days
        return self.is_expired or age_days > 90 or self._agent_version_changed()

    def rotate(self) -> None:
        self.last_rotated = datetime.utcnow()
        self.status = "rotating"
        new_credential = provision_fresh_credential(self)
        update_secret_store(self.credential_id, new_credential)
        self.status = "active"
```

Just-in-time (JIT) credentials are the endgame: issue a short-lived token per task, auto-revoke when the task completes. This eliminates the "long-lived secret that lives forever in an env var" failure mode entirely.

### Phase 3 — Runtime Monitoring: Behavioral Baselines

A credential that was issued for CRM read access and is suddenly making 4,000 API calls per minute is not behaving correctly. Monitor for:

- **Volume anomaly**: Calls/min vs. the 30-day baseline for this agent-tool pair
- **Scope drift**: Using a CRM-read credential to access an API endpoint the credential was never issued for
- **Temporal anomaly**: Activity at 3 AM from an agent that only runs during business hours
- **Export anomaly**: Credential suddenly downloading data volumes inconsistent with its task

```python
@dataclass
class CredentialUsage:
    credential_id: str
    agent_id: str
    tool: str
    calls_last_hour: int
    unique_endpoints: list[str]
    data_exfiltrated_mb: float
    timestamp: datetime

def evaluate_credential_health(usage: CredentialUsage, baseline: dict) -> list[Alert]:
    alerts = []
    volume_pct = usage.calls_last_hour / baseline.get("calls_per_hour_p95", 1)
    if volume_pct > 5.0:
        alerts.append(Alert(
            severity="critical",
            message=f"Credential {usage.credential_id} making {volume_pct:.0f}x baseline calls"
        ))
    if usage.data_exfiltrated_mb > baseline.get("data_export_p95_mb", 10) * 3:
        alerts.append(Alert(
            severity="critical",
            message=f"Credential {usage.credential_id} exporting {usage.data_exfiltrated_mb:.1f}MB — possible exfiltration"
        ))
    return alerts
```

### Phase 4 — Offboarding: Revocation as a First-Class Event

Agent decommissioning is not "stop the process." It's: revoke all credentials, terminate active sessions, rotate any credentials the agent may have shared with a successor instance, and update the NHI registry to `decommissioned`.

```python
async def offboard_agent(agent_id: str) -> OffboardingReport:
    # 1. Revoke all credentials
    credentials = await nhi_registry.list_credentials_for_agent(agent_id)
    for cred in credentials:
        await secret_manager.revoke(cred.credential_id)
        await secret_manager.rotate_shared_credentials(cred.credential_id)

    # 2. Terminate active sessions
    await session_registry.terminate_agent_sessions(agent_id)

    # 3. Update registry
    await nhi_registry.update_status(agent_id, "decommissioned")

    # 4. Log for compliance
    await audit_log.record(OffboardingEvent(
        agent_id=agent_id,
        credentials_revoked=len(credentials),
        timestamp=datetime.utcnow(),
        reason="agent_decommissioned"
    ))

    return OffboardingReport(agent_id, len(credentials), "complete")
```

### Phase 5 — NHI Registry: Your Source of Truth

Every credential every agent holds must be in a registry that security and compliance can query. The registry is the difference between "we think we know what credentials exist" and "we know."

```yaml
# nhi-registry.yaml — the operational source of truth
agents:
  - id: "support-agent-prod-v3"
    owner: "support-team"
    risk_level: "medium"
    credentials:
      - id: "cred_sf_read_2026_07"
        resource: "salesforce"
        scope: ["read:contacts", "read:opportunities"]
        issued: "2026-07-15"
        expires: "2026-10-15"
        rotated_last: "2026-07-15"
        status: "active"
        last_used: "2026-08-02T14:23:11Z"
      - id: "cred_email_send_2026_08"
        resource: "sendgrid"
        scope: ["send:transactional"]
        issued: "2026-08-01"
        expires: "2026-08-08"  # JIT: 7-day max
        rotated_last: "2026-08-01"
        status: "active"
        last_used: "2026-08-02T14:23:45Z"
    compliance:
      last_reviewed: "2026-08-01"
      next_review: "2026-11-01"
      approved_by: "security-team@company.com"
```

### The Non-Negotiable Controls

If you do nothing else, implement these three — they address 90% of real-world NHI incidents:

1. **Credential registry**: You cannot govern what you cannot see. Inventory every credential every agent holds. Update on every deployment, rotation, and decommission.
2. **Just-in-time over long-lived**: Replace standing credentials with per-task tokens wherever the workflow allows. A 1-hour token that expires automatically beats a permanent API key even if neither gets rotated.
3. **Credential hygiene in CI/CD**: Run `git secrets`, TruffleHog, or Gitleaks on every commit. Claude Code's 3.2% leak rate means every agent-assisted commit is a potential credential spill — your pipeline is the last line of defense.

## Cross-links

- [S-1083 · The Platform Credential Boundary](s1083-the-platform-credential-boundary-when-your-agent-has-a-secret-second-identity-on-the-cloud-platform.md) — platform-attached service identities that sit outside MCP scoping
- [S-1062 · The MCP Supply Chain Integrity Stack](s1062-the-mcp-supply-chain-integrity-stack-when-40-cves-and-9-of-11-marketplaces-compromised-became-a-structural-problem.md) — MCP marketplace poisoning as a credential supply chain vector
- [S-2046 · The Infra Blast-Radius Stack](s2046-the-infra-blast-radius-stack-when-your-ai-agent-deleted-your-production-database-in-9-seconds.md) — OWASP ASI03: identity and privilege abuse as the mechanism behind destructive agent actions
