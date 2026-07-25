# S-1613 · The Multi-Agent Handoff Eval Stack — When Every Agent Passes Its Test But Your System Fails

Your five-agent pipeline scores 96% on per-agent unit tests. In production, it ships wrong answers 28% of the time. Every agent is individually excellent. The system is not. The failure lives in the handoffs — the moments when Agent A's output becomes Agent B's input — and your evaluation framework never checked those.

## Forces

- **Single-agent eval misses the failure mode that dominates production.** Standard agent evals score an agent as (input → system prompt → output). Multi-agent systems are sequences of these pairs linked by message channels. Scoring each pair independently ignores the real failure surface: what gets lost, distorted, or drifted at each handoff boundary.
- **Individual excellence compounds into collective failure.** A team where every agent scores 0.95 per turn can still ship a wrong consensus 30% of the time if each handoff drops one constraint or one piece of context per pair. Five agents × 0.95^5 ≈ 77% — not 95%.
- **Format contract violations are silent by default.** A downstream agent silently receiving the wrong schema, wrong units, or wrong null semantics does not raise an error. It processes garbage and returns plausible-looking garbage.
- **Per-handoff evaluation is non-obvious.** Engineers reach for end-to-end task completion scoring first. That misses the specific failure mode: the system got the right answer the wrong way, or the wrong answer in a way that looks right. Only per-handoff scoring surfaces where the drift entered.

## The Move

Evaluate at the handoff, not just at the task boundary. Three evaluation failure modes live specifically in handoffs, each requiring its own rubric.

### Three Handoff Failure Modes

**1. Handoff Interpretation Drift**
Agent A produces output. Agent B interprets it. The two interpretations diverge — same data, different meaning assigned. Example: A returns a list of transactions "sorted by amount." B interprets "sorted" as ascending; A meant descending. The pipeline runs without error and produces a ranked list that is internally consistent but semantically backwards for the downstream task.

**2. Role Drift**
Over the course of a long session, Agent B gradually takes on responsibilities that belong to Agent C. The handoff still fires, but the receiver has already absorbed task context that should have come from the channel, leading to premature closure or wrong scope decisions.

**3. Group Coherence Collapse**
In group chat patterns (multiple agents contributing to a shared task simultaneously), inter-agent messages diverge from the shared goal without triggering any individual failure threshold. Each agent is correct in isolation. The aggregate answer is wrong.

### Three Per-Handoff Rubrics

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import json

class HandoffFidelity(Enum):
    """Did the receiver get what the sender sent?"""
    EXACT     = "exact"     # Receiver output matches sender output semantics
    PARSIAL   = "partial"   # Core intent preserved, peripheral data dropped
    DRIFTED   = "drifted"   # Semantic mismatch between sender intent and receiver interpretation
    SILENT    = "silent"    # Schema/format changed without error, downstream silently adapted

class RoleAdherence(Enum):
    """Did the receiver act within its defined role at handoff?"""
    ON_ROLE   = "on_role"   # Task scope matches receiver's defined responsibilities
    BLEED     = "bleed"     # Receiver absorbed tasks from neighboring agent's scope
    SHIRKED   = "shirked"   # Receiver delegated its own tasks elsewhere

class GroupCoherence(Enum):
    """In group chat: did all contributions stay coherent with the shared goal?"""
    COHERENT  = "coherent"  # All agent contributions converge on the same goal
    DIVERGING = "diverging" # Agents pursuing related-but-distinct sub-goals
    LOST      = "lost"      # No shared goal state; agents are solving different problems

@dataclass
class HandoffEvalResult:
    handoff_id: str
    sender_agent: str
    receiver_agent: str
    fidelity: HandoffFidelity
    role_adherence: RoleAdherence
    group_coherence: Optional[GroupCoherence] = None
    fidelity_score: float  # 0.0–1.0
    drift_signals: list[str]  # Human-readable: "sender said ASC, receiver used DESC"

    def is_pass(self, fidelity_threshold: float = 0.85,
                 role_threshold: float = 0.90) -> bool:
        return (
            self.fidelity_score >= fidelity_threshold
            and self.fidelity != HandoffFidelity.SILENT
            and self.fidelity != HandoffFidelity.DRIFTED
            and self.role_adherence == RoleAdherence.ON_ROLE
            and (self.group_coherence is None
                 or self.group_coherence == GroupCoherence.COHERENT)
        )

# --- LLM-as-judge for semantic fidelity ---
def evaluate_handoff_semantics(sender_output: str, receiver_input: str,
                                receiver_output: str,
                                handoff_prompt: str) -> HandoffEvalResult:
    """
    Use a judge model to score the semantic fidelity of a handoff.
    The judge receives the sender's output, the handoff prompt, and the
    receiver's output — then decides what was preserved, dropped, or drifted.
    """
    judge_prompt = f"""You are evaluating the fidelity of a handoff between two agents.

SENDER OUTPUT:
{sender_output}

HANDOFF PROMPT (what the sender was told to communicate):
{handoff_prompt}

RECEIVER OUTPUT (what the receiver produced after receiving the handoff):
{receiver_output}

Evaluate:
1. SEMANTIC FIDELITY: Did the receiver's work preserve the sender's intent?
2. ROLE ADHERENCE: Did the receiver stay within its defined scope?
3. DRIFT SIGNALS: What specifically changed between send and receive?

Respond in JSON:
{{"fidelity": "exact|partial|drifted|silent",
 "role": "on_role|bleed|shirked",
 "score": 0.0-1.0,
 "drift_signals": ["signal 1", "signal 2"]}}
"""
    # In production: call your judge model here
    # response = judge_model.generate(judge_prompt)
    # result = json.loads(response)
    return HandoffEvalResult(
        handoff_id="pending",
        sender_agent="pending",
        receiver_agent="pending",
        fidelity=HandoffFidelity.EXACT,
        role_adherence=RoleAdherence.ON_ROLE,
        fidelity_score=0.95,
        drift_signals=[]
    )
```

### Production Observability: Per-Pair Span Attribution

Standard distributed tracing gives you spans per agent. Handoff evaluation needs spans per *pair*. Instrument your orchestration layer to emit a span for each (sender → receiver) relationship:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def trace_handoff(sender: str, receiver: str, task_id: str, handoff_span_name: str):
    """
    Emit a span covering the full handoff lifecycle.
    Instrument at the orchestration layer, not inside individual agents.
    """
    with tracer.start_as_current_span(
        handoff_span_name,
        attributes={
            "handoff.sender": sender,
            "handoff.receiver": receiver,
            "handoff.task_id": task_id,
            "handoff.pair": f"{sender}→{receiver}",
        }
    ) as span:
        # The span covers: sender produces → message sent → receiver receives
        # → receiver processes → receiver produces → handoff complete
        yield span  # Caller runs the handoff inside the span context
        # After yield: record the handoff eval result on the span
        result = evaluate_handoff_semantics(...)
        span.set_attribute("handoff.fidelity", result.fidelity.value)
        span.set_attribute("handoff.fidelity_score", result.fidelity_score)
        span.set_attribute("handoff.role_adherence", result.role_adherence.value)
        if result.drift_signals:
            span.add_event("handoff.drift_detected", {
                "signals": "; ".join(result.drift_signals)
            })
```

### The Production Loop

1. **Trace**: instrument every agent-pair handoff with per-pair spans (not just per-agent spans).
2. **Sample**: route all handoffs through the eval rubric — on a 10% sample in steady state, 100% on detected anomalies.
3. **Score**: run the LLM-as-judge evaluation per rubric; store scores alongside traces.
4. **Cluster**: group failure signals by (sender, receiver, task_type) to find systematic drift patterns.
5. **Alert**: fire when any handoff pair drops below the fidelity threshold for three consecutive runs.

> Verified 2026-07-25 — Based on: FutureAGI "Evaluating AutoGen Agents 2026" (Mar 2026, updated May 2026); GitHub Blog "Multi-agent workflows often fail" (Gwen Davis, Feb 2026); Agentrial open-source eval framework (multi-agent metrics: delegation accuracy, handoff fidelity, cascade failure depth). Receipt pending — actual instrumented eval run not executed in this environment.

## See also
- [S-1567 · The Typed Handoff Protocol Stack](stacks/s1567-the-typed-handoff-protocol-stack-when-your-multi-agent-system-succeeds-at-every-step-and-fails-at-every-handoff.md) — schema contracts prevent handoff misinterpretation
- [S-1388 · The A2A Context Fidelity Stack](stacks/s1388-the-a2a-context-fidelity-stack-when-your-agent-hands-off-a-task-and-the-receiver-loses-the-thread.md) — context loss across A2A protocol boundaries
- [S-1013 · The Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — boundary disagreement as a class of handoff failure
