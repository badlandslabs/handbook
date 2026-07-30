# [S-1863] · The Calibration Gap Stack

When your agent reports task completion with confidence, but its confidence carries zero information about whether the outcome is correct.

## Situation

Your agent wraps up a 47-step data migration, logs "Migration complete — 12,847 records processed," and exits cleanly. You have no signal that 3,291 records were silently skipped due to a schema mismatch on step 23. The agent reported success because every individual tool call returned a success code. The gap between reported confidence and actual correctness is the calibration gap.

## Forces

- **Confidence is cheap, correctness is expensive.** Agents generate natural-language confidence signals at no cost; verifying actual correctness requires external validation.
- **Single-turn calibration doesn't generalize.** ECE and temperature-tuning work for one-shot outputs. Multi-step trajectories have compounding errors, tool-call uncertainty, and failure modes that only emerge at trajectory scale.
- **Early confidence predicts nothing.** An agent confident in step 3 can be catastrophically wrong by step 47. Traditional calibration looks at aggregate confidence, not trajectory-level process signals.
- **Overconfident failure enables over-autonomy.** The more an agent believes it succeeded, the more actions it takes downstream — propagating silent errors across delegation boundaries.
- **Interpretability and calibration pull in opposite directions.** You can have a confident answer or an explainable one. Agents give you the former without the machinery for the latter.

## The move

The pattern: **extract process-level diagnostic features across the trajectory, then predict success probability before the agent commits to a downstream action.** Instead of asking "how confident is this agent?" (which the agent answers unhelpfully), you compute "what signals in the execution history correlate with failure?"

**Holistic Trajectory Calibration (HTC)** — the approach from Salesforce AI Research (arXiv:2601.15778, Jan 2026) — extracts 48 process-level features across four categories:

1. **Early-step entropy** — uncertainty in the first tool selections. High early entropy predicts trajectory instability.
2. **Confidence gradients** — how confidence changes step-to-step. Declining confidence gradients flag approaching failure modes.
3. **Stability dynamics** — whether repeated similar inputs produce consistent outputs. Low stability = unreliable agent.
4. **Context utilization** — whether the agent is using available context or hallucinating from thin air.

A lightweight linear model over these features achieves better calibration than any single-turn method across 8 benchmarks. The key insight: **calibration is a property of the trajectory shape, not the final output.**

For production use, you don't need 48 features. The three highest-signal ones are:

- **Tool-call entropy**: how uncertain is the agent's tool selection across similar states? (Use temperature-sampled rollouts.)
- **Step-to-step consistency**: does the agent contradict itself across turns? (Track claimed facts vs. retrieved context.)
- **Budget consumption rate**: is the agent burning tokens faster than progress? (Token/second vs. task-completion-rate ratio.)

```python
# Minimal calibration-gap probe — run after every N steps
def calibration_probe(agent_id: str, trajectory: list[Step]) -> CalibrationReport:
    """
    Compute lightweight process signals. Return a CalibrationReport
    with success_probability and recommended action.
    """
    # Signal 1: tool-call entropy over last K steps
    tool_sequence = [s.tool_name for s in trajectory[-10:]]
    tool_entropy = compute_entropy(tool_sequence)  # high entropy = scattered strategy

    # Signal 2: consistency between claimed facts and memory
    claimed = extract_claims(trajectory)
    memory_hits = [verify_claim(c, agent.memory) for c in claimed]
    consistency_ratio = sum(memory_hits) / max(len(memory_hits), 1)

    # Signal 3: budget burn rate vs. progress
    steps_per_minute = len(trajectory) / max(1, trajectory[-1].elapsed_seconds / 60)
    # Define your baseline: acceptable steps/minute for this task type
    budget_efficiency = steps_per_minute / BASELINE_SPM[agent_id]

    # Composite signal (simplified — full model from arXiv:2601.15778)
    risk_score = (
        0.4 * normalize_entropy(tool_entropy) +
        0.4 * (1.0 - consistency_ratio) +
        0.2 * abs(1.0 - budget_efficiency)
    )

    # Map risk score to recommended action
    if risk_score > 0.7:
        return CalibrationReport(
            success_probability=0.15,  # near-zero confidence in success
            action="ESCALATE",
            reason="High tool entropy + low memory consistency + anomalous burn rate",
        )
    elif risk_score > 0.4:
        return CalibrationReport(
            success_probability=0.45,
            action="VERIFY_AND_CONFIRM",
            reason="Mixed signals — run semantic exit gate before delivery",
        )
    else:
        return CalibrationReport(
            success_probability=0.82,
            action="PROCEED",
            reason="Low risk across all three signals",
        )


@dataclass
class CalibrationReport:
    success_probability: float  # P(success) — NOT the agent's self-reported confidence
    action: str                 # ESCALATE | VERIFY_AND_CONFIRM | PROCEED
    reason: str                 # human-readable signal breakdown


# Integration with your agent loop
def run_with_calibration(agent, task, probe_every=10):
    trajectory = []
    while not agent.is_done():
        step = agent.run_next()
        trajectory.append(step)

        if len(trajectory) % probe_every == 0:
            report = calibration_probe(agent.id, trajectory)
            if report.action == "ESCALATE":
                # Stop the agent, surface the report to human reviewer
                agent.pause(report.reason)
                return report
            elif report.action == "VERIFY_AND_CONFIRM":
                # Inject a verification gate before continuing
                verified = semantic_exit_gate(agent, task)
                if not verified:
                    agent.pause("Calibration probe flagged risk; exit gate confirmed failure")
                    return report
    return CalibrationReport(success_probability=1.0, action="COMPLETE", reason="Task ended normally")
```

The critical shift: **the calibration report's `success_probability` is NOT what the agent said. It is a computed estimate from trajectory signals.** An agent reporting 95% confidence might produce a report showing 0.15 probability of success — and the 0.15 is the number you act on.

## Receipt

> Verified 2026-07-30 — arXiv:2601.15778 (Salesforce AI Research, Jan 2026) introduces the formal problem definition and HTC framework. The Context Lab (Feb 2026) independently quantifies the underlying problem: agents achieving 60% pass@1 show only 25% consistency across repeated trials. Glen Rhodes (2026) documents the termination logic angle — agents confident at the point of failure, not before it. These are independent sources converging on the same gap. The code above synthesizes the three-signal simplification from these sources. Receipt pending — integration with a live agent harness not executed in this run.

## See also

- **[S-1239 · The Runtime Verification Loop Stack](s1239-the-runtime-verification-loop-stack-when-you-need-to-know-if-your-agent-step-was-correct.md)** — the external validation counterpart; calibration tells you whether to verify, verification tells you whether you were right
- **[S-1856 · The Belief State Boundary Stack](s1856-the-belief-state-boundary-stack-when-your-agent-knows-something-it-cant-prove.md)** — the epistemic layer: what the agent believes vs. what it can evidence
- **[S-1837 · The Agentic FinOps Stack](s1837-the-agentic-finops-stack-when-your-agent-spends-400-to-find-a-nickel.md)** — budget burn rate as a calibration signal; anomalous spend patterns often precede capability collapse
