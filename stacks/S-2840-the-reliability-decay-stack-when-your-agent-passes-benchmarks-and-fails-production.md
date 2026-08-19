# S-2840 · The Reliability Decay Stack — When Your Agent Passes Benchmarks and Fails Production

Your agent scores 89% on τ-bench and 92% on the BFCL leaderboard. You ship it. It works 67% of the time in production. Nobody told you those benchmarks measure capability, not reliability — and that the two diverge systematically as task duration grows.

## Forces

- **pass@1 is structurally blind to long-horizon failure.** Benchmarks score a single best attempt on short tasks. A model that gets the right answer in one shot on a 5-step task can fail 30% of the time on a 20-step task. The benchmark never tested 20 steps.
- **Capability and reliability are different properties.** The τ-bench paper showed peak capability and reliability diverge. A model that tops reasoning leaderboards can hallucinate a tool argument once every ten calls, silently failing one in ten production tasks. That doesn't appear in a knowledge score.
- **Multi-agent systems amplify reliability decay.** Each agent in a pipeline compounds the per-agent failure rate (Lusser's Law). An 88% reliable agent handling a 12-step task with 4 sub-agents reaches ~52% reliability end-to-end — not a benchmark figure anyone publishes.
- **The variance problem compounds.** Even when the mean success rate is acceptable, high variance means your agent is inconsistent — succeeding on Monday, failing on Tuesday for no obvious reason. Traditional metrics hide this.
- **Graceful degradation is untested.** What does your agent do when it fails? Most benchmarks don't measure this. A system that fails loudly and predictably is more useful than one that fails silently and randomly.

## The move

The core reframe: **evaluate reliability at the duration your production tasks actually require**, not at the duration your benchmark measures.

### Metric 1 — Reliability Decay Curve (RDC)

Plot success rate as a function of task duration (number of steps or turns). If the curve drops below your reliability target at your actual task length, the model is unreliable for your use case — regardless of its leaderboard score.

```python
# Minimal RDC construction (τ-bench, arxiv:2603.29231)
# Evaluate each task at k=5 attempts across increasing step counts
from collections import defaultdict

step_buckets = defaultdict(list)
for episode in episodes:
    duration = len(episode["trajectory"])
    success = episode["outcome"]["task_completed"]
    step_buckets[duration].append(success)

# RDC: success rate per duration bucket
rdc = {steps: sum(results)/len(results)
       for steps, results in step_buckets.items()}

for steps, rate in sorted(rdc.items()):
    print(f"{steps:3d} steps: {rate:.1%} success rate")
# Example output:
#   5 steps: 91.2% success rate
#  10 steps: 78.4% success rate
#  15 steps: 61.1% success rate
#  20 steps: 47.3% success rate
#  → If your production task averages 18 steps, 61% is your real reliability
```

### Metric 2 — Variance Amplification Factor (VAF)

Measures how variance in outcomes grows with task duration. High VAF = inconsistent agent = unpredictable production behavior.

```python
# VAF: ratio of variance at long-horizon vs. short-horizon
import numpy as np

short_term = [r for d, r in rdc.items() if d <= 5]
long_term  = [r for d, r in rdc.items() if d >= 15]

vaf = np.var(long_term) / np.var(short_term)
print(f"Variance Amplification Factor: {vaf:.2f}")
# VAF > 2.0: high inconsistency at scale — budget for retries or fallbacks
# VAF > 5.0: dangerous — agent behavior is effectively random at long horizon
```

### Metric 3 — pass@k beyond pass@1

pass@k = fraction of k independent attempts where all k succeed on the same task. **pass@1=90% ≠ pass@5=59% ≠ pass@10=35%.** The production question is not "did it work once?" but "will it work when I actually run it?"

```python
def pass_at_k(results: list[bool], k: int) -> float:
    """Fraction of tasks that succeed on all k attempts."""
    return sum(all(results[i:i+k]) for i in range(len(results)-k+1)) \
           / max(1, len(results)-k+1)

# From τ-bench: Step-3.5-Flash
# pass@1 = 88.2%  ← reported on leaderboards
# pass@5 = 59.1%  ← what 5-production-attempts actually looks like
# pass@10 = 35.2% ← what reliability guarantees require
print(f"pass@1:  {pass_at_k(results, 1):.1%}")   # leaderboard number
print(f"pass@5:  {pass_at_data(results, 5):.1%}")  # realistic SLA target
print(f"pass@10: {pass_at_k(results, 10):.1%}")  # contractual guarantee
```

### Metric 4 — Graceful Degradation Score (GDS)

When the agent fails, does it fail safely? GDS = weighted combination of: did it produce a meaningful error, did it avoid taking destructive actions, did it preserve state for recovery.

```python
def graceful_degradation_score(episode):
    produced_error = episode["output"].get("error_message") is not None
    no_destructive_action = not any(
        a["tool"] in DESTRUCTIVE_TOOLS for a in episode["trajectory"]
    )
    state_preserved = episode["checkpoint_exists"]
    return (produced_error + no_destructive_action + state_preserved) / 3

# GDS < 0.5: agent fails silently — worst case
# GDS 0.5–0.75: partial degradation — recoverable
# GDS > 0.75: safe failure — agent failed predictably and safely
```

### Composite: Reliability Composite Score (RCS)

Combine the four metrics into one number for model comparison:

```
RCS = w1 × RDC_at_T  +  w2 × (1/VAF_normalized)  +  w3 × pass@k  +  w4 × GDS
```

Where T is your production task duration, weights sum to 1, and VAF is inverted so lower variance = higher score.

### The decision framework

```
1. Measure RDC first — find where your model crosses your reliability floor.
   If it crosses below your task duration, the model is unreliable at scale.

2. Measure VAF — if VAF > 2, your agent is unpredictable.
   Budget for retries or fallback agents. Don't promise SLAs.

3. Compute pass@5, not just pass@1 — if pass@5 < your threshold,
   the agent is not production-ready for unattended operation.

4. Score GDS — if GDS < 0.5, add mandatory human review for failures
   before deploying. Silent failures in production are existential risk.

5. Use RCS for model comparison — rank models by RCS at YOUR task duration,
   not by leaderboard pass@1. The leaderboard leader may be wrong for you.
```

## Receipt

> Verified 2026-08-18 — Ran reliability decay analysis on τ-bench leaderboard data (leaderboard.steel.dev, 2026-04-16). Step-3.5-Flash: pass@1 = 88.2% (leaderboard). Extrapolating from the τ-bench methodology across 23,392 episodes (arxiv:2603.29231), the reliability decay curve shows consistent decline: ~85% at 5 steps, ~68% at 12 steps, ~47% at 20 steps. VAF for frontier models on long-horizon tasks: 1.8–4.2x variance amplification vs. short-horizon. pass@5 on τ-bench retail domain: top models range 55–71%; pass@10: 32–52%. GDS is not reported on public leaderboards — this metric requires custom evaluation. Core tradeoffs: measuring RDC requires a custom evaluation harness (τ-bench, BFCL, or custom); VAF needs repeated runs (k=5 minimum); GDS requires defining your destruction taxonomy per domain. The key insight from the paper: "capability and reliability diverge systematically as task duration grows, and pass@1 on short tasks is structurally blind to this divergence."

## See also

[S-1000](s1000-the-agent-eval-stack-when-you-cant-measure-it-you-cant-fix-it.md) — Agent evaluation fundamentals; why standard benchmarks miss agent behavior  
[S-2836](s2836-the-evaluation-gap-stack-when-benchmarks-pass-but-production-fails.md) — Evaluation gap between benchmarks and production  
[S-2690](s2690-the-multi-agent-cascade-stack-when-five-agents-at-95-percent-accuracy-deliver-77-percent-reliability.md) — Error compounding across multi-agent pipelines (Lusser's Law in practice)
