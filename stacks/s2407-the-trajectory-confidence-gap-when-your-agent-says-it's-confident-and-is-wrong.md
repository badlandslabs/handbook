# S-2407 · The Trajectory Confidence Gap — When Your Agent Says It's Confident and Is Wrong

Your code-review agent completes a PR review. It returns a structured report: 3 issues found, 2 approved, confidence 0.94. The report looks solid — correct syntax, coherent reasoning, plausible severity ratings. You merge. Two days later the payment service is broken. The agent correctly identified style issues. It missed a race condition in the async payment handler. It reported high confidence on both correct and incorrect assessments equally. Its per-call confidence score was meaningless as a quality signal.

Agents are not calibrated at the trajectory level. Per-step confidence does not predict outcome correctness.

## Forces

- **Model confidence is a single-turn signal applied to a multi-turn problem.** Logprob and verbalized confidence measure the model's uncertainty about the *next token*. They say nothing about whether the accumulated plan is sound, whether tool calls were the right choice, or whether the final output is grounded in reality.
- **Agents are systematically overconfident in failure.** RLHF trains models to produce confident-sounding outputs. SFT on agent trajectories reinforces fluent, complete-seeming responses. Neither rewards accurate uncertainty reporting. The result: agents are most confident precisely when they are most wrong.
- **Blast radius and confidence are inversely correlated.** The actions agents are most confident about — the ones that look cleanest in the trace — are often the ones with the largest blast radius. A race condition passes with confidence. A schema-mismatch error in a non-critical field gets flagged. Consequence size is orthogonal to model confidence.
- **Review depth cannot scale with every agent action.** Full human review of every agent output is economically impossible. The practical need is to route human attention to the trajectories where the agent's self-assessment is most likely to be wrong — which requires knowing when that is.

## The move

**1. Classify action consequence tier at step planning time.**

Before the agent proceeds, classify the current step by blast radius: TIER_A (irreversible: writes, payments, deletes, role grants), TIER_B (moderate consequence: external API calls, data reads of sensitive records, email sends), TIER_C (low consequence: internal calculations, style checks, read-only searches). This classification runs once per step and drives all downstream gates.

```python
from enum import Enum
from typing import Literal

class ConsequenceTier(Enum):
    TIER_A = "irreversible"      # payments, deletes, grants, deploys
    TIER_B = "moderate"          # external API calls, email, sensitive reads
    TIER_C = "low"               # internal calcs, reads, style checks

def classify_step(planned_action: dict, context: dict) -> ConsequenceTier:
    action_type = planned_action.get("type")
    target = planned_action.get("target", "")
    is_reversible = planned_action.get("reversible", False)

    high_risk_types = {"write", "delete", "grant", "deploy", "payment", "send"}
    if action_type in high_risk_types or any(k in target for k in ["payment", "grant", "delete"]):
        return ConsequenceTier.TIER_A
    if action_type in {"api_call", "email", "http_request"}:
        return ConsequenceTier.TIER_B
    return ConsequenceTier.TIER_C
```

**2. Implement trajectory-level calibration metrics, not per-call confidence.**

Per-call logprob does not predict trajectory correctness. Track instead: step entropy (variance in tool selection across N independent samples), null baseline comparison (how does the agent perform with no tools vs. full tool access?), consequence-tier error rate (historical accuracy broken down by TIER_A/B/C), and retrieval grounding ratio (fraction of output claims traceable to a retrieved source).

```python
import numpy as np

class TrajectoryCalibrator:
    def __init__(self, history_window: int = 200):
        self.history_window = history_window
        # Per-tier rolling accuracy: tracks whether agent was right per tier
        self.tier_correct = {tier: [] for tier in ConsequenceTier}
        # Step entropy: tracks variance in tool selection per step
        self.step_entropies = []

    def record_step(self, tier: ConsequenceTier, agent_correct: bool,
                    tool_variance: float, grounding_ratio: float):
        """Call after outcome is known."""
        self.tier_correct[tier].append(1 if agent_correct else 0)
        self.step_entropies.append(tool_variance)

        # Trim to window
        if len(self.tier_correct[tier]) > self.history_window:
            self.tier_correct[tier] = self.tier_correct[tier][-self.history_window:]

    def calibration_score(self, tier: ConsequenceTier) -> float:
        """Brier score: lower is better calibrated."""
        n = len(self.tier_correct[tier])
        if n < 20:
            return None  # Insufficient data
        accuracy = np.mean(self.tier_correct[tier])
        entropy = np.mean(self.step_entropies[-n:])

        # Penalize high confidence when accuracy is low; reward when matched
        # A well-calibrated agent: high accuracy → high confidence signals trustworthy
        # A miscalibrated agent: low accuracy + high confidence → low score
        return accuracy * (1.0 - entropy)  # heuristic; use proper Brier scoring in prod

    def review_depth(self, tier: ConsequenceTier, model_confidence: float) -> str:
        """Recommend human review depth based on tier + calibration gap."""
        cal_score = self.calibration_score(tier)
        if cal_score is None:
            return "full_review"  # Unknown tier, default to full review

        # If agent confidence is high but calibration score is low → deep review
        if model_confidence > 0.8 and cal_score < 0.5:
            return "full_review"
        if tier == ConsequenceTier.TIER_A and model_confidence < 0.95:
            return "full_review"
        if tier == ConsequenceTier.TIER_C and model_confidence > 0.7:
            return "skip_review"
        return "spot_check"
```

**3. Calibrate against null baselines per consequence tier.**

For TIER_A actions, run a null probe before execution: invoke the agent with no tools and ask "what would you do?" Compare the no-tool response against the actual tool-augmented response. Divergence signals that the agent's decision was tool-contingent rather than reasoning-contingent — a higher-risk signal. Run this as a shadow execution, not a blocking gate, and track divergence rate per agent.

```python
def null_baseline_probe(agent, state: dict, tier: ConsequenceTier) -> float:
    """
    Returns divergence score between tool-augmented and no-tool responses.
    High divergence = decision was tool-dependent = higher risk for TIER_A.
    """
    with_tools = agent.plan(state, tools=enabled_tools)
    without_tools = agent.plan(state, tools=[])

    # Semantic similarity of the planned action, not the text
    action_similarity = compute_action_overlap(with_tools, without_tools)
    divergence = 1.0 - action_similarity

    # For TIER_A, divergence > 0.3 triggers mandatory human review
    if tier == ConsequenceTier.TIER_A and divergence > 0.3:
        return divergence  # Flag for review
    return divergence
```

**4. Route review based on the gap, not the confidence.**

Review queue priority = blast_radius × calibration_gap. Actions with large blast radius AND poor calibration history get full review. Actions with small blast radius OR strong calibration get spot-check or skip. This is the inversion: you are not reviewing agent outputs, you are reviewing the calibration model itself — and using it to gate attention.

## Receipt

> Verified 2026-08-10 — arXiv 2601.15778 "Agentic Confidence Calibration" (Zhang et al., Salesforce AI Research, 2026) formally defines trajectory-level calibration as a distinct problem from single-turn calibration, proposing Holistic Trajectory Calibration (HTC). JetBrains 2026 Developer Ecosystem Survey: AI logic errors 2.3x more common than human logic errors. Agent PR substantial rework rate: 23% vs. 15% human baseline (DevOS Team, 2026). Combined penalty for AI logic bugs: ~15x vs. human errors (6.5x escape cost × 2.3x frequency). Devos.team/blog/ai-agent-failure-cost-statistics-2026; arxiv.org/abs/2601.15778; Salesforce AI Research Agentic Confidence Calibration.

## See also

- [S-53 · Confidence Calibration](../stacks/s53-confidence-calibration.md) — single-call model calibration (not trajectory-level)
- [S-1240 · The Reliability Multiplication Law](../stacks/s2404-the-budget-cliff-stack-when-your-agent-spends-more-while-youre-not-watching.md) — 95% per-step accuracy → 36% task completion
- [S-375 · Agentic Prompt Injection Defense-in-Depth](../stacks/s375-agentic-prompt-injection-defense-in-depth.md) — privilege separation for high-consequence actions
- [F-97 · Output Field Confidence Annotation](../forward-deployed/f97-output-field-confidence-annotation.md) — per-field confidence scores (poorly calibrated, run externally)
