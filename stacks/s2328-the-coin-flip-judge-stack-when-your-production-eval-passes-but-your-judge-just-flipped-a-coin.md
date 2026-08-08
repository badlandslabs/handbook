# [S-2328] · The Coin Flip Judge Stack

When your production eval passes reliably every time — until it doesn't, and you can't tell if the system degraded or the judge itself drifted overnight.

## Situation

You're running continuous quality monitoring: a judge LLM scores every production agent interaction on a 1-5 rubric, and you page the team whenever the rolling average drops below 4.0. This week the score was 4.1. Last week it was 4.3. The system is improving — or is it? You don't know whether the judge is getting more lenient, the judge model silently version-bumped, or your product actually got better. Every alert is ambiguous between two completely different root causes, and you've been responding to the wrong one for three weeks.

## Forces

- LLM-as-Judge is 100-1000x cheaper than human annotation ($0.001-0.05 vs $0.10-3.00 per evaluation), making it the default production scorer for any team that can't afford human-in-the-loop review at scale.
- Single-trial pairwise preference flips 13.6% of the time even on identical inputs — a judge that says A > B this run may say B > A next run with the same temperature 0.7 model on the same question.
- Judge drift is invisible: API model versions are bumped silently, and a single version change re-scores your entire history differently — making trend analysis meaningless.
- Self-preference bias means judges consistently favor outputs from the same model family they belong to, inflating scores by 0.3-1.2 points and masking real regressions.
- Position effects (50-67% win rate for first-presented response) mean the ordering of candidates in pairwise eval is itself a confound you may not control.

## The Move

Build a three-layer reliability envelope around every LLM-as-Judge deployment: **anchor stabilization**, **multi-trial consensus**, and **judge-attribution separation**.

### Layer 1 — Anchor Stabilization (fix the drift problem)

Maintain a frozen, human-labeled anchor set of 50-200 representative interactions spanning all quality tiers (clear pass, marginal, clear fail). Re-score these anchors interleaved with every production eval batch.

```
anchor_set = load_anchors("human_labeled_anchors.jsonl")  # 50-200 items
                                              # Each item: {input, output, human_score, human_label}

def score_with_anchor_check(candidate, judge, anchor_set, threshold=0.05):
    # Step 1: Re-score anchors to measure judge drift
    anchor_scores = [judge.score(a) for a in anchor_set]
    drift = mean(anchor_scores) - mean([a['human_score'] for a in anchor_set])

    # Step 2: Adjust candidate score by measured drift
    candidate_score = judge.score(candidate)
    adjusted_score = candidate_score - drift

    # Step 3: Flag if judge has drifted beyond acceptable threshold
    if abs(drift) > threshold:
        alert(f"Judge drift detected: {drift:.3f}. Anchors re-evaluated.")
        # Do NOT ship this batch — re-run with a pinned judge version

    return adjusted_score
```

Pin judge model versions via provider API parameters (`model-version` on OpenAI, `version` on Anthropic). Log the exact version alongside every score. This is the only way to make cross-time comparisons meaningful.

### Layer 2 — Multi-Trial Consensus (fix the flip problem)

Run each evaluation 3-5 times at temperature > 0 and require majority consensus. For pairwise comparisons, run 5 trials and accept the winner only if they win ≥ 4/5 times.

```
from collections import Counter

def pairwise_consensus(judge, candidate_a, candidate_b, n_trials=5, threshold=4):
    wins = Counter()
    for _ in range(n_trials):
        result = judge.pairwise_compare(candidate_a, candidate_b, temperature=0.7)
        wins[result['winner']] += 1

    if wins[max(wins, key=wins.get)] >= threshold:
        return {"winner": wins.most_common(1)[0][0], "confidence": wins.most_common(1)[0][1] / n_trials}
    return {"winner": "TIE", "confidence": wins.most_common(1)[0][1] / n_trials}
```

For pointwise scoring, take the mode across trials or the median if you have 5+. Single-trial scores are not actionable — they are noise masked as signal.

### Layer 3 — Judge Attribution Separation (fix the ambiguity problem)

Log a structured attribution record for every eval batch that separates judge behavior from system behavior:

```
eval_record = {
    "batch_id": "b-2026-08-08-001",
    "timestamp": "2026-08-08T10:00:00Z",
    "judge_model": "gpt-4.1-mini",
    "judge_version": "2026-08-01",           # Pinned, not floating
    "anchor_drift": +0.07,                     # From Layer 1
    "consensus_rate": 0.91,                    # % of items where 4/5 trials agreed
    "n_samples": 1247,
    "mean_score": 4.12,
    "adjusted_mean": 4.05,                     # mean_score - anchor_drift
    "drift_alert": False
}
```

This record lets you run post-hoc root cause: if `adjusted_mean` dropped, the system degraded. If `anchor_drift` spiked, the judge drifted. If `consensus_rate` fell, the task complexity increased. Each has a different remediation.

### Layer 4 — Self-Preference Guard

If you're evaluating your own model's outputs, run a cross-family judge (evaluate Claude outputs with a GPT judge, and vice versa). Self-judging self is the most corrupting form of this failure mode.

## Receipt

> Verified 2026-08-08 — arXiv 2606.15474 (Yitao Li, Jun 2026) formalizes the anchor stabilization approach: a fixed human-labeled anchor set interleaved with production evals resolves judge-vs-system attribution ambiguity. arXiv 2606.13685 (Yagubyan, Apr 2026) quantifies the flip rate: pairwise preferences flip 13.6% on identical inputs across trials; pointwise scoring at temperature 0.7 has a standard deviation of 0.47 on a 1-5 scale. AgentMarketCap (Apr 2026) reports self-preference bias inflating scores by 0.3-1.2 points. VulpineOS production data shows a single autonomous loop burning $200-$2,000 overnight — the same economic explosion risk applies to eval infrastructure if judges are allowed to run without budget or consensus guards.

## See also

- [S-1010 · The Agent Eval Stack — When You Cannot Trust Your Tests](stacks/s1010-the-agent-eval-stack-when-you-cannot-trust-your-tests.md) — broader context on eval infrastructure
- [S-825 · The Trace-Eval Gap Stack — Knowing When Your Agent Is Lying to You](stacks/s825-the-trace-eval-gap-stack-knowing-when-your-agent-is-lying-to-you.md) — the gap between what traces show and what evaluations measure
- [S-901 · The Golden Set Trap — When Your Eval Suite Gives You Confidence You Haven't Earned](stacks/s901-the-golden-set-trap-when-your-eval-suite-gives-you-confidence-you-havent-earned.md) — the complementary failure: overfitting your anchors
