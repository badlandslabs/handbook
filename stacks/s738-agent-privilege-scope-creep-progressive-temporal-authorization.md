# S-738 · Agent Privilege Scope Creep: Progressive Temporal Authorization

Agents start with whatever permissions you grant them — then encounter situations you never planned for. A read-only research agent encounters an anomaly that warrants action. A single-task agent gets repurposed mid-session. A narrowly-scoped tool turns out to need a sibling capability. Traditional IAM stops at onboarding. Agent authorization has to run live.

## Forces

- **The capability gap**: Agents encounter unanticipated sub-tasks that require permissions nobody pre-authorized
- **The blast radius problem**: Broad permissions at startup make every future failure catastrophically worse
- **The revocation latency gap**: Permissions granted at session start stay active until explicit revocation — often never
- **The context shift problem**: An agent authorized for task A gets handed task B mid-run; nobody re-checks the permissions
- **The ambient capability illusion**: Agents appear scoped to tools in their definition, but at runtime can chain tools into higher-privilege actions nobody explicitly allowed

## The Move

Progressive Temporal Authorization (PTA): rather than granting capabilities at session start and holding them indefinitely, authorize at the moment of need with explicit time bounds, scope limits, and explicit revocation triggers.

### The Three Dimensions

**1. Time-bounded grants (temporal scoping)**
Every permission carries an explicit TTL. Not "can send emails" but "can send emails for the next 12 minutes or until this task completes, whichever comes first." The TTL resets only on explicit re-authorization, not on continued use.

```
# Authorization token with explicit bounds
grant = AuthorizationGrant(
    capability="send_email",
    scope={"recipients": ["@allowed-domains.com"], "rate": "1/min"},
    ttl=timedelta(minutes=12),
    revocation_trigger="task_complete",
    principal=agent_id,
)
```

**2. Capability chaining detection**
An agent that can read a user list AND send emails has a combined capability nobody authorized explicitly: mass email. PTA monitors capability combinations across tool calls, not just individual tool invocations. If the combination wasn't authorized as a unit, it requires escalation.

**3. Progressive disclosure gates**
Rather than granting everything upfront, authorize in layers aligned with task phases:

| Phase | Granted | Denied |
|-------|---------|--------|
| Discover | read-only search | writes, deletes, sends |
| Propose | read + draft generation | execution |
| Approve | write + send (with preview) | destructive actions |
| Execute | full scope (task-scoped) | cross-account, admin |

Each gate requires human or policy authorization. The agent sees the next gate before it needs the capability — it doesn't hit a wall mid-execution.

### Implementation Pattern

```
# Minimal PTA enforcement layer
class ProgressiveAuthZ:
    def __init__(self):
        self.active_grants: dict[str, Grant] = {}
        self.policy = load_policy("agent_authorization_policy.yaml")

    def authorize(self, agent_id: str, capability: str, context: dict) -> Grant | Denied:
        # Check if already granted and still valid
        if existing := self.active_grants.get(f"{agent_id}:{capability}"):
            if existing.is_valid():
                return existing
            return Denied("grant_expired")

        # Check if the capability combination is pre-authorized
        combo_key = self._capability_combo(agent_id)
        if self.policy.is_combo_authorized(combo_key, capability):
            grant = self._issue_grant(agent_id, capability, context)
            return grant

        # Capability not pre-authorized — escalate
        return Denied("requires_authorization").with_escalation_path(
            approver=self.policy.get_approver(capability),
            justification_template=self.policy.get_template(capability),
        )

    def revoke_all(self, agent_id: str, reason: str = "explicit"):
        for key in list(self.active_grants.keys()):
            if key.startswith(f"{agent_id}:"):
                self.active_grants[key].revoke(reason)
```

### The Revocation Hygiene Rule

Every grant must specify its revocation condition in advance — not just a TTL. Examples:
- `"revoke_on_task_complete"` — grant dies when the originating task resolves
- `"revoke_on_conversation_end"` — grant dies when the user's session closes
- `"revoke_on_capability_superseded"` — grant dies if a higher-privilege version is issued
- `"revoke_on_circuit_trip"` — grant dies if the agent hits a safety circuit breaker

Without explicit revocation conditions, grants outlive their justification. PTA makes revocation a first-class concern at authorization time, not a cleanup concern later.

## Receipt

> Verified 2026-07-07 — Pattern synthesized from T. Pan (tianpan.co, Apr 2026), Locus agent payment infrastructure docs, AWS Agentic AI Security Scoping Matrix (2026), OWASP ASI Top 10 (Dec 2025). Concrete code pattern above is illustrative; TTL + revocation trigger enforcement requires integration with an agent governance layer (see S-719: AI Control Plane).

## See also
- [S-355 · Agent Autonomy Levels](stacks/s355-agent-autonomy-levels-bounded-autonomy.md) — the autonomy level determines which PTA phase an agent starts at
- [S-719 · The AI Control Plane](stacks/s719-the-ai-control-plane-owasp-runtime-governance.md) — PTA grants flow through the policy store and evaluator chain
- [F-193 · Agent Escalation Gating](forward-deployed/f193-agent-escalation-gating.md) — escalation is the path when PTA blocks a capability
- [S-574 · Agent Per-Principal, Per-Endpoint Least Privilege](stacks/s574-agent-per-principal-per-endpoint-least-privilege-at-nhi-scale.md) — PTA is the runtime enforcement of least privilege; NHI least privilege is the static policy
