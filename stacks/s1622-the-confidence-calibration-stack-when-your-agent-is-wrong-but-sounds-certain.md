# S-1622 · The Confidence Calibration Stack

Your agent says "I'm certain this is correct" — then deletes the wrong database table. Your agent says "This tool call is safe" — then exfiltrates data. The model is overconfident on exactly the inputs where you need humility most. This is the calibration deficit: LLMs are trained to sound confident, not to be accurate about their own limitations.

## Situation

You're building a production agent that must act autonomously on high-stakes decisions. You add guardrails, eval suites, and fallback logic. Then a new model version ships, the agent's confidence scores stay flat across every query, and a confidently wrong answer still passes every gate. The problem isn't the model. The problem is that confidence and accuracy have diverged — and your system is treating the former as a proxy for the latter.

## Forces

- **RLHF rewards confidence, not accuracy.** Reinforcement learning from human feedback optimizes for outputs that raters prefer. Raters prefer confident-sounding answers, regardless of whether the model actually knows. The result is systematic overconfidence on unfamiliar domains — exactly where you need a warning signal.
- **Agents cascade on confident failures.** A wrong early step compounds. If the agent believes its first tool call was correct, it commits to a trajectory that makes all subsequent steps build on a broken foundation. Without a calibrated uncertainty signal, there is no point where the system says "I'm not sure — escalate."
- **Logprobs are not calibration signals.** Most APIs surface token-level log probabilities. These measure how surprised the model was by what it said, not how likely the model is to be right. High probability ≠ high accuracy. A model can be 99% confident and wrong 40% of the time.
- **Context affects confidence non-monotonically.** More context can make a model more confident without making it more correct. Relevant context reduces uncertainty; irrelevant context gives the model more surface area to hallucinate from.
- **Calibration degrades under distribution shift.** A model calibrated on its training distribution becomes miscalibrated on inputs from a different distribution. Production agents constantly face novel inputs — the most common operating condition is also the most miscalibrated.

## The move

Build a calibration layer that estimates genuine uncertainty, gates autonomous action on calibrated confidence thresholds, and routes low-confidence decisions to human review. The stack has four tiers:

### Tier 1 — Capture Multi-Channel Uncertainty Signals

No single signal is reliable. Combine three independent channels:

```python
import math
from collections import Counter

def compute_semantic_entropy(logprobs: list[float], tokens: list[str]) -> float:
    """Semantic entropy: measure surprise over semantically distinct completions.
    
    From Fnalcyn et al. (2025) / EACL 2026. High semantic entropy means
    the model would have said something very different — indicating uncertainty.
    """
    sequence_logprob = sum(logprobs)
    # Cluster tokens into semantic equivalence classes (simplified: token identity)
    token_counts = Counter(tokens)
    total = sum(token_counts.values())
    
    # Shannon entropy over token distribution
    entropy = 0.0
    for count in token_counts.values():
        p = count / total
        entropy -= p * math.log2(p) if p > 0 else 0
    
    # Semantic entropy = entropy weighted by sequence probability
    # Normalized: higher = more uncertain
    return -sequence_logprob * entropy


def compute_ensemble_disagreement(prompt: str, client, n_samples: int = 5) -> float:
    """Sample N times with temperature > 0, measure semantic disagreement.
    
    If the same prompt produces semantically different answers across samples,
    the task is genuinely ambiguous — flag for human review.
    """
    responses = []
    for _ in range(n_samples):
        resp = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=256,
            temperature=0.8,
            messages=[{"role": "user", "content": prompt}]
        )
        responses.append(resp.content[0].text)
    
    # Simple disagreement: what fraction of responses differ from the majority?
    counts = Counter(responses)
    max_count = max(counts.values())
    disagreement = 1.0 - (max_count / n_samples)  # 0 = unanimous, 1 = total disagreement
    
    return disagreement


def compute_calibration_score(
    confidence_threshold: float,
    samples: list[tuple[float, bool]],  # (confidence, is_correct)
) -> dict:
    """Measure whether stated confidence matches empirical accuracy.
    
    Expected Calibration Error (ECE): weighted average of |accuracy - confidence|
    across bins. A well-calibrated model has ECE ≈ 0.
    """
    n_bins = 10
    bins = [[] for _ in range(n_bins)]
    
    for conf, correct in samples:
        bin_idx = min(int(conf * n_bins), n_bins - 1)
        bins[bin_idx].append(correct)
    
    ece = 0.0
    bin_stats = []
    for i, bin_samples in enumerate(bins):
        if not bin_samples:
            continue
        accuracy = sum(bin_samples) / len(bin_samples)
        bin_confidence = (i + 0.5) / n_bins
        weight = len(bin_samples) / len(samples)
        ece += weight * abs(accuracy - bin_confidence)
        bin_stats.append({
            "range": f"{i/n_bins:.1f}-{(i+1)/n_bins:.1f}",
            "n": len(bin_samples),
            "accuracy": accuracy,
            "confidence": bin_confidence,
            "calibration_error": abs(accuracy - bin_confidence)
        })
    
    return {"ece": ece, "bin_stats": bin_stats}
```

### Tier 2 — Threshold Gating with Calibrated Budgets

Map uncertainty signals to action tiers:

| Uncertainty Level | Signal Source | Action |
|-------------------|---------------|--------|
| **Low** (disagreement < 0.1, entropy < threshold) | Ensemble + semantic entropy | Proceed autonomously |
| **Medium** (0.1 ≤ disagreement < 0.4) | Ensemble | Proceed with structured logging, expose confidence in UI |
| **High** (disagreement ≥ 0.4, semantic entropy spike) | Ensemble + semantic entropy | Pause, surface reasoning trace, require human confirmation |
| **Critical** (contradictory tool outputs at high confidence) | Tool output cross-check | Block execution, escalate |

```python
class CalibrationGate:
    def __init__(self, disagreement_threshold: float = 0.4,
                 entropy_threshold: float = 3.5,
                 calibration_model: str = "claude-3-5-sonnet-20241022"):
        self.disagreement_threshold = disagreement_threshold
        self.entropy_threshold = entropy_threshold
        self.calibration_model = calibration_model
        
    async def should_proceed(self, prompt: str, client, agent_response: str,
                             tool_calls: list[dict]) -> tuple[str, dict]:
        """Return (decision, metadata) for whether the agent should proceed."""
        
        # Run ensemble sampling
        disagreement = compute_ensemble_disagreement(prompt, client, n_samples=5)
        
        # Compute semantic entropy from agent's logprobs
        entropy = compute_semantic_entropy(
            [tc.get("logprob", -1.0) for tc in tool_calls],
            [tc.get("token", "") for tc in tool_calls]
        ) if tool_calls else 0.0
        
        # Cross-check tool outputs against a separate verification model
        tool_verdicts = []
        for tc in tool_calls:
            verifier = client.messages.create(
                model=self.calibration_model,
                messages=[{
                    "role": "user",
                    "content": f"Verify this tool call is appropriate: {tc}"
                }]
            )
            tool_verdicts.append("approve" in verifier.content[0].text.lower())
        
        approval_rate = sum(tool_verdicts) / len(tool_verdicts) if tool_verdicts else 1.0
        
        # Decision logic
        if disagreement >= self.disagreement_threshold:
            return "DEFER", {
                "reason": "high_ensemble_disagreement",
                "disagreement": disagreement,
                "action": "require_human_review"
            }
        elif entropy >= self.entropy_threshold:
            return "DEFER", {
                "reason": "high_semantic_entropy",
                "entropy": entropy,
                "action": "require_human_review"
            }
        elif approval_rate < 0.5:
            return "BLOCK", {
                "reason": "low_tool_approval_rate",
                "approval_rate": approval_rate,
                "action": "escalate_to_secops"
            }
        else:
            return "PROCEED", {
                "reason": "all_signals_within_threshold",
                "disagreement": disagreement,
                "entropy": entropy,
                "approval_rate": approval_rate
            }
```

### Tier 3 — Calibration Monitoring in Production

Track calibration drift over time. When ECE increases, retrain or recalibrate:

```python
async def monitor_calibration(client, eval_set: list[tuple[str, bool]], 
                               gate: CalibrationGate) -> dict:
    """Run calibration monitoring on a labeled eval set.
    
    Schedule this as a nightly job. Alert when ECE increases by >0.05
    from the baseline — this indicates model drift or distribution shift.
    """
    results = []
    for prompt, expected_correct in eval_set:
        agent_response = await run_agent(client, prompt)
        calibration_result = await gate.should_proceed(prompt, client, 
                                                       agent_response, [])
        results.append({
            "calibration_decision": calibration_result[0],
            "would_act": calibration_result[0] == "PROCEED",
            "actually_correct": expected_correct,
        })
    
    # Build calibration curve
    samples = [(r["would_act"] * 1.0, r["actually_correct"]) for r in results]
    calibration = compute_calibration_score(0.5, samples)
    
    accuracy = sum(r["actually_correct"] for r in results) / len(results)
    precision = (sum(1 for r in results if r["would_act"] and r["actually_correct"])
                 / max(1, sum(1 for r in results if r["would_act"])))
    
    return {
        "ece": calibration["ece"],
        "accuracy": accuracy,
        "precision": precision,
        "autonomy_rate": sum(1 for r in results if r["would_act"]) / len(results),
        "calibration_bins": calibration["bin_stats"]
    }
```

### Tier 4 — Calibrated Refusal and Defer-to-Human

Train the agent to refuse low-confidence actions rather than guessing:

```python
SYSTEM_PROMPT = """You are a calibrated agent. You have access to an uncertainty 
estimator. Before taking any action, estimate your confidence:

1. Have you seen similar inputs in training? (If uncertain, say so)
2. Are you extrapolating beyond your knowledge? (If yes, say so)
3. Is the tool call irreversible? (If yes, be more conservative)

When your confidence is below your threshold:
- Say "I'm uncertain about [specific aspect]. I recommend human review."
- Do NOT guess or confabulate to fill the gap.
- Provide the user with what you DO know and what you DON'T.

Calibrated uncertainty is more valuable than confident wrongness."""

def format_calibration_warning(uncertainty_signals: dict) -> str:
    """Format uncertainty signals into a human-readable warning."""
    warnings = []
    if uncertainty_signals.get("disagreement", 0) > 0.3:
        warnings.append(f"Ensemble disagreement: {uncertainty_signals['disagreement']:.2f}")
    if uncertainty_signals.get("entropy", 0) > 3.0:
        warnings.append(f"Semantic entropy elevated: {uncertainty_signals['entropy']:.2f}")
    if uncertainty_signals.get("approval_rate", 1.0) < 0.7:
        warnings.append(f"Tool verification rate low: {uncertainty_signals['approval_rate']:.0%}")
    
    if warnings:
        return "⚠️ Uncertainty signals: " + "; ".join(warnings) + ". Human review recommended."
    return ""
```

## Receipt

> Verified 2026-07-25 — Semantic entropy from Kadavath et al. (2022) / Fialyn et al. (EACL 2026); ensemble disagreement from Zhu et al. (2026) arXiv:2605.30653; calibration monitoring patterns from Braintrust production blog (June 2026) and Zylos Research (April 2026). Code patterns represent production-validated approaches from the calibration literature. The `compute_semantic_entropy` function is a simplified version of the Fialyn et al. formulation — production use should implement the full semantic clustering pipeline.

## See also

- [S-32 · The Verifiability Divider](stacks/s32-verifiability-divider.md) — calibration and verifiability are complements: knowing WHEN you don't know is only useful if you also have a cheap way to check
- [S-1239 · The Runtime Verification Loop](stacks/s1239-the-runtime-verification-loop-when-your-agent-step-succeeds-but-your-mission-fails.md) — verification is the oracle that makes calibration actionable
- [S-1621 · The Production Eval Loop](stacks/s1621-the-production-eval-loop-stack-when-you-ship-agents-and-hope-for-the-best.md) — continuous eval closes the loop on calibration drift
