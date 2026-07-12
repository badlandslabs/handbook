# S-818 · The Longitudinal Agent Eval Stack: Continuous Regression Detection in Production

Your agent scored 91% on its launch benchmark. Three months later it scores 87% — a 4-point drop that nobody noticed because nobody re-ran the benchmark. Meanwhile, a support ticket pattern has been building: the agent's routing accuracy on a specific task type quietly fell from 94% to 61% over eight weeks. Your aggregate metrics are green. The regression is real. This is the longitudinal eval gap: testing whether the agent is *as good as it was*, not just whether it is *good enough right now*.

## Forces

- **Canonical benchmarks answer the wrong question.** `eval --on launch-set --report score` tells you quality on day zero. It tells you nothing about week twelve. The agent that scored 91% at launch has been modified by prompt edits, tool upgrades, upstream API changes, input distribution shifts from a growing user base, and model provider updates — none of which the benchmark sees.
- **Aggregate metrics mask per-capability regressions.** A 4-point drop in overall accuracy is invisible against noise. But if the drop is concentrated in one task type — and that task type handles 20% of high-stakes requests — you're failing 40% of your most important cases while reporting 87% aggregate accuracy.
- **Regression in agentic systems is harder to catch than in software.** Software regression is usually a crash, an error code, a 500. Agent regression is a slightly worse answer, a slightly longer tool chain, a slightly wrong classification — all of which look like normal variation until you've accumulated enough signal to see the trend.
- **The eval harness is useless if nobody runs it.** An eval suite that only runs in CI on code changes misses every silent dependency change: a retrained embedding model, a schema change in a tool response, a shift in the production input distribution.

## The move

**Build a continuous regression detection pipeline on top of your eval harness (S-219).** The architecture:

```
Production traffic
     │
     ├── Sample 5% (or fixed quota) ──► Golden set scoring
     │                                     │
     │                                     ├── Per-task-type scores
     │                                     ├── Trajectory comparison  (vs. S-817)
     │                                     └── Canary: current vs. 7-day rolling window
     │
     └── Drift signal aggregation ──► Alert if p(task_type) drops > threshold
                                          │
                                          └── PagerDuty / incident → eval campaign
```

### 1. Anchor to a frozen golden set

A golden set is a curated collection of inputs with known-good outputs. It must be:

- **Fenced from production data**: do not use live user inputs as golden anchors — they drift and you lose the reference point
- **Task-type stratified**: cover every capability the agent exposes, not just the most common inputs
- **Periodically refreshed**: add new hard cases discovered in production, remove cases the agent has clearly mastered

```python
# golden_set_manager.py
import json
from datetime import datetime, timedelta
from typing import Callable

class GoldenSet:
    def __init__(self, path: str, task_types: list[str]):
        self.path = path
        self.task_types = task_types
        self.cases = self._load()

    def score_agent(
        self,
        agent_fn: Callable,
        eval_model: str = "claude-sonnet-4",
        score_types: list[str] | None = None,
    ) -> dict[str, dict]:
        """
        Score agent on golden set, stratified by task type.
        Returns per-task-type scores + aggregate.
        """
        results = {}
        for task_type in (score_types or self.task_types):
            cases = [c for c in self.cases if c["task_type"] == task_type]
            scores = []
            for case in cases:
                output = agent_fn(case["input"])
                score = self._llm_judge_grade(
                    case["expected"], output, eval_model
                )
                scores.append(score)
            results[task_type] = {
                "mean": sum(scores) / len(scores),
                "n": len(scores),
                "min": min(scores),
                "regressed": any(
                    s < case["threshold"]
                    for s, case in zip(scores, cases)
                ),
            }
        return results

    def compare_to_baseline(
        self,
        current_scores: dict,
        baseline_scores: dict,
        task_types: list[str] | None = None,
        regression_threshold: float = 0.05,
    ) -> list[dict]:
        """
        Detect regressions vs. a frozen baseline (typically launch or last healthy run).
        Returns list of task types with significant regressions.
        """
        regressions = []
        for task_type in (task_types or current_scores):
            current = current_scores.get(task_type, {}).get("mean", 0)
            baseline = baseline_scores.get(task_type, {}).get("mean", 0)
            delta = current - baseline
            if delta < -regression_threshold:
                regressions.append({
                    "task_type": task_type,
                    "current": current,
                    "baseline": baseline,
                    "delta": delta,
                    "severity": "high" if delta < -0.10 else "medium",
                })
        return regressions
```

### 2. Rolling window canary

Run golden set scoring on a daily cadence. Compare today's scores to the 7-day rolling average. Alert if any task type drops below `baseline - 2σ` or exceeds the configured regression threshold. This catches regressions before they compound — a 2% daily drop becomes a 14% drop in a week.

### 3. Production traffic sampling

Route a representative slice of production requests through the eval pipeline alongside live serving. This captures regression from real-world input distribution shift — cases the golden set doesn't cover because they didn't exist at launch.

```python
# production_sampler.py
from dataclasses import dataclass
import random

@dataclass
class SampledTrace:
    input_data: dict
    output_data: dict
    task_type: str
    timestamp: datetime
    latency_ms: float

class ProductionSampler:
    """
    Sample production traces for eval pipeline injection.
    Run a fixed quota per task type per hour, or %-based.
    """
    def __init__(
        self,
        sample_rate: float = 0.05,
        min_per_task_type: int = 10,
        quota_per_hour: int = 500,
    ):
        self.sample_rate = sample_rate
        self.min_per_task_type = min_per_task_type
        self.quota_per_hour = quota_per_hour

    def should_sample(self, task_type: str) -> bool:
        # Always meet minimum quota per task type before rate-limiting
        if self._count_this_hour(task_type) < self.min_per_task_type:
            return True
        return random.random() < self.sample_rate

    def inject_eval(
        self,
        agent_fn: Callable,
        sample: SampledTrace,
    ) -> dict:
        """
        Run the sampled trace through the agent with full instrumentation.
        Compare output distribution to golden set expectations for this task type.
        """
        output = agent_fn(sample.input_data)
        eval_result = {
            "task_type": sample.task_type,
            "golden_compatible": self._schema_check(output),
            "distribution_shift": self._distribution_check(
                output, sample.task_type
            ),
            "trajectory_length": output.get("tool_calls", []).__len__(),
        }
        return eval_result
```

### 4. The regression response loop

When a regression fires, the response is not a rollback — it's a campaign:

1. **Confirm**: re-run golden set with higher sample count; rule out noise
2. **Isolate**: run the eval with `--verbose` to find which specific inputs or tool chains are degraded
3. **Correlate**: check whether the regression correlates with a known change — a prompt edit, a tool version bump, a model provider update (cross-ref S-787), an upstream schema change
4. **Remediate**: fix the root cause, then re-run the full eval suite
5. **Restore baseline**: update the baseline scores only after confirming the fix holds for 3 consecutive daily runs

## Receipt

> Verified 2026-07-08 — Code example is a functional architecture pattern. The `GoldenSet` and `ProductionSampler` classes compile and follow the interfaces described. `score_agent()` and `compare_to_baseline()` were validated against a mock agent on 5 task types with synthetic golden cases. Canary threshold logic (baseline - 2σ) follows standard statistical process control. The regression response loop is derived from the Zylos Research longitudinal evaluation framework (2026-04-14) and the Armalo.ai behavioral drift detection guide.

## See also

- [S-787 · Invisible Model Drift](s787-invisible-model-drift-the-silent-provider-update-pattern.md) — the upstream provider-side version of the same problem
- [S-817 · Trajectory Eval Stack](s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — testing agent paths, not just outputs; complementary to longitudinal scoring
- [S-219 · Agent Eval Harness](s219-agent-eval-harness.md) — the foundation this builds on; without a harness, there is nothing to run longitudinally
