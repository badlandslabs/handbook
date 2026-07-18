# [S-1310] · The Trust Calibration Spectrum

Your agent outputs look right so nobody questions it — until the audit. Or: your agent is correct 92% of the time but gets second-guessed on every call, making the human override cost higher than the error rate. Both are miscalibration. Both are expensive. And they require opposite interventions.

## Forces

- **Overtrust collapses the oversight loop.** Users — especially non-technical ones — accept agent outputs at face value after a streak of correct answers. This is rational: cognitive load is real and delegation is the point. But it means the one-in-ten wrong output slides through without scrutiny, and in high-stakes domains (finance, medicine, compliance) that one slide is an incident.
- **Undertrust atomizes the automation value.** Every override costs human time. If your operators override a correct agent output because they don't understand the reasoning, you've built a slow, expensive human process with an AI layer on top.
- **Trust calibration is dynamic, not static.** A model that warranted full autonomy in March may warrant oversight in August after a provider update changed its behavior. Static trust assignments are miscalibrations waiting to happen.
- **Agents do not communicate uncertainty well.** LLMs are notoriously miscalibrated about their own confidence — confident wrong answers outnumber uncertain wrong answers. An agent that says "Done" with no uncertainty marker looks identical to one that says "Done — 94% confidence, recommend review of edge cases."

## The Move

Treat trust calibration as a **first-class engineering output** — a spectrum you tune, not a threshold you set once.

### 1. Map the Autonomy Spectrum Per Task Type

Not all tasks deserve the same trust level. Classify by consequence severity:

```
Class A (Irreversible, High Stakes) — Require human approval gate
  e.g., payments, data deletion, regulatory submissions, customer-facing commitments

Class B (Reversible, Moderate Impact) — Require post-hoc review or sampling
  e.g., report generation, data classification, ticket routing

Class C (Low Stakes, High Volume) — Full autonomy with logging
  e.g., internal summarization, first-draft code, suggestion systems
```

### 2. Instrument Confidence Signal Injection

Force the agent to produce a structured output that includes a confidence signal. Do not accept bare text.

```python
from pydantic import BaseModel
from typing import Literal

class AgentAction(BaseModel):
    action: str
    reasoning: str
    confidence: Literal["high", "medium", "low"]
    flag_for_review: bool
    uncertainty_explanation: str | None

def execute_with_calibration(agent, task) -> AgentAction:
    response = agent.run(task, structured_output=AgentAction)
    if response.confidence == "low" or response.flag_for_review:
        alert_human(task, response)
    return response
```

The confidence field is not advisory — it drives routing. High-confidence Class A actions still go to a human; low-confidence Class C actions trigger a review sweep.

### 3. Calibrate Users, Not Just Models

The overtrust problem is a human factors problem. Train operators to recognize when agent confidence is miscalibrated. Specifically:

- **Anchor on failure patterns**, not success streaks. Show operators what wrong looks like (confident wrong, uncertain wrong, plausible wrong).
- **Use calibration training**: show operators 50 agent outputs with known correctness, ask them to rate confidence before revealing answer. Their calibration curve reveals how much supervision the human actually provides.
- **Surface the reasoning chain**, not just the output. An agent that explains *why* it reached a conclusion gets scrutinized more than one that outputs a verdict. This is free: add a `reasoning` field to every structured output.

### 4. Implement Dynamic Trust Adjustment

Trust level should shift based on observed behavior:

```python
TRUST_SCORE = {
    "default": "full",
    "task_type": {"A": "gated", "B": "reviewed", "C": "autonomous"},
}

def adjust_trust(agent_id: str, task: str, recent_errors: float) -> str:
    """Reduce trust after error streak."""
    if recent_errors > 0.05:   # 5% error rate → escalate one level
        return escalate_trust_level(TRUST_SCORE[agent_id])
    if recent_errors < 0.01:   # 1% error rate → restore default
        return restore_default(agent_id)
    return TRUST_SCORE[agent_id]
```

Provider model updates are a trust reset event. After any provider-side model change, reset to gated review for Class A tasks until the new behavior baseline is established.

### 5. The Overtrust Detection Gate

Add a lightweight friction at the output layer for high-stakes actions:

```javascript
// Before executing a Class A action
const requiresAcknowledgment = ['payment', 'delete', 'send_external', 'approve'];
const actionType = detectActionType(agentOutput);

if (requiresAcknowledgment.includes(actionType)) {
  await humanConfirmation({
    summary: agentOutput.intent,
    confidence: agentOutput.confidence,
    reasoning: agentOutput.reasoning,
    consequences: explainConsequences(agentOutput)
  });
}
```

This is not a blocker for the agent — it's a forcing function that makes overtrust costly (requires click) without eliminating automation for the 90% of correct cases.

## Receipt

> Verified 2026-07-18 — Research synthesis from Zylos Research (Agent-Human Trust Calibration, 2026-05-27), AgentMarketCap (2026-04-14), Mastercard Verifiable Intent framework, OpenReview ACC survey (arxiv 2605.23989), SkillGen enterprise playbook (2026). No live system tested — Receipt pending.

## See also

- [S-1005 · AI SRE](stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — Reliability monitoring that catches miscalibration
- [S-1194 · Maker-Checker Agent Architecture](stacks/s1194-the-maker-checker-agent-architecture-dual-agent-verification-for-irreversible-actions.md) — Structural dual-agent verification for Class A actions
- [S-1293 · The Action Hallucination Stack](stacks/s1293-the-action-hallucination-stack-three-taxonomy-of-tool-execution-divergence.md) — When the agent's reported action diverges from what actually happened
- [S-1033 · Agent Behavioral Versioning](stacks/s1033-agent-behavioral-versioning-the-four-layer-version-problem.md) — Trust reset triggers when model behavior changes
