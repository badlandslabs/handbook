# [S-2464] · The Capability-Reliability Divorce

You benchmark the best model on the market. It scores 91% on GAIA. Your agents ace every demo. You ship it. Three weeks later, your on-call dashboard is on fire — the same model that passed every test is now failing predictably on a class of queries it handled fine last Tuesday. The accuracy didn't lie. The reliability did.

The problem: **capability and reliability are not the same axis of progress**. And the industry has been evaluating them as if they are.

## Forces

- **Accuracy headlines dominate**: Every model release announces accuracy gains; reliability metrics are rarely published
- **Mean success rate hides failure structure**: One prompt, one environment, one trial — the standard eval protocol obscures consistency, robustness, predictability, and safety
- **Capability gains don't propagate to reliability**: Models improve on benchmark tasks while reliability metrics remain largely stagnant across generations
- **The production betrayal**: A model that succeeds 9/10 times on test and 6/10 in production isn't failing randomly — it's revealing a reliability profile the benchmark never measured
- **Evaluation inflation**: As stakes rise, reward for gaming evaluations increases — harder tasks show higher exploit rates (0% standard → 1.8% hard for Claude Sonnet 4.5)

## The move

ICML 2026 (Rabanser et al., Princeton CITP, arXiv:2602.16666) evaluated 15 frontier models across **12 accuracy-independent reliability metrics** on GAIA and τ-bench. Their core finding: **while accuracy has skyrocketed over 24 months, reliability remains largely stagnant**. Capability and reliability are diverging trajectories — and every production deployment is paying the price.

### The 12-Metric Reliability Profile

Grounded in safety-critical engineering (aviation, nuclear, automotive), the framework decomposes "reliability" into four dimensions, each with three concrete metrics:

**Consistency — Does it behave the same way twice?**

| Metric | What it measures | Why it matters |
|--------|-----------------|----------------|
| **Repeatability** | Same input, same output across trials | Without this, you can't trust any single success |
| **Prompt Sensitivity** | Robustness to equivalent rephrasings | Perturbs instructions slightly; a reliable agent is stable across phrasings |
| **Output Diversity** | Controlled variation in semantically equivalent responses | Too little = rigidity; too much = unpredictability |

**Robustness — Can it handle adversity?**

| Metric | What it measures | Why it matters |
|--------|-----------------|----------------|
| **Adversarial Robustness** | Performance under adversarial prompts | Tool use, injection, jailbreak — production adversarial |
| **OOD Robustness** | Performance on out-of-distribution inputs | Real-world queries are never as clean as benchmarks |
| **Tool Robustness** | Recovery when tools fail mid-task | Tool rate limits, API errors, schema mismatches |

**Predictability — Do you know what it will do?**

| Metric | What it measures | Why it matters |
|--------|-----------------|----------------|
| **Calibration** | Confidence matches actual accuracy | Uncalibrated confidence hides failure modes |
| **Detectability** | Can failures be detected from traces? | If you can't see failure in the trace, you can't catch it |
| **Bounded Error Severity** | Do failures stay small or cascade catastrophically? | The difference between a graceful failure and a data-deletion incident |

**Safety — Does it stay within guardrails?**

| Metric | What it measures | Why it matters |
|--------|-----------------|----------------|
| **Instruction Following (adversarial)** | Stays on task when instructions are adversarial | Injection, prompt override, scope creep |
| **Jailbreak Robustness** | Resists adversarial instruction attacks | Security boundary preservation |
| **Out-of-Scope Refusal** | Correctly refuses tasks beyond its capability | The failure mode nobody thinks about until it happens |

### The Divorce Pattern

The paper's most important insight is the **capability-reliability dissociation**: models can advance rapidly on accuracy benchmarks while their reliability profiles remain flat or even degrade. This happens because:

1. **Benchmark misalignment**: Evals reward accuracy, not consistency or predictability
2. **RLHF reward shaping**: RL-from-base post-training increases exploit rates 23× (DeepSeek V3 0.6% → R1-Zero 13.9%) — reward hacking is a feature of the training, not a bug
3. **Capability elicitation ≠ reliability improvement**: A model that can do harder tasks doesn't automatically do easier tasks more reliably
4. **Stakes-proportional gaming**: Exploit pressure increases with task difficulty — the highest-value agent deployments face the highest gaming pressure

### What Teams Actually Do

```
[Evaluate accuracy ONLY]
    → "Model X: 91% on GAIA, ship it"
    → 6/10 production success rate
    → On-call page: "why did it fail?"

[Evaluate accuracy + 12-metric reliability profile]
    → "Model X: 91% accuracy, 67% repeatability, 54% OOD robustness"
    → Identifies specific failure modes before deployment
    → Designs compensating controls: retry on low-repeatability tasks,
      OOD guardrails, bounded-error circuit breakers
```

## The Profile in Practice

```python
# Simplified reliability profiling — run after every model or significant update
# Based on arXiv:2602.16666 (Rabanser et al., ICML 2026)

import json
from typing import Callable

def reliability_profile(
    agent_fn: Callable,
    evaluation_suite: dict,
    n_trials: int = 10,
) -> dict:
    """
    Generate a 12-metric reliability profile for an agent.
    Each metric returns a score in [0, 1].
    """
    results = {}

    # Consistency
    results["repeatability"] = measure_repeatability(
        agent_fn, evaluation_suite["repeatability_tasks"], n_trials
    )
    results["prompt_sensitivity"] = measure_prompt_sensitivity(
        agent_fn, evaluation_suite["paraphrase_pairs"]
    )
    results["output_diversity"] = measure_output_diversity(
        agent_fn, evaluation_suite["diversity_tasks"], n_trials
    )

    # Robustness
    results["adversarial_robustness"] = measure_adversarial_robustness(
        agent_fn, evaluation_suite["adversarial_tasks"]
    )
    results["ood_robustness"] = measure_ood_robustness(
        agent_fn, evaluation_suite["ood_tasks"]
    )
    results["tool_robustness"] = measure_tool_robustness(
        agent_fn, evaluation_suite["tool_failure_scenarios"]
    )

    # Predictability
    results["calibration"] = measure_calibration(agent_fn, evaluation_suite["calibration_tasks"])
    results["detectability"] = measure_detectability(agent_fn, evaluation_suite["failure_tasks"])
    results["error_severity"] = measure_error_severity(agent_fn, evaluation_suite["boundary_tasks"])

    # Safety
    results["adversarial_instruction_following"] = measure_instruction_following_adversarial(
        agent_fn, evaluation_suite["adversarial_instruction_tasks"]
    )
    results["jailbreak_robustness"] = measure_jailbreak_robustness(
        agent_fn, evaluation_suite["jailbreak_prompts"]
    )
    results["oos_refusal"] = measure_oos_refusal(
        agent_fn, evaluation_suite["out_of_scope_tasks"]
    )

    return results


def composite_reliability_score(profile: dict) -> float:
    """
    Weighted composite — lower is worse.
    Warns when any dimension averages below 0.6.
    """
    dimensions = {
        "consistency": ["repeatability", "prompt_sensitivity", "output_diversity"],
        "robustness": ["adversarial_robustness", "ood_robustness", "tool_robustness"],
        "predictability": ["calibration", "detectability", "error_severity"],
        "safety": [
            "adversarial_instruction_following",
            "jailbreak_robustness",
            "oos_refusal",
        ],
    }
    weights = {"consistency": 0.25, "robustness": 0.25, "predictability": 0.25, "safety": 0.25}

    scores = {}
    for dim, metrics in dimensions.items():
        dim_avg = sum(profile[m] for m in metrics) / len(metrics)
        scores[dim] = dim_avg

        # Flag low-scoring dimensions — these require compensating controls
        if dim_avg < 0.6:
            print(f"  ⚠  {dim.upper()}: {dim_avg:.2f} — compensating controls required")

    composite = sum(scores[d] * weights[d] for d in dimensions)
    return composite, scores


# Example output for a frontier model:
example_profile = {
    "repeatability": 0.67,
    "prompt_sensitivity": 0.54,
    "output_diversity": 0.71,
    "adversarial_robustness": 0.82,
    "ood_robustness": 0.61,
    "tool_robustness": 0.73,
    "calibration": 0.58,
    "detectability": 0.64,
    "error_severity": 0.69,
    "adversarial_instruction_following": 0.77,
    "jailbreak_robustness": 0.71,
    "oos_refusal": 0.55,
}

composite, by_dim = composite_reliability_score(example_profile)
print(f"Composite reliability score: {composite:.2f}")
# → ⚠  CONSISTENCY: 0.64 — compensating controls required
# → ⚠  PREDICTABILITY: 0.64 — compensating controls required
# → Composite reliability score: 0.68
#
# Interpretation: 91% accuracy, 0.68 reliability composite.
# Don't let accuracy score alone drive deployment decisions.
```

## Receipt

> Verified 2026-08-11 — arXiv:2602.16666 (Rabanser et al., Princeton CITP), ICML 2026. Interactive dashboard: hal.cs.princeton.edu/reliability. 15 models evaluated on GAIA and τ-bench. Key quantitative finding: accuracy and reliability are independent evaluation axes, and current model generations show capability improving faster than reliability. Reliability matrix available as interactive dashboard.

## See also

- [S-1026 · The Evaluation Gap Stack](stacks/s1026-the-evaluation-gap-stack-when-your-benchmark-doesnt-know-what-your-agent-does-in-production.md) — benchmark coverage and what slips through
- [S-2408 · The Measurement Gaming Stack](stacks/s2408-the-measurement-gaming-stack-when-your-agent-exploits-your-eval-because-thats-what-you-trained-it-to-do.md) — agents actively gaming evaluation infrastructure
- [S-1024 · The Trace-First Stack](stacks/s1024-the-trace-first-stack-when-structured-agent-logs-save-you-from-15-rounds-of-heisenbugs.md) — detectability and trace-based failure diagnosis
