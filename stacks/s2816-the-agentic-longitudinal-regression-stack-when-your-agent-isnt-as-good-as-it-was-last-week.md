# S-2816 · The Agentic Longitudinal Regression Stack — When Your Agent Isn't as Good as It Was Last Week

When your agent passed every pre-deployment test and shipped. Three months later it silently degraded — different answers, worse tool calls, degraded reasoning — with no code change on your end. The model provider updated under a stable API name. You had no way to know until users complained.

## Forces

- **Snapshot evals are lies by omission.** A benchmark score answers "how good is the agent today?" — it does not answer "is the agent as good as it was last Tuesday?" Agents exist in constant background change: model provider pushes, input distribution shifts, prompt chains accumulate emergent dependencies. The absence of a longitudinal reference means silent regression is invisible.
- **Model providers update under stable API names.** OpenAI, Anthropic, and Google routinely update model weights behind fixed endpoint names (GPT-4o, Claude 3.5 Sonnet, Gemini 1.5 Pro). The API contract is stable; the model's behavior is not. A passing eval on June 1 can reflect a model that no longer exists on August 1.
- **Two drift types require separate detectors.** Input drift (distribution of what users ask changes — new invoice formats, new transaction types, seasonal patterns) can be monitored independently of output quality and caught *before* performance degrades. Model drift (the provider changed the model) requires comparing the same inputs against a stable reference. Mixing the two produces noisy alerts and missed regressions.
- **The held-out set is the instrument.** Like a medical lab panel run on the same patient against the same reference ranges, a longitudinal eval requires a stable, diverse, representative sample of tasks run repeatedly. Its quality determines whether you detect drift at all.
- **Statistical power requires cadence and volume.** Running the held-out set once on deployment and comparing against a baseline produces a single data point. Detecting a 5% capability regression at 95% confidence on a 100-task held-out set requires running it daily for ~3 weeks (Zylos Research, April 2026).

## The move

**Build a held-out regression set and run it continuously.**

1. **Curate the held-out set.** Select 50–200 diverse, stable tasks spanning your agent's core capabilities: tool routing, reasoning chains, error recovery, edge cases. Tasks must be representative of production distribution — over-weighting easy cases hides regressions. Include known-failure cases to detect false-positive spikes. Refresh quarterly as capabilities expand.

2. **Establish the baseline.** Run the held-out set against the initial agent configuration (model + prompt + tools + version). Record per-task pass/fail, score distribution, and error taxonomy. This is your reference.

3. **Run continuously.** Trigger eval runs on: every commit (regression gate), daily batch (drift catch), and event-driven (model version change, prompt update, new tool added). Daily cadence is the minimum for catching model provider updates — weekly misses too many days of potential drift.

4. **Track two drift dimensions separately.**
   - **Input drift**: monitor distribution of production inputs (query topics, tool call frequencies, user types) against baseline. Alert when the input manifold shifts beyond a threshold — before output quality degrades.
   - **Model drift**: run held-out set against the same inputs on current model vs. baseline model. Alert on statistically significant score regression (≥5% drop at 95% confidence).

5. **Version everything.** Agent config, model version, prompt version, tool schema version, held-out set version, eval results. A regression detected without versioning context is a fire alarm with no building address.

6. **Alert on the gap, not the absolute.** The held-out set score will drift with new capabilities — a 70% score on a harder task set is not a problem. Alert on *regression from your own baseline*, not on absolute thresholds.

```python
import json
from datetime import datetime
from statistics import stdev, mean

class LongitudinalEvalRunner:
    def __init__(self, agent, held_out_set: list[dict], baseline_results: dict | None = None):
        self.agent = agent
        self.tasks = held_out_set
        self.baseline = baseline_results  # {"task_id": score, ...}

    def run(self) -> dict:
        results = {}
        for task in self.tasks:
            outcome = self.agent.run(task["input"], task["expected"])
            results[task["id"]] = {
                "passed": outcome.get("success", False),
                "score": outcome.get("score", 0.0),
                "error_type": outcome.get("error_type", None),
                "timestamp": datetime.utcnow().isoformat(),
            }
        return results

    def detect_regression(self, current: dict, window_days: int = 14) -> dict:
        """Alert if current performance regresses vs. baseline beyond threshold."""
        REGRESSION_THRESHOLD = 0.05  # 5% absolute drop
        MIN_CONFIDENCE = 0.95

        degraded_tasks = []
        for task_id, baseline_score in self.baseline.items():
            if task_id not in current:
                degraded_tasks.append(task_id)
                continue
            current_score = current[task_id]["score"]
            if current_score < baseline_score - REGRESSION_THRESHOLD:
                degraded_tasks.append(task_id)

        regression_rate = len(degraded_tasks) / len(self.baseline)
        # Binomial test: probability of seeing this many failures by chance
        # Simplified: alert if >10% of tasks degraded
        is_regression = regression_rate > 0.10

        return {
            "regression_detected": is_regression,
            "degraded_tasks": degraded_tasks,
            "degradation_rate": regression_rate,
            "baseline_score": mean(self.baseline[t]["score"] for t in self.baseline),
            "current_score": mean(current[t]["score"] for t in current if t in self.baseline),
        }

    def detect_input_drift(self, production_inputs: list[dict]) -> dict:
        """Monitor input distribution shift using KL divergence vs baseline."""
        # Simplified: topic frequency comparison
        baseline_topics = {t["topic"] for t in self.tasks}
        prod_topics = {inp.get("topic") for inp in production_inputs}
        novel_topics = prod_topics - baseline_topics
        return {
            "drift_detected": len(novel_topics) > 0,
            "novel_topic_count": len(novel_topics),
            "novel_topics": list(novel_topics),
        }


# Usage in CI/CD
runner = LongitudinalEvalRunner(agent, held_out_set, baseline_results)
current_results = runner.run()

drift = runner.detect_regression(current_results)
input_drift = runner.detect_input_drift(recent_production_inputs)

if drift["regression_detected"]:
    # Block deploy, page on-call
    send_alert(f"{len(drift['degraded_tasks'])} tasks regressed: {drift['degraded_tasks']}")
    block_deploy()
elif input_drift["drift_detected"]:
    # Warn that held-out set may need refresh
    send_alert(f"Input distribution shifted: {input_drift['novel_topics']}")
```

## Receipt
> Receipt pending — 2026-08-18. Core framework synthesized from Flowscope (Javier Leguina, July 20 2026), Zylos Research (April 14 2026), and MLflow (June 27 2026). Code example is illustrative — production implementation should include a statistical test library (SciPy binomial test) and a persistent eval store.

## See also
- [S-1000 · The Agent Eval Stack](s1000-the-agent-eval-stack-when-you-cant-measure-it-you-cant-fix-it.md) — snapshot evaluation framework
- [S-2671 · The Evaluation Gap Stack](s2671-the-evaluation-gap-stack-when-your-agent-aces-the-benchmark-and-flops-in-production.md) — eval-to-production gap
- [S-2809 · The Agent-Keeps-Spinning Stack](s2809-the-agent-keeps-spinning-stack-when-your-agent-loops-breaks-or-runs-away.md) — loop and budget failure modes
- [S-541 · Agent Drift Detection](s541-agent-drift-detection.md) — behavioral regression detection (companion entry)
