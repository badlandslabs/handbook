# S-1936 · The Attribution Ceiling Stack — When You See a $100K Invoice but Can't Find a Single Dollar

You run 12 agents across three teams. The monthly invoice is $100,000. You know the total. You know nothing else — not which agent burned the budget, which phase of which workflow generated the spike, or whether a single misbehaving loop caused 80% of the charge. You have trace data. You have cost logs. You don't have attribution. This is the attribution ceiling: the point where your observability stack stops telling you anything useful, right when you need it most.

Per-agent, per-phase, per-call-type token attribution is not a nice-to-have. It is the difference between blind cost-cutting and surgical optimization. Without it, every cost-reduction decision is a guess.

## Forces

- **Token costs are invisible at the agent level.** Providers give you a total. Most observability stacks give you a total. Neither tells you which agent, phase, or call type generated the spend. A $100K invoice with no per-agent breakdown is an invoice you cannot act on.
- **The multi-agent invoice is a black box.** When a supervisor agent orchestrates 8 sub-agents, each sub-agent makes its own API calls. The provider sees 8 separate API keys or 8 line items with identical project IDs. The orchestrator sees a total. Nobody sees the causal chain from task → agent → call → token.
- **Naive attribution is worse than none.** Attributing cost by call count gives you a number that has almost no correlation with actual spend. A Haiku call that loops 200 times costs more than a single Opus call. Call count is a proxy that actively misleads.
- **Optimization requires dimensionality you don't have.** You can't route tasks to cheaper models without knowing which agent types consume the most tokens. You can't fix a retry loop without knowing which tool-call type triggers it. You can't do capacity planning without per-phase cost curves. All of these require attribution at the dimension where the action happens.
- **EU AI Act and billing requirements are converging.** Article 12 of the EU AI Act requires documented oversight of AI system costs and resource use. Per-agent attribution is the infrastructure that makes compliance possible — and most teams don't have it.

## The move

**Build a five-dimension attribution model that tags every token to a specific cell.** The goal is not to reduce cost directly. It is to make cost *operational* — to give engineering teams a queryable model where any dollar of spend can be traced to a specific (agent_role, phase, call_type, context_bucket, retry_tax) tuple.

### The five dimensions

**1. Agent Role** — Who consumed the token. Supervisor, researcher, coder, reviewer, escalation-agent. Not the agent *instance* (which changes on every run) but the *role* (which is stable across runs). Tag at the span level using the agent's initialized role name.

**2. Phase** — Where in the workflow the token was consumed. intake, decomposition, parallel-execution, synthesis, review, escalation, rollback. Phases are defined by the orchestration graph, not the agent. A "review" phase costs money whether it runs in agent A or agent B.

**3. Call Type** — What kind of LLM call it was. `llm.planning`, `llm.execution`, `llm.reasoning` (thinking tokens), `llm.synthesis`, `tool.result.summary`. The call type determines the cost per token and the retry risk. Reasoning calls (extended thinking) cost 5–8× more per token than standard calls but don't appear in `choices[0].message.content` — meaning standard loggers miss them entirely.

**4. Context Carry** — Which tokens were newly added vs. carried forward. `input.new`, `input.carry`, `output.generated`. Context carry tags let you distinguish between agents that add value and agents that just re-send existing context. A carry ratio >0.7 on an agent means that agent is mostly re-transmitting context — a strong signal for optimization.

**5. Retry Tax** — Tokens consumed by failed calls that had to be retried. Tag every token from calls that returned non-terminal errors (rate limit, parse failure, timeout). The retry tax is the most actionable dimension: it is 100% waste, and it is almost always invisible without explicit tagging.

### The implementation

```python
from opentelemetry import trace
from opentelemetry.trace import SpanKind

tracer = trace.get_tracer(__name__)

def attributed_llm_call(
    agent_role: str,
    phase: str,
    call_type: str,
    model: str,
    messages: list,
    max_retries: int = 3,
) -> dict:
    span = tracer.start_span(
        f"{agent_role}.{call_type}",
        kind=SpanKind.CLIENT,
    )
    span.set_attribute("agent.role", agent_role)
    span.set_attribute("workflow.phase", phase)
    span.set_attribute("call.type", call_type)
    span.set_attribute("model.name", model)

    # Tag context carry
    input_tokens = estimate_tokens(messages)
    carry_tokens = estimate_carry_tokens(messages)
    span.set_attribute("context.new_tokens", input_tokens - carry_tokens)
    span.set_attribute("context.carry_tokens", carry_tokens)
    span.set_attribute("context.carry_ratio", carry_tokens / max(input_tokens, 1))

    attempt = 0
    retry_tokens = 0
    last_error = None

    while attempt <= max_retries:
        try:
            response = model_call(model, messages)
            span.set_attribute("call.success", True)
            span.set_attribute("output.tokens", response.usage.completion_tokens)
            span.set_attribute("input.tokens", response.usage.prompt_tokens)

            # Tag thinking tokens if present (extended thinking models)
            if hasattr(response.usage, 'thinking_tokens'):
                span.set_attribute("output.thinking_tokens", response.usage.thinking_tokens)
                span.set_attribute("call.type", "llm.reasoning")

            # Tag retry tax
            if retry_tokens > 0:
                span.set_attribute("retry.tokens", retry_tokens)
                span.set_attribute("retry.count", attempt)

            span.set_attribute("cost.total", calculate_cost(
                input_tokens + carry_tokens,
                response.usage.completion_tokens,
                model
            ))
            span.end()
            return response

        except (RateLimitError, ParseError, TimeoutError) as e:
            attempt += 1
            last_error = e
            retry_tokens += estimate_tokens(messages)  # approximate; exact requires response
            if attempt > max_retries:
                span.set_attribute("call.success", False)
                span.set_attribute("retry.tokens", retry_tokens)
                span.set_attribute("retry.count", attempt - 1)
                span.record_exception(e)
                span.end()
                raise

    raise last_error
```

### The attribution query model

Once every call is tagged, cost becomes a query:

```python
# Which agent roles consume the most on retry tax?
retries_by_role = query_traces(
    filter={"call.success": False},
    group_by="agent.role",
    metric="sum(retry.tokens)",
    aggregate=cost_dollar
)
# → {"researcher": "$4,200", "coder": "$890", "supervisor": "$120"}

# What % of each phase's cost is pure waste (retry tax)?
waste_ratio_by_phase = query_traces(
    group_by="workflow.phase",
    metric="sum(retry.tokens) / sum(cost.total)"
)
# → {"parallel-execution": 0.31, "intake": 0.02, "review": 0.08}

# Which call types have the highest carry ratio (re-transmitting context)?
carry_by_call_type = query_traces(
    group_by="call.type",
    metric="avg(context.carry_ratio)"
)
# → {"llm.synthesis": 0.82, "llm.execution": 0.41, "llm.planning": 0.15}
```

A carry ratio >0.7 on `llm.synthesis` means the synthesis agent is paying full price to re-read context it didn't add. The fix: push the synthesis agent a compressed summary instead of full context.

### The priority stack

1. **Start with agent role + call type** — two attributes that cost nothing to add and unlock the most common optimization questions.
2. **Add retry tax** — the single highest-ROI dimension. Every retry token is 100% waste. Tag it, alert on it, and the fix is usually a timeout, a backoff, or a circuit breaker.
3. **Add phase** — requires coordination with the orchestration layer but enables per-workflow cost curves.
4. **Add context carry** — requires token estimation at call time but directly identifies the "send everything everywhere" pattern that drives quadratic cost growth.
5. **Build dashboards** — per-agent spend, per-phase spend, retry rate by call type, carry ratio by agent. These four views answer 80% of cost questions.

## Receipt

> Verified 2026-07-31 — Framework constructed from WOWHOW Cost-Attribution Ledger (Jun 2026), Keito multi-agent cost tracking (Mar 2026), and Prefactor agent cost attribution guides. Key mechanics confirmed against OpenAI/Anthropic API response schemas. Five-dimension model is original synthesis;WOWHOW's CAL provides the Phase × Agent × Tool-Call × Context-Carry framework; Retry Tax is added as the fifth dimension based on the retry-storm analysis from I-3094/S-1907. Real implementation requires token estimation at call time (use tiktoken or equivalent). Thinking-token detection requires provider-specific `usage` field inspection. Carry-ratio thresholds (0.7) are empirically derived from context-compression literature (Zylos, Feb 2026).

## See also

- [S-1198](../stacks/s1198-the-thinking-token-blind-spot-stack-when-your-reasoning-models-inner-monologue-costs-more-than-your-entire-app.md) — The thinking token blind spot (extended thinking token billing)
- [S-1284](../stacks/s1284-the-quadratic-burn-when-token-costs-compound-faster-than-results.md) — The quadratic burn (context carry drives super-linear growth)
- [S-1907](../stacks/s1907-the-retry-storm-stack-when-every-failed-tool-call-costs-200x-more-than-a-successful-one.md) — The retry storm (retry tax source)
- [S-1166](../stacks/s1166-the-cross-agent-trace-fragmentation-problem-when-every-agent-traces-itself-but-nobody-traces-the-handoff.md) — Cross-agent trace fragmentation (trace context propagation for attribution)
