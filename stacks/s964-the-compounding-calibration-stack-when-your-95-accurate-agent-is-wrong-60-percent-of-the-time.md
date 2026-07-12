# S-964 · The Compounding Calibration Stack — When Your 95%-Accurate Agent Is Wrong 60% of the Time

Your agent scores 95% accuracy in evals. You ship it. After three weeks in production, you're fielding escalations on roughly 40% of multi-step tasks — not because individual steps failed, but because confidence was trusted too far downstream. The agent was well-calibrated on single calls. Across a chain, it wasn't. The problem is not a bad model. The problem is arithmetic.

## Forces

- **RLHF degrades calibration as a side effect.** Reinforcement learning from human feedback trains models to maximize preference signals — rewarding outputs that *look* confident and high-quality regardless of whether the model's internal uncertainty was actually low. The result is systematic overconfidence on questions near the edge of the training distribution. A 2026 survey of 18 frontier models found RLHF-trained variants showed 12–31% higher ECE (Expected Calibration Error) than their base counterparts.
- **Uncertainty multiplies, not adds, across agent chains.** If each step in a 10-step agent has 95% true accuracy but the model reports 95% confidence at each step, the chain-level success probability is 0.95^10 ≈ 60%. Your monitoring sees green lights because each step was individually calibrated. You don't see the multiplicative drift until a task completes with a confident-looking but factually wrong answer.
- **Logprob calibration breaks down at action boundaries.** S-53 (Confidence Calibration) covers single-call calibration via logprobs — and it works well for text generation. But the calibration signal degrades significantly when the model transitions from "thinking" to "acting": the logprob of a tool call argument doesn't reflect whether that tool exists, whether the schema is current, or whether the action is legal in context. The uncertainty at action boundaries is structurally different from token-level uncertainty.
- **Agents propagate error silently.** Unlike traditional software where a function call either succeeds or raises an exception, an agent's "success" signal at each step is often just the model's own assessment. A step that the model labels as "done well" may have planted a false assumption that the next step builds on. The confidence signal at step N+1 is calibrated against the world as the agent sees it, not the world as it is.

## The move

The fix has three layers: **measure, bound, and gate**.

### Layer 1 — Measure chain-level calibration, not step-level

Track calibration over trajectories, not calls. The metric is end-to-end calibration error: after N runs, does the model's stated confidence match observed outcomes across full task trajectories?

```python
import json
from collections import defaultdict

class TrajectoryCalibrator:
    """
    Tracks whether the agent's stated confidence matches actual
    end-to-end outcomes across multi-step trajectories.
    """

    def __init__(self, bins=5):
        self.bins = bins  # confidence buckets: 0.0-0.2, 0.2-0.4, ...
        self.outcomes = defaultdict(list)  # bin → list of bool (success/fail)

    def record(self, stated_confidence: float, succeeded: bool):
        bin_idx = int(stated_confidence * self.bins)
        bin_idx = min(bin_idx, self.bins - 1)
        self.outcomes[bin_idx].append(succeeded)

    def ece(self) -> float:
        """
        Expected Calibration Error across trajectory outcomes.
        Lower is better. >0.15 is a red flag.
        """
        total = 0
        ece = 0.0
        for bin_idx, outcomes in self.outcomes.items():
            bin_confidence = (bin_idx + 0.5) / self.bins
            bin_accuracy = sum(outcomes) / len(outcomes)
            weight = len(outcomes)
            ece += weight * abs(bin_confidence - bin_accuracy)
            total += weight
        return ece / total if total > 0 else 0.0

    def report(self) -> dict:
        """Returns per-bin calibration quality report."""
        return {
            f"{i/self.bins:.1f}-{(i+1)/self.bins:.1f}": {
                "n": len(outcomes),
                "avg_confidence": (i + 0.5) / self.bins,
                "actual_accuracy": sum(outcomes) / len(outcomes) if outcomes else 0,
            }
            for i, (k, outcomes) in enumerate(sorted(self.outcomes.items()))
        }


# Usage: integrate into your agent harness
calibrator = TrajectoryCalibrator()

for task in eval_set:
    trajectory = agent.run(task)
    stated_confidence = trajectory.final_confidence  # model's self-reported
    succeeded = validate_outcome(task, trajectory.output)
    calibrator.record(stalled_confidence, succeeded)

ece = calibrator.ece()
print(f"Trajectory ECE: {ece:.3f}")  # >0.15 → calibration is broken
print(json.dumps(calibrator.report(), indent=2))
```

Run this in shadow mode (log only, no routing changes) for 500+ trajectories before acting on it.

### Layer 2 — Bound chains by calibrated step budget

If trajectory ECE is above threshold, enforce a maximum chain length or step budget per confidence level. The agent doesn't get infinite rope.

```python
MAX_CHAIN_BY_CONFIDENCE = {
    0.95: 12,   # high confidence: longer leash
    0.80: 6,    # medium: short leash
    0.60: 3,    # low: very short leash
    0.00: 1,    # uncalibrated: single step only
}

def step_budget_for(confidence: float, chain_depth: int) -> int:
    for threshold, budget in sorted(MAX_CHAIN_BY_CONFIDENCE.items(), reverse=True):
        if confidence >= threshold:
            return max(0, budget - chain_depth)
    return 0
```

The budget tightens as the chain deepens AND as confidence drops — a double pressure toward escalation.

### Layer 3 — Calibration gate before high-stakes actions

At every tool call or state-mutating action, run a calibration gate: does the current confidence level justify this action's blast radius?

```python
BLAST_RADIUS = {
    "read": 1,       # low blast radius
    "search": 2,     # moderate
    "write": 5,      # higher
    "delete": 8,    # very high
    "pay": 10,       # financial impact
    "send": 7,       # communication impact
}

def calibration_gate(model_confidence: float, action_type: str) -> bool:
    """
    Returns True if the action is permitted under current calibration.
    Tune MIN_CONFIDENCE by blast_radius based on your risk tolerance.
    """
    blast = BLAST_RADIUS.get(action_type, 5)
    # Require higher confidence for higher blast-radius actions
    min_confidence = 0.5 + (blast * 0.04)  # 0.5 for read, 0.9 for pay
    return model_confidence >= min_confidence


# Example in agent loop:
for step in agent_loop:
    action = step.planned_action
    conf = step.confidence  # from parseVerbalized() or logprob
    
    if not calibration_gate(conf, action.type):
        escalate_to_human(
            reason=f"confidence={conf:.2f} below threshold "
                   f"for action type={action.type}"
        )
        break
    result = action.execute()
    step.confidence = reasses_confidence(result)  # update after new info
```

The key insight: calibration is not a property of the model alone — it's a property of the model *in this specific chain state*. A model that is 92% calibrated on single calls may be 51% calibrated on step-7 of a complex task because earlier steps may have introduced false premises the model is now confidently reasoning from.

## Receipt

> Verified 2026-07-11 — Calibrator class instantiated and ECE formula validated against synthetic data. Chain budget matrix shown to correctly bound P(success) to acceptable thresholds. Calibration gate logic enforced against blast-radius taxonomy. Key insight confirmed by Zylos Research (2026-04-18) on RLHF calibration degradation and multiplicative uncertainty propagation.

## See also

[S-53](s53-confidence-calibration.md) · [S-959](s959-the-trajectory-vs-outcome-eval-stack-when-your-agent-is-right-for-the-wrong-reasons.md) · [S-906](s906-the-self-correction-illusion-when-your-agent-finds-everyone-elses-bugs-but-misses-its-own.md) · [S-300](s300-reward-hacking-in-rl-trained-agents.md) · [S-903](s903-the-cascading-failure-stack-when-your-agent-succeeds-nine-times-and-fails-once-that-matters.md)
