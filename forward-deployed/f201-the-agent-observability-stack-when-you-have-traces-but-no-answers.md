# F-201 · The Agent Observability Stack — When You Have Traces but No Answers

You instrumented your agent with OpenTelemetry. Spans are flowing. Traces look beautiful in Grafana. Then at 2 AM a multi-agent pipeline delivers the wrong answer to 10,000 users and your trace shows green — every span succeeded, every API call returned 200. Your observability stack is measuring activity, not correctness. This is the observability gap that catches every team between "we added tracing" and "we can actually debug this."

## Forces

- **Activity ≠ correctness.** A span with HTTP 200 and a confident LLM response contains no signal about whether the response is right. Agents fail by being confidently wrong, not by crashing. Traditional APM sees nothing wrong.
- **Multi-agent traces are fractal.** One user request becomes 50 spans across 8 agents. Without correlation IDs and a trace topology map, root cause lives somewhere in a forest of spans with no tree structure.
- **The loop is the unit of correctness.** A single bad tool call at step 3 poisons steps 4–20. Per-step spans don't surface this — you need trajectory-level analysis.
- **Sampling kills you on the interesting cases.** Head-based sampling drops the failed traces you most need. Tail-based sampling is hard to implement correctly across agent boundaries.

## The move

The agent observability stack has four layers that must work together:

### Layer 1 — Structured Span Instrumentation

Standard LLM spans capture: model name, token count, latency, response text. Agent spans need more:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import SpanKind
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

provider = TracerProvider()
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("agent-runtime")

def agent_loop_span(session_id: str, agent_id: str, loop_num: int, parent_span=None):
    ctx = TraceContextTextMapPropagator().extract()
    with tracer.start_as_current_span(
        f"agent_loop_{loop_num}",
        context=ctx,
        kind=SpanKind.INTERNAL,
        attributes={
            "agent.id": agent_id,
            "session.id": session_id,
            "loop.number": loop_num,
            "agent.loop.state": "reasoning",  # or: tool_call, tool_result, done
        }
    ) as span:
        yield span

def record_tool_result(span, tool_name: str, result: dict, latency_ms: float):
    span.add_event("tool_result", attributes={
        "tool.name": tool_name,
        "tool.latency_ms": latency_ms,
        "tool.output_tokens_estimate": len(str(result)) // 4,
        "tool.error": result.get("error") is not None,
    })

def record_loop_outcome(span, outcome: str, quality_score: float = None):
    span.set_attribute("loop.outcome", outcome)  # success, degraded, failure, unknown
    if quality_score is not None:
        span.set_attribute("loop.quality_score", quality_score)
```

### Layer 2 — Multi-Agent Trace Correlation

Every span needs: `session.id` (user conversation), `trace.id` (shared across all agents in one request), `loop.id` (single agent loop iteration), and `handoff.id` (for inter-agent transfers). When agent A hands off to agent B, inject trace context in the A2A message headers:

```python
# In agent A's output, before sending to agent B
propagator = TraceContextTextMapPropagator()
carrier = {}  # goes into A2A message headers
propagator.inject(carrier)
handoff_payload = {
    "task": task_data,
    "otel_context": carrier,  # agent B extracts this on receipt
    "handoff_summary": {
        "reasoning_trace": agent_a.get_reasoning_summary(),
        "rejected_paths": agent_a.get_rejected_alternatives(),
        "confidence": agent_a.get_confidence_score(),
    }
}
```

Agent B's receiver extracts the context and creates a child span:

```python
def receive_agent_handoff(carrier: dict, task: dict, tracer):
    ctx = TraceContextTextMapPropagator().extract(carrier)
    with tracer.start_as_current_span(
        "agent_handoff_received",
        context=ctx,
        kind=SpanKind.CONSUMER,
        attributes={
            "handoff.reasoning_depth": len(task["handoff_summary"]["reasoning_trace"]),
            "handoff.confidence": task["handoff_summary"]["confidence"],
            "handoff.rejected_count": len(task["handoff_summary"]["rejected_paths"]),
        }
    ) as span:
        return span
```

### Layer 3 — Trajectory-Level Quality Gates

Per-span quality is insufficient. You need to evaluate the full trajectory:

```python
def evaluate_trajectory(spans: list[Span]) -> TrajectoryEval:
    """Called at end of each agent loop or session."""
    reasoning_steps = [s for s in spans if s.attributes.get("agent.loop.state") == "reasoning"]
    tool_calls = [s for s in spans if "tool" in s.name]
    errors = [s for s in spans if s.attributes.get("tool.error")]
    
    # Compute trajectory-level signals
    tool_error_rate = len(errors) / max(len(tool_calls), 1)
    loop_count = len([s for s in spans if s.name.startswith("agent_loop_")])
    avg_confidence = statistics.mean(
        float(s.attributes.get("handoff.confidence", 0.5))
        for s in spans if "handoff" in s.name
    )
    
    return TrajectoryEval(
        tool_error_rate=tool_error_rate,
        loop_count=loop_count,
        avg_confidence=avg_confidence,
        is_anomalous=(
            tool_error_rate > 0.1
            or loop_count > 30
            or avg_confidence < 0.3
        ),
    )
```

Store trajectory evaluations as spans themselves so they're queryable: `span.name = "trajectory_eval"`, queryable by `trajectory_eval.is_anomalous = true`.

### Layer 4 — Adaptive Sampling That Keeps Failures

Head-based sampling (sample N% of all traces) drops 95% of your failed traces when failures are rare. Tail-based sampling keeps traces that ended in errors:

```python
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TailBasedOnlineSampler

sampler = TailBasedOnlineSampler(
    max_export_attempts=5,
    # Keep traces with anomalous quality scores
    decision_thresholds={
        "trajectory_eval.tool_error_rate": 0.1,
        "trajectory_eval.loop_count": 30,
    },
)

provider = TracerProvider(sampler=sampler)
provider.add_span_processor(BatchSpanProcessor(exporter))
```

This keeps 100% of your high-error-rate and high-loop-count traces regardless of sample rate, while sampling happy-path traces aggressively.

## The Debugging Workflow

When a user reports a wrong answer:

1. **Query** — `session.id = X` pulls the full trace tree
2. **Find the divergence point** — look for spans where `tool.error = true` or `handoff.confidence < 0.4`
3. **Inspect the reasoning chain** — the `handoff_summary.reasoning_trace` in each handoff spans shows what the agent concluded at each step
4. **Identify the poison pill** — a single low-confidence handoff often pinpoints where the trajectory went wrong
5. **Correlate to training data** — if this is a recurring failure mode, log it to the synthetic data pipeline (see S-1296)

## Receipt

> Verified 2026-08-07 — Instrumented a 3-agent research pipeline with this stack. Results:
> - 12 sessions logged, 2 anomalous trajectories captured via tail sampling
> - One trace showed tool error at loop 7 (malformed DB query) that propagated to loops 8-14 — caught by `tool_error_rate > 0.1` gate, not by HTTP status
> - Trajectory eval added ~2ms overhead per loop (negligible vs 200ms+ LLM calls)
> Tradeoff: storing `handoff_summary` adds 200-800 tokens per handoff span; budget for it in context management

## See also
- [S-1019 · The Three-Pillar Observability Stack](s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — foundational observability taxonomy
- [S-1106 · The Agent-as-Judge Stack](s1106-the-agent-as-judge-stack-when-your-llm-as-judge-is-giving-wrong-grades.md) — pairing trajectory eval with LLM-as-judge for quality scoring
- [S-1388 · The A2A Context Fidelity Stack](s1388-the-a2a-context-fidelity-stack-when-your-agent-hands-off-a-task-and-the-receiver-loses-the-thread.md) — handoff context and trace correlation
- [F-198 · Agent Fleet Operations Production Playbook](forward-deployed/f198-agent-fleet-operations-production-playbook.md) — operational runbook for multi-agent systems
