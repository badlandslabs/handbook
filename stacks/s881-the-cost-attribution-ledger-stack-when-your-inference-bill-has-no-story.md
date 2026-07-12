# S-881 · The Cost Attribution Ledger Stack — When Your Inference Bill Has No Story

Your CFO asks why inference spend jumped 40% last month. You pull the provider dashboard — one rising line, one number. You can't tell which team caused it, which agent workflow, which tool, which retry loop, or whether any of it produced value. The bill is real; the story behind it is absent. The Cost Attribution Ledger (CAL) fixes this: a five-layer schema that labels every token inside every agent span by where it came from and why it burned.

## Forces

- A single agentic request generates 5–30× more LLM calls than a chatbot — one outer request spawns a classifier, a retriever rewriter, a generator, a judge, and retries at each step; the provider invoice shows one number, one entry
- Token costs fall into structurally different buckets — planning, tool execution, context carry, retry tax — and each bucket has a different fix; lumping them together makes optimization impossible
- The noisy neighbor problem in multi-agent fleets: one team's workflow quietly saturates the shared inference budget, and without per-span attribution you can't identify the culprit until the bill arrives
- Cache accounting is non-trivial — cached-read, cached-write, and batch tokens price differently; a naive `total tokens × list price` over-reports spend by 40%+ on cached workloads
- Per-user and per-tenant attribution are different axes — the same workflow serving a high-volume vs. low-volume tenant has radically different unit economics that aggregate rollups hide

## The move

### Layer 1 — The Cost Event Schema

Every LLM call emits a structured event at the gateway layer, before it reaches the provider:

```python
@dataclass
class CostEvent:
    trace_id:     str          # links to parent OTel trace
    span_id:      str
    phase:        Phase        # PLANNING | TOOL_USE | REASONING | GENERATION
    agent_role:   str          # "orchestrator" | "evaluator" | "retriever"
    tool_type:    str | None   # "database_query" | "web_search" | None
    input_tokens: int
    output_tokens: int
    cache_hits:   int          # cached input tokens
    cache_creation: int        # tokens written to cache this call
    retry_count:  int          # which retry attempt is this (0 = first)
    tenant_id:    str
    feature:      str          # "customer_support" | "code_review" | ...
    model:        str
    stop_reason:  str | None
    latency_ms:   float
```

Instrument at the gateway — not inside the agent — so every call is captured regardless of where the model provider is, what SDK is used, or whether the agent code is correct.

### Layer 2 — Five Attribution Buckets

Aggregate tokens into these five cost centers, not a single total:

| Bucket | What it captures | The question it answers |
|---|---|---|
| **Phase** | Which agent step (plan, tool, judge, gen) | Which step burns most? |
| **Agent Role** | Which role in the fleet (orchestrator, specialist, critic) | Which agent is expensive? |
| **Tool-Call Type** | Which external call drove the token spend | Which tool is costly? |
| **Context Carry** | Tokens from prior turns repeated in this call | Is context growing or stable? |
| **Retry Tax** | Tokens spent on failed attempts | Are failures expensive? |

```sql
-- Core attribution query
SELECT
    phase,
    agent_role,
    tool_type,
    SUM(input_tokens - cache_hits) AS cacheable_tokens,
    SUM(cache_creation) AS cache_write_tokens,
    SUM(output_tokens) AS generation_tokens,
    SUM(retry_count > 0) AS is_retry,
    COUNT(*) AS call_count
FROM cost_events
WHERE trace_id = :trace_id
GROUP BY ROLLUP(phase, agent_role, tool_type)
ORDER BY (cacheable_tokens + generation_tokens) DESC;
```

### Layer 3 — Context Carry Audit

Context carry tokens are the most invisible cost. Track them explicitly:

```python
def estimate_context_carry(span: dict, prior_spans: list[dict]) -> int:
    """Count tokens from prior turns carried into this span's prompt."""
    carry = 0
    for prior in prior_spans:
        if prior["span_id"] in span.get("context_refs", []):
            carry += prior["output_tokens"]  # model's output becomes next input
    return carry
```

Alert when context carry exceeds 60% of input tokens — this is the pattern that silently inflates costs across long-horizon tasks.

### Layer 4 — Retry Tax Isolation

Retry loops are the hidden multiplier. Instrument retries at the call level:

```python
for attempt in range(MAX_RETRIES):
    span = tracer.start_span("llm.call")
    try:
        result = llm.call(prompt, **kwargs)
        span.set_attribute("retry.count", attempt)
        span.set_attribute("retry.is_retry", attempt > 0)
        emit_cost_event(span, attempt=attempt, ...)
        return result
    except RateLimitError:
        span.set_attribute("error.type", "rate_limit")
        if attempt == MAX_RETRIES - 1:
            raise
        await asyncio.sleep(2 ** attempt)  # backoff
```

Isolate retry cost in dashboards — a workflow at 80% pass rate with no retry accounting looks fine; with retry accounting it shows 5× effective cost on the 20% that fail.

### Layer 5 — Per-Tenant Burn-Down

```python
def compute_burn_down(tenant_id: str, window: str = "30d") -> BurnDown:
    events = query_cost_events(tenant_id=tenant_id, window=window)
    return BurnDown(
        total_tokens=sum(e.cacheable_tokens + e.generation_tokens for e in events),
        cache_savings=sum(e.cache_hits for e in events),
        effective_cost=sum(
            effective_cost_per_call(e) for e in events
        ),
        by_phase=group_by(events, "phase"),
        by_feature=group_by(events, "feature"),
        outcome_rate=compute_outcome_rate(events),  # JOIN with outcome table
        cost_per_outcome=sum(effective_costs) / outcome_count,
    )
```

The key metric is `cost_per_outcome`, not `cost_per_call`. A Haiku call at $0.0008 looks cheap until 20% of calls fail and require downstream correction. At 80% pass rate, effective cost-per-outcome is $0.001000 — 25% worse than a $0.001/call model with 99% pass rate.

## Receipt

> Verified 2026-07-09 — Reviewed production cost-attribution schemas from AppScale (June 2026), Digital Applied (April 2026), and the WOWHOW Cost Attribution Ledger framework. Cross-checked against existing handbook entries S-170 (cost-per-outcome), S-208 (per-tenant attribution), S-196 (OTel telemetry), and S-209 (agent observability). No existing entry covers per-span, five-bucket token attribution across Phase × Agent Role × Tool-Call Type × Context Carry × Retry Tax within agent traces. The new angle is structural decomposition of cost within a single trace, not aggregate rollup or per-call pricing.

## See also

- [S-170 · Cost-Per-Outcome Tracker](s170-cost-per-outcome-tracker.md) — aggregate cost-per-outcome across pipelines; this entry adds per-span decomposition
- [S-209 · Agent Production Observability](s209-agent-production-observability.md) — behavioral observability; this entry adds the financial dimension
- [S-196 · OTel GenAI Telemetry](s196-otel-genai-telemetry.md) — trace infrastructure; this entry adds the cost-event schema on top of spans
- [S-123 · Prompt Section Cost Attribution](s123-prompt-section-cost-attribution.md) — per-section token breakdown; this entry adds per-span structural role
