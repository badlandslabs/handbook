# S-2486 · The Synthetic Collapse Stack — When Your Fine-Tuned Agent Gets Worse Over Time

You spent six weeks and $18,000 fine-tuning a domain-specialist agent. The first version was excellent — 91% task accuracy on your internal eval. Three months later, after retraining on agent-generated data, accuracy is 67%. The model still passes your eval suite (your eval suite also trained on synthetic data). You have quietly created a local model collapse, and you are the only one who doesn't notice until users start complaining.

This is not a training bug. It is a structural failure mode of any fine-tuning pipeline that generates its own training data without anchor constraints.

## Forces

- **Synthetic data is cheap to generate and expensive to validate.** A Magpie or Self-Instruct pipeline can produce 100K instruction examples in hours. Filtering them down to 5K high-quality examples requires either human annotation (expensive) or automated quality filters (themselves LLM-based, hence circular). (Source: [CallSphere, 2026](https://callsphere.ai/blog/vw8g-synthetic-data-generation-fine-tuning-2026))
- **The 25% real-data rule is known but violated under pressure.** Research consistently shows that maintaining ≥25% real, human-generated data prevents collapse. Teams violate this rule when production data is scarce, legally restricted, or expensive to label — the exact conditions that make synthetic data appealing. (Source: [Nature, s44387-026-00127-w](https://www.nature.com/articles/s44387-026-00127-w.pdf))
- **Eval suites collapse alongside the model.** If your eval harness is generated from the same distribution as your training data, it passes the collapsing model. The ForTIFAI paper (Nature, 2026) documents this: recursive training on synthetic data degrades both capability and discriminability simultaneously — the model becomes worse AND your test suite stops detecting it. (Source: [ForTIFAI, Nature 2026](https://www.nature.com/articles/s44387-026-00127-w.pdf))
- **Generational drift compounds.** Train model V1 on real data. V2 on 80% V1 output + 20% real. V3 on 80% V2 output + 20% real. By V3 the distribution has shifted enough that the model's "style" dominates but its "knowledge" has thinned. The tails of the distribution — rare edge cases, niche domain knowledge — disappear first.

## The move

### Layer 1 — Real Data Anchor (mandatory floor)

Never train below 25% human-generated examples. Treat this as a hard constraint, not a guideline. In practice:

```
# Data mix constraint — enforce in pipeline, not policy
def mix_ratio(pairs):
    real = [p for p in pairs if p.source == "human"]
    synth = [p for p in pairs if p.source == "synthetic"]
    if len(real) / len(pairs) < 0.25:
        raise DataMixViolation(f"Real data: {len(real)/len(pairs):.1%} < 25% minimum")
    return True
```

Track the ratio per capability cluster (e.g., tool calling, reasoning, domain knowledge) — not just overall. A model can pass the aggregate threshold while having a collapsed subset.

### Layer 2 — Quality Filtering Funnel (100K → 5K)

Raw synthetic output → diversity filter → quality filter → deduplication → human spot-check.

```
# 100K → 5K pipeline (CallSphere, 2026)
raw = generate_via_magpie(n=100_000)

# 1. Diversity filter: discard near-duplicates (embedding similarity > 0.95)
filtered = diversity_filter(raw, threshold=0.95)  # ~100K → ~40K

# 2. Quality filter: LLM-as-judge scoring (1-5 scale, discard ≤3)
scored = judge_score(filtered, min_score=4.0)    # ~40K → ~12K

# 3. Capability cluster balance: max 20% from any single cluster
balanced = cluster_balance(scored, max_per_cluster=0.20)  # ~12K → ~8K

# 4. Human spot-check: 2% random sample reviewed by annotator
verified = human_spot_check(balanced, sample_rate=0.02)   # ~8K → ~5K
```

### Layer 3 — Distributional Health Monitoring

Track statistics across generations, not just aggregate quality:

```
# Per-generation health metrics (watch for collapse signals)
metrics = {
    "perplexity_shift": current_perplexity - baseline_perplexity,
    "output_entropy": measure_token_entropy(sample_outputs),
    "rare_token_freq": count_rare_token_occurrences(outputs, threshold=1e-5),
    "capability_cluster_retention": count_retained_clusters(eval_clusters),
}

# Collapse is signaled by: entropy drops + rare token freq drops + cluster retention drops
# All three together = collapse. Any one alone = normal variation.
```

### Layer 4 — Eval Suite Independence

Keep the eval harness grounded in real-world data, not synthetic data:

```
# Eval suite construction — never generate evals from training distribution
eval_examples = human_annotate(real_production_samples)  # real data only
eval_examples = augment_with_expert_edge_cases(eval_examples)  # human-crafted

# Evals generated from synthetic data are circular — they measure whether
# the model matches its own output, not whether it solves the real task.
```

## Receipt

> Verified 2026-08-11 — Sources confirmed: ForTIFAI (Nature s44387-026-00127-w, 2026) documents recursive training collapse in synthetic-dominant pipelines. CallSphere blog (Apr 2026, updated Aug 2026) provides the 100K→5K filtering pipeline. The 25% real-data threshold is documented across multiple sources (Nature, aitechconnect, whysogeek, 2026). ARC paper (arXiv:2607.25066) referenced for context management but not directly applicable to this entry. Framework lock-in and checkpoint-resume patterns verified as separate coverage areas.

## See also

- [S-820 · The Memory Poisoning Defense Stack](stacks/s820-the-memory-poisoning-defense-stack-when-your-agent-remembers-the-wrong-lessons.md) — External data poisoning; this entry covers self-generated data poisoning
- [S-2337 · The Fail-Plausible Fabrication Stack](stacks/s2337-the-fail-plausible-fabrication-stack-when-your-agent-turns-errors-into-convincing-success-stories.md) — Failure taxonomy and detection; complements this entry's quality monitoring layer
- [S-1005 · AI SRE](stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — Behavioral SLOs and drift detection; the health metrics in this entry feed into SLO tracking
