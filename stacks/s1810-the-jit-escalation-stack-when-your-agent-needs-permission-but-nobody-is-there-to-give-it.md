# S-1810 · The JIT Escalation Stack — When Your Agent Needs Permission but Nobody Is There to Give It

Your agent encounters a high-impact action: delete 200 customer records, export sensitive data, or modify a payment workflow. Your policy requires human approval. Your agent has been running for six hours across 3,400 steps. Nobody is watching. The agent waits for an approval email that will arrive in 45 minutes — and by then the context window has rotated, the session state is gone, and the task has already timed out.

The human-in-the-loop (HITL) pattern assumes a human in the loop. Agents break that assumption by design. You need a Just-In-Time escalation architecture that works at machine speed.

## Forces

- **Agents act at millisecond cadence, humans respond at human speed.** A traditional approval workflow assumes someone checks Slack, reads the request, and clicks approve. An agent making 500 tool calls per minute cannot pause for a 45-minute approval cycle. HITL for agents requires pre-authorization, not synchronous consent.
- **Pre-authorizing everything is not security — it is theater.** Granting broad permissions "just in case" eliminates the control without eliminating the risk. The agent still has blast radius; you just removed the safety valve.
- **Escalation without a fallback chain is a single point of failure.** If human approval is the only escalation path and nobody approves, the agent either loops waiting or gives up. Neither is acceptable for a production workflow.
- **Escalation telemetry is often missing from the audit log.** When agents do get approval, the audit trail often doesn't capture the chain of reasoning that led to the escalation, making compliance reviews impossible.
- **Scope creep compounds silently.** An agent granted broad permissions early in a project accumulates scope as the project grows. By the time anyone audits it, the agent has access it no longer needs.

## The move

The JIT escalation stack replaces synchronous human approval with a pre-authorized escalation hierarchy: define escalation contracts at deploy time, not at runtime. The agent knows what it can do, what triggers escalation, and what the fallback chain looks like — before the session starts.

### Tiered blast-radius escalation

Scope each escalation tier with a bounded blast radius. Escalation is not "do anything" — it is "do this class of things within these limits."

```python
# escalation_policy.py
from dataclasses import dataclass, field
from typing import Callable
from enum import Enum
import time

class EscalationTier(Enum):
    SELF = "self"           # Agent operates within pre-authorized scope
    ELEVATED = "elevated"  # Tier-1 escalation (automated review)
    CRITICAL = "critical"  # Tier-2 escalation (human or hard break)
    BLOCKED = "blocked"    # Always denied, even if requested

@dataclass
class BlastRadius:
    request_rate: int | None = None        # Max calls/minute
    record_count: int | None = None         # Max records per operation
    dollar_impact: float | None = None      # Max financial exposure
    data_class: list[str] | None = None     # Allowed data sensitivity labels
    action_types: list[str] | None = None   # Allowed action verbs
    tenant_scope: list[str] | None = None   # Resource boundary
    ttl_seconds: int | None = None          # Authorization lifetime

@dataclass
class EscalationPath:
    tier: EscalationTier
    blast_radius: BlastRadius
    approval_mechanism: str                  # "automated_review" | "human_sync" | "hard_deny"
    fallback_tier: EscalationTier | None     # What to do if this tier times out
    timeout_seconds: int = 300

# Example: email agent escalation policy
EMAIL_POLICY = {
    "read_email": EscalationPath(
        tier=EscalationTier.SELF,
        blast_radius=BlastRadius(
            action_types=["read", "search", "list"],
            data_class=["internal", "public"],
            tenant_scope=["own-tenant"],
            ttl_seconds=3600,
        ),
        approval_mechanism="automated_review",
        fallback_tier=None,
    ),
    "send_email": EscalationPath(
        tier=EscalationTier.SELF,
        blast_radius=BlastRadius(
            action_types=["send"],
            record_count=50,
            data_class=["internal", "public"],
            tenant_scope=["own-tenant"],
            ttl_seconds=1800,
        ),
        approval_mechanism="automated_review",
        fallback_tier=EscalationTier.CRITICAL,
    ),
    "delete_records": EscalationPath(
        tier=EscalationTier.CRITICAL,
        blast_radius=BlastRadius(
            action_types=["delete"],
            record_count=5,
            data_class=["internal"],
            tenant_scope=["own-tenant"],
            dollar_impact=0,           # Non-negotiable: no financial exposure
            ttl_seconds=600,
        ),
        approval_mechanism="human_sync",
        fallback_tier=EscalationTier.BLOCKED,
        timeout_seconds=600,
    ),
    "export_pii": EscalationPath(
        tier=EscalationTier.BLOCKED,
        blast_radius=BlastRadius(),
        approval_mechanism="hard_deny",
        fallback_tier=None,
    ),
}
```

### Agent-side escalation check

```python
class JITAgent:
    def __init__(self, escalation_policy: dict, agent_capabilities: dict):
        self.policy = escalation_policy
        self.capabilities = agent_capabilities  # What this agent is allowed to do
        self.active_tiers: dict[str, EscalationTier] = {}
        self._initialize_tiers()

    def _initialize_tiers(self):
        """Pre-authorize tiers at session start based on deployment config."""
        for action, path in self.policy.items():
            if path.tier == EscalationTier.SELF:
                self.active_tiers[action] = EscalationTier.SELF

    def check_escalation(self, action: str, params: dict) -> tuple[bool, str, BlastRadius]:
        """
        Returns (approved, escalation_type, blast_radius).
        Raises if action is BLOCKED.
        """
        if action not in self.policy:
            # Unscoped action: deny by default
            return False, "unscoped_action", BlastRadius()

        path = self.policy[action]

        if path.tier == EscalationTier.BLOCKED:
            raise PermissionError(f"Action '{action}' is hard-blocked by policy")

        if path.tier == EscalationTier.SELF:
            # Self-authorized within blast radius
            return self._check_blast_radius(action, path.blast_radius, params)

        # Elevated or Critical: attempt escalation
        approved, radius = self._attempt_escalation(action, path, params)
        return approved, str(path.tier.value), radius

    def _attempt_escalation(
        self, action: str, path: EscalationPath, params: dict
    ) -> tuple[bool, BlastRadius]:
        """Attempt escalation through the configured approval mechanism."""
        blast = self._merge_blast_radius(path.blast_radius, params)

        if path.approval_mechanism == "automated_review":
            # Automated review: LLM-as-judge or rule engine
            approved = self._automated_review(action, blast, params)
            if approved:
                self.active_tiers[action] = path.tier
                return True, blast
            # Fall through to fallback

        elif path.approval_mechanism == "human_sync":
            # Synchronous human approval (real-time channel, e.g. Slack PagerDuty)
            approved, timeout = self._sync_human_approval(action, blast, params)
            if approved:
                self.active_tiers[action] = path.tier
                return True, blast

        # Fallback chain
        if path.fallback_tier and path.fallback_tier != EscalationTier.BLOCKED:
            fallback_path = self._get_path_for_tier(path.fallback_tier, action)
            return self._attempt_escalation(action, fallback_path, params)
        elif path.fallback_tier == EscalationTier.BLOCKED:
            raise PermissionError(
                f"Action '{action}' escalated to BLOCKED tier via fallback chain"
            )

        return False, BlastRadius()

    def _automated_review(self, action: str, blast: BlastRadius, params: dict) -> bool:
        """LLM-as-judge or rule-based review for automated escalation."""
        review_prompt = (
            f"Review this agent action for policy compliance:\n"
            f"Action: {action}\nParams: {params}\n"
            f"Blast radius: {blast}\n"
            f"Context: {params.get('task_context', 'N/A')}"
        )
        # Rule-based guard: hard limits always checked first
        if blast.record_count and params.get("record_count", 0) > blast.record_count:
            return False
        if blast.dollar_impact == 0 and params.get("has_financial_impact"):
            return False
        # LLM review for soft policy judgment
        return self._llm_judge(review_prompt)

    def _sync_human_approval(self, action, blast, params) -> tuple[bool, int]:
        """Send to Slack/Teams PagerDuty, wait for response within timeout."""
        # Pseudocode: real implementation calls notification service
        alert = {
            "action": action,
            "blast_radius": blast,
            "params": params,
            "timeout": self.policy[action].timeout_seconds,
            "escalation_id": f"esc-{int(time.time())}-{action}",
        }
        response = self.notification_service.send_approval_request(alert)
        return response["approved"], response.get("latency_ms", 0)

    def execute_action(self, action: str, params: dict):
        approved, escalation_type, blast = self.check_escalation(action, params)

        if not approved:
            # Escalation failed: trigger fallback chain result
            return {
                "status": "denied",
                "escalation_type": escalation_type,
                "fallback_action": "return_partial_result",
                "audit_id": self._log_denial(action, params, escalation_type),
            }

        return {
            "status": "approved",
            "blast_radius": blast,
            "escalation_type": escalation_type,
            "audit_id": self._log_approval(action, params, escalation_type, blast),
        }
```

## Receipt

> Receipt pending — 2026-07-29. Code is structural pseudocode demonstrating the escalation contract pattern. Real implementations vary by framework (Prefactor, Microsoft Copilot Studio, AWS Bedrock Guardrails all expose different surfaces for escalation configuration). Core insight verified against Microsoft Security Blog (July 16, 2026) "Least privilege for AI agents" — the three-layer model (scoped credentials, pre-tool hooks, blast-radius constraints) maps directly to the tiered escalation stack described here.

## See also

- [S-842 · The Over-Permissioned Agent Stack](s842-the-over-permissioned-agent-stack-when-legitimate-credentials-do-illegitimate-work.md) — Scoped credential design is the foundation this builds on
- [S-1453 · The Excessive Agency Stack](s1453-the-excessive-agency-stack-when-your-agent-has-permission-but-no-proportion.md) — Blast-radius analysis for identifying overpermission
- [F-200 · The Permission Guard Stack](forward-deployed/f200-the-permission-guard-stack-when-your-agent-does-exactly-what-it-was-designed-to-do-and-wreaks-havoc.md) — Runtime enforcement hooks for permission boundaries
- [S-1809 · The Recovery Escalation Stack](s1809-the-recovery-escalation-stack-when-your-agent-errors-and-has-no-idea-what-to-do-next.md) — Escalation hierarchy for error recovery (adjacent stack)
