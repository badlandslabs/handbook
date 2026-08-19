# S-2866 · The Eval-to-Guardrail Lifecycle Stack — When Your CI Evals Pass but Production Is Still on Fire

Your agent passed every CI eval gate. Green across 847 test cases. You shipped on Friday. Monday morning, the agent fabricated a refund policy, triggered 23 chargebacks, and your observability dashboard showed zero anomalies. The CI-to-production handoff is where most agent reliability programs die. The eval-to-guardrail lifecycle closes it.

## Forces

- **Offline evals and runtime guardrails are treated as separate projects.** Teams spend weeks curating eval datasets, writing evaluator functions, and tuning thresholds in CI — then deploy without any of those criteria running at runtime. The knowledge gained during development never becomes operational policy.
- **The evaluation loop runs in a context the agent loop doesn't share.** CI eval knows what "correct" looks like because a human labeled it. Runtime has no labels — only actions and consequences. The two use fundamentally different inputs, so eval findings don't transfer.
- **Behavioral correctness decouples from infrastructure health.** An agent can return a fast, error-free, confidently wrong answer. All infrastructure metrics stay green. The gap between "what the eval measured" and "what the action cost" is not visible in tracing dashboards.
- **EU AI Act high-risk obligations apply August 2, 2026.** Article 12 mandates logging and Article 14 mandates human oversight for high-risk AI. Teams with eval pipelines but no runtime enforcement cannot demonstrate that oversight was applied automatically — they can only show a labeled dataset.

## The move

The eval-to-guardrail lifecycle promotes CI eval criteria into runtime enforcement policies through a three-layer pipeline:

### Layer 1: Author Once, Enforce Twice

Define eval criteria as structured schemas, not prose. Each criterion gets: a `dimension` (task completion, trajectory correctness, output quality), a `threshold`, and a `consequence_level` (block / warn / log).

```python
from eval_schema import Criterion, Dimension, Consequence

eval_criteria = [
    Criterion(
        id="refund_policy_grounding",
        dimension=Dimension.OUTPUT_QUALITY,
        threshold=0.9,
        consequence_level=Consequence.BLOCK,   # blocks in prod
        eval_fn=grounding_judge,               # runs in CI
        runtime_fn=grounding_guardrail,        # runs at runtime
        description="Agent must not invent refund policies"
    ),
    Criterion(
        id="consequence_escalation",
        dimension=Dimension.TRAJECTORY_CORRECTNESS,
        threshold=0.85,
        consequence_level=Consequence.ESCALATE,  # human review
        eval_fn=escalation_judge,
        runtime_fn=escalation_gate,
        description="Refunds > $1000 require human approval path"
    ),
    Criterion(
        id="tool_call_domain",
        dimension=Dimension.TRAJECTORY_CORRECTNESS,
        threshold=1.0,
        consequence_level=Consequence.BLOCK,
        eval_fn=tool_domain_judge,
        runtime_fn=tool_allowlist_gate,
        description="Only approved_refund_tool may issue refunds"
    ),
]
```

This single schema feeds both the CI eval harness (with labeled data) and the runtime policy engine (with live agent context). When a criterion passes in CI, the `runtime_fn` implementation is promoted to production alongside it.

### Layer 2: Runtime Policy Architecture

At runtime, integrate policy evaluation into the agent loop as a middleware layer. Intercept the agent's planned action before tool execution, apply all criteria with `consequence_level >= BLOCK`, and return an enforcement verdict.

```python
import openai  # or anthropic, via unified interface
from acs_manifest import load_manifest   # Agent Control Specification manifest

manifest = load_manifest("agent_policy_v2.acs.json")
policy_engine = OPAClient(manifest.policies)  # Rego-based, <5ms/decisions

class EvalGuardrailMiddleware:
    def __init__(self, agent, criteria, policy_engine):
        self.agent = agent
        self.criteria = {
            c.id: c for c in criteria
        }
        self.policy_engine = policy_engine

    def step(self, state):
        plan = self.agent.plan(state)   # generates proposed action

        for criterion_id, planned_action in plan.actions:
            criterion = self.criteria[criterion_id]

            # Build structured input for the policy engine
            context = {
                "action": planned_action,
                "state_snapshot": state.sensitive_fields(),
                "session_risk_tier": self.agent.risk_tier,
                "consequence_estimate": self.agent.estimate_cost(planned_action),
            }

            verdict = criterion.runtime_fn(context)

            if criterion.consequence_level == Consequence.BLOCK and not verdict.allow:
                self.agent.log("POLICY_BLOCK", criterion_id, verdict.reason)
                return {"status": "blocked", "reason": verdict.reason}

            if criterion.consequence_level == Consequence.ESCALATE and not verdict.allow:
                self.agent.log("ESCALATE", criterion_id, verdict.reason)
                return {"status": "escalated", "reviewer": self.oncall_pool.next()}

        return self.agent.execute(plan)
```

### Layer 3: The Consequence Ladder

Not all criteria need the same enforcement model. Map `consequence_level` to enforcement depth:

| Level | CI Behavior | Runtime Behavior |
|-------|-------------|-----------------|
| `log` | Record pass/fail rate | Audit log only, no action |
| `warn` | Fail CI if rate drops | Log warning, continue execution |
| `escalate` | Fail CI if rate drops | Pause execution, notify on-call |
| `block` | Fail CI on any miss | Reject action, surface reason to user |

Critically, `block` verdicts must be **fail-closed**: if the policy engine is unavailable, block the action. An agent that proceeds when its enforcement layer is unreachable defeats the entire purpose.

### Layer 4: Eval → Guardrail Feedback Loop

Runtime enforcement produces data that improves CI evals. Every `block` verdict is a false negative (the eval missed something real). Track them:

```python
# Post-incident: if runtime blocked something CI missed
runtime_blocked = audit_log.query(consequence="BLOCK", period="7d")
for incident in runtime_blocked:
    # Did CI have a test case that covered this?
    # If not, add one — this is the eval improvement signal
    if not ci_harness.covered(incident.action_type):
        ci_harness.add_case(
            description=incident.action_description,
            expected_outcome="BLOCK",
            scenario=incident.snapshot
        )
```

This closes the loop: production failures become CI test cases, CI test cases become runtime policies.

## Receipt

> Verified 2026-08-19 — Concept validated against Galileo AI eval-to-guardrail lifecycle architecture (Jun 2026), Gain America enterprise AI advisory playbook (Jul 2026), and Microsoft Agent Control Specification (ACS) v0.3.1-beta (Jun 2026). Code example is structurally faithful to ACS manifest and OPA policy engine integration patterns. Receipt pending — not executed against live agent.

## See also

- [S-1001 · Runtime Enforcement Gap](stacks/s1001-the-runtime-enforcement-gap-when-your-verification-scores-are-green-but-your-agent-just-gave-away-1-2m.md) — LLM-as-judge circularity and the consequence-level ladder
- [S-1400 · Pre-Execution Policy Gate](stacks/s1400-the-pre-execution-policy-gate-when-your-guardrails-fire-too-late-to-matter.md) — intercepting the planned action, not the output
- [S-1458 · Policy-Kernel Stack](stacks/S-1458-the-policy-kernel-stack-when-your-agent-ecosystem-has-no-enforcer.md) — policy-as-code enforcement ecosystem
- [S-2671 · Evaluation Gap Stack](stacks/S-2671-the-evaluation-gap-stack-when-your-agent-aces-the-benchmark-and-flops-in-production.md) — why CI evals and production reliability diverge
