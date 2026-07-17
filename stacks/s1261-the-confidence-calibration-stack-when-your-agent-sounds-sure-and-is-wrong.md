# S-1261 · The Confidence Calibration Stack — When Your Agent Sounds Sure and Is Wrong

Your agent reports 0.92 confidence on a medical dosage recommendation. The model almost never scores below 0.7. The escalation rule fires only below 0.5 — so it never fires. The answer is wrong and nobody catches it until the emergency room call. This is not a model capability problem. It is a **confidence calibration problem**: the model's stated probability has no reliable relationship to its actual accuracy.

## Situation

You build a production agent that routes support tickets, approves refunds, or flags legal clauses. You add a confidence threshold: if the agent is less than 80% sure, escalate to a human. The threshold feels conservative. In practice, the model reports 0.85+ confidence on 94% of outputs — including the ones that are catastrophically wrong. You ship on confidence and discover post-incident that the model's calibration curve looks nothing like its accuracy curve.

RLHF systematically degrades calibration. Reward signals reward confident-sounding answers, not accurate ones. The result: models are simultaneously more capable and less calibrated than their pre-RLHF ancestors.

## Forces

- **RLHF punishes hedging, even correct hedging.** "I'm 60% sure the answer is X" gets lower reward than "The answer is definitely X." Models learn to never express low confidence even when they genuinely don't know.
- **Verbalized confidence is generated text, not a probability.** The model outputs a token like "0.92" the same way it outputs any other token — based on what looks most plausible, not what the internal uncertainty actually is.
- **Agents compound the problem across steps.** If Step 1 is miscalibrated, its confident output becomes Step 2's confident input. Error compounds silently through the agentic loop.
- **Escalation thresholds are theater without calibration data.** A 0.8 threshold means nothing if the model's average reported confidence is 0.88 across all outputs, right or wrong.
- **Distribution shift makes calibration brittle.** A model calibrated on code-completion tasks may be wildly miscalibrated on domain-specific outputs in production.

## The Move

### 1. Measure before you act

Run calibration evaluation before setting any threshold. Use a held-out labeled dataset:

```python
import numpy as np
from sklearn.metrics import brier_score_loss, log_loss

# Collect (predicted_probability, outcome) pairs
# outcome = 1 if model was correct, 0 if wrong
probs = [p["confidence"] for p in eval_results]  # reported 0-1
outcomes = [p["correct"] for p in eval_results]  # binary

# Expected Calibration Error (ECE)
# Partition into M bins, compute weighted avg of |acc - conf| per bin
def ece(probs, outcomes, M=10):
    bins = np.linspace(0, 1, M+1)
    ece_total = 0.0
    for i in range(M):
        mask = (np.array(probs) >= bins[i]) & (np.array(probs) < bins[i+1])
        if mask.sum() == 0:
            continue
        acc = np.mean(np.array(outcomes)[mask])
        conf = np.mean(np.array(probs)[mask])
        ece_total += mask.sum() * abs(acc - conf)
    return ece_total / len(probs)

# Brier score (lower = better)
brier = brier_score_loss(outcomes, probs)

# If ECE > 0.1, calibration is bad enough to matter
print(f"ECE: {ece(probs, outcomes):.3f}  Brier: {brier:.3f}")
```

### 2. Ensemble multiple uncertainty signals

No single signal is reliable. Stack them:

| Signal | Source | Best for |
|--------|--------|----------|
| Verbalized probability | Model output token | Quick sanity check; never use alone |
| Mean top-1 logprob | Token-level logprobs | Structured/classification output |
| Top-k token entropy | Distribution spread | Reasoning-heavy steps |
| Semantic entropy | Meaning-clustered completions | Open-ended generation (no logprobs needed) |
| Internal reasoning confidence | Chain-of-thought reasoning trace | Planning and tool selection |

```python
def ensemble_confidence(prompt, response, client):
    # Signal 1: verbalized
    verbalized = parse_verbalized_confidence(response)  # extract "0.92" token

    # Signal 2: logprob-based (if available from API)
    try:
        top1_logprob = response.usage.logprobs[0]  # API-specific
        signal2 = np.exp(top1_logprob)  # convert logprob to prob
    except (AttributeError, TypeError):
        signal2 = None

    # Signal 3: semantic entropy via repeated sampling
    samples = [generate(prompt) for _ in range(8)]
    semantic_entropy = compute_semantic_entropy(samples)  # cluster by meaning

    # Combine: normalize each to [0,1], weighted average
    signals = [s for s in [verbalized, signal2, semantic_entropy] if s is not None]
    if not signals:
        return None  # escalate everything when you have no signal

    # Platt scaling: fit a logistic regression on calibration set
    # trained to map (signal values) -> actual P(correct)
    calibrated = platt_model.predict_proba([signals])[0][1]
    return calibrated
```

### 3. Set thresholds on calibrated scores, not raw model output

```python
# WRONG: threshold on verbalized confidence
# if parse_verbalized(response) < 0.5: escalate()  # never fires

# RIGHT: threshold on calibrated_ensemble_score
CALIBRATED_THRESHOLD = 0.85  # set after measuring ECE on your eval set
if calibrated_score < CALIBRATED_THRESHOLD:
    escalate(reason=f"calibrated confidence {calibrated_score:.2f} below threshold")

# Also log the raw signals for post-hoc analysis
log_event(
    "confidence_check",
    verbalized=verbalized,
    logprob_signal=signal2,
    semantic_entropy=semantic_entropy,
    calibrated=calibrated_score,
    final_outcome=final_correctness,  # filled in after verification
)
```

### 4. Add a calibration monitor in production

Calibration drifts. Re-evaluate monthly on recent production samples:

```python
def monthly_calibration_check():
    recent = fetch_recent_production_samples(n=500)
    probs = [r["calibrated_score"] for r in recent]
    outcomes = [r["verified_correct"] for r in recent]
    current_ece = ece(probs, outcomes)
    if current_ece > 0.15:
        alert("Calibration degradation detected", ece=current_ece)
        # Trigger recomputation of thresholds
        recompute_thresholds(recent)
```

### 5. Use abstention as a first-class signal

When uncertainty is genuinely high, the best agent behavior is to say "I don't know" — not to produce a plausible-sounding wrong answer. Design your prompts and reward signals to value calibrated abstention:

```python
# In your evaluation harness
def agent_reward(response, ground_truth, calibrated_confidence):
    if calibrated_confidence < 0.6:
        # Correct abstention = good
        if "I don't know" in response or "insufficient information" in response:
            return 1.0
        # Confident and wrong = severe penalty
        return -2.0
    else:
        # Confident and correct = normal reward
        return 1.0 if response_correct(response, ground_truth) else -0.5
```

## Sources

- Zylos Research (2026-04-18): "LLM Calibration and Uncertainty Quantification in Production AI Agents" — RLHF mechanism, calibration deficit, production patterns
- FutureAGI (2026-02-24, updated 2026-05-20): "Evaluating LLM Confidence and Uncertainty" — 5-signal calibration stack, HTC framework
- arXiv:2601.15778: "Agentic Confidence Calibration" — feature categories for agent confidence, domain transfer analysis
- AgentMarketCap (Apr 2026): $0.001/chat vs $5-8/task agentic cost differential, inference flip (85% enterprise AI budget on inference)

## See also

- [S-1026 · The PAEF Stack](./s1026-the-paef-stack-when-your-benchmark-says-pass-but-4-out-of-7-failure-modes-sneaked-past.md) — eval methodology that surfaces hidden failure modes
- [S-1023 · The Recovery Ladder](./s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — outcome verification that grounds confidence to reality
- [S-1019 · The Three-Pillar Observability Stack](./s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — tracing that makes confidence signals visible in production
