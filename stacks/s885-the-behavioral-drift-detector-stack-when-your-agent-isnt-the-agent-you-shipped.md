# S-885 · The Behavioral Drift Detector Stack — When Your Agent Isn't the Agent You Shipped

Your agent shipped in April. By May it was silently worse. By June your users were filing bugs and your team had no idea why. Nothing in the code changed. The model version log showed nothing. The dashboard was green. This is behavioral drift: the silent, non-structural degradation of an agent's competence over time — not a crash, not a visible error, just a different agent wearing the same name.

Carmel Labs monitored 6,200+ production agents across 10 million tests over 30 days. **88% showed measurable behavior change within the window.** Not model version bumps — behavioral changes. The agent stopped answering correctly, started refusing valid requests, or began calling the wrong tools. Nothing broke. Everything drifted.

## Forces

- **Agents degrade before they fail.** A 5% drop in answer correctness is invisible to traditional monitoring. There is no 500 error. The API returns 200. The user gets a worse answer. Drift accumulates silently until a customer escalates.
- **Traditional monitoring assumes breakage, not change.** HTTP error rates, latency percentiles, and token budgets all stayed flat during the worst drift events in the Carmel Labs study. The agent wasn't broken — it was different.
- **Baseline comparison is the only reliable signal.** Drift is defined relative to a reference. Without a rolling baseline of agent behavior, you cannot distinguish "the agent is drifting" from "the agent was always like this."
- **Four drift types compound independently.** Answer correctness, response speed, tool-call accuracy, and refusal rate all degrade on separate timelines. An agent can drift in one dimension while holding steady in others.
- **Offline eval is a snapshot, not a monitor.** A passing eval suite at deploy time tells you the agent was acceptable then. It says nothing about now.

## The Move

The Behavioral Drift Detector runs a continuous evaluation loop in production, comparing each agent's behavior against its own rolling baseline. When behavior shifts beyond a threshold, it alerts and optionally gates or rolls back.

### 1. Establish a Behavioral Baseline

Before drift is detectable, you need a reference. Capture the agent's answer correctness, refusal rate, response latency, and tool-call accuracy on a standardized probe set — ideally 50–200 cases spanning the agent's core scenarios — on day one of production. Store the distribution, not just the mean.

```
baseline = {
  "answer_correctness": {"mean": 0.91, "std": 0.04, "n": 200},
  "refusal_rate":       {"mean": 0.03, "std": 0.01, "n": 200},
  "latency_p50_ms":     {"value": 820},
  "latency_p95_ms":     {"value": 2100},
  "tool_accuracy":      {"mean": 0.95, "std": 0.03, "n": 200},
  "captured_at": "2026-04-01"
}
```

### 2. Run a Rolling Probe Set

Schedule a lightweight eval to run against production traffic or a shadow environment daily (high-stakes agents: twice daily). Use the same probe set — consistency in inputs is what makes drift visible. The probe set should be small enough to run cheaply but diverse enough to cover the agent's core capabilities.

```
def rolling_score(agent, probe_set, window=7) -> dict:
    scores = [evaluate(agent, probe) for probe in probe_set]
    return {
        "answer_correctness": mean([s.correct for s in scores]),
        "tool_accuracy":       mean([s.tool_correct for s in scores]),
        "refusal_rate":       mean([s.is_refusal for s in scores]),
        "latency_ms":         mean([s.duration_ms for s in scores]),
        "window": window,
        "captured_at": now()
    }
```

### 3. Detect Drift Against the Baseline

Compare the current rolling score to the baseline using z-score or percentage deviation. Flag when the current score falls more than 2–3 standard deviations below the baseline mean — or when a rolling window of the last 7 days shows a sustained drop below a configurable threshold (e.g., answer correctness drops below 0.87).

```
def detect_drift(current: dict, baseline: dict, thresholds: dict) -> list[DriftEvent]:
    events = []
    for metric, threshold in thresholds.items():
        current_val = current[metric]
        baseline_val = baseline[metric]["mean"]
        baseline_std = baseline.get(f"{metric}_std", 0.01)
        
        z = (current_val - baseline_val) / baseline_std
        if z < -2.5:  # 2.5 sigma below baseline
            events.append(DriftEvent(
                metric=metric,
                current=current_val,
                baseline=baseline_val,
                z_score=z,
                severity="high" if z < -3.5 else "medium"
            ))
        elif current_val < threshold:
            events.append(DriftEvent(
                metric=metric,
                current=current_val,
                baseline=baseline_val,
                z_score=z,
                severity="medium"
            ))
    return events
```

### 4. Route to the Right Response

Not all drift needs the same response. Calibrate by drift type and severity:

| Drift Type | Severity | Response |
|---|---|---|
| Refusal rate increases | Medium | Audit recent user input distribution — the agent may be over-refusing on valid queries |
| Answer correctness drops | High | Trigger eval against latest probe set, alert team, prepare rollback |
| Response latency spikes | Medium | Check infrastructure (provider rate limits, model deprecations) |
| Tool-call accuracy drops | High | Inspect tool schema — likely MCP or API schema change (see [S-883](s883-the-mcp-schema-drift-stack-when-your-agent-uses-a-tool-that-no-longer-exists.md)) |
| Multiple metrics simultaneously | Critical | Provider model change — roll back to pinned version immediately |

### 5. Close the Loop: Promote Failures Back to the Probe Set

When a drift event is resolved (by rollback, prompt fix, or tool fix), capture the failed cases and add them to the probe set. Drift events are your most valuable eval signal — they represent the inputs that your agent actually failed on, not synthetic test cases.

```
def promote_failure(failed_probe: ProbeCase, resolution: str):
    # Add to probe set so this specific failure mode is caught going forward
    probe_set.add(failed_probe)
    # Log the drift event with resolution for pattern analysis
    drift_log.record(
        event=failed_probe,
        resolution=resolution,
        agent_version=current_agent_version
    )
```

## Tradeoffs

- **Probe set maintenance is real work.** The probe set drifts too if it isn't refreshed. Review it quarterly against production distribution — stale probes miss new failure modes.
- **Rolling baselines introduce their own stability problem.** If the agent is slowly degrading, the rolling baseline tracks the degradation, making drift invisible. Use a fixed anchor baseline (initial deploy) alongside a rolling window to catch this.
- **Eval cost compounds at scale.** Running a 200-case probe set against 50 production agents daily is ~10,000 eval calls/day. Use model tiering: run full probes daily on critical agents, lightweight 20-case probes on the rest.
- **Drift detection without drift response is just anxiety.** Every alert needs a pre-defined response play — otherwise the alert becomes noise and gets ignored until users complain.

## See also
[S-209](s209-agent-production-observability.md) · [S-839](s839-the-provider-model-drift-stack-when-your-agent-changes-without-you.md) · [S-865](s865-the-tool-behavior-drift-stack-when-the-schema-holds-but-the-silence-wrong.md) · [S-884](s884-the-production-eval-stack-when-your-agent-looks-perfect-in-tests-and-wrong-in-production.md)

> Receipt pending — 2026-07-09 — Source: Carmel Labs AgentStatus drift report (Apr 2026, 6,200+ agents, 10M tests, 1.54M drift events); Armalo AI behavioral drift detection guide (2026); Zylos Research agent observability (Apr 2026).
