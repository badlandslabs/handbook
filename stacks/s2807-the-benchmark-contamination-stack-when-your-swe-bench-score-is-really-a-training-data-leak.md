# S-2807 · The Benchmark Contamination Stack — When Your SWE-Bench Score Is Really a Training-Data Leak

Your model scores 81% on SWE-bench Verified. Your engineering team sees this, benchmarks look good, you ship. The model is actually solving roughly 23% of novel software engineering tasks. The 58-point gap is not a calibration problem — it is a training-data contamination problem hiding inside a performance metric.

## Situation

SWE-bench Verified became the de facto measure of AI coding capability in 2024–2025. Top models climbed from ~13% in early 2024 to 78–81% by early 2026. In February 2026, OpenAI published an audit explaining why it was permanently stopping SWE-bench Verified score reporting: the improvements no longer reflected genuine capability gains — they reflected how much the model had been exposed to the benchmark at training time.

SWE-bench Pro was designed by Scale AI specifically to address this. Its 1,865 instances are drawn from:
- **Held-out public codebases** governed by strong copyleft licenses (GPL-class), whose "viral" licensing makes them legally unlikely to appear in training scrapes
- **Completely private commercial codebases** from enterprise startups — never available to any model's training data

On Pro's private dataset, top models average 23–46%. Claude Opus 4.7 hits 64.3% on public held-out; drops to ~46% on private. The SWE-bench Verified score was not a performance metric — it was a training-data leak indicator.

## Forces

- **Public GitHub solutions are a contamination chokepoint.** Any model trained on GitHub data after mid-2024 has likely seen substantial portions of SWE-bench Verified solutions. The test exists publicly. The answers exist publicly. Models memorized the answers, not the reasoning.
- **You cannot fix contamination retroactively.** Once a model was trained on the data, no amount of prompting or fine-tuning removes the contamination signal. The score is structurally invalid for that model, regardless of what you do at inference time.
- **Your procurement decision used a contaminated metric.** If your team evaluated agents using SWE-bench Verified scores (as most did), your benchmark-to-production gap was baked in at evaluation time, not deployment time.
- **Pro has its own limits.** Private commercial datasets introduce IP and confidentiality concerns. Held-out public codebases still risk indirect contamination from similar patterns. SWE-bench Pro is a better measure, not a perfect one.
- **TerminalBench and LiveCodeBench add orthogonal signals.** TerminalBench tests real shell interactions against private HackerRank tasks. LiveCodeBench tracks continuous contamination over time. No single benchmark is sufficient.

## The move

**1. Treat SWE-bench Verified as a training-data leak test, not a capability benchmark.**
A high Verified score means your model has seen those tasks. A high Pro score means it can generalize. Report both. If a vendor only shows Verified, ask why.

**2. Audit your evaluation stack for contamination risk.**
Any benchmark task whose solution is publicly visible on GitHub is potentially contaminated for any model trained post-publication. Build a contamination registry:
```
tasks = load_benchmark("my-eval-set")
for task in tasks:
    if solution_publicly_visible(task):
        flag(task, "CONTAMINATION-RISK")
    elif task_from_private_repo():
        flag(task, "CANDIDATE-CLEAN")
    else:
        flag(task, "UNKNOWN")
```
Use clean tasks for procurement decisions. Use contaminated tasks only for regression detection (did the model un-learn something it was supposed to know?).

**3. Build a private benchmark from your own codebase.**
The only contamination-proof evaluation is one built from code no model has ever seen: your private repositories, with real issues and real test suites. Structure it as:
- Representative task extraction (extract 50–200 real issues per quarter)
- Automated test-suite verification (run the actual test suite against the generated patch)
- Longitudinal tracking (same codebase, different quarters, measures genuine improvement)

**4. Use TerminalBench as a complementary signal.**
TerminalBench (private HackerRank tasks) tests end-to-end agent behavior — not just patch generation, but the full trajectory: understand issue → run commands → write code → verify. This catches scaffold failures that code-generation benchmarks miss.

**5. Watch LiveCodeBench for temporal contamination.**
LiveCodeBench re-generates tasks monthly from recent GitHub commits, making it harder to contaminate via memorization. Use it as a trending indicator: if your model's LiveCodeBench score tracks Verified but diverges from Pro, contamination is the likely cause.

```python
# Composite benchmark hygiene check
def benchmark_hygiene_score(model_name, verified_score, pro_score, livecode_score):
    """Returns (hygiene_score, recommendation)"""
    contamination_gap = verified_score - pro_score
    verified_livecode_divergence = abs(verified_score - livecode_score) / verified_score

    if contamination_gap > 40:
        return 0, "CRITICAL: Verified score likely contaminated. Do not use for procurement."
    elif contamination_gap > 20:
        return 1, "WARNING: Significant gap. Weight Pro heavily; use Verified only for regression."
    elif verified_livecode_divergence > 0.3:
        return 2, "CAUTION: Verified diverges from LiveCodeBench. Investigate training data overlap."
    else:
        return 3, "ACCEPTABLE: Scores consistent across contamination-resistant measures."
```

## Receipt

> Verified 2026-08-18 — SWE-bench Verified→Pro gap (81%→23%) sourced from OpenAI audit (Feb 2026) and byteiota.com aggregation of Scale AI Pro leaderboard data. Scale AI SWE-Bench Pro leaderboard (labs.scale.com/leaderboard/swe_bench_pro_private) shows Claude Opus 4.7 at 64.3% public / ~46% private. Wasyra engineering blog (April 2026) independently reproduces the 23% top-model-average finding on Pro private dataset. tianpan.co (April 2026) independently reports the 30-point delta (Verified→Pro) as the "real coding capability gap." AgentMarketCap (April 2026) documents the OpenAI Verified retirement. All figures cited are from primary sources or directly verifiable primary aggregations. Code example is illustrative — the hygiene_score function is a pattern description, not a validated instrument.

## See also

- [S-2671 · The Evaluation Gap Stack](/stacks/s2671-the-evaluation-gap-stack-when-your-agent-aces-the-benchmark-and-flops-in-production.md) — general eval gap framing
- [S-996 · The Harness Matters More Stack](/stacks/s996-the-harness-matters-more-stack-when-your-model-isnt-the-problem.md) — harness-driven improvement
- [S-1007 · The Tool-Call Hallucination Plateau](/stacks/s1007-tool-call-hallucination-plateau.md) — pass@k vs single-run accuracy
