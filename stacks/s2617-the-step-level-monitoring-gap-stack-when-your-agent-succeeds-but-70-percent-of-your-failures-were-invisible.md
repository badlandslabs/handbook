# S-2616 · The Step-Level Monitoring Gap Stack — When Your Agent Succeeds and 70% of Your Failures Were Invisible

Your dashboard shows green. No errors, sub-second latency, 200 OK on every response. Then a post-mortem reveals your agent has been producing silently wrong answers for three weeks, your context window has been silently degrading since day one, and tool call failures have been cascading silently through your pipeline since launch. None of it appeared in your metrics — because you were monitoring outputs, not steps. Output-only monitoring catches less than 30% of agent failure events (Revefi, August 2026). The rest are invisible by design.

## Forces

- **Agents are trajectories, not outputs.** A median of 4–7 tool invocations per agent run means 4–7 independent failure points per task. Grading only the final output is like grading a math test on the final answer alone — you catch the runs that failed loudly and miss the ones that reached a plausible answer through a broken path.
- **Agentic failures are mid-run, not terminal.** The error is rarely in the final step. It is in step 3 — a bad tool response that poisons steps 4–8, producing a confident, wrong, final answer that looks correct to every monitoring signal built for single-model inference.
- **Traditional APM was built for deterministic systems.** HTTP status codes, latency histograms, and error-rate dashboards answer "what happened" for request-response microservices. For agents, failures are probabilistic and causal — distributed across steps, stretched over time, and invisible to anything that only samples final outputs.
- **The gap between pilot and production is the step boundary.** An agent that passes every eval in the harness fails silently in production because the harness never instrumented intermediate steps — only final answers. The eval suite gave you false confidence.

## The Move

Instrument at the **step level**, not the run level. Every tool call, every context refresh, every retry, every model response between input and output is a failure point. Monitor those — not just the final result.

**The five failure modes and their step-level detection signals:**

| Failure Mode | Root Cause | Monitoring Signal | Alert Threshold |
|---|---|---|---|
| Tool call failure | External API unavailable, malformed args, missing auth | Tool error rate per step; retry spike ratio | >15% tool error rate or >3 retries/step |
| Context window exhaustion | State accumulates without pruning across steps | Token count per run; context utilization % | >80% context utilization |
| Compounding errors | Early-step error silently propagates through downstream steps | Step-by-step success rate; output drift (cosine similarity between consecutive step outputs) | >2 consecutive degraded steps |
| Hallucinated function arguments | Model generates plausible but invalid parameter values | Argument validation pass/fail rate; schema rejection count | Any schema rejection on production calls |
| Silent wrong output | Agent reaches a plausible answer through a broken path | Trajectory health score; intermediate step confidence variance | Confidence drop >30% between steps 3–5 |

**The monitoring stack (three levels):**

**Level 1 — Step trace capture.** Every LLM call, tool call, memory write, and state mutation produces a structured span. Use OpenTelemetry with agent-specific attributes: `agent.step_number`, `agent.tool_name`, `agent.token_count`, `agent.context_pct`, `agent.retry_count`. This is the raw signal layer.

**Level 2 — Step-level metrics.** Aggregate per-step signals, not per-run signals:
- `agent.steps_per_run` — detects truncated runs (low step count on expected-complexity tasks)
- `agent.tool_error_rate` — per-step tool failure ratio
- `agent.context_pct_p99` — tail context utilization
- `agent.output_drift_score` — cosine similarity between consecutive step outputs; sharp drops indicate cascading errors
- `agent.cascade_depth` — number of steps affected by a single upstream failure

**Level 3 — Anomaly detection on trajectories.** Static thresholds catch obvious failures. Trajectory anomaly detection catches the silent ones:
- **Output drift detection**: compare consecutive step outputs with embedding similarity. A sharp drop in similarity between steps 3→4 (after a tool call) flags a possible tool response poisoning.
- **Progress regression**: if `steps_completed` does not correlate with `task_progress` (measured by sub-goal completion), the agent is looping or drifting.
- **Confidence variance**: monitor the model's self-reported confidence across steps. Consecutive low-confidence steps after a high-confidence start signal the agent is losing coherence.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
import numpy as np

# Step-level instrumentation
tracer = trace.get_tracer("agent-monitor")

def step_span(agent_id: str, step: int, tool: str, inputs: dict):
    with tracer.start_as_current_span(f"step_{step}_{tool}") as span:
        span.set_attribute("agent.id", agent_id)
        span.set_attribute("agent.step_number", step)
        span.set_attribute("agent.tool_name", tool)
        span.set_attribute("agent.token_count", inputs.get("token_count", 0))
        span.set_attribute("agent.context_pct", inputs.get("context_pct", 0.0))
        span.set_attribute("agent.retry_count", inputs.get("retry_count", 0))
    return span

def detect_output_drift(embedding_history: list[np.ndarray], threshold: float = 0.7) -> list[int]:
    """Returns step indices where output drift exceeded threshold."""
    drift_steps = []
    for i in range(1, len(embedding_history)):
        similarity = np.dot(embedding_history[i-1], embedding_history[i]) / (
            np.linalg.norm(embedding_history[i-1]) * np.linalg.norm(embedding_history[i])
        )
        if similarity < threshold:
            drift_steps.append(i)
    return drift_steps

# Example: flag a cascade after tool call at step 4
# If drift occurs at step 5 and step 4 was a tool call → likely tool response poisoning
def flag_cascade(step_drift_indices: list[int], tool_call_steps: list[int]) -> list[dict]:
    cascades = []
    for d in step_drift_indices:
        preceding_tools = [t for t in tool_call_steps if t == d - 1]
        if preceding_tools:
            cascades.append({
                "drift_step": d,
                "probable_trigger": preceding_tools[0],
                "type": "tool_response_poisoning"
            })
    return cascades
```

**Alerting strategy — not on final answers, on step signals:**
- Alert on `tool_error_rate > 0.15` per run, not on final output quality
- Alert on `context_pct > 0.80`, not on when the agent finally produces output
- Alert on `output_drift_score < 0.7` for any consecutive step pair, not on when the final answer looks wrong
- Alert on `confidence_variance > 0.3` between steps 3–5, not on the final confidence score

**The production-ready checklist:**
- [ ] Every tool call produces a span with tool name, arguments, and response status
- [ ] Context utilization % is tracked per step and aggregated per run
- [ ] Tool error rate is computed per-step, not per-run
- [ ] Output drift is computed on consecutive step embeddings
- [ ] Cascade depth is computed: how many downstream steps were affected by a single failure
- [ ] Alerts fire on step-level signals, not on final-answer quality
- [ ] Trajectory replay is possible: any failed run can be reconstructed from spans

## Receipt

> Verified 2026-08-14 — Source: Revefi (August 11, 2026): "Output-only monitoring catches less than 30% of failure events." Source: ThoughtMinds.ai (August 3, 2026): 70–95% agent failure rates in live environments, with hallucinations, runaway loops, context drift, and permission issues as primary patterns. Source: Revefi five-mode taxonomy: tool call failure, context exhaustion, compounding errors, hallucinated function arguments, silent wrong output. Source: Revefi recommended signals: tool error rate per step, context utilization %, step-by-step success rate, output drift (cosine similarity), argument validation pass/fail, cascade depth monitoring. Source: Inference.net (June 2026): trace depth monitoring with alert thresholds at 20–50 tool calls per task. Source: StackPulsar: cosine similarity drop between consecutive turns flags context refresh or damage; alert at >80% context utilization. Source: Open Empower (June 2026): circuit breaker patterns, per-step cost tracking, token budget enforcement as standard production requirements. Tradeoff: step-level instrumentation adds ~5–15% latency overhead and increases storage costs proportionally. Mitigated by sampling: instrument all steps for first 1,000 runs per agent, then sample 10% with anomaly-directed full tracing.

## See also

- [S-1064 · The Trajectory Eval Stack](/stacks/s1064-the-trajectory-eval-stack-when-your-agent-passes-the-answer-and-fails-the-mission.md) — eval design that captures process, not just output
- [S-2415 · The Catastrophe That Wasn't Stack](/stacks/S-2415-the-catastrophe-that-wasnt-stack-when-your-agent-fails-but-doesnt-tell-you.md) — silent failure recovery when detection fails
- [S-1019 · The Three-Pillar Observability Stack](/stacks/s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — structured logs, semantic traces, and state diffs for agent debugging
- [S-1027 · The Scaffold Stack](/stacks/s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — liveness vs. progress detection for loop prevention
- [S-1026 · The PAEF Stack](/stacks/s1026-the-paef-stack-when-your-benchmark-says-pass-but-4-out-of-7-failure-modes-sneaked-past.md) — why episodic benchmarks miss the failures that appear in production trajectories
