# S-706 · The Silent Model Update: Detecting LLM Provider Drift Before Production Breaks

[Your p99 latency is flat. Uptime is green. Error rate is 0.02%. Users are still getting responses. But three weeks ago your agent extracted structured JSON correctly 98% of the time — now it's 81%. Nothing changed in your code, your config, or your traffic. The model provider updated their weights on Tuesday and didn't mention it in the changelog. Your existing agent-drift monitoring (error rates, latency) shows nothing wrong.]

## Forces

- **Agent-drift monitoring misses provider-drift.** Existing drift detection focuses on behavioral change at the agent level (tool selection frequency, output format drift). But the root cause — the provider quietly updated weights or RLHF — is invisible to agent-level metrics until the behavioral symptoms cascade. You need to catch the model change itself, not just its consequences.
- **Provider-side updates are opaque and continuous.** Model providers ship RLHF updates, safety patches, and capability changes continuously, often without detailed changelogs. A model that benchmarked at 94% on your eval set in January is not the same model serving production in July. The "same" API endpoint serves a different model.
- **Pinned model versions are the only honest baseline.** Unless you pin a specific model SHA or dated snapshot, you have no reproducible reference. "gpt-4o-latest" is a moving target — treating it as a stable contract is the fundamental error that provider drift exploits.
- **Shadow model comparison is the only reliable detection mechanism.** If you don't simultaneously run the same request against a pinned baseline and compare outputs, you cannot distinguish "the model changed" from "the user's query distribution changed" or "the agent pipeline changed."

## The move

### The four drift axes

| Axis | What degrades | Detection signal |
|------|--------------|-----------------|
| **Behavioral** | Tone, verbosity, formatting, response structure | Output distribution metrics, schema-validation failure rate |
| **Capability** | Specific skills (JSON extraction, classification, tool selection) | Task-specific eval scores, golden trace match rate |
| **Distribution** | Query patterns from users shift | Token/completion ratio, topic cluster drift |
| **Provider** | Weights/RLHF/safety changes without notice | Shadow model comparison, pinned baseline eval |

### The drift detection stack

**1. Pinned eval baseline — your canary**
Run a fixed eval set against every production request sample (≥1% of traffic). Track task completion rate, tool selection accuracy, and output schema validity over time. Alert on >2σ drop in any metric.

```python
class DriftDetector:
    def __init__(self, eval_set: list[EvalCase], baseline_window: int = 7):
        self.eval_set = eval_set
        self.baseline = {}   # metric_name -> list of scores
        self.baseline_window = baseline_window

    def record_sample(self, metric_name: str, score: float):
        if metric_name not in self.baseline:
            self.baseline[metric_name] = deque(maxlen=self.baseline_window)
        self.baseline[metric_name].append(score)

    def check(self, metric_name: str, current: float) -> bool:
        """True if current score is within 2 sigma of baseline mean."""
        history = list(self.baseline.get(metric_name, []))
        if len(history) < 5:
            return True  # Not enough data yet
        mean = statistics.mean(history)
        std = statistics.stdev(history)
        z = (current - mean) / std if std > 0 else 0
        return abs(z) < 2.0

    def alert(self, metric_name: str, current: float, threshold: float):
        if not self.check(metric_name, current):
            slack.send(
                f":warning: Agent drift detected on `{metric_name}`: "
                f"current={current:.3f}, baseline_mean={statistics.mean(self.baseline[metric_name]):.3f}"
            )
            # Trigger: pin to baseline model, route to shadow model, page human
```

**2. Shadow model comparison**
Route 5% of production traffic to a pinned "known-good" model version simultaneously. Compare outputs for behavioral equivalence. Flag when divergence rate exceeds threshold — this catches provider-side updates that aren't announced.

```python
async def shadow_compare(prompt: str, production_model: str, pinned_model: str, threshold: float = 0.15):
    prod_task = llm.call(production_model, prompt)
    pinned_task = llm.call(pinned_model, prompt)
    prod_out, pinned_out = await asyncio.gather(prod_task, pinned_task)

    divergence = semantic_similarity(prod_out, pinned_out)
    if divergence > threshold:
        metrics.increment("shadow_model.divergence", tags={"model": production_model})
        if metrics.get("shadow_model.divergence_rate") > 0.10:
            ops_alert("Provider model drift: divergence rate exceeds 10%")
    return prod_out  # Serve production output; shadow is read-only
```

**3. Tool selection audit log**
Track which tool the agent selects at each step. A drift in tool selection frequency — e.g., suddenly preferring `read_file` over `search_files` — often precedes a quality regression. Maintain a rolling distribution and alert on χ² deviation.

**4. Output schema validation rate**
If your agent produces structured JSON, track schema validation pass rate per hour. A 3% drop in validation rate is easier to detect than a 3% drop in "task quality" and often precedes it by 24-48 hours.

### The response protocol

| Drift severity | Signal | Response |
|----------------|--------|----------|
| Minor (1σ) | Single metric slightly off | Log + watch for 24h |
| Moderate (2σ) | Consistent deviation, 2+ metrics | Pin to baseline model, increase eval frequency |
| Severe (3σ or shadow divergence >15%) | Clear regression | Roll back to pinned model, open provider investigation |

### Anti-drift hygiene

- **Pin model versions in staging.** Never test against "latest." Lock to a SHA or dated snapshot.
- **Treat eval sets as code.** Version them, review them quarterly, and expand them with every production failure that wasn't caught.
- **Run the golden trace match continuously.** S-703 covers trajectory invariants — apply that pattern to drift detection by re-running your golden trace set on every production deployment candidate.
- **Instrument what providers don't tell you.** Build your own changelog by comparing today's production distribution against yesterday's. If something changed but you can't find it in release notes, treat it as a provider-side update.

## Receipt

> Receipt pending — 2026-07-06

## See also

- [S-401 · Agent Drift: The Longitudinal Regression Problem](stacks/s401-agent-drift-the-longitudinal-regression-problem.md) — this entry covers agent-level behavioral drift; S-706 covers the provider/model-level root cause that precedes it
- [F-171 · Agent Drift Detection](forward-deployed/f171-agent-drift-detection.md) — field notes on operationalizing drift detection in production; shares the monitoring stack with the shadow model approach here
- [S-646 · Agent Drift in Multi-Agent Systems](stacks/s646-agent-drift-in-multi-agent-systems.md) — multi-agent amplification of provider drift; when one agent's model shifts, coordination cascades multiply the effect
