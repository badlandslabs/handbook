# S-2721 · The Guardrail Composition Problem — When Your Seven Safety Layers Contradict Each Other

You deployed seven guardrails. An input filter, a policy layer, a permission gate, a HITL checkpoint, an output validator, an audit logger, and a kill switch. They each work in isolation. Together, they produce outcomes nobody designed: a denied-but-continues error, a silently bypassed policy, a log entry for an action that never executed, or a kill switch that fires after the damage. This is the guardrail composition problem — the hardest part of agent safety is not any single layer, it is what happens at the seams.

## Forces

- **Guardrails are designed individually, deployed collectively.** Each layer was validated in isolation. Nobody tested the 2×7 interaction matrix. The failure modes at layer boundaries are combinatorial and rarely surface until production.
- **Failure posture is not uniform across layers.** Your input filter fails closed (block on error), your policy layer fails open (allow on timeout), and your kill switch fails silently (logs but doesn't halt). When the kill switch fires on an action your input filter was supposed to block, the logs show a successful action followed by a kill — after the side effect already occurred.
- **The LLM-dependent layers are the weakest links.** Input validation and policy enforcement that rely on the same model being evaluated are defeated by the same prompt manipulation that targets the agent itself. An attacker who evades the agent can often evade the guardrail using the same technique.
- **Layer count compounds latency and cost.** Each guardrail check adds latency and token overhead. Seven synchronous layers on every tool call can add 30-50% to per-step cost. Teams strip layers under latency pressure, then discover the removed layer was the only thing blocking a specific failure mode.

## The move

The solution is **explicit composition architecture**: define the interaction contract between layers, enforce a consistent failure posture, and instrument the seams.

### 1. Define a Layer Interaction Contract

Each guardrail produces one of four outcomes: `ALLOW`, `DENY`, `BLOCK_AND_RETRY`, or `ESCALATE`. Every layer must emit one of these. No layer returns "allow with a warning" or "deny but continue" — those ambiguous states are where incidents live.

```python
from enum import Enum
from typing import Protocol
from dataclasses import dataclass

class GuardrailOutcome(Enum):
    ALLOW = "allow"
    DENY = "deny"
    BLOCK_AND_RETRY = "block_retry"
    ESCALATE = "escalate"

@dataclass
class GuardrailResult:
    outcome: GuardrailOutcome
    reason: str
    layer: str
    audit_id: str  # correlates across layers

class Guardrail(Protocol):
    def check(self, action: Action, ctx: AgentContext) -> GuardrailResult: ...

# Composed evaluator enforces uniform contract
class LayeredGuardrail:
    def __init__(self, layers: list[Guardrail]):
        self.layers = layers

    def evaluate(self, action: Action, ctx: AgentContext) -> GuardrailResult:
        results = []
        for layer in self.layers:
            result = layer.check(action, ctx)
            results.append(result)
            if result.outcome == GuardrailOutcome.ESCALATE:
                return result  # human review — stop evaluation
            if result.outcome == GuardrailOutcome.DENY:
                return result  # fail fast on deny

        # All ALLOW or BLOCK_AND_RETRY
        # BLOCK_AND_RETRY → agent replans, re-submits
        # Aggregate BLOCK_AND_RETRY count; after 3, escalate
        retry_count = sum(
            1 for r in results if r.outcome == GuardrailOutcome.BLOCK_AND_RETRY
        )
        if retry_count >= 3:
            return GuardrailResult(
                outcome=GuardrailOutcome.ESCALATE,
                reason=f"3 layers requested retry — possible evasion pattern",
                layer="composition",
                audit_id=results[0].audit_id,
            )
        return results[-1]
```

### 2. Set Consistent Failure Posture

Define one posture for all layers: **fail closed** (block on error) or **fail open** (allow on error). LLM-dependent layers (input rail, judge) must fail closed — they are the layers an attacker would target first. Infrastructure layers (kill switch, audit logger) fail closed by definition — they cannot fail open.

```
Layer → Default Posture → Error Posture
─────────────────────────────────────────
Input filter     → ALLOW → DENY (fail closed)
Policy engine    → ALLOW → DENY (fail closed)
Permission gate  → DENY  → DENY (always fail closed)
HITL checkpoint → ALLOW → ESCALATE (never fail open)
Output validator → ALLOW → ESCALATE (never fail open)
Audit logger     → LOG   → LOG+ALERT (never block on error)
Kill switch      → PASS  → HARD_KILL (cannot be bypassed)
```

The kill switch gets special treatment: it operates out-of-band, cannot be overridden by the agent or any other layer, and fires on both explicit trigger conditions and correlation-pattern anomalies (e.g., three DENY→ALLOW transitions in 60 seconds).

### 3. Instrument the Seams

Every guardrail handoff generates a structured event with a shared `audit_id`. The events are correlated in a guardrail trace — not a span, a separate correlation tree — so you can answer: "Which layer detected the anomaly? Which layers processed the same action? In what order? With what outcome?"

```python
# Each layer emits a structured event to the guardrail trace
async def evaluate_guarded(self, action: Action, ctx: AgentContext) -> Action | None:
    audit_id = str(uuid4())
    trace = GuardrailTrace(audit_id=audit_id, action=action.snapshot())

    for layer in self.layers:
        result = await layer.check(action, ctx)
        trace.add_event(layer.name, result)

        if result.outcome == GuardrailOutcome.DENY:
            ctx.metrics.increment("guardrail.deny", labels={"layer": layer.name})
            return None  # action blocked
        if result.outcome == GuardrailOutcome.ESCALATE:
            ctx.metrics.increment("guardrail.escalate", labels={"layer": layer.name})
            await ctx.human_review_queue.enqueue(action, audit_id)
            return None

    trace.finalize(outcome="allow")
    ctx.metrics.increment("guardrail.allow")
    return action
```

A silent incident signature: when the audit log shows a DENY followed by an ALLOW for the same action_id with no intervening retry. This means a layer blocked, the agent resubmitted without retry logic, and a downstream layer allowed it. The audit trail is the only way to catch this.

### 4. Trim the Layer Count

Seven layers on every action is not a feature — it is a liability. Audit every layer with two questions:

1. **What does this layer catch that no other layer catches?** If the answer is "nothing," merge or remove it.
2. **What is the latency and token cost of this layer?** If >15ms + >500 tokens with no unique coverage, route it to async/background evaluation.

Typical elimination candidates: redundant input/output filters (merge into policy engine), a second audit logger on top of the first, and policy layers that duplicate the permission gate's output.

## Cross-links

- [S-1000 · Structural Agent Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — the typed governance-to-agent wire; this entry's composition model builds on that foundation
- [S-375 · Agentic Prompt Injection: Defense-in-Depth](s375-agentic-prompt-injection-defense-in-depth-for-production.md) — the LLM-dependent layers (input rail, judge) in this entry inherit those vulnerabilities
- [S-1032 · Dead Letter Stack](s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — the escalation queue in this entry connects to the DLQ pattern
- [S-1054 · Agent Interrupt Stack](s1054-the-agent-interrupt-stack-when-your-agent-is-going-off-rails-and-you-cant-stop-it-cleanly.md) — the kill switch in this entry is the infrastructure-layer shutdown referenced there
- [S-1069 · Threat-Model-Driven Sandbox](s1069-the-threat-model-driven-sandbox-stack-when-subprocess-is-not-enough.md) — sandbox decisions define what the permission gate should allow; these must be co-designed, not layered on after

## Receipt

Receipt pending — 2026-08-16. Aurora (Arvo AI, July 2026) published the canonical 7-layer model. CSA/Pillar Security (July 2026) documented the "kill switch fires after the damage" pattern in sandbox escape analysis. Gartner (2026) projects 40%+ of agentic AI projects cancelled by 2027, with inadequate guardrail composition as a primary contributor.
