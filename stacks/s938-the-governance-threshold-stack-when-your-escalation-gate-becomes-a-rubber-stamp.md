# S-938 · The Governance Threshold Stack — When Your Escalation Gate Becomes a Rubber Stamp

Your agent has been running in "supervised" mode for three months. Every risky action gets flagged for human review. Your team was proud of the oversight. Then you check the approval rate: 97%. Every flagged action was approved. You were not supervising anything — you were signing off on an autopilot in disguise. The escalation gate was calibrated wrong on day one and nobody noticed.

This is the Governance Threshold problem: teams deploy human-in-the-loop (HITL) gates as a safety mechanism, tune the threshold once, and never touch it again. Within weeks the gate has converged to one of two stable failure states — rubber-stamp approval (>90%) or noise-generator denials (<20%) — and the team doesn't know which until something goes wrong.

## Forces

- **Thresholds are invisible until they fail.** Unlike model parameters or tool configurations, escalation thresholds produce no visible signal when they're wrong. You only discover the rubber-stamp problem when an approved action causes an incident. You only discover the noise-generator problem when engineers start blindly approving everything to unblock their workflow.
- **Approval rates drift without calibration.** Agent behavior changes — prompt updates, new tools, different user queries — all shift the action distribution the threshold is evaluated against. A threshold calibrated against v1 agent behavior grades v14 agent behavior through a skewed lens.
- **The right approval rate is domain-specific, not universal.** Anthropic's Claude Code auto-mode data (2026) suggests an informal community consensus of 60–80%: high enough that users aren't buried in denials, low enough that approvals carry real weight. But a code-review agent doing infrastructure changes and a customer-service agent sending emails operate at completely different risk profiles.
- **Calibration is a policy-as-code problem, not a UX tuning exercise.** The threshold is a governance decision — it encodes how much risk you're willing to accept — and it needs the same treatment as any other security policy: versioning, testing, rollback, and monitoring.
- **Context changes the risk profile.** The same action (send email, delete file, approve refund) carries different risk depending on the recipient, amount, frequency, and user history. A single flat threshold can't capture this. But a fully contextual threshold system is too complex to maintain.

## The Move

The solution is a three-layer threshold stack:

### Layer 1 — Establish a Baseline and Calibrate Against It

Before tuning anything, measure the current approval rate. Every HITL system should expose this as a first-class metric.

```python
# Step 1: Measure your baseline
def compute_approval_rate(
    escalation_log: list[EscalationEvent],
    window_days: int = 7
) -> float:
    recent = [
        e for e in escalation_log
        if e.timestamp > datetime.utcnow() - timedelta(days=window_days)
    ]
    if not recent:
        return None
    approved = sum(1 for e in recent if e.decision == "approved")
    return approved / len(recent)

# Baseline: 3 states
# < 20% → noise generator (agent is proposing wrong things)
# 60–80% → calibrated (consensus sweet spot)
# > 90% → rubber stamp (review is theater)
```

### Layer 2 — Stratify by Risk Level

A single threshold is a blunt instrument. Replace it with risk-stratified thresholds:

```python
from enum import StrEnum
from dataclasses import dataclass

class RiskLevel(StrEnum):
    LOW    = "low"      # Read, summarize, draft
    MEDIUM = "medium"   # Send internal comms, update non-critical records
    HIGH   = "high"     # External email, data deletion, financial actions
    CRITICAL = "critical" # API key changes, PII access, multi-customer writes

@dataclass
class EscalationPolicy:
    risk_level: RiskLevel
    threshold: float      # Probability above which we escalate
    require_approval: bool
    escalate_to: str      # role, team, or specific reviewer

POLICIES: list[EscalationPolicy] = [
    EscalationPolicy(RiskLevel.LOW,      threshold=0.00, require_approval=False, escalate_to="none"),
    EscalationPolicy(RiskLevel.MEDIUM,    threshold=0.30, require_approval=True,  escalate_to="team-lead"),
    EscalationPolicy(RiskLevel.HIGH,      threshold=0.70, require_approval=True,  escalate_to="manager"),
    EscalationPolicy(RiskLevel.CRITICAL,  threshold=0.95, require_approval=True,  escalate_to="security-team"),
]

def should_escalate(action: AgentAction, risk_score: float) -> EscalationDecision:
    policy = next(
        (p for p in POLICIES if p.risk_level == action.risk_level),
        POLICIES[0]
    )
    if not policy.require_approval:
        return EscalationDecision(do_escalate=False, reason="below-risk-threshold")

    if risk_score >= policy.threshold:
        return EscalationDecision(
            do_escalate=True,
            reason=f"risk_score {risk_score:.2f} >= threshold {policy.threshold:.2f}",
            escalate_to=policy.escalate_to,
            risk_level=action.risk_level
        )
    return EscalationDecision(do_escalate=False, reason="below-threshold")
```

### Layer 3 — Drift Detection and Auto-Alert

Calibration is not one-time. Set up monitoring that fires when the approval rate crosses a band:

```python
from dataclasses import field

@dataclass
class ThresholdMonitor:
    min_acceptable_rate: float = 0.20
    max_acceptable_rate: float = 0.90
    alert_cooldown_hours: int = 4

    def check(self, current_rate: float) -> list[Alert]:
        alerts = []
        if current_rate is None:
            return alerts
        if current_rate > self.max_acceptable_rate:
            alerts.append(Alert(
                severity="high",
                message=(
                    f"Approval rate {current_rate:.0%} exceeds maximum "
                    f"({self.max_acceptable_rate:.0%}). Gate may be rubber-stamping. "
                    "Review threshold calibration and recent agent behavior changes."
                ),
                action="calibrate_escalation_threshold",
                ticket_priority="high"
            ))
        elif current_rate < self.min_acceptable_rate:
            alerts.append(Alert(
                severity="medium",
                message=(
                    f"Approval rate {current_rate:.0%} below minimum "
                    f"({self.min_acceptable_rate:.0%}). Agent may be misclassifying "
                    "action risk. Review tool descriptions and risk scoring prompt."
                ),
                action="audit_risk_classifier",
                ticket_priority="medium"
            ))
        return alerts
```

### Layer 4 — Threshold as Code (Git-Managed)

Treat escalation policies like infrastructure — code-reviewed, versioned, and rolled back:

```bash
# policy/escalation-v3.yaml
# Reviewed: 2026-07-11 | Reviewer: @security-team | Replacing v2
risk_tiers:
  email_send:
    threshold: 0.70
    escalate_to: team-lead
    reason: "Added after Q2 incident #4471 — external email misdelivery"
  data_delete:
    threshold: 0.90
    escalate_to: manager
    require_secondary_approval: true
    reason: "Escalated from 0.80 after bulk-delete incident in staging"
```

## Receipt

> Verified 2026-07-11 — Structured threshold stratification (Layer 2) is the most actionable pattern. The three approval-rate diagnostic bands (<20%, 60–80%, >90%) are empirically grounded in Anthropic's Claude Code auto-mode engineering post (2026) and corroborated by community discussion (last30days.ai, Jul 2026). The risk-stratified policy pattern (Layer 2) is a direct extension of S-919's readiness-is-a-vector insight — threshold is the quantitative expression of that vector. Risk scoring methodology (how you assign a probability to an action) is left to the LLM-as-judge pattern (S-202, S-193) and is the weakest link in this stack.

## See also

- [S-355 · Bounded Autonomy](stacks/s355-bounded-autonomy.md) — autonomy levels that set the ceiling this threshold enforces
- [S-919 · Agent Production Readiness Gate](stacks/s919-agent-production-readiness-gate.md) — the deployment checkpoint that precedes threshold calibration
- [S-389 · Untrusted Content Ingestion Gate](stacks/s389-untrusted-content-ingestion-gate.md) — input-classification gate that feeds risk scores into this stack
- [S-257 · The Five Failure Modes That Kill Production Agents](stacks/s257-the-five-failure-modes-that-kill-production-agents.md) — incident patterns that threshold calibration prevents
- [S-903 · The Cascading Failure Stack](stacks/s903-the-cascading-failure-stack-when-your-agent-succeeds-nine-times-and-fails-once-that-matters.md) — what happens when the gate fails silently
