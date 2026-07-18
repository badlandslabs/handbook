# S-1321 · The Frozen Endpoint Problem — When Your Model Endpoint Changes Without a Version Bump

Your agent passed every test. It shipped. Three weeks later, task success dropped from 91% to 67%. You didn't deploy anything. The model name didn't change. But GPT-4 is no longer the same model it was on launch day. Your API endpoint is not a frozen artifact — it is a moving target, and you had no idea.

## Situation

You pin your agent to `gpt-4o` via your LLM gateway. Every CI run passes. Every golden dataset check is green. Then users start complaining about a specific failure mode that never happened before: the model now formats tool-call arguments slightly differently, your parser breaks, and cascading failures silently multiply. You spend two days assuming it was a prompt regression before discovering the provider quietly updated the inference stack.

This is not a hypothetical. A Stanford/UC Berkeley study documented GPT-4's accuracy on a specific reasoning task dropping from **84% to 51%** between March and June 2023 — with no version change announced, no changelog entry, no notification. The endpoint name was identical; the behavior was not.

## Forces

- **Model endpoints are mutable, not frozen.** Providers update weights, RLHF tuning, safety filters, and inference infrastructure continuously. The same API alias can point to different model artifacts at different times. Unlike library versions (pip install foo==1.2.3), LLM API endpoints carry no semver contract.

- **Traditional tests don't catch behavioral drift.** Your unit tests check for correct output formats, not behavioral consistency across semantically equivalent inputs. An agent that produces the right answer via a slightly different reasoning path still passes. But if the new path is less reliable on edge cases, you're flying blind.

- **The 37% eval-to-production gap.** Production agent failures often aren't eval failures — they're silent behavioral shifts in the model provider that your test harness never measured. The eval suite is answering "does this work today?" instead of "does this work the same way it did last week?"

- **Human override rate is the real canary.** A gradual increase in human intervention rate — from 5% to 12% over two weeks — typically precedes a system-level quality incident. This signal is invisible to traditional APM, which tracks HTTP 200s, not semantic correctness.

- **eval-view made this actionable.** The GitHub tool `eval-view` (124 stars, Apache-2.0) snapshots agent tool-call sequences and diffs them against baselines on every run. When a model update causes the agent to call the wrong tool, skip a clarification step, or change output format, the diff surfaces it before users do.

## The move

### 1. Treat the model endpoint as an external dependency that can regress

Pin to specific versioned model aliases where available (`gpt-4o-2024-08-06` rather than `gpt-4o`). When this isn't possible, accept that your model is a mutable dependency and instrument for behavioral change detection.

### 2. Snapshot behavioral baselines, not just output correctness

Store canonical trajectories — tool-call sequences, parameter values, reasoning step counts — for a representative golden dataset. On every CI run or scheduled interval, re-execute the golden set and diff the trajectories against the baseline. A version that changes *how* the agent reasons without changing *what* it outputs is still a regression.

```python
# eval-view pattern: snapshot and diff tool-call trajectories
from evalview import AgentSnapshot, compare_trajectories

# Capture baseline on known-good version
baseline = AgentSnapshot.capture(
    agent=agent,
    test_cases=golden_dataset,
    metadata={"model": "gpt-4o-2024-08-06", "prompt_version": "v2.3"}
)
baseline.save("trajectories/baseline-v2.3.json")

# In CI, compare current trajectories against baseline
current = AgentSnapshot.capture(agent=agent, test_cases=golden_dataset)
diff = compare_trajectories(current, baseline)

if diff.tool_call_changes or diff.param_drift or diff.step_count_delta > 2:
    # Surface as CI failure — model or prompt change altered behavior
    raise RegressionDetected(
        f"Behavioral drift detected: {diff.summary}"
    )
```

### 3. Track the Agent Stability Index (ASI)

Compute a composite stability metric from trajectory data over time:

- **Tool-sequence consistency:** how often does the agent use the same tool sequence on equivalent inputs? Drift in tool ordering is an early signal.
- **Reasoning step variance:** std dev of reasoning step counts on repeated equivalent inputs. Increasing variance = instability.
- **Output format entropy:** entropy of output structure on structured-output tasks. Rising entropy = reliability loss.

```python
class AgentStabilityIndex:
    def __init__(self, window: int = 50):
        self.window = window
        self.trajectories: deque = deque(maxlen=window)

    def record(self, trajectory: Trajectory):
        self.trajectories.append(trajectory)

    def compute(self) -> float:
        if len(self.trajectories) < 10:
            return 1.0  # insufficient data

        # Tool-sequence similarity to rolling baseline
        seq_similarity = self._tool_sequence_similarity(
            list(self.trajectories)[-self.window:]
        )

        # Reasoning variance (lower = more stable)
        step_counts = [t.reasoning_steps for t in self.trajectories]
        reasoning_variance = np.std(step_counts)

        # Format entropy for structured outputs
        format_entropy = self._output_format_entropy(self.trajectories)

        # ASI: weighted composite (higher = more stable)
        return (
            0.4 * seq_similarity +
            0.3 * max(0, 1 - reasoning_variance / 10) +
            0.3 * (1 - format_entropy)
        )

    def alert_threshold(self) -> float:
        return 0.85  # ASI below this = investigate model drift
```

### 4. Monitor human intervention rate as the production canary

Instrument the human-override flow: every time a human corrects, overrides, or abandons an agent decision, log it with timestamp, task type, and agent version. Track intervention rate over rolling windows. A sustained 2x increase over a two-week baseline triggers a model-drift investigation before the broader user impact materializes.

### 5. Implement a canary evaluation pipeline

Run a lightweight behavioral eval (5-10 minutes, 50 representative cases) against every model endpoint on a daily schedule. Compare against the previous day's score. If the canary eval score drops by more than 5 percentage points, freeze the deployment and investigate before pushing more traffic.

```python
# Canary eval: daily smoke test against current endpoint
def canary_eval(agent, endpoint: str, cases: list[EvalCase]) -> CanaryReport:
    results = [agent.evaluate(case, endpoint=endpoint) for case in cases]
    scores = [r.score for r in results]

    # Compare to rolling 7-day baseline
    baseline = get_baseline(endpoint, days=7)
    delta = np.mean(scores) - baseline.mean_score

    return CanaryReport(
        endpoint=endpoint,
        current_mean=np.mean(scores),
        baseline_mean=baseline.mean_score,
        delta=delta,
        degraded_cases=[
            c for c, r in zip(cases, results)
            if r.score < baseline.per_case_baseline[c.id] - 0.1
        ],
        action="DEPLOY_HALT" if delta < -0.05 else "DEPLOY_OK"
    )
```

## Receipt

> Receipt pending — 2026-07-18. eval-view (hidai25/eval-view, Apache-2.0, 124 stars) provides the snapshot-diff implementation. Agent Stability Index is a pattern synthesis from Zylos longitudinal evaluation research (2026-04-14). Stanford/UC Berkeley GPT-4 accuracy drop (84%→51%) documented in published study. Human intervention rate as canary from Zylos research. Canary eval pipeline pattern from MLflow monitoring guide (2026-06-27) and eval-view CI integration examples.

## See also

- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — covers input distribution drift and emergent multi-agent dependencies; this entry covers the separate failure mode of provider-side behavioral change
- [S-1010 · The Agent Eval Stack](s1010-the-agent-eval-stack-when-you-cannot-trust-your-tests.md) — covers eval methodology failures; this entry covers the specific gap of longitudinal consistency measurement
- [S-1013 · The Trace Replay Harness](s1013-the-trace-replay-harness-when-your-agent-breaks-in-production-and-you-cannot-reproduce-it.md) — covers replay-based regression testing from production failure traces
- [S-997 · The Agent Observability Stack](s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — covers runtime decision observability
