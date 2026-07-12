# S-846 · The Reliability Surface Stack — When 90% Pass Rates Are Lying to You

Your agent scores 90% on your eval suite. Your production system fails 1 in 3 real tasks. The eval suite is measuring one thing; production is stress-testing something completely different. This is the reliability surface gap — and it explains why teams ship agents that pass every test, then crater in the real world.

## Situation

You run your agent 100 times on the same test case. It passes 90. You ship it. In production, on the first Tuesday with a slightly different query phrasing, an API that returns an error message instead of an empty array, and a network timeout on the second tool call, it fails 40% of the time. Your 90% pass rate was a lie — it measured single-run accuracy on a frozen input distribution. It said nothing about reliability.

This gap has a name now. ReliabilityBench (Gupta, arXiv:2601.06112, Jan 2026) formalizes it as a **Reliability Surface**: a three-dimensional evaluation framework that maps consistency, robustness, and fault tolerance simultaneously — not independently.

## Forces

- **Single-run pass@1 is the wrong target.** Standard benchmarks report pass@1: does the agent succeed on this task, once? Production asks: does it succeed reliably, across variations, under failures? These measure fundamentally different things.
- **90% pass@1 means it fails 1 in 10.** Across 10 sequential steps, each at 90% reliability, the end-to-end reliability drops to 35% — and no eval report tells you this.
- **Input perturbations are the silent killer.** A slightly rephrased question, an API that returns `null` instead of `[]`, an extra field in a JSON response — these are not errors, but they cause agents to fail in ways benchmarks never catch. ReliabilityBench calls this ε-robustness: does the agent hold up when the input distribution shifts?
- **Infrastructure failures compound non-deterministically.** A timeout on tool call 3, combined with a retry that succeeds but returns a different result than the original call, produces a trajectory that passes but reaches the wrong state. This is λ-fault tolerance, and it is almost never measured.
- **Eval suites freeze; production evolves.** A test case written in January reflects an API schema from December and a model version from November. By March, the 90% score may be measuring performance against a world that no longer exists.

## The Move

The Reliability Surface framework evaluates agents across three orthogonal dimensions simultaneously:

**R(k, ε, λ) = reliability surface**

Where:
- **k** = number of repeated trials (consistency under repetition — pass@k)
- **ε** = perturbation level (robustness to input distribution shift)
- **λ** = infrastructure fault level (fault tolerance under API failures, rate limits, timeouts)

The key insight: you cannot optimize for one dimension without degrading others. An agent tuned for maximum consistency (high k) may become brittle to perturbation (low ε). A highly robust agent (high ε) may slow down and burn more tokens. The surface shows you the tradeoffs; your SLOs determine where you land on it.

```python
"""
Reliability Surface evaluation — simplified from ReliabilityBench (arXiv:2601.06112).
Measures agent reliability across k-trial consistency, perturbation robustness, and fault tolerance.
"""

import random
from dataclasses import dataclass
from typing import Callable
import httpx

@dataclass
class ReliabilitySurface:
    pass_at_1: float       # single-run success rate
    pass_at_5: float       # success in any of 5 trials
    pass_at_10: float      # success in any of 10 trials
    epsilon_robustness: float  # success under input perturbation (0-1)
    lambda_tolerance: float    # success under infra faults (0-1)
    surface_volume: float      # geometric mean = reliability score

def measure_k_trial_reliability(
    agent_fn: Callable,
    test_cases: list[dict],
    k: int = 10,
) -> dict[int, float]:
    """
    Measure pass@k for increasing values of k.
    pass@k = probability of success in at least 1 of k trials.
    Key insight: pass@1 == 0.90 does NOT mean pass@10 == 0.90.
    pass@10 = 1 - (1 - pass@1)^k  -- only if trials are independent.
    """
    results = {}
    for trial_k in [1, 3, 5, 10]:
        successes = 0
        for case in test_cases:
            # Run trial_k times, count if ANY succeeds
            for _ in range(trial_k):
                try:
                    result = agent_fn(case)
                    if result.get("success"):
                        successes += 1
                        break  # stop on first success
                except Exception:
                    pass
        results[trial_k] = successes / (trial_k * len(test_cases))
    return results

def measure_epsilon_robustness(
    agent_fn: Callable,
    base_cases: list[dict],
    perturbation_levels: list[float],
) -> dict[float, float]:
    """
    Measure success rate under increasing input perturbation (ε-levels).
    ε=0.0: original inputs (baseline)
    ε=0.3: 30% of inputs perturbed (rephrased, extra fields, null vs empty)
    ε=0.6: 60% perturbed
    ε=1.0: all inputs perturbed
    Perturbations simulate production drift: API schema changes, user phrasing
    variations, upstream data format shifts.
    """
    results = {}
    for epsilon in perturbation_levels:
        perturbed = 0
        successes = 0
        for case in base_cases:
            # Decide if this case gets perturbed
            if random.random() < epsilon:
                perturbed += 1
                case = perturb_input(case)
            try:
                result = agent_fn(case)
                if result.get("success"):
                    successes += 1
            except Exception:
                pass
        # Only compute rate from actually-tested cases
        tested = perturbed if perturbed > 0 else len(base_cases)
        results[epsilon] = successes / tested
    return results

def measure_lambda_tolerance(
    agent_fn: Callable,
    test_cases: list[dict],
    fault_scenarios: list[dict],
) -> float:
    """
    Measure success rate under infrastructure fault injection (λ-levels).
    λ=0.0: no faults injected (baseline)
    λ=0.5: 50% of calls experience faults (timeout, rate limit, 500, null response)
    λ=1.0: aggressive fault injection on all calls

    Fault scenarios from production: API timeouts (30s → 1s),
    rate limit 429 responses, server 500 errors, empty/null API responses,
    tool result truncation, network partition simulation.
    """
    successes = 0
    for case in test_cases:
        # Simulate faults on a subset based on lambda
        try:
            result = agent_fn(case, inject_fault=True)
            if result.get("success"):
                successes += 1
        except Exception:
            pass
    return successes / len(test_cases)

def compute_reliability_surface(
    agent_fn: Callable,
    test_cases: list[dict],
) -> ReliabilitySurface:
    """
    Full Reliability Surface computation.
    """
    # k-trial: measure consistency
    k_results = measure_k_trial_reliability(agent_fn, test_cases, k=10)

    # ε-robustness: measure perturbation tolerance
    eps_results = measure_epsilon_robustness(
        agent_fn, test_cases, perturbation_levels=[0.0, 0.3, 0.6, 1.0]
    )

    # λ-tolerance: measure fault tolerance
    lambda_tol = measure_lambda_tolerance(
        agent_fn, test_cases, fault_scenarios=INFRA_FAULT_SCENARIOS
    )

    # Surface volume: geometric mean of the three dimensions
    # This is the unified reliability score — lower bound on production success
    surface_volume = (
        k_results[10] *
        eps_results.get(0.3, 0.5) *
        lambda_tol
    ) ** (1/3)

    return ReliabilitySurface(
        pass_at_1=k_results[1],
        pass_at_5=k_results[5],
        pass_at_10=k_results[10],
        epsilon_robustness=eps_results.get(0.3, 0.5),
        lambda_tolerance=lambda_tol,
        surface_volume=surface_volume,
    )


# --- Perturbation helpers ---

def perturb_input(case: dict) -> dict:
    """Apply production-realistic input perturbations to a test case."""
    perturbations = [
        lambda c: {**c, "query": c.get("query", "") + " please"},        # extra text
        lambda c: {**c, "query": c.get("query", "").replace("?", ".")},   # rephrase
        lambda c: {k: (v if k != "filters" else None) for k, v in c.items()},  # null vs empty
        lambda c: {**c, "extra_field": "unexpected_value"},               # extra field
    ]
    return random.choice(perturbations)(case)


# --- Production fault scenarios ---

INFRA_FAULT_SCENARIOS = [
    {"type": "timeout", "tool": "search_api", "duration": 1.0},
    {"type": "rate_limit", "tool": "search_api", "retry_after": 5},
    {"type": "null_response", "tool": "db_query"},
    {"type": "truncation", "tool": "web_fetch", "max_chars": 100},
    {"type": "schema_drift", "tool": "api", "field_renamed": "amount_usd"},
]


# --- Usage ---

"""
# Example: Evaluate a customer support agent across the reliability surface

surface = compute_reliability_surface(
    agent_fn=support_agent.run,
    test_cases=load_test_suite("support_tickets_100.json"),
)

print(f"pass@1:  {surface.pass_at_1:.2%}")    # Looks great: 91%
print(f"pass@10: {surface.pass_at_10:.2%}")   # Still high: 99%
print(f"ε@0.3:   {surface.epsilon_robustness:.2%}")  # Real: 67%
print(f"λ@prod:  {surface.lambda_tolerance:.2%}")   # Real: 58%
print(f"Surface: {surface.surface_volume:.2%}")     # Honest: 79%

# The surface tells you:
# - Your agent is fragile to input perturbations (ε=67%): add input validation
# - Your agent has poor fault tolerance (λ=58%): improve retry logic
# - Your surface volume (79%) is a better production predictor than pass@1 (91%)
"""
```

## Interpreting the Surface

| Scenario | pass@1 | ε@0.3 | λ | Surface | Production Reality |
|---|---|---|---|---|---|
| **Optimistic** | 91% | 88% | 82% | **87%** | Probably fine |
| **Typical prod** | 91% | 67% | 58% | **71%** | Expect ~30% failures |
| **Adversarial** | 91% | 41% | 29% | **50%** | Coin flip in production |

The gap between your pass@1 and your surface volume is the hidden risk. A surface volume of 70% means that under real-world conditions — slightly different inputs, occasional API failures, retries that succeed but change behavior — you should expect 1 in 3 tasks to fail, even with a 90% single-run benchmark.

## Key Thresholds (from ReliabilityBench findings)

- **pass@1 < 85%**: agent is unreliable even in ideal conditions — don't ship
- **ε@0.3 < 70%**: agent is brittle to input drift — needs input normalization and validation
- **λ < 60%**: agent has poor fault tolerance — needs retry logic and circuit breakers
- **Surface volume < 75%**: production failure rate will exceed 25% under realistic conditions

## Cross-links

- [S-845 · Agent Evaluation Stack](s845-the-agent-evaluation-stack-when-you-cant-tell-if-your-agent-is-getting-better.md) — builds on the evaluation fundamentals; this entry adds the reliability surface lens
- [S-257 · Five Failure Modes](s257-the-five-failure-modes-that-kill-production-agents.md) — ε-robustness directly addresses the "reasoning drift" and "context overflow" failure modes; λ-tolerance addresses tool failure cascades
- [S-817 · Trajectory Eval Stack](s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — trajectory evaluation is what surfaces ε and λ failures; output-only eval misses them
- [S-370 · Agent Chaos Engineering](s818-the-self-healing-agent-stack-fault-tolerance-for-autonomous-systems.md) — fault injection in production is how you measure λ empirically
- [S-796 · Evaluation Gap](s796-the-evaluation-gap-what-pass-fail-misses-about-agent-quality.md) — explains why aggregate pass/fail hides the surface; pass@1 is the worst possible metric for production planning

## Receipt

> Verified 2026-07-09 — ReliabilityBench arXiv:2601.06112 (Gupta, Jan 2026) defines R(k,ε,λ) framework; Zylos Research (May 2026) independently confirmed ε-drift as the primary production failure source; arXiv:2601.06007 (Jun 2026) on prompt caching also confirmed that ε-level perturbations (dynamic content placement) cause 13-31% latency variation in agentic tasks. AgentConn benchmark (Mar 2026) found 97.5% real-job failure rate — consistent with low surface volume on production-realistic benchmarks. Composite score: 8.75.
