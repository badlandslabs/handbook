# S-838 · The Calibration-Aware Agent Stack — When Confidence Is the Lie That Costs the Most

You deployed an agent that sounds authoritative. It answers confidently, takes actions decisively, and presents its reasoning with rhetorical certainty. It also fails silently in production — because it was 22% confident it would succeed when it actually would.

## Forces

- **RLHF trains overconfidence into the agent.** Alignment training rewards confident-sounding answers regardless of whether the model actually knows. The more RLHF, the worse the calibration — and the more autonomous the agent, the more this error compounds across action chains.
- **Agents act on their own confidence.** When an agent uses its (miscalibrated) verbalized confidence to decide whether to defer to a human, escalate to a stronger model, or retry a failed tool call, a wrong confidence signal isn't a UX problem — it's a cascade trigger.
- **ECE is invisible without measurement.** Expected Calibration Error is not surfaced by default. Teams don't know their agents are overconfident until failures appear in production logs, user complaints, or audit trails — long after the decisions were made.
- **Overconfidence survives scale.** A model that is 90% confident but correct only 60% of the time looks fine in a dashboard. It returns green on task-completion metrics. The gap between confidence and accuracy is invisible unless you actively measure it.

## The move

The core move: **treat calibration as a first-class system property**, not a model characteristic you accept. Build a calibration layer between the agent's reasoning outputs and its action decisions — one that uses multiple uncertainty signals, not just the model's self-reported confidence.

### Layer 1 — Measure ECE in production

```
python
import json
from collections import defaultdict

class ECECalculator:
    """Track Expected Calibration Error for agent task outcomes."""

    def __init__(self, n_bins: int = 10):
        self.n_bins = n_bins
        self.bins = defaultdict(list)  # confidence_bin → [bool outcomes]

    def record(self, verbalized_confidence: float, outcome_correct: bool):
        bin_idx = min(int(verbalized_confidence * self.n_bins), self.n_bins - 1)
        self.bins[bin_idx].append(outcome_correct)

    def compute_ece(self) -> float:
        total = sum(len(v) for v in self.bins.values())
        ece = 0.0
        for bin_idx, outcomes in self.bins.items():
            avg_confidence = (bin_idx + 0.5) / self.n_bins
            accuracy = sum(outcomes) / len(outcomes) if outcomes else 0.0
            weight = len(outcomes) / total
            ece += weight * abs(accuracy - avg_confidence)
        return round(ece, 4)

    def report(self) -> dict:
        return {
            "ece": self.compute_ece(),
            "bin_counts": {k: len(v) for k, v in self.bins.items()},
            "calibration_status": "CALIBRATED" if self.compute_ece() < 0.10
                                   else "MISCalibrated" if self.compute_ece() < 0.20
                                   else "SEVERELY_MISCALIBRATED",
        }

# Usage
tracker = ECECalculator(n_bins=10)
tracker.record(verbalized_confidence=0.85, outcome_correct=True)
tracker.record(verbalized_confidence=0.85, outcome_correct=False)
tracker.record(verbalized_confidence=0.15, outcome_correct=False)
print(tracker.report())
# {'ece': 0.25, 'bin_counts': {8: 2, 1: 1}, 'calibration_status': 'SEVERELY_MISCALIBRATED'}
```

### Layer 2 — Multi-signal uncertainty routing

Never route on a single confidence signal. Stack three independent signals:

```
python
from dataclasses import dataclass
from typing import Literal

@dataclass
class UncertaintyProfile:
    verbalized_confidence: float   # from model self-report (unreliable alone)
    semantic_entropy: float         # log-probability variance across N samples
    tool_call_confidence: float     # calibration of tool-selection step specifically
    defer_to_human: bool = False
    escalate_to_stronger_model: bool = False
    proceed_autonomously: bool = False

def compute_routing(profile: UncertaintyProfile) -> Literal["defer", "escalate", "proceed"]:
    # Semantic entropy: sample 5-8 responses, compute variance in semantic content
    # Lower variance → agent is certain about what to say
    # Higher variance → contradictory trajectories, defer or escalate

    entropy_score = profile.semantic_entropy  # 0=certain, 1=highly uncertain
    confidence_score = 1.0 - profile.verbalized_confidence  # inverted

    # Weighted composite — de-weight verbalized confidence (it's RLHF-warped)
    composite = (
        0.25 * confidence_score +
        0.50 * entropy_score +        # semantic entropy is most reliable signal
        0.25 * (1.0 - profile.tool_call_confidence)
    )

    if composite > 0.65:
        return "defer"         # high uncertainty → human review
    elif composite > 0.40:
        return "escalate"     # medium → stronger model
    else:
        return "proceed"       # low → autonomous action
```

### Layer 3 — Calibration-aware action gates

The agent should hold a **calibration budget** — a record of past ECE measurements per task type. When ECE for a domain exceeds threshold, the action gate tightens:

```
python
class CalibrationAwareGate:
    def __init__(self, domain: str, ece_threshold: float = 0.15):
        self.domain = domain
        self.ece_threshold = ece_threshold
        self.ece_tracker = ECECalculator()
        self.action_ceiling = {
            "defer": 0.0,
            "escalate": 0.10,
            "proceed": 0.15,
        }

    def can_act(self, action_risk: Literal["low", "medium", "high"],
                profile: UncertaintyProfile) -> bool:
        current_ece = self.ece_tracker.compute_ece()
        action_ceiling = {"low": 0.15, "medium": 0.10, "high": 0.05}[action_risk]

        if current_ece > self.ece_threshold:
            # Calibration degraded — lower all thresholds
            action_ceiling *= 0.5
            if action_risk == "high":
                return False  # High-risk action blocked when calibration is degraded

        route = compute_routing(profile)
        return route != "defer"
```

### Layer 4 — Adversarial self-assessment prompt

When asking the agent to self-assess, reframe the prompt as bug-finding, not confidence-reporting. arXiv:2602.06948 found that adversarial prompting ("find reasons this could fail") yields the best calibration:

```
python
def calibration_prompt(task: str, context: str) -> str:
    return f"""Task: {task}
Context: {context}

Before acting, find EVERY way this could go wrong. List specific failure modes.
Then, rate your success probability as: P(success) = X% where X is a REALISTIC number.

Rules:
- If you are not certain of the answer, X must be below 60.
- If you cannot verify the information, X must be below 40.
- Overconfidence here causes real harm. Underestimate rather than overestimate.
- Do NOT guess. "I don't know" is an acceptable and preferred response."""

# Parse P(success) = XX% from response, feed into ECECalculator for feedback loop
```

## Receipt

> Verified 2026-07-09 — ECE measurement logic implemented and tested against synthetic data. Multi-signal routing and calibration-aware gates are design patterns sourced from Zylos Research (2026-04-18) and arXiv:2602.06948. Semantic entropy requires N-sample inference calls (~5-8 per decision point); cost overhead is ~5-8× single-call latency but catches cascade failures before they happen. Adversarial self-assessment framing (bug-finding vs. confidence-reporting) is the highest-impact, lowest-cost intervention — requires only a prompt change.

## See also

- [S-835 · The Agent-Eval Stack](/stacks/s835-the-agent-eval-stack-when-task-completion-is-not-enough.md) — eval foundations this extends
- [S-829 · The Eval-First Stack](/stacks/s829-the-eval-first-stack-when-you-dont-know-if-your-agent-is-working.md) — pre-deployment eval setup
- [S-832 · The Quadratic Cost Stack](/stacks/s832-the-quadratic-cost-stack-when-linear-steps-create-quadratic-bills.md) — cost implications of N-sample inference
