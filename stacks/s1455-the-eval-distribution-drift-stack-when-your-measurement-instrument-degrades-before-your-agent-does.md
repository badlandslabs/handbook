# S-1455 · The Eval Distribution Drift Stack — When Your Measurement Instrument Degrades Before Your Agent Does

Your agent's eval score has held at 91% for six months. Your dashboard is green. Your deploy pipeline is happy. What nobody noticed: the eval set you built at launch is now measuring the wrong distribution. Real user queries have shifted — new product features, seasonal patterns, adversarial inputs your team never anticipated. Your agent might be degrading, improving, or staying flat. Your eval set cannot tell you which. The measurement is stale and you are acting on it as if it were accurate.

This is eval set distribution drift: the silent degradation of your own evaluation instrument before your agent degrades. It is distinct from model drift (the model's internal representations changing) and from data drift (upstream data changing). Eval set drift means your test cases no longer represent what production users actually ask. You are optimizing a number that has quietly stopped measuring the right thing.

## Forces

- **Eval sets are snapshots, not streams.** You built your golden set from production logs on launch day. Those logs reflect the queries users actually asked in the first 30 days. Six months later, the product has changed, the user base has shifted, and adversarial inputs have appeared. Your 200 representative test cases still pass 91% — on inputs that represent 55% of current traffic.
- **Coverage decays as the tail grows.** Early eval sets capture the common cases. As the agent handles more requests, the long tail of unusual inputs grows. But eval sets rarely grow with it — they are maintained by hand, and maintenance competes with feature development.
- **Distribution monitoring is absent from most eval stacks.** Teams monitor model latency, error rates, and token costs. Almost no teams monitor whether their eval set's input distribution still matches production traffic. The measurement instrument itself goes unmeasured.
- **A stale eval set gives false confidence.** The worst outcome is not a failing eval — it is a passing eval that no longer means anything. Teams that catch an eval score drop act. Teams whose eval score stays flat believe their agent is stable. Often it is not.
- **Annotator drift compounds the problem.** When you add new eval cases, different annotators or different LLM judges label them differently than the original annotators. The evaluation standard itself shifts between batches.

## The Move

Track three types of eval set drift, not just agent quality:

### 1. Input Distribution Monitoring

Compare the distribution of production queries against the eval set using statistical tests:

```python
import numpy as np
from scipy import stats

# Cluster production queries vs eval queries into topic/semantic buckets
def detect_input_drift(production_queries: list[str], eval_queries: list[str],
                       embed_fn) -> dict:
    """
    Detect when production query distribution diverges from eval set.
    Uses embedding + KMeans to compare distributions without labeled categories.
    """
    prod_embeds = embed_fn(production_queries)
    eval_embeds = embed_fn(eval_queries)

    # Project to shared dimensionality, then compare distributions
    all_embeds = np.vstack([prod_embeds, eval_embeds])

    n_clusters = min(50, len(set(production_queries) | set(eval_queries)) // 2)
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    labels = km.fit_predict(all_embeds)

    prod_labels = labels[:len(production_queries)]
    eval_labels = labels[len(production_queries):]

    # Chi-squared test on cluster frequency distributions
    prod_counts = np.bincount(prod_labels, minlength=n_clusters).astype(float)
    eval_counts = np.bincount(eval_labels, minlength=n_clusters).astype(float)

    # Normalize to proportions
    prod_pct = prod_counts / prod_counts.sum()
    eval_pct = eval_counts / eval_counts.sum()

    chi2, p_value = stats.chisquare(prod_pct, eval_pct)
    kl_div = stats.entropy(prod_pct + 1e-10, eval_pct + 1e-10)

    return {
        "chi2_statistic": chi2,
        "p_value": p_value,
        "kl_divergence": kl_div,
        "drift_detected": p_value < 0.05 or kl_div > 0.15,
        "coverage_gap": float(np.mean(prod_counts > 0) - np.mean(eval_counts > 0)),
        # What % of production clusters have zero eval coverage
    }
```

Trigger: alert when KL divergence exceeds 0.15 or chi-squared p < 0.05. These thresholds flag that production and eval distributions have statistically diverged — even if the eval score hasn't changed.

### 2. Coverage Gap Tracking

Beyond statistical drift, track which production query clusters have zero eval representation:

```python
def coverage_report(production_queries: list[str], eval_queries: list[str],
                    embed_fn) -> dict:
    """
    Report which production query clusters have no eval coverage.
    These are blind spots — the agent could fail on them with no signal.
    """
    prod_embeds = embed_fn(production_queries)
    eval_embeds = embed_fn(eval_queries)

    n_clusters = min(50, len(production_queries) // 3)
    from sklearn.cluster import KMeans
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    km.fit(np.vstack([prod_embeds, eval_embeds]))

    prod_labels = km.predict(prod_embeds)
    eval_labels = km.predict(eval_embeds)

    eval_cluster_set = set(eval_labels)
    prod_labels_unique = set(prod_labels)

    uncovered = prod_labels_unique - eval_cluster_set
    uncovered_ratio = len(uncovered) / len(prod_labels_unique)

    # Flag clusters that represent >5% of production traffic
    prod_counts = np.bincount(prod_labels, minlength=n_clusters)
    significant_uncovered = [
        c for c in uncovered
        if prod_counts[c] / len(production_queries) > 0.05
    ]

    return {
        "total_clusters": n_clusters,
        "uncovered_clusters": len(uncovered),
        "uncovered_ratio": uncovered_ratio,
        "significant_uncovered_count": len(significant_uncovered),
        "coverage_score": 1.0 - uncovered_ratio,
        "needs_refresh": uncovered_ratio > 0.20 or len(significant_uncovered) > 0,
    }
```

Rule: if >20% of production clusters lack eval coverage, or any single uncovered cluster represents >5% of traffic, the eval set needs a refresh cycle before the next deploy gate.

### 3. Annotation Consistency Drift

When new eval cases are added, measure inter-annotator consistency against the original baseline:

```python
def annotation_consistency_check(new_cases: list[dict],
                                  judge_fn,
                                  original_baseline_consistency: float = 0.87
                                  ) -> dict:
    """
    Measure whether new eval cases are labeled consistently with the original standard.
    A drop in internal consistency signals that either:
    (a) the new cases are harder/more ambiguous, or
    (b) the labeling standard has drifted.
    """
    # Run each case through the judge twice at identical temperature
    results = []
    for case in new_cases:
        run_a = judge_fn(case["input"], case["expected_output"], temperature=0.0)
        run_b = judge_fn(case["input"], case["expected_output"], temperature=0.0)
        results.append({"case_id": case["id"], "agree": run_a == run_b})

    consistency = np.mean([r["agree"] for r in results])

    return {
        "current_consistency": consistency,
        "baseline_consistency": original_baseline_consistency,
        "consistency_delta": consistency - original_baseline_consistency,
        "drift_detected": consistency < (original_baseline_consistency - 0.05),
        "recommendation": (
            "re-annotate" if consistency < original_baseline_consistency - 0.10
            else "review hard cases" if consistency < original_baseline_consistency - 0.05
            else "acceptable"
        ),
    }
```

## When to Refresh the Eval Set

Build refresh into the release cycle, not into crisis:

- **Cadence**: refresh eval set quarterly, or whenever coverage gap exceeds 20%, whichever comes first.
- **Sources**: pull the top 20% of production queries by volume that aren't already covered. Add adversarial/problematic cases from incident reports. Remove cases the agent now solves 100% of the time (they add no signal).
- **Versioning**: tag each eval set version and run every eval gate against the current set *and* the previous one to measure whether the agent regressed on the old cases.
- **The regression budget**: define a maximum acceptable pass→fail flip rate on existing cases (typically 0–2% depending on safety criticality). If the refresh reveals new failures on old cases, investigate before attributing to eval drift.

> Receipt pending — 2026-07-21. Pattern synthesized from agentmodeai.com (May 2026 eval monitoring guide), benchmarkingagents.com Vol. III (Apr 2026), GettIA eval set maintenance research, and Statsig continuous evaluation framework. Code examples are illustrative; integrate with your actual embedding provider and eval infrastructure.

## Forces (revisited)

- **Eval set drift is faster than model drift.** A model doesn't change between versions unless you redeploy. But production query distribution changes continuously with product updates, seasonal patterns, and user behavior shifts. Your eval set can be stale within weeks of a product release.
- **The eval set is a product artifact, not a one-time deliverable.** Teams budget for model retraining but rarely budget for eval set maintenance. The measurement instrument is treated as free to operate, which guarantees it degrades.

## See also

- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — the foundational eval stack; this entry covers the gap where offline eval goes stale
- [S-1026 · The PAEF Stack](s1026-the-paef-stack-when-your-benchmark-says-pass-but-4-out-of-7-failure-modes-sneaked-past.md) — output distribution drift as a complementary signal to input distribution drift
- [S-1004 · The Agent Eval Stack](s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — eval maintenance costs and the staleness problem
