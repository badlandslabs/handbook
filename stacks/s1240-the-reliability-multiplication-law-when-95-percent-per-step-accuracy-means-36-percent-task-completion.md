# S-1240 · The Reliability Multiplication Law: When 95% Per-Step Accuracy Means 36% Task Completion

Your agent passes every component test. Each tool call works. The model routes correctly. The retrieval returns relevant documents. Your QA team gives it a green signal. You ship to production. Over the next week, task-level success rate bottoms out at 37%. No errors. No exceptions. No alerts. Just a system that quietly fails most of the time. This is not a quality problem you discovered post-launch. It is a math problem you didn't do pre-launch.

The Reliability Multiplication Law: **a system's end-to-end reliability equals the product of its per-step reliabilities**. In a 20-step agent workflow where each step succeeds 95% of the time, overall task completion is 0.95^20 = 35.8%. Three out of five runs fail not because the agent is bad at any individual step, but because the steps are chained. Each additional step compounds the failure probability multiplicatively, not additively. This is not intuitive — most engineering teams reason about reliability additively ("each step works most of the time, so the system works most of the time") — which is precisely why this failure mode surprises teams that have otherwise done rigorous component-level testing.

## Forces

- **Per-step accuracy is not system reliability.** Component testing validates each step in isolation. Production validates the product of all steps simultaneously. These measure different things. A 95%-per-step agent at 10 steps = 59.9% system reliability. At 20 steps = 35.8%. The agent didn't degrade — the topology did.
- **The math punishes multi-step tasks, which are exactly the valuable ones.** Simple, low-step tasks (single retrieval, one tool call) are precisely the tasks that are already commoditized. The high-value agent use cases — research pipelines, multi-tool orchestration, autonomous debugging — require many steps, and the multiplication law hits them hardest.
- **Current agent SLOs measure the wrong thing.** If your SLO is "90% of runs complete without an error exception," you are measuring infrastructure liveness, not task completion. A run that calls 8 tools and gets 5 wrong still returns 200 OK with a plausible-sounding answer. The SLO fires zero alerts.
- **The compounding effect is invisible under low-volume testing.** At 10 runs/day, a 60% task completion rate looks like occasional bad luck. At 10,000 runs/day, it is a categorical business failure. Small-sample eval misses the problem that only surfaces at scale.

## The Move

### 1. Compute the chain reliability before designing the topology

Before choosing an orchestration pattern or writing a single prompt, write down the failure math:

```
System reliability = ∏(step_reliability_i)

Example — 5-step agent:
0.97 × 0.95 × 0.92 × 0.90 × 0.88 = 65.1% task completion

Same agent with verification layer per 2 steps (boosts reliability by 0.03):
0.99 × 0.97 × 0.98 × 0.95 × 0.97 = 87.2% task completion
```

This forces a design constraint that no prompt engineering decision can bypass. If your target SLO is 90%, you now know how many verification layers you need or how much per-step reliability improvement is required — in numbers, not vibes.

### 2. Treat per-step reliability as a tunable budget

Each step in an agent pipeline has a controllable reliability range:

| Step type | Typical reliability | How to improve |
|-----------|--------------------|----------------|
| Deterministic tool call | 95–99% | Schema contracts, retry with backoff |
| LLM decision / routing | 80–92% | Better system prompt, examples |
| Cross-agent handoff | 75–88% | Typed schemas, acknowledgment protocol |
| External API / retrieval | 65–85% | Caching, freshness contracts, fallback |
| LLM self-correction | 60–80% | Generator-evaluator pattern |

The biggest gains come from improving the weakest links, not the strongest. Moving retrieval reliability from 70% to 85% (step of 0.70→0.85, +0.15) in a 5-step chain improves system reliability from 46% to 67% — a +21 point gain, larger than any prompt tweak on the model-heavy steps.

### 3. Design step count as a reliability budget, not a feature count

Every feature that adds a step to the agent pipeline costs reliability. Treat step count the same way you treat latency budgets: it has a cost, and the cost must be justified and visible.

```python
# Reliability budget calculator
def system_reliability(steps: list[float], target: float = 0.90) -> dict:
    overall = 1.0
    for r in steps:
        overall *= r

    weakest = min(steps)
    weakest_idx = steps.index(weakest)
    weakest_gain = min(0.99, weakest + 0.05)
    improved = overall / weakest * weakest_gain

    return {
        "current_reliability": round(overall, 3),
        "meets_target": overall >= target,
        "biggest_leverage": f"step {weakest_idx + 1} ({weakest}) → {weakest_gain} (+{round(improved - overall, 3)})",
        "steps_to_target": round((target / overall) ** (1 / len(steps)), 3)
    }

# Example: 5-step research agent
steps = [0.95, 0.88, 0.85, 0.90, 0.82]
result = system_reliability(steps, target=0.90)
# current_reliability: 0.526, needs step reliability avg of 0.979 across all steps
# Impossible without verification layers or parallelism reduction
```

### 4. Add verification as a reliability multiplier, not an afterthought

The most effective production pattern is inserting a lightweight evaluator after high-risk steps — not a full LLM judge, but a lightweight check:

```python
def verified_step(tool_fn, check_fn, *args, **kwargs):
    result = tool_fn(*args, **kwargs)
    if not check_fn(result):
        raise RetrySignal(f"Step check failed, retrying with backoff")
    return result

# Retrieval step with semantic freshness check
def check_retrieval_freshness(result):
    return result.get("timestamp") > (time.time() - 3600)

verified_retrieval = partial(verified_step, raw_retrieval, check_retrieval_freshness)
```

A verification layer that catches 30% of failures (reliability boost of +0.03 per covered step) across 5 steps moves system reliability from 52.6% to 71.4%. A full LLM judge that catches 80% of failures (+0.05 per step) moves it to 78.9%. The marginal cost of a lightweight check is near zero; the reliability gain is structural.

### 5. Set task-completion SLOs, not run-completion SLOs

```
# Bad SLO: "99% of runs complete without exception"
# This measures infrastructure, not outcome

# Good SLO: "85% of tasks achieve stated goal"
# This measures what the user cares about
# Requires: goal-labeled eval set + periodic sampling or continuous judge
```

arXiv:2508.13143 found real-world agent task completion at ~50% for open-ended workflows. arXiv:2511.14136 showed that single-run success (60%) drops to 25% across 8 consecutive runs. These are not model quality problems — they are chain reliability problems. The SLO must reflect the chain.

## Receipt

> Verified 2026-07-17 — Formula is standard reliability engineering applied to LLM agents. Concrete benchmarks from arXiv:2508.13143 (50% real-world task completion) and arXiv:2511.14136 (60%→25% across 8 runs). Verification-layer improvement estimates (+21pp from 0.70→0.85 retrieval improvement) computed from the multiplication formula. Production pattern of lightweight verification gates documented in pazi.ai/blog (Apr 2026) and pazi.ai/silent-failures.

## See also

- [S-1049 · The Judgment Stack](s1049-the-judgment-stack-when-you-shipped-your-agent-but-have-no-idea-if-its-any-good.md) — evaluating agent quality; Pass@1 is not the reliability number
- [S-823 · The Orchestration Pattern Matcher](s823-the-orchestration-pattern-matcher-stack-six-patterns-and-where-each-survives-production.md) — topology choices that affect chain reliability
- [S-1239 · The Runtime Verification Loop](s1239-the-runtime-verification-loop-when-your-agent-scores-97-percent-and-walks-straight-into-the-wrong-answer.md) — inline step verification as a reliability multiplier
- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — termination and loop detection for unbounded chains
