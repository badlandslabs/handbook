# S-1130 · The Trace-Attributed Cost Optimization Stack: When Cheaper Models Cost More

You swapped GPT-4o for Haiku. Cost-per-token dropped 65%. The monthly invoice went up. This is not a billing error — it is a measurement error. The cheapest token is not the cheapest outcome. Optimizing agent cost without trace-attributed spans and quality-gated quality signals reliably makes things worse.

## Forces

- **Cost-per-token is a line item, not a metric.** Swapping to a cheaper model reduces the price of each call. It does not reduce the number of calls. If the cheaper model picks the wrong tool first, loops twice as often, and retries on parseable errors, cost-per-outcome goes up.
- **The step count is the hidden multiplier.** Each agent step is an LLM call. A 4-step execution path at $0.001/call costs 4× a 1-step path — not because the model is expensive, but because of the execution graph. Step count is itself a stochastic output of the model.
- **Routing decisions are made once and never audited.** Teams set a routing policy at launch (use Haiku for simple tasks, GPT-4o for complex ones) and never measure whether that policy is actually cheaper. The policy is a hypothesis, not a result.
- **Infrastructure overhead hides in the line item.** Inference infrastructure adds 15–40% to total AI spend (FutureAGI, 2026). Vector DB hosting, observability tooling, and retry traffic are invisible unless token metering assigns them to a span.
- **Quality and cost are a single variable.** A 70% task-completion rate at $0.0008/call is more expensive than an 98% rate at $0.003/call. The correct comparison is `cost-per-resolved-outcome = total cost / successful completions`. Most teams never compute it.

## The move

### 1. Instrument every token as a span attribute

Wrap every LLM call with an OpenTelemetry span. Attach `token_count.input`, `token_count.output`, `token_count.cached`, and `cost.dollars` as span attributes. Attach a `task_id` and `resolution_status` (success/fail/retry) at the run level. This is the only foundation that makes everything else possible.

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

def llm_call(messages, model, span_name="llm"):
    with tracer.start_as_current_span(span_name) as span:
        start = time.time()
        response = model.invoke(messages)
        elapsed = time.time() - start

        # Token counting (provider-specific or via tokenizer)
        input_tokens = count_tokens(messages, model)
        output_tokens = count_tokens(response.content, model)
        cached_tokens = estimate_cached_tokens(messages, model)  # if supported

        span.set_attribute("llm.input_tokens", input_tokens)
        span.set_attribute("llm.output_tokens", output_tokens)
        span.set_attribute("llm.cached_tokens", cached_tokens)
        span.set_attribute("llm.cost_dollars", compute_cost(input_tokens, output_tokens, model))
        span.set_attribute("llm.latency_ms", elapsed * 1000)
        span.set_attribute("llm.model", model)

        return response
```

### 2. Compute cost-per-resolved-outcome, not cost-per-call

Aggregate at the run level. One user request = one run. Count resolved outcomes by your own success criteria (not model-defined). A run is resolved when your downstream validator accepts the output.

```python
# Per-run aggregation
run = trace.get_current_span()
run.set_attribute("run.task_type", task_type)
run.set_attribute("run.total_cost_usd", total_cost_across_spans)
run.set_attribute("run.total_tokens", total_tokens_across_spans)
run.set_attribute("run.resolution", "success" if downstream_validator.accepts(output) else "failed")

# The metric that matters
# cost_per_resolved = Σ(run.cost) / Σ(run.resolution == "success")
# NOT: Σ(span.cost) / Σ(span.count)
```

### 3. Trace-attributed cost dashboard (per-span breakdown)

Group spans by type: `llm.*`, `tool.*`, `retrieval.*`, `mcp.*`. Show cost contribution and resolution correlation per group. The highest-cost span is not always the problem — a low-cost span called 300 times can dwarf an expensive span called 3 times.

```python
# Aggregate across all runs (rolling window)
def cost_attribution_report(traces, window_hours=24):
    by_span_type = defaultdict(lambda: {"cost": 0, "calls": 0, "runs": set(), "resolutions": []})
    for run in traces:
        for span in run.spans:
            key = span.name  # e.g. "llm.planner", "tool.search", "retrieval.vector"
            by_span_type[key]["cost"] += span.attributes["llm.cost_dollars"]
            by_span_type[key]["calls"] += 1
            by_span_type[key]["runs"].add(run.id)
            by_span_type[key]["resolutions"].append(run.attributes["resolution"])

    report = []
    for name, stats in by_span_type.items():
        success_rate = sum(stats["resolutions"]) / len(stats["resolutions"])
        cost_per_run = stats["cost"] / len(stats["runs"])
        report.append({
            "span": name,
            "total_cost": stats["cost"],
            "calls": stats["calls"],
            "unique_runs": len(stats["runs"]),
            "cost_per_run": cost_per_run,
            "success_rate": success_rate,
        })
    return sorted(report, key=lambda x: x["total_cost"], reverse=True)
```

### 4. Quality-bounded model swap

Before swapping a model, compute `cost_per_resolved_outcome` for both candidates on the same task distribution. A model swap passes the quality gate only if cost-per-outcome improves at the same or higher resolution rate. Do this in a shadow traffic period before full rollout.

```python
def quality_bounded_swap(candidate_model, production_model, shadow_runs, quality_threshold=0.95):
    shadow_results = []
    for run in shadow_runs:
        production_result = run.production_output  # already computed
        candidate_result = run_candidate(run.task, candidate_model)

        shadow_results.append({
            "task": run.task,
            "prod_cost": run.production_cost,
            "prod_resolution": downstream_validator.accepts(production_result),
            "cand_cost": run.candidate_cost,
            "cand_resolution": downstream_validator.accepts(candidate_result),
        })

    prod_cpo = compute_cost_per_outcome(shadow_results, "prod_resolution", "prod_cost")
    cand_cpo = compute_cost_per_outcome(shadow_results, "cand_resolution", "cand_cost")
    prod_sr = sum(r["prod_resolution"] for r in shadow_results) / len(shadow_results)
    cand_sr = sum(r["cand_resolution"] for r in shadow_results) / len(shadow_results)

    if cand_sr < quality_threshold:
        return {"approved": False, "reason": f"candidate SR {cand_sr:.1%} below threshold {quality_threshold:.1%}"}
    if cand_cpo >= prod_cpo:
        return {"approved": False, "reason": f"candidate CPO ${cand_cpo:.4f} >= production ${prod_cpo:.4f}"}
    return {
        "approved": True,
        "prod_cpo": prod_cpo,
        "cand_cpo": cand_cpo,
        "savings_pct": (prod_cpo - cand_cpo) / prod_cpo * 100,
        "prod_sr": prod_sr,
        "cand_sr": cand_sr,
    }
```

### 5. The operational loop: detect → attribute → optimize → verify

Run the attribution report weekly. The optimization lever is always one of: reduce step count (better planner prompting), reduce retrieval volume (tighter query, fewer chunks), eliminate retry loops (better tool error parsing), or re-route by task complexity (not by heuristic). Never swap models without running the shadow period first.

```
Weekly cost review:
1. Pull attribution report (last 7 days)
2. Identify span type with highest cost/ratio
3. Investigate worst-case runs (highest cost, lowest resolution)
4. Hypothesize cause (wrong model, excess retrieval, retry loop)
5. Intervention: prompt, routing policy, retrieval config, or model swap
6. Shadow period: run intervention on 5% traffic for 3 days
7. If quality-bounded swap passes → full rollout
8. Track resolution rate and cost-per-outcome post-deploy
```

## Receipt

> Verified 2026-07-15 — Research synthesis from FutureAGI "AI Agent Cost Optimization and Observability (2026)" and MHTECHIN "Cost Optimization for Autonomous AI Agents: The Complete 2026 Guide." Core findings: (1) token pricing is decoupled from outcome cost — teams optimizing cost-per-token without measuring step count and resolution rate reliably increase total spend; (2) multi-agent architectures consume 15× more tokens than single-agent approaches; (3) real-world cost reductions of 60–80% are achievable through trace-attributed optimization, quality-bounded routing, and retrieval tuning. The operational loop and quality-bounded swap protocol are synthesized from production engineering patterns described in FutureAGI's tier-routing framework. Gap confirmed: S-170 covers cost-per-outcome as a metric but not the instrumentation foundation or optimization loop; S-1080 covers forecasting but not trace-attributed active optimization; S-389 covers the numbers but not the quality gate or operational cadence. This stack fills the active optimization layer.

## See also

- [S-170 · Cost-Per-Outcome Tracker](s170-cost-per-outcome-tracker.md) — defines the metric; this stack supplies the instrumentation and loop
- [S-1080 · The Agent Cost Forecaster Stack](s1080-the-agent-cost-forecaster-stack-when-your-budget-meets-stochastic-execution.md) — forecasting at the budget layer; this stack operates at the per-trace layer
- [S-389 · Production Agent Cost — The Numbers That Actually Matter](s389-production-agent-cost-numbers.md) — the step-count multiplier insight; this stack operationalizes it
- [S-157 · Tool-Aware Model Router](s157-the-tool-aware-model-router-when-your-router-picks-the-wrong-model-for-the-wrong-task.md) — routing policy; quality-bounded swap is the deployment discipline for router changes
