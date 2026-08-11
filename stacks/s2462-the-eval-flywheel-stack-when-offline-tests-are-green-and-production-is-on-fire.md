# S-2462 · The Eval Flywheel Stack: When Offline Tests Are Green and Production Is On Fire

Your eval suite passes 97%. Your users are filing bug reports. The agent drifts off policy on 8% of sessions, loops silently on edge cases 12% of the time, and fabricates citations at a rate that legal flagged. Your offline benchmark never caught any of it — because the benchmark never saw it. The gap between offline and production isn't a gap in testing rigor. It's a gap in the feedback signal itself. You need an eval flywheel: a closed loop where production failures flow back into the eval dataset, so each regression teaches the system instead of only teaching the team.

## Forces

- **Offline evals measure what you thought to test.** Golden datasets capture yesterday's failure modes. Production surfaces the failures you didn't anticipate — the cases that aren't in any test suite because nobody imagined them. An eval that can't learn from production is an eval that slowly loses relevance.
- **Final-answer scoring misses the modes that matter most.** Trajectory regressions, policy violations, tool-call fabrications, tone drift — none of these appear in a pass/fail score on the last token. By the time the final answer is scored, the damage is done and the signal is gone.
- **The stale-dataset death spiral.** Teams update golden datasets manually. Manual updates are slow. By the time a failure mode is added to the dataset, it's already been affecting users for weeks. The eval becomes a lagging indicator, not a leading one.
- **Manual eval curation doesn't scale.** At 1,000+ production sessions per day, human review can sample 2-5% at most. The vast majority of production behavior is unobserved and unrecorded. The gap between what happens and what's measured grows monotonically.

## The move

Build a three-stage eval pipeline where per-turn production classifiers continuously seed the golden dataset, and fresh data continuously refreshes the offline eval. The loop is the product.

### Stage 1 — Per-turn production classifiers

Intercept every reasoning/action turn in live traffic at 1–5% sampling rate. Classify each turn independently:

```
TURN_STATE = STUCK | PROGRESSING | FAILING
```

A STUCK turn: agent re-attempts the same tool with the same arguments. A FAILING turn: tool returns an error, policy violation detected, or confidence score drops below threshold. A PROGRESSING turn: nominal execution.

Target: <90ms classification latency so the signal is available inline within the reasoning loop — not just for post-hoc analysis.

Production signal unlocked here that offline never sees:
- **Policy drift**: agent gradually stops following system instructions across conversation depth
- **Jailbreak proximity**: user turns approaching successful injection — caught before the payload executes
- **Prompt injection**: malicious content in retrieved context beginning to influence agent output
- **Tone/persona drift**: agent persona eroding without a final-answer failure (the "helpful but wrong tone" failure)
- **Tool-call fabrication**: agent describing a tool call it plans to make before the result arrives

### Stage 2 — The feedback gate

Collected production failures flow through a triage gate before entering the golden dataset:

1. **Deduplication**: Cluster failures by root cause (same prompt template, same tool, same context pattern). One representative case per cluster, not 47 copies of the same failure.
2. **Human calibration**: A rotating reviewer samples 10% of automated classifications for accuracy. If classifier precision drops below 80% on the human calibration set, retrain before propagating failures downstream.
3. **Difficulty triage**: Classify new cases as regression targets (cases the agent should handle) vs. capability gaps (cases beyond current design). Only regression targets enter the golden dataset.

### Stage 3 — Dataset refresh and eval re-run

Fresh golden cases are merged into the versioned eval dataset with a retention policy:

```
KEEP:  Most recent instance of every failure cluster
      Canonical examples of every covered capability
DISCARD:  Cases where the underlying tool, prompt, or model has changed
          Duplicates more than 90 days old
          Cases flagged as non-reproducible
```

Re-run the full offline eval pipeline on every model/prompt change, gated by the updated dataset. Delta reporting shows which failure clusters are resolved, which are new, and which are persistent.

```
[Production Traffic]
      ↓ (1-5% sampling)
[Per-Turn Classifiers: stuck/progressing/failing]
      ↓
[Triage Gate: dedup → human calibrate → difficulty triage]
      ↓
[Golden Dataset (versioned, retention-policy enforced)]
      ↓
[Offline Eval Pipeline → Delta Report → Regression Gate]
      ↓
[Production Traffic]  ← feedback loop closes
```

## The flywheel insight

The eval flywheel works because each stage feeds the others: production failures train classifiers, classifiers surface failures, failures seed the dataset, the dataset makes offline eval more accurate, and more accurate offline eval catches regressions before they hit production — which means cleaner production signal. The leverage compounds over time. After 30 days, the golden dataset contains cases that didn't exist when the agent was shipped. After 90 days, the classifier model has seen enough production edge cases to outperform the original benchmark on the failure modes that actually matter.

The single biggest mistake teams make: they treat eval as a release gate (pass → ship, fail → don't ship) rather than as a learning system. A flywheel doesn't gate — it compounds.

## The <90ms constraint

The per-turn classifier must run in under 90ms to stay within the reasoning loop on fast-path agents. This constraint has architectural consequences:

- **No LLM call in the hot path.** Classifiers must be deterministic rule-based systems or lightweight fine-tuned models, not general-purpose LLM judges. LLM-as-judge belongs in Stage 2 triage, not Stage 1 production traffic.
- **Feature extraction happens once per turn.** Tool name, error code, turn index, context occupancy, conversation depth — these are the signal features, not raw text.
- **Batch scoring is a trap.** Real-time classification enables intervention (flag the session, alert the operator). Batch scoring at end-of-session means failures are discovered after users are affected.

## Code

```python
# Stage 1: Per-turn classifier (deterministic, <90ms target)
from enum import Enum
from dataclasses import dataclass
import time

class TurnState(Enum):
    PROGRESSING = "progressing"
    STUCK = "stuck"
    FAILING = "failing"

@dataclass
class TurnFeatures:
    tool_name: str
    error_code: int | None
    turn_index: int
    context_tokens: int
    conversation_depth: int
    recent_tools: list[str]  # last 5 tool names
    confidence_score: float | None

def classify_turn(f: TurnFeatures, threshold: float = 0.3) -> TurnState:
    """
    Deterministic per-turn classifier targeting <90ms.
    Runs in the hot path of the agent reasoning loop.
    """
    # Rule 1: Tool error → failing
    if f.error_code is not None and f.error_code >= 400:
        return TurnState.FAILING

    # Rule 2: Same tool called 3+ times consecutively → stuck
    if len(f.recent_tools) >= 3:
        if all(t == f.recent_tools[-1] for t in f.recent_tools[-3:]):
            return TurnState.STUCK

    # Rule 3: Confidence collapse → failing
    if f.confidence_score is not None and f.confidence_score < threshold:
        return TurnState.FAILING

    # Rule 4: Context overflow proximity → stuck
    MAX_TOKENS = 128_000
    if f.context_tokens > 0.9 * MAX_TOKENS:
        return TurnState.STUCK

    return TurnState.PROGRESSING


# Stage 2: Failure triage gate
from collections import Counter

def triage_failure_cluster(
    failures: list[TurnFeatures],
    calibration_set: list[tuple[TurnFeatures, TurnState]],
    precision_threshold: float = 0.80,
) -> list[TurnFeatures]:
    """
    Deduplicate and calibrate before seeding the golden dataset.
    """
    # Cluster by root cause (simplified: same tool + same error code)
    clusters = {}
    for f in failures:
        key = (f.tool_name, f.error_code)
        clusters.setdefault(key, []).append(f)

    # One representative per cluster
    representatives = [cluster[0] for cluster in clusters.values()]

    # Calibrate against human-annotated subset
    hits = sum(
        1 for f, expected in calibration_set
        if classify_turn(f) == expected
    )
    precision = hits / len(calibration_set) if calibration_set else 1.0

    if precision < precision_threshold:
        raise RuntimeError(
            f"Classifier precision {precision:.2%} below threshold. "
            f"Retrain before propagating failures."
        )

    return representatives
```

## Receipt

> Verified 2026-08-11 — Pattern derived from: MorphLLM "AI Agent Evaluation (2026)" (three eval layers + per-turn classifier loop, June 2026); S-1004 (three eval layers framework); S-1010 (golden dataset + offline gating); S-1036 (trajectory quality index). Novel contribution: the continuous feedback mechanism tying per-turn production signal → dataset refresh → offline eval re-run. Specific quantitative data (<90ms latency target, 1-5% sampling rate, 80% precision threshold, 30-day golden dataset cycle) drawn from MorphLLM.com and cyberquickly.com reporting on APEX-Agents benchmark (<25% first-attempt success).

## See also

- [S-1004 · The Agent Eval Stack](s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — the three eval layers framework; this entry extends it with the feedback mechanism
- [S-1036 · The Trajectory Quality Index](s1036-the-trajectory-quality-index-when-your-agent-passes-but-the-path-is-broken.md) — trajectory scoring within the eval harness; TQI provides the diagnostic signal the flywheel feeds on
- [S-1000 · Structural Agent Governance](s1000-structural-agent-governance-stack-when-your-prompt-based-guardrails-break-under-pressure.md) — per-turn policy violation detection; the flywheel's Stage 1 classifiers can serve as the governance signal source
