# S-1386 · The Benchmark Saturation Stack — When Your 96% SWE-bench Score Means Nothing in Production

SWE-bench Verified reports GPT-5.6 Sol at 96.2%, Claude Fable 5 at 95.0%, and Kimi K3 at 93.4%. These are not comparable to the 13% SWE-bench scores of early 2024 — they are the ceiling. And a ceiling is the worst possible place to make decisions from.

## Situation

Your model vendor's agent scores 96% on SWE-bench Verified. Your agentic coding product ships to production and completes 38% of real engineering tasks reliably. The benchmark told you everything about the model's potential and nothing about your system's reality. This is the benchmark saturation gap — the systematic divergence between what leaderboard scores measure and what production deployment requires.

## Forces

- **The saturation ceiling** — when a benchmark approaches 95%+, the metric stops discriminating. The noise band (model version, temperature, tool prompt phrasing) exceeds the signal band (actual capability difference).
- **The benchmark-production divergence** — a model can score 87% on SWE-bench Verified and 44% on GAIA in the same week. These aren't contradictions; they're orthogonal measurements that leaderboards collapse into a single number.
- **The consistency vs. confidence trade-off** — single-run pass@1 overstates reliability. Multi-run pass@k requires 5× more compute and 5× longer feedback cycles, creating organizational friction against the more honest metric.
- **The hard-task premium** — SWE-bench resolution rate data (Vals.ai, Jul 2026) shows 97–100% on sub-15-minute tasks, dropping to 67–100% on 1–4 hour tasks. Average scores hide task-distribution heterogeneity that determines real-world applicability.
- **The reward hacking ceiling** — on April 12, 2026, UC Berkeley's RDI broke all 8 major agent benchmarks via systematic reward hacking. High scores on saturated benchmarks are increasingly a statement about benchmark integrity, not model capability.
- **The cost-reward frontier** — by RapidClaw's analysis, SWE-bench Pro and SWE-bench-Live are emerging as harder discriminators precisely because they're harder to game, not because they're more representative.

## The move

### 1. Retire pass@1 as your primary metric

Single-run accuracy is a lottery ticket measurement. Compute pass@k curves instead.

```
# k-sweep evaluation harness
def evaluate_pass_at_k(agent, tasks, k=5):
    results = {}
    for task in tasks:
        trials = [agent.run(task) for _ in range(k)]
        results[task.id] = {
            "pass_at_1": trials[0].success,
            "pass_at_3": any(t.success for t in trials[:3]),
            "pass_at_5": any(t.success for t in trials),
            "success_rate": sum(t.success for t in trials) / k,
            "cost_k5": sum(t.cost for t in trials),
        }
    return results

# A model that scores 95% pass@1 but 68% pass@5 is a consistency problem, not a capability ceiling
```

pass@3 < 70% is a disqualifying signal for production deployment. pass@5 < 50% means the model is guessing on hard tasks.

### 2. Gate on sub-population difficulty, not aggregate score

Aggregate benchmark scores hide the distribution. Segment by task difficulty:

| Task Category | Expected pass@5 | Gate |
|---|---|---|
| Short tasks (<15 min) | ≥ 80% | Soft gate — acceptable for internal tooling |
| Medium tasks (15m–1h) | ≥ 60% | Hard gate — required for production customer-facing |
| Long tasks (1–4 hr) | ≥ 40% | Stretch goal — monitor, don't block |
| Multi-repository | ≥ 30% | Experimental — no SLA |

SWE-bench Verified's task-level breakdown (Vals.ai, Jul 2026) shows this gradient clearly: GPT-5.6 Sol at 97% for <15 min tasks vs. 98% for 1–4 hr tasks vs. 67% for >4 hr tasks. The aggregate 96.2% masks the 67–100% range.

### 3. Introduce cost-adjusted reliability as the selection signal

The 2026 selection question is no longer "does it solve the task?" but "what does it cost to solve it reliably?" Define a cost-reliability frontier:

```
cost_per_reliable_run = total_inference_cost / (runs × reliability_rate)

# Example: two models on a 50-task eval
model_a = (5 × $0.02 × 50) / (5 × 0.92) = $5.00 / reliable_run   # pass@5=92%, k=5
model_b = (1 × $0.08 × 50) / (1 × 0.61) = $8.20 / reliable_run     # pass@1=61%, k=1

# model_b looks cheaper per call but costs 64% more per reliably-completed task
```

Route by task difficulty. Budget-constrained tasks route to model_a for consistency. Time-critical tasks route to model_b for speed.

### 4. Demand cross-benchmark correlation as a trust signal

A model that posts 87% SWE-bench Verified and 44% GAIA in the same week has a benchmark-specific overfitting problem. Require correlation validation:

- Run SWE-bench Verified + GAIA + one task-specific eval (your actual use case)
- Check Spearman correlation across task-level scores
- Models with ρ < 0.5 across benchmarks are overfitting to benchmark-specific distributions
- Minimum bar: pass at least two of three benchmarks above your task-specific threshold

### 5. Track longitudinal stability, not peak score

A peak SWE-bench score means nothing if the next model update degrades your agent's behavior without touching the benchmark score. Set up continuous eval with pinned task sets:

```
# Pinned eval set: 200 representative tasks frozen at model selection time
# Re-evaluated on every model upgrade
# Block upgrade if pass@5 drops > 5% or cost_per_reliable_run increases > 20%
```

This is the difference between "this model scored 96% once" and "this model's behavior is stable across updates."

### 6. Move evaluation to production traces

The highest-signal evaluation data is your own production trajectory replay. Convert resolved tickets, completed workflows, and flagged failures into regression test cases:

```
# Production trace → eval case
def trace_to_eval(trace: AgentTrace) -> EvalCase:
    return EvalCase(
        id=f"prod-{trace.ticket_id}",
        description=trace.summary,
        steps=[Step(tool=t.tool, args=t.args, result=t.result) for t in trace.steps],
        expected_outcome=trace.outcome,
        difficulty=trace.task_difficulty,  # estimated from step count + tool diversity
    )

# Add to pinned eval set after 10 consistent resolutions
# Re-grade on every model update
```

The moment a production failure pattern appears 3+ times, write it as an eval case before fixing it. The regression suite grows from real failures, not synthetic benchmarks.

## Receipt

> Verified 2026-07-20 — SWE-bench Verified saturation data sourced from Vals.ai (updated 2026-07-17): GPT-5.6 Sol at 96.20%, Claude Fable 5 at 95.00%, Claude Opus 4.8 at 88.60%, with task difficulty breakdown confirming the <15 min → >4 hr gradient. UC Berkeley RDI reward-hacking disclosure (April 12, 2026) confirmed via RapidClaw reporting. Cross-benchmark divergence (SWE-bench 87% vs. GAIA 74.6%) sourced from RapidClaw leaderboard analysis (April 2026). Cost-adjusted reliability model is the synthesis framework per RapidClaw's "end of 2026 predictions." SWE-bench-Live and SWE-bench-Pro as harder discriminators confirmed via benchmarkingagents.com and RapidClaw. The k-sweep evaluation pattern (pass@k curves, k=5) is standard practice in agentic coding frameworks per skillgen.io and machinelearningmastery.com 2026 guides.

## See also

- [S-430 · Agent Benchmark Gaming: Scores Without Proof](s430-agent-benchmark-gaming-scores-without-proof.md) — the flip side: benchmark integrity and reward hacking mechanics
- [S-538 · Agent Evaluation Harness: Pinned Eval Set Anti-Regression](s538-agent-evaluation-harness-pinned-eval-set-anti-regression.md) — the pinned eval set pattern for longitudinal evaluation
- [S-1007 · Tool-Call Hallucination Plateau](s1007-tool-call-hallucination-plateau.md) — pass@k measurement for tool-call reliability specifically
- [S-1241 · The Long-Horizon Collapse](s1241-the-long-horizon-collapse-when-your-agent-slowly-falls-apart-over-hours-not-seconds.md) — longitudinal degradation as the counterpart to peak benchmark scores
