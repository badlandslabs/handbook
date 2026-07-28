# F-101 · The Handoff Fidelity Problem — When Your Agent Said It But the Other Didn't Hear It

You have two agents: a researcher that spent 3 minutes gathering 12 pieces of evidence, and a writer that produces a flat, evidence-free summary. The researcher logged everything. The writer received a degraded approximation. This isn't a schema mismatch — the schemas matched. The data arrived. The *meaning* didn't survive the crossing. This is the handoff fidelity problem.

## Forces

- **The receiving agent rebuilds context from scratch.** When context reaches a new agent, it doesn't inherit understanding — it must reconstruct it from the signal encoded in the handoff message. Whatever couldn't be compressed into that message is lost.
- **Schema contracts solve format, not meaning.** S-643 covers schema versioning and typed handoffs. But even a perfectly typed handoff with all required fields populated can lose the *weight* of evidence, the *urgency* of a constraint, or the *preference ordering* the sender used to make decisions.
- **Confidence and reasoning paths don't serialize.** A sender might have high confidence in one conclusion (0.97) and low confidence in another (0.31). It might have rejected 9 other hypotheses. None of this survives a standard structured output unless explicitly encoded — and encoding it means the sender knows what's important to the receiver.
- **The handoff memo is written by the wrong agent.** The sender decides what to include. The receiver needs different information than the sender naturally produces. There's a structural incentive mismatch baked into every unmediated handoff.

## The move

### 1. Separate signal types at the handoff boundary

Every handoff carries three distinct signal layers:

| Layer | What it carries | Default behavior |
|-------|-----------------|-----------------|
| **Data layer** | Facts, outputs, structured results | Usually transmitted — schema handles this |
| **Provenance layer** | Source attribution, confidence scores, rejection log | Often dropped — not in standard schemas |
| **Intent layer** | Why this was chosen, what's still uncertain, what matters next | Almost always lost — natural language can't encode it |

Build your handoff schema to include all three. If the writer needs evidence, the researcher can't just send "here are 12 facts" — it must send provenance for each: "I found this via search query X, discarded the top-3 results as irrelevant, and rated this fact 0.91 confidence."

### 2. Use a handoff fidelity contract — not just a data contract

A fidelity contract specifies what the *receiver* needs to function, not just what the sender can produce. Negotiate it from the receiver's perspective:

```python
# The receiver declares its minimum operating context
class WriterHandoffRequirements:
    min_evidence_count: int = 5          # Below this, writer degrades
    require_source_url: bool = True      # Claims need citations
    require_confidence_per_claim: bool = True  # Low-confidence items get flagged
    require_rejection_log: bool = False  # Nice-to-have, not required
    max_age_minutes: int = 30            # Stale evidence degrades output

# The sender's handoff memo must satisfy these requirements
# before the handoff is considered complete
def handoff_ready(sender_output: dict, requirements: WriterHandoffRequirements) -> bool:
    if sender_output["evidence_count"] < requirements.min_evidence_count:
        return False
    if requirements.require_source_url and any(e.get("source_url") is None for e in sender_output["evidence"]):
        return False
    if any(e.get("confidence", 1.0) < 0.7 for e in sender_output["evidence"]):
        return False  # Or flag for human review instead of failing
    return True
```

### 3. Encode the decision tree, not just the decision

The single highest-fidelity signal you can send is the *decision path*, not the outcome. Instead of:

```json
{"result": "Use PostgreSQL", "confidence": 0.87}
```

Send:

```json
{
  "result": "Use PostgreSQL",
  "confidence": 0.87,
  "alternatives_considered": [
    {"choice": "MongoDB", "rejected_at": "cost estimation", "rejection_reason": "2.3x cost of Postgres at this scale"},
    {"choice": "DynamoDB", "rejected_at": "team expertise", "rejection_reason": "zero prior experience, 6-week ramp"}
  ],
  "pivots": [
    {"signal": "request_rate > 50k RPS", "would_trigger": "DynamoDB"}
  ],
  "confidence_breakdown": {
    "team_fits_postgres": 0.95,
    "scale_handles_postgres": 0.82,
    "cost_stays_budget": 0.79
  }
}
```

The receiving agent can now *re-derive* the decision, not just accept it. If context changes (new budget, new team member), it can reason about what would change.

### 4. Verify fidelity at the boundary

Run a reconstruction check: after the receiving agent processes the handoff, ask it to summarize what the sender concluded and *why*. Compare against the sender's actual output. Fidelity degradation shows up immediately — the reconstruction diverges even when the data matched.

```python
def fidelity_check(sender_context: dict, receiver_reconstruction: str, threshold: float = 0.7) -> dict:
    """Verify the receiver understood what the sender meant, not just what it said."""
    # LLM-as-judge: does receiver's summary match sender's key conclusions?
    score = judge_score(
        f"Does this reconstruction accurately reflect the sender's conclusions and reasoning?\n"
        f"Sender: {sender_context['conclusions']}\n"
        f"Receiver reconstruction: {receiver_reconstruction}"
    )
    return {
        "fidelity_score": score,
        "passed": score >= threshold,
        "divergence_points": extract_divergences(sender_context, receiver_reconstruction)
    }
```

Track fidelity scores over time. A consistent drop below 0.7 means the handoff schema needs renegotiation.

### 5. Design for iterative reconstruction

The most resilient pattern: the receiving agent doesn't just receive context — it asks for what's missing. A structured clarification loop at handoff boundaries catches fidelity loss before it propagates:

```python
RECEIVER_PROMPT = """
You received a handoff from {sender_role}. Before proceeding:
1. List the 3 most important conclusions from the handoff
2. List 2 things that are still unclear or could be ambiguous
3. For each unclear item, specify what additional context would resolve it
Only proceed when you have answers to your clarification questions.
"""
```

## Receipt

> Receipt pending — 2026-07-28

## See also

- [S-643 · The Coordination Layer Is the Product](stacks/s643-the-coordination-layer-is-the-product.md) — schema contracts and typed handoffs
- [S-1314 · The Pipeline Collapse Stack](stacks/s1314-the-pipeline-collapse-stack-when-multi-agent-systems-fail-at-the-handoff.md) — pipeline failures at handoff boundaries
- [F-179 · Multi-Agent Coordination Failures](forward-deployed/f179-multi-agent-coordination-failures.md) — the MAST failure taxonomy for multi-agent systems
