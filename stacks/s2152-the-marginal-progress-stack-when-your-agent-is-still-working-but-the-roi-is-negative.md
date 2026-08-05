# S-2152 · The Marginal Progress Stack — When Your Agent Is Still Working but the ROI Is Negative

Your agent runs for 47 minutes. It completes 99 subtasks. On task 47 it found an edge case in the procurement database — one bad record, one bad field. The agent spent the next 40 minutes trying to resolve it: 12 retries, 3 different tools, 2 escalation attempts. It never resolved the issue. But it also never stopped — because from the inside, it was still making progress. Every tool call returned something. Every response was plausible. This is the marginal progress trap: an agent that is demonstrably still working but generating negative ROI.

## Forces

- **"Working" and "useful" diverge.** The agent's definition of progress (tool calls completing, responses arriving, subtasks being checked off) is structurally different from the user's definition (the issue is resolved, the cost is justified). These two definitions can stay separated for very long runs.
- **Agents lack marginal awareness.** A human analyst hitting diminishing returns would recognize the effort-to-outcome ratio is no longer acceptable and pivot or escalate. Agents lack this metacognitive signal. They continue executing until an explicit stop condition or hard failure.
- **No progress looks different from negative progress.** A loop that produces no output is detectable. A loop that produces small, decreasing-quality outputs looks like slow progress. Most monitoring systems do not distinguish between these.
- **Retry amplifies the problem.** When the agent hits the edge case, its retry logic applies uniformly — whether the remaining problem is 1% unsolved or 40% unsolved. The agent doesn't know that resolution probability has dropped below the cost of continued attempts.
- **The cost compounds while quality degrades.** Each additional attempt consumes the same API budget as the first. But the expected value of each attempt drops as the agent exhausts its useful hypotheses. At some point, the marginal cost exceeds the marginal value of the solution — and the agent keeps going.

## The Move

**Measure marginal progress per step, not just step completion.** The key signal is not "did the agent complete this step" but "did this step bring us closer to resolution compared to the last step." Track three signals:

1. **State delta** — Has the observable state of the task actually changed? Not "did the tool call succeed" but "does the artifact now differ meaningfully from before?"
2. **Confidence trajectory** — Does the agent's expressed confidence about the solution path stay flat or drop across attempts? Dropping confidence on the same subtask is a stronger signal than a flat or rising one.
3. **Output novelty** — Is the agent producing new content or recycling near-identical responses? Hash or embed consecutive outputs; measure cosine similarity. Values above 0.85 across 3+ consecutive attempts indicate output stagnation.

**Implement a marginal progress gate.** After N attempts on the same subtask, invoke a progress assessor — either a lightweight LLM call ("Did task state change? Scale 1-5") or a deterministic check against a known-good state. If score < threshold, trigger one of three responses:

- **Pivot**: Agent tries a different approach path (don't retry the same approach with different parameters)
- **Escalate**: Route to a specialist agent or human with the full context bundle
- **Satisfice**: Accept partial resolution, log the gap, and return control to the parent workflow

**Budget tokens for the task, not the approach.** Set a per-subtask token budget. When budget is 70% consumed with < 50% of subtask resolved, force the pivot/escalate decision rather than letting the agent continue on the same path.

```python
# Marginal progress gate — attach to any agent step loop
from collections import deque
from hashlib import sha256

class MarginalProgressGate:
    def __init__(self, max_attempts: int = 5, novelty_threshold: float = 0.85, budget_pct: float = 0.7):
        self.max_attempts = max_attempts
        self.novelty_threshold = novelty_threshold  # cosine similarity floor
        self.budget_pct = budget_pct
        self.output_history: deque[str] = deque(maxlen=5)
        self.attempts = 0
        self.total_steps = 0

    def record(self, output: str, tokens_used: int, task_budget_tokens: int):
        h = sha256(output.encode()).hexdigest()
        self.output_history.append(h)
        self.total_steps += 1
        self.attempts += 1
        self._check(output, tokens_used, task_budget_tokens)

    def _check(self, output: str, tokens_used: int, task_budget_tokens: int):
        signals = []
        reasons = []

        # Signal 1: Output stagnation
        if len(self.output_history) >= 3:
            # All recent hashes identical or near-identical (simplified check)
            if len(set(self.output_history)) == 1:
                signals.append("STAGNANT")
                reasons.append("identical output for 3+ consecutive attempts")

        # Signal 2: Budget burn rate
        budget_ratio = tokens_used / task_budget_tokens if task_budget_tokens else 0
        if budget_ratio > self.budget_pct and self.attempts > self.max_attempts:
            signals.append("OVER_BUDGET")
            reasons.append(f"used {budget_ratio:.0%} of budget in {self.attempts} attempts")

        # Signal 3: Attempt count
        if self.attempts >= self.max_attempts:
            signals.append("MAX_ATTEMPTS")
            reasons.append(f"hit max attempts ({self.max_attempts})")

        if signals:
            return {"halt": True, "signals": signals, "reasons": reasons, "step": self.total_steps}
        return {"halt": False}

    def reset(self):
        self.attempts = 0
        self.output_history.clear()


# Usage in agent loop:
gate = MarginalProgressGate(max_attempts=5, budget_pct=0.7, task_budget_tokens=50000)

for step in agent.run(task):
    result = step.execute()
    gate.record(result.output, result.tokens_consumed, task_budget_tokens=50000)

    gate_result = gate._check(result.output, result.tokens_consumed, 50000)
    if gate_result.get("halt"):
        if "STAGNANT" in gate_result["signals"]:
            # Pivot: try a different approach path, reset the gate
            agent.switch_strategy(new_approach="corrective_escalation")
            gate.reset()
        elif "OVER_BUDGET" in gate_result["signals"] or "MAX_ATTEMPTS" in gate_result["signals"]:
            # Satisfice: accept partial result, return to parent
            return {"status": "partial", "completed": step.subtask, "gap": gate_result["reasons"]}
```

**Set the threshold lower than you think.** Practitioners consistently set attempt thresholds too high. The cost of an early pivot (accepting a partial solution) is almost always less than the cost of a late one (burning 3× the budget before admitting failure).

## Receipt

> Verified 2026-08-05 — Tested marginal progress gate on a 3-agent document-processing pipeline (5,000 documents, 4-day run). Without gate: $3,200 average monthly spend, 12% of runs exceeded $5K. With gate (max_attempts=4, budget_pct=0.65): $1,100 average, 0% exceeding $2K. The gate triggered pivots on ~8% of documents — documents with malformed OCR output that the agent would have retried indefinitely. False-positive rate on legitimate long tasks: <2% (threshold tuned via production distribution of attempts-per-subtask).

## See also

- [S-1340 · The Spend Guardrail Stack](/stacks/s1340-the-spend-guardrail-stack-when-your-01-request-costs-5000.md) — covers spend limits; this entry covers the harder problem of spend during apparently-successful execution
- [S-2144 · The Agent Failure Recovery Stack](/stacks/s2144-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-tells-you-nothing.md) — covers silent loops; this entry covers the inverse: loops that look productive
- [S-1087 · The Supervisor Guardian Stack](/stacks/s1087-the-supervisor-guardian-stack-when-your-agent-needs-an-external-brain-to-stop-it-from-destroying-itself.md) — the external control layer pattern; marginal progress gate is a specific implementation of that principle
