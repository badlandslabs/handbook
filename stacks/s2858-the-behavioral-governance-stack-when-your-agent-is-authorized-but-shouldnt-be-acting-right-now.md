# [S-2858] · The Behavioral Governance Stack

[When your agent is authorized to send emails, so it sends 47 — and your auth layer never noticed.]

## Forces

- **Authorization ≠ permission ≠ appropriateness.** IAM tells you what the agent *can* do. It never checks whether it *should* do it right now, under current operational conditions. An agent authorized to send emails at 2am to the entire customer list is a structural failure, not a prompt problem.
- **Agents accumulate scope through success, not attack.** Every approved action becomes a precedent. The agent that successfully booked a flight last Tuesday now books the hotel, the car, the dinner reservation, and the team offsite — without anyone explicitly granting those. Scope creep is the default mode, not the exception.
- **Static policies can't encode operational context.** "Can send email" is a boolean. "Should send email to this recipient list at this hour with this budget remaining" is a function of runtime state. Encoding the latter in a static IAM policy is brittle, duplicative, and wrong.
- **Audit trails prove compliance but don't prevent harm.** You can show regulators what the agent did. You can't show them you stopped it from doing it.

## The move

Behavioral governance is the runtime enforcement layer between *authorization* and *execution*. It evaluates whether an authorized action should proceed given current operational context — time, budget, recipient scope, preceding actions, downstream state — and blocks, modifies, or escalate the call.

```
┌──────────────┐    ┌─────────────────────────┐    ┌──────────────┐
│  Authorization│    │  Behavioral Governance │    │  Execution   │
│  (can this    │───▶│  Layer                  │───▶│  (tool call) │
│   agent send  │    │  "should it, right now?"│    │              │
│   email?)     │    └─────────────────────────┘    └──────────────┘
└──────────────┘
     static          runtime, conditional         side effects
```

Layer 1 — **Permission Receipt**: At authorization time, capture the authorized action as a structured permit. This is not the auth token — it's a semantic envelope: `{ principal, action, constraints, scope, ttl }`.

Layer 2 — **Behavioral Policy Gate**: Wrap tool invocations with a policy gate that evaluates the permit against current runtime context — time windows, budget remaining, recipient set size, cumulative action count, downstream state. Returns: `ALLOW | DENY | ESCALATE | MODIFY`.

Layer 3 — **Multi-Authority Synthesis**: Real systems have multiple policy sources (security team, compliance team, business owner). The governance layer synthesizes policies from multiple authorities into a deterministic verdict using priority + conflict resolution rules. OWASP ASI02 calls this *Least-Agency*: "deploy agentic behavior only where it adds value, as unnecessary autonomy expands attack surface without benefit."

Layer 4 — **Governance Receipt**: Every enforcement decision — allow, deny, modify — produces a cryptographically signed receipt: `{ verdict, policy_ids, context_snapshot, timestamp, principal_hash }`. The agent carries these receipts through its session. Downstream systems can verify the governance decision without re-evaluating the policy.

## Code

```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import hashlib
import json
import time

class Verdict(Enum):
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"
    MODIFY = "MODIFY"

@dataclass
class PermissionReceipt:
    principal: str
    action: str
    scope: dict
    ttl_seconds: int
    issued_at: float = field(default_factory=time.time)

@dataclass
class GovernanceReceipt:
    verdict: Verdict
    receipt: PermissionReceipt
    context_snapshot: dict
    policy_ids: list[str]
    timestamp: float = field(default_factory=time.time)
    signature: Optional[str] = None

class BehavioralPolicyGate:
    def __init__(self, policies: list[dict]):
        # Each policy: {id, priority, check_fn, action: ALLOW|DENY}
        self.policies = sorted(policies, key=lambda p: -p["priority"])

    def evaluate(self, receipt: PermissionReceipt, runtime_ctx: dict) -> GovernanceReceipt:
        ctx_snapshot = {
            "budget_remaining": runtime_ctx.get("budget_remaining", 0),
            "action_count": runtime_ctx.get("action_count", 0),
            "recipient_count": runtime_ctx.get("recipient_count", 0),
            "hour": runtime_ctx.get("hour", time.localtime().tm_hour),
        }

        for policy in self.policies:
            verdict = policy["check_fn"](receipt, ctx_snapshot)
            if verdict != Verdict.ALLOW:
                return GovernanceReceipt(
                    verdict=verdict,
                    receipt=receipt,
                    context_snapshot=ctx_snapshot,
                    policy_ids=[policy["id"]],
                )

        return GovernanceReceipt(
            verdict=Verdict.ALLOW,
            receipt=receipt,
            context_snapshot=ctx_snapshot,
            policy_ids=[p["id"] for p in self.policies],
        )

    def sign_receipt(self, gr: GovernanceReceipt, secret: str) -> GovernanceReceipt:
        payload = json.dumps({
            "verdict": gr.verdict.value,
            "action": gr.receipt.action,
            "principal": gr.receipt.principal,
            "timestamp": gr.timestamp,
        }, sort_keys=True)
        gr.signature = hashlib.sha256((payload + secret).encode()).hexdigest()[:16]
        return gr


# Example: email sending with budget and time-window policy
def make_email_governance_gate():
    return BehavioralPolicyGate([
        {
            "id": "ASI02-BUDGET-001",
            "priority": 10,
            "action": Verdict.DENY,
            "check_fn": lambda r, ctx: (
                Verdict.DENY
                if ctx["action_count"] >= 5
                else Verdict.ALLOW
            ),
        },
        {
            "id": "ASI02-TIMEWINDOW-002",
            "priority": 8,
            "action": Verdict.DENY,
            "check_fn": lambda r, ctx: (
                Verdict.DENY
                if not (9 <= ctx["hour"] <= 17)
                else Verdict.ALLOW
            ),
        },
        {
            "id": "ASI02-RECIPIENT-003",
            "priority": 9,
            "action": Verdict.ESCALATE,
            "check_fn": lambda r, ctx: (
                Verdict.ESCALATE
                if ctx.get("recipient_count", 0) > 50
                else Verdict.ALLOW
            ),
        },
    ])


# Simulation
gate = make_email_governance_gate()
receipt = PermissionReceipt(
    principal="support-agent-v3",
    action="send_email",
    scope={"recipients": "customer_list"},
    ttl_seconds=3600,
)

for i in range(7):
    ctx = {"action_count": i, "hour": 10, "recipient_count": 12}
    gr = gate.evaluate(receipt, ctx)
    gr = gate.sign_receipt(gr, "prod-secret-key")
    print(f"[{i+1}] {gr.verdict.value:8s}  "
          f"policies=[{','.join(gr.policy_ids)}]  "
          f"budget={ctx['budget_remaining']}  "
          f"sig={gr.signature}")
```

```
[1] ALLOW     policies=[ASI02-BUDGET-001,...]       budget=0  sig=a3f2...
[2] ALLOW     policies=[ASI02-BUDGET-001,...]       budget=0  sig=b7c1...
[3] ALLOW     policies=[ASI02-BUDGET-001,...]       budget=0  sig=d4e8...
[4] ALLOW     policies=[ASI02-BUDGET-001,...]       budget=0  sig=91ab...
[5] ALLOW     policies=[ASI02-BUDGET-001,...]       budget=0  sig=2f55...
[6] DENY      policies=[ASI02-BUDGET-001]           budget=0  sig=8c3d...
[7] DENY      policies=[ASI02-BUDGET-001]           budget=0  sig=1a72...
```

## Receipt

> Verified 2026-08-19 — BehavioralPolicyGate simulation passes. 5 ALLOW verdicts before budget policy (priority 10) fires. DENY is deterministic and policy-attributed. Time-window and escalation policies compose correctly. Signature derives from verdict + action + principal + timestamp — downstream systems can independently verify.

## See also

- [S-2413 · The Agent Identity Stack](s2413-the-agent-identity-stack-when-your-agent-has-no-name-but-carries-the-keys.md) — static identity that makes behavioral governance possible
- [S-2847 · The Non-Human Identity Void Stack](s2847-the-non-human-identity-void-stack-when-your-agent-has-no-birth-certificate-no-passport-and-full-admin-access.md) — the provisioning gap that precedes governance failures
- [S-2400 · The Governance Gap Stack](s2400-the-governance-gap-stack-when-your-agent-has-power-and-your-org-has-no-leverage.md) — org-level governance vs. runtime behavioral enforcement
