# S-1911 · The Trajectory Calibration Stack — When Your Agent Is 97% Confident and Three Steps from Failure

Your agent just recommended rejecting a $40,000 insurance claim. It shows 0.97 confidence. The threshold is 0.95 — you're covered. Except the agent made a wrong tool call on step 3, reasoned confidently through a corrupted retrieval result on step 7, and the final answer is confidently wrong. By the time confidence is measured, the reasoning path is already poisoned. The fix is not a better final-output threshold — it is **trajectory-level calibration** that watches the execution process, not just the conclusion.

## Situation

You build a production agent that handles multi-step workflows: insurance claims, invoice approvals, legal document review. You add a confidence threshold for escalation. The agent reports 0.97. It never fires. Three weeks later, a customer calls about a denied claim. You audit the trace: the agent called the wrong database on step 3 (a subtle schema mismatch it didn't flag), used that result as ground truth for steps 4-8, and produced a confident, internally consistent answer that was completely wrong. The traditional calibration signal — final output confidence — gave no warning. The failure was baked into the trajectory long before the final token was generated.

This is not a model capability problem. The model was working exactly as designed. The problem is that **existing calibration methods were built for single-turn outputs, not multi-step agentic trajectories**. They measure what the agent says, not how it got there.

## Forces

- **Compounding error amplification.** A low-confidence tool call on step 3 contaminates the context for steps 4 through N. Each subsequent step inherits corrupted state and generates confident reasoning over it. The final output confidence is high because the trajectory has no self-consistency signal to detect the root cause.
- **Traditional calibration is output-gated.** Methods like temperature scaling and verbalized confidence measure `C = H(s_N, a_N)` — confidence at the final step, given the final state. If the damage was done three steps earlier, this signal is structurally blind to it.
- **RLHF degrades calibration systematically.** Alignment training rewards confident-sounding output regardless of actual accuracy. Post-RLHF models have worse calibration than pre-trained models, and this effect is strongest in multi-turn trajectories where each step compounds the problem.
- **Tool uncertainty is invisible to output-based methods.** When an agent calls `fetch_policy(status=active)` and gets a wrong result due to a schema mismatch, the LLM wraps the wrong result in confident reasoning. The tool error is logged but the LLM never flags uncertainty — it just continues.
- **Trajectory data is expensive to collect.** Agent trajectories require LLM inference, tool interactions, and human evaluation. This makes training data scarce precisely when you need it most.

## The Move

Extract process-level features across the entire execution trace — not just the final output — and train a failure predictor that operates mid-trajectory. This is the core insight of Holistic Trajectory Calibration (HTC) from Zhang, Xiong & Wu at Salesforce AI Research (arXiv:2601.15778, Jan 2026).

### The 48-Feature Taxonomy

HTC identifies 48 features across three levels:

**Macro-dynamics** — broad trajectory characteristics:
- Trajectory length, total token count, step count
- Reward signals at intermediate checkpoints
- Action diversity (entropy of tool selection)
- Tool call sequence patterns

**Cross-step dynamics** — how steps relate to each other:
- Tool-call outcome consistency (does step N+1 logically follow from step N?)
- Retrieval result overlap (is the agent re-retrieving the same facts?)
- State dependency depth (how many prior steps does the current step depend on?)
- Intermediate outcome drift (are intermediate conclusions stable or oscillating?)

**Micro-stability** — per-step signals:
- Token-level probability variance within each step
- Attention weight distribution shifts
- Self-correction frequency (is the agent revising its own conclusions?)
- Tool-call error rates (are tools returning errors the agent is ignoring?)

### The Calibration Pipeline

```python
import anthropic
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TrajectoryStep:
    step_id: int
    input_tokens: list[str]
    output_tokens: list[str]
    tool_calls: list[dict]
    tool_results: list[dict]
    token_logprobs: list[float]          # micro-stability signal
    self_corrections: int = 0            # micro-stability signal
    intermediate_confidence: float = 1.0  # cross-step signal
    cumulative_state_dependencies: int = 0

@dataclass
class TrajectoryFeatures:
    # Macro-dynamics
    total_steps: int
    total_tokens: int
    action_entropy: float
    tool_error_rate: float

    # Cross-step dynamics
    step_consistency_score: float       # -1 to 1: does N+1 follow from N?
    retrieval_overlap_ratio: float        # fraction of retrievals with overlap
    max_state_dependency_depth: int
    intermediate_drift_score: float      # how much do intermediate conclusions oscillate?

    # Micro-stability
    avg_token_logprob: float
    self_correction_rate: float
    avg_step_confidence_variance: float

def extract_htc_features(trajectory: list[TrajectoryStep]) -> TrajectoryFeatures:
    """Extract 48 features across three levels. Simplified from HTC (arXiv:2601.15778)."""

    # Macro-dynamics
    total_steps = len(trajectory)
    total_tokens = sum(len(s.input_tokens) + len(s.output_tokens) for s in trajectory)

    tool_choices = [tc["tool"] for s in trajectory for tc in s.tool_calls]
    action_entropy = _compute_entropy(tool_choices) if tool_choices else 0.0

    all_errors = [r.get("error") for s in trajectory for r in s.tool_results]
    tool_error_rate = sum(1 for e in all_errors if e) / max(len(all_errors), 1)

    # Cross-step dynamics
    step_consistency_scores = []
    for i in range(len(trajectory) - 1):
        score = _compute_step_consistency(trajectory[i], trajectory[i + 1])
        step_consistency_scores.append(score)
    step_consistency_score = sum(step_consistency_scores) / max(len(step_consistency_scores), 1)

    retrieval_overlap_ratio = _compute_retrieval_overlap(trajectory)
    max_state_dependency_depth = max((s.cumulative_state_dependencies for s in trajectory), default=0)
    intermediate_drift_score = _compute_drift(trajectory)

    # Micro-stability
    all_logprobs = [lp for s in trajectory for lp in s.token_logprobs]
    avg_token_logprob = sum(all_logprobs) / max(len(all_logprobs), 1.0)

    self_corrections = sum(s.self_corrections for s in trajectory)
    self_correction_rate = self_corrections / max(total_steps, 1)

    confidence_variances = [_variance(s.token_logprobs) for s in trajectory if s.token_logprobs]
    avg_step_confidence_variance = sum(confidence_variances) / max(len(confidence_variances), 1.0)

    return TrajectoryFeatures(
        total_steps=total_steps,
        total_tokens=total_tokens,
        action_entropy=action_entropy,
        tool_error_rate=tool_error_rate,
        step_consistency_score=step_consistency_score,
        retrieval_overlap_ratio=retrieval_overlap_ratio,
        max_state_dependency_depth=max_state_dependency_depth,
        intermediate_drift_score=intermediate_drift_score,
        avg_token_logprob=avg_token_logprob,
        self_correction_rate=self_correction_rate,
        avg_step_confidence_variance=avg_step_confidence_variance,
    )

class TrajectoryCalibrator:
    """Mid-trajectory failure predictor using HTC features."""

    def __init__(self, htc_model_path: str = "models/htc-classifier.pt"):
        self.classifier = self._load_model(htc_model_path)
        self.escalation_threshold = 0.72  # tuned on validation set

    def predict_failure_probability(
        self, trajectory: list[TrajectoryStep]
    ) -> tuple[float, dict]:
        """Return P(failure) and per-feature breakdown for debugging."""
        features = extract_htc_features(trajectory)
        prob = self.classifier.predict_proba([features])[0]

        # Per-dimension risk signals for observability
        breakdown = {
            "tool_error_risk": min(features.tool_error_rate * 3.0, 1.0),
            "consistency_risk": max(0, 1.0 - features.step_consistency_score),
            "drift_risk": features.intermediate_drift_score,
            "depth_risk": min(features.max_state_dependency_depth / 10, 1.0),
            "micro_stability_risk": max(0, 1.0 - features.avg_token_logprob / -1.0),
        }

        return prob, breakdown

    def should_escalate(
        self, trajectory: list[TrajectoryStep], action_stakes: str = "standard"
    ) -> bool:
        """Decide whether to interrupt based on trajectory health signals."""
        prob, breakdown = self.predict_failure_probability(trajectory)

        # Stake-adjusted threshold: high-stakes actions escalate at lower P(failure)
        thresholds = {"low": 0.85, "standard": 0.72, "high": 0.50, "critical": 0.30}
        threshold = thresholds.get(action_stakes, 0.72)

        if prob >= threshold:
            return True

        # Sanity gate: escalate if ANY single risk signal is extreme
        if breakdown["consistency_risk"] > 0.9:
            return True
        if breakdown["drift_risk"] > 0.85:
            return True
        if features.tool_error_rate > 0.4:
            return True

        return False

# Integration with an agent loop
async def agent_loop_with_trajectory_calibration(prompt: str, stakes: str = "standard"):
    client = anthropic.Anthropic()
    trajectory: list[TrajectoryStep] = []
    MAX_STEPS = 15

    for step_id in range(MAX_STEPS):
        step = await _execute_step(client, prompt, trajectory)
        trajectory.append(step)

        # Mid-trajectory calibration check
        calibrator = TrajectoryCalibrator()
        if calibrator.should_escalate(trajectory, action_stakes=stakes):
            prob, breakdown = calibrator.predict_failure_probability(trajectory)
            # Log for post-hoc analysis, initiate human review
            _initiate_escalation(
                trajectory=trajectory,
                failure_prob=prob,
                risk_breakdown=breakdown,
                step_id=step_id,
            )
            return {"status": "escalated", "step": step_id, "trajectory": trajectory}

    return {"status": "complete", "trajectory": trajectory}
```

### The Key Design Decision: When to Measure

Output-based calibration measures once, at the end. Trajectory calibration measures at every step and computes a running failure probability. The escalation threshold should be **lower for higher-stakes actions** — not because the agent is more likely to fail, but because the cost of failure justifies earlier intervention.

Also: the calibration model itself must be trained on real failure trajectories. HTC (arXiv:2601.15778) shows that the 48-feature approach outperforms both outcome-based and verbalized-confidence baselines on the TRAJ-CAL benchmark across 5 agent frameworks.

## Receipt
> Receipt pending — 2026-07-31 — Requires HTC classifier model (arXiv:2601.15778) training pipeline and TRAJ-CAL benchmark evaluation. Code structure verified syntactically.

## See also
- [S-1261 · Confidence Calibration](stacks/s1261-the-confidence-calibration-stack-when-your-agent-sounds-sure-and-is-wrong.md) — output-gated calibration; this entry is the trajectory-level extension
- [S-1433 · Confidence-Gated Autonomy](stacks/s1433-the-confidence-gated-autonomy-stack-when-your-agent-decides-it-knows-best-and-it-doesnt.md) — action-agnostic vs. action-aware confidence thresholds
- [S-1531 · Calibration Gap](stacks/s1531-the-calibration-gap-stack-when-your-agent-is-certain-and-wrong.md) — RLHF-induced overconfidence in chains of action
- [S-1602 · Metacognitive Handoff](stacks/s1602-the-metacognitive-handoff-stack-when-your-agent-knows-its-about-to-fail-and-asks-for-help-before-it-destroys-value.md) — proactive failure prediction; complementary to this entry's feature extraction approach
