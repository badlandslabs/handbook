# S-1581 · The SLO Blind Spot Stack: When Your Agent Score Is 87% and Nobody Can Tell You Why

Your AI SRE dashboard shows agent_score at 87%. The on-call engineer pulls the number, alerts the team, and opens an incident. Forty-five minutes later, no one knows which of the six SLOs is actually failing. Task completion looks fine. Latency looks fine. Cost is within budget. But something is wrong — the composite score dropped 8 points in 24 hours and the production traces show elevated failure rates. Nobody knows which metric moved.

This is the SLO blind spot — the failure mode where you have aggregate reliability data but no diagnostic decomposition. It is the most expensive state in AI operations: you know the system is sick, you cannot prescribe treatment, and you waste hours finding what should take minutes.

## Forces

- **Composite scores hide dimension-level failures.** A system can score 87% because task completion dropped to 62% (one catastrophic regression) while all other SLOs sit at 98%. Averaging masks the critical signal. This is not a visualization problem — it is an architectural one: you cannot decompose what you never disaggregated.
- **Each SLO dimension has a different remediation path.** A guardrail trip problem requires different tooling than a tool-call failure, which requires different tooling than a recovery failure. Knowing the composite is broken tells you nothing about which intervention to try first. You end up addressing the wrong layer while the real problem compounds.
- **Agent traces are too large to manually inspect.** A single production trace can span 50+ tool calls across 200KB of JSON. Searching for "which dimension degraded" in raw traces is archaeology, not engineering. Without pre-built diagnostic spans for each SLO dimension, debugging an agent incident is comparable to debugging a distributed system with no metrics — possible, but at enormous time cost.
- **The blast radius is time, not correctness.** Every minute spent finding which SLO is failing is a minute your agent continues degrading or burning budget at elevated rates. The composite score problem is not just diagnostic frustration — it is direct business impact measured in dollars and user trust.

## The move

**Measure each SLO dimension independently from day one. Structure your tracing spans around the six dimensions, not around agent architecture.**

### The six SLO dimensions

These are orthogonal metrics. A healthy agent has all six green; a broken one fails on one or two.

| Dimension | SLI | SLO target | Alert on |
|---|---|---|---|
| Task completion | End-to-end goal achievement (human eval or outcome signal) | ≥ 90% | < 88% |
| Tool-call success | Correct tool + schema-valid args + non-null response | ≥ 95% | < 92% |
| Recovery rate | Task recovered from transient failure without human intervention | ≥ 80% | < 75% |
| p99 latency | Time from task start to final output token | ≤ 120s | > 150s |
| Guardrail trip rate | Fraction of calls where guardrail fires or forces retry | ≤ 5% | > 10% |
| Trace-grounded score | LLM-as-judge evaluation of output quality on golden set | ≥ 0.85 | < 0.80 |

### Instrument with per-dimension spans

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource

provider = TracerProvider(resource=Resource.create({"service.name": "agent-runner"}))
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

# Instrument each SLO dimension as a dedicated span attribute
def run_agent_task(task_id: str, goal: str) -> dict:
    with tracer.start_as_current_span("agent.task") as task_span:
        task_span.set_attribute("task.id", task_id)
        task_span.set_attribute("task.goal", goal)

        # Dimension 1: Tool-call success
        with tracer.start_as_current_span("slo.tool_call") as tc_span:
            tc_span.set_attribute("slo.dimension", "tool_call_success")
            tool_calls = agent.plan(goal)
            tc_span.set_attribute("tool_call.count", len(tool_calls))
            tc_span.set_attribute("tool_call.schema_valid", all(c.schema_valid for c in tool_calls))
            tc_span.set_attribute("tool_call.success_rate", compute_success_rate(tool_calls))

        # Dimension 2: Recovery rate
        with tracer.start_as_current_span("slo.recovery") as rec_span:
            rec_span.set_attribute("slo.dimension", "recovery_rate")
            result, recovered = agent.execute_with_retry(tool_calls)
            rec_span.set_attribute("recovery.attempts", recovered)

        # Dimension 3: Guardrail trip rate
        with tracer.start_as_current_span("slo.guardrail") as gr_span:
            gr_span.set_attribute("slo.dimension", "guardrail_trip_rate")
            gr_span.set_attribute("guardrail.fired", result.guardrail_fired)
            gr_span.set_attribute("guardrail.blocked", result.guardrail_blocked)

        # Dimension 4: Latency
        import time
        with tracer.start_as_current_span("slo.latency") as lat_span:
            lat_span.set_attribute("slo.dimension", "p99_latency")
            lat_span.set_attribute("latency.total_seconds", result.duration_ms / 1000)

        # Dimension 5: Trace-grounded score (async, sampled)
        if should_sample_for_quality_eval(task_id):
            with tracer.start_as_current_span("slo.quality") as qual_span:
                qual_span.set_attribute("slo.dimension", "trace_grounded_score")
                score = llm_judge.evaluate(result, golden_set)
                qual_span.set_attribute("quality.score", score)
                task_span.set_attribute("quality.score", score)

        # Dimension 6: Task completion (terminal)
        with tracer.start_as_current_span("slo.completion") as comp_span:
            comp_span.set_attribute("slo.dimension", "task_completion")
            comp_span.set_attribute("task.completed", result.goal_achieved)
            task_span.set_attribute("task.completed", result.goal_achieved)

        return {"status": "ok" if result.goal_achieved else "failed", "spans": {...}}
```

### Build an alert matrix, not an aggregate alert

```python
# Alert routing: which SLO dimension → which team → which runbook
ALERT_MATRIX = {
    "tool_call_success": {"threshold": 0.92, "team": "platform", "runbook": "RUNBOOK-tool-call"},
    "recovery_rate": {"threshold": 0.75, "team": "reliability", "runbook": "RUNBOOK-recovery"},
    "guardrail_trip_rate": {"threshold": 0.10, "team": "safety", "runbook": "RUNBOOK-guardrail"},
    "p99_latency": {"threshold_ms": 150_000, "team": "infra", "runbook": "RUNBOOK-latency"},
    "trace_grounded_score": {"threshold": 0.80, "team": "quality", "runbook": "RUNBOOK-quality"},
    "task_completion": {"threshold": 0.88, "team": "all", "runbook": "RUNBOOK-task-completion"},
}

def check_slo_dashboard(metrics: dict) -> list[Alert]:
    alerts = []
    for dimension, value in metrics.items():
        cfg = ALERT_MATRIX.get(dimension)
        if cfg is None:
            continue
        threshold = cfg["threshold"] if isinstance(cfg["threshold"], float) else value
        if value < cfg["threshold"]:
            alerts.append(Alert(
                dimension=dimension,
                value=value,
                threshold=cfg["threshold"],
                team=cfg["team"],
                runbook=cfg["runbook"],
            ))
    return alerts  # One alert per dimension, not one alert for "agent_score dropped"
```

### The anti-pattern to avoid

Do not build a single `agent_score` as your primary signal. It answers "is something wrong?" but cannot answer "what is wrong?" — and the answer to the second question is the one your engineer needs at 2 AM. Use the composite for executive dashboards only. For operational use, decompose.

## Receipt

> Verified 2026-07-24 — Source: FutureAGI "AI Agent Reliability Metrics: Six SLOs (2026)" (futureagi.com, Sep 2025, updated May 2026). Pattern validated against existing S-1005 (AI SRE) and S-1240 (Reliability Multiplication Law) — those entries cover *what* to measure and *why* the math compounds. This entry fills the gap: *how* to instrument each dimension as an independent, actionable span with targeted alerting. Deduplication confirmed: S-1005 does not show per-dimension span instrumentation; S-929 and S-946 cover eval coverage gaps but not diagnostic decomposition of a failing production system.

## See also

- [S-1005 · AI SRE — The Reliability Discipline Your Agent Team Doesn't Have Yet](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the four golden signals and incident taxonomy
- [S-1240 · The Reliability Multiplication Law — When 95% Per-Step Accuracy Means 36% Task Completion](s1240-the-reliability-multiplication-law-when-95-percent-per-step-accuracy-means-36-percent-task-completion.md) — why chain length matters more than per-step quality
- [S-1574 · The Eval Gap Stack — Why Your Agent Passes Every Test and Still Fails in Production](s1574-the-eval-gap-stack-when-your-agent-passes-every-test-and-still-fails-in-production.md) — when your eval set diverges from production distribution
