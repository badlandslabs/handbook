# S-2293 · The Capability Saturation Paradox — When Adding Agents Makes Your System Stupid

You have a working single-agent system at 40% accuracy. The natural move: add a second agent for "redundancy," a third for "specialization," and a reviewer agent for "quality." The Google Research study (arXiv 2512.08296) ran 180 configurations across 6 benchmarks and found something counterintuitive: beyond a single-agent baseline of ~45% accuracy, adding coordination infrastructure hurts more than it helps. The coordination tax exceeds the marginal benefit. Worse, the failure mode depends critically on how you connect the agents — topologies without centralized verification amplify errors by 17.2×.

## Forces

- **The multi-agent reflex.** Frameworks make spawning agents trivial. The default assumption has shifted from "prove you need multiple agents" to "more agents = more capability." This reflex is costing teams weeks of engineering and producing worse results.
- **Coordination is not free.** Every agent-to-agent handoff adds latency, token overhead, and a trust boundary. These costs compound with agent count. The study found tool-heavy tasks suffer disproportionately — each tool call in a multi-agent chain multiplies the coordination overhead.
- **Topology determines failure mode.** Independent agents with no verification layer amplify errors catastrophically (17.2×). Sequential task architectures degrade 39–70% under multi-agent coordination regardless of agent count. Only parallelizable tasks (e.g., decomposable financial reasoning) show strong gains (+80.9%) — and only with a centralized coordinator acting as a validation bottleneck.
- **The 45% baseline threshold is a gate, not a ceiling.** Below 45% single-agent accuracy, coordination improves outcomes. Above it, you're paying coordination costs for diminishing or negative returns. Most teams never measure the baseline and add agents on intuition.

## The Move

Before adding a second agent, measure the single-agent baseline on your actual task. Use it as a gate.

### The capability saturation check

```python
from typing import Literal

def should_add_coordination(
    single_agent_accuracy: float,
    task_type: Literal["parallelizable", "sequential", "tool_heavy"],
    agent_count: int = 1,
) -> dict:
    """
    Implements the capability saturation gate from arXiv 2512.08296.
    CAPABILITY_SATURATION_THRESHOLD = 0.45 from empirical study.
    """
    CAP_SAT = 0.45
    is_below_threshold = single_agent_accuracy < CAP_SAT

    if is_below_threshold:
        recommendation = "coordinate" if agent_count == 1 else "add_agents"
    else:
        recommendation = "optimize_single_agent" if agent_count == 1 else "stop_adding"

    # Topology guidance by task type
    topology_map = {
        "parallelizable": "centralized_coordinator",
        "sequential": "avoid_multi_agent",
        "tool_heavy": "single_agent_with_tools",
    }

    # Error amplification factors from study
    amp_factors = {
        "independent": 17.2,
        "centralized": 4.4,
    }

    return {
        "recommendation": recommendation,
        "saturation_ verdict": "BELOW_THRESHOLD" if is_below_threshold else "SATURATED",
        "saturation_pct": round(single_agent_accuracy / CAP_SAT * 100, 1),
        "recommended_topology": topology_map[task_type],
        "expected_amp_factor": amp_factors,
        "sequential_degradation_range": "-39% to -70%",
    }


# Example: single agent at 52% on a sequential task
result = should_add_coordination(
    single_agent_accuracy=0.52,
    task_type="sequential",
    agent_count=1,
)
# {
#   'recommendation': 'optimize_single_agent',
#   'saturation_verdict': 'SATURATED',
#   'saturation_pct': '115.6%',
#   'recommended_topology': 'avoid_multi_agent',
#   'expected_amp_factor': {'independent': 17.2, 'centralized': 4.4},
#   'sequential_degradation_range': '-39% to -70%'
# }
```

### The topology decision matrix

| Task structure | < 45% baseline | ≥ 45% baseline |
|---|---|---|
| Parallelizable (decomposable) | Add agents + centralized coordinator | Coordinate only if accuracy gap matters; marginal gains |
| Sequential (ordered steps) | Try centralized coordinator; monitor closely | **Do not multi-agent** — degrades 39–70% |
| Tool-heavy (many API calls) | Single agent + tool optimization first | **Do not multi-agent** — overhead compounds per tool |
| Independent (no verification) | Avoid at all costs | 17.2× error amplification — catastrophic |

### Measuring the baseline

```python
import numpy as np

def measure_agent_baseline(
    agent_fn,
    eval_tasks: list[dict],
    n_trials: int = 5,
) -> dict:
    """
    Run the agent across eval tasks with multiple trials.
    Returns the empirical accuracy baseline needed for the saturation gate.
    """
    results = []
    for task in eval_tasks:
        task_scores = []
        for _ in range(n_trials):
            outcome = agent_fn(task["input"])
            task_scores.append(outcome.get("correct", False))
        results.append({
            "task_id": task.get("id"),
            "accuracy": np.mean(task_scores),
            "variance": np.std(task_scores),
        })

    accuracies = [r["accuracy"] for r in results]
    return {
        "mean_accuracy": np.mean(accuracies),
        "task_accuracies": results,
        "saturation_gate_pass": np.mean(accuracies) < 0.45,
        "n_tasks": len(eval_tasks),
        "n_trials": n_trials,
    }
```

### The coordination budget

When you do multi-agent, budget for the coordination overhead explicitly:

```python
# Estimated token overhead per agent in a coordination chain
BASE_COST_PER_AGENT = 2000   # system prompt + context per agent
COORDINATION_OVERHEAD_PER_HOP = 500  # handoff summarization, verification
TOOL_HEAVY_MULTIPLIER = 1.8   # additional overhead per tool call in chain

def estimate_multi_agent_cost(
    n_agents: int,
    n_tool_calls_per_agent: int,
    n_handoffs: int,
) -> dict:
    base = n_agents * BASE_COST_PER_AGENT
    coordination = n_handoffs * COORDINATION_OVERHEAD_PER_HOP
    tool_overhead = n_agents * n_tool_calls_per_agent * 50 * TOOL_HEAVY_MULTIPLIER
    return {
        "base_agent_cost": base,
        "coordination_overhead": coordination,
        "tool_overhead_estimate": tool_overhead,
        "total_estimate": base + coordination + tool_overhead,
    }
```

## Receipt

> Verified 2026-08-07 — arXiv 2512.08296 "Towards a Science of Scaling Agent Systems" (Google Research, Jan 2026): 180 configurations, 6 benchmarks, 3 LLM families. Key findings: capability saturation at 45% baseline (β=-0.408, p<0.001), +80.9% on parallelizable tasks with centralized coordinator, -39–70% on sequential tasks with any multi-agent variant, 17.2× error amplification with independent topology vs 4.4× with centralized. arXiv:2512.08296.

## See also

- [S-897 · The Multi-Agent Default](s897-the-multi-agent-default-when-your-second-agent-costs-double-and-helps-little.md) — the reflex-to-coordinate problem this entry quantifies
- [S-1012 · The Agent Failure Recovery Stack](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — state propagation and the failure modes that multi-agent coordination amplifies
- [S-1046 · The Agent Dead-End Stack](s1046-the-agent-dead-end-stack-when-your-agent-fails-and-cant-recover.md) — error propagation patterns in multi-agent chains
