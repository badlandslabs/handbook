# S-1943 · The Agentic Observability Gap Stack

*When your dashboard is green and your agent isn't.*

Your HTTP health probe returns 200. Your latency metrics show 143ms. No errors in your logs. But your customer just got charged twice, your agent filed a refund it wasn't authorized to give, and your LLM bill is 4× the baseline — all in the last hour. Your standard APM dashboard is useless here. It was built for deterministic software. Agents are not deterministic. The problem is not your monitoring stack — it's the layer it doesn't reach.

Standard APM captures what software does: HTTP status codes, database query times, memory pressure. An agent's value is delivered inside the reasoning loop — which tools it chose and why, whether those choices were sound, and whether the final output is correct. That happens in a latent space your observability stack cannot see. AgentMarketCap measured this gap in April 2026: ~89% of teams have infrastructure observability, but only ~50% have quality-level evaluation of agent outputs. The remaining 70% of agent behavior is invisible to your monitoring.

## Forces

- **Agents fail with the surface plausibility of success.** Unlike a crashed API, an agent that degrades produces outputs that look correct. Standard error-rate metrics stay flat. The failure is semantic, not syntactic.
- **The execution graph is runtime-generated.** A REST API's call graph is fixed at compile time. An agent generates its own execution graph at runtime — 2 steps or 20 depending on the model's reasoning. Traditional APM has no trace to display.
- **The cost lives in reasoning tokens, not response tokens.** A runaway agent loop burns millions of tokens silently. Standard cost dashboards show API spend by endpoint, not by agent step. The runaway is invisible until the bill arrives.
- **Cross-system side effects are invisible without trace propagation.** An agent calling an MCP tool that calls an external API generates events in three systems. Without W3C Trace Context propagation across the MCP layer, you cannot reconstruct which agent decision caused which database write.

## The move

**Instrument the execution loop, not just the infrastructure.**

The canonical agent observability stack in 2026 rests on OpenTelemetry (OTel) — the vendor-neutral standard that converged on MCP-specific semantic conventions in early 2026. Rather than building a bespoke monitoring layer, plug into OTel spans and propagate context through every tool call. The stack has four layers:

### Layer 1 — Span instrumentation inside the agent loop

Every agent step emits a span. The span records: which model was called, the full prompt (truncated), the reasoning trace, which tools were proposed vs. called, arguments passed, latency per step, and token consumption per call.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.semconv.resource import ResourceAttributes

provider = TracerProvider(
    resource=Resource.create({
        ResourceAttributes.SERVICE_NAME: "support-agent",
        ResourceAttributes.DEPLOYMENT_ENVIRONMENT: "production",
    })
)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer("agent-loop")

with tracer.start_as_current_span("agent.turn") as span:
    span.set_attribute("agent.session_id", session_id)
    span.set_attribute("agent.turn_count", turn_count)

    with tracer.start_as_current_span("llm.call") as llm_span:
        llm_span.set_attribute("llm.model", model_id)
        llm_span.set_attribute("llm.prompt_tokens", prompt_tokens)
        llm_span.set_attribute("llm.completion_tokens", completion_tokens)
        llm_span.set_attribute("llm.total_tokens", prompt_tokens + completion_tokens)
        response = llm_client.chat completions(...)
        llm_span.set_attribute("llm.latency_ms", elapsed_ms)

    with tracer.start_as_current_span("tool_selection") as tool_span:
        tool_span.set_attribute("tool.candidates", len(proposed_tools))
        tool_span.set_attribute("tool.selected", selected_tool)
        # ... tool execution with per-call spans
```

### Layer 2 — MCP trace propagation with W3C Trace Context

MCP tool calls carry `traceparent` headers across the wire. When your MCP client calls an external MCP server, the server receives the trace context and can emit child spans that associate back to the originating agent decision. The MCP OTel conventions (published at `opentelemetry.io`, 2026) standardize attributes: `mcp.tool.name`, `mcp.server.name`, `mcp.context.propagated`.

```python
# Propagate trace context through MCP client calls
from opentelemetry.propagate import inject

def call_mcp_tool(client, tool_name: str, arguments: dict) -> dict:
    headers = {}
    inject(headers)  # Adds traceparent, tracestate to headers
    # MCP client passes headers to server
    return client.call_tool(tool_name, arguments, headers=headers)
```

Without this, your MCP server spans are orphans — they appear in your traces dashboard but have no connection to the agent decision that invoked them.

### Layer 3 — Output quality evaluation as a first-class span

Infrastructure metrics (latency, error rate) capture 30% of what matters. The remaining 70% — whether the agent's output is correct, safe, and within policy — requires LLM-based evaluation emitted as spans. Phoenix (Arize), Langfuse, and LangSmith all support evaluation-as-span patterns.

```python
from opentelemetry import metrics

meter = metrics.get_meter("agent-loop")
eval_counter = meter.create_counter(
    name="agent.eval.pass_rate",
    description="LLM-as-judge pass rate per agent decision",
    unit="1"
)

def evaluate_tool_selection(decision: AgentDecision, span) -> EvalResult:
    judge_prompt = f"""
    Given the user's goal: {decision.goal}
    And the tool chosen: {decision.selected_tool} with args {decision.arguments}
    Was this tool selection correct, given the goal?
    Rate: CORRECT / MARGINAL / WRONG
    """
    judgment = llm_client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": judge_prompt}]
    )

    eval_counter.add(1, {"decision_quality": judgment.label})
    span.set_attribute("eval.tool_selection", judgment.label)
    return EvalResult(label=judgment.label, reason=judgment.reason)
```

### Layer 4 — Token budget alerts as operational signals

Treat token burn rate as an operational metric with alerting thresholds. A circuit breaker on accumulated tokens per session catches runaway reasoning loops before the budget is exhausted.

```python
TOKEN_BUDGET_PER_SESSION = 50_000
token_counter = meter.create_histogram(
    name="agent.tokens.total",
    description="Running token count per session",
    unit="tokens"
)

def check_token_budget(session_id: str, current_tokens: int, span):
    token_counter.record(current_tokens, {"session_id": session_id})
    if current_tokens > TOKEN_BUDGET_PER_SESSION:
        span.set_attribute("agent.token_budget.exceeded", True)
        # Trigger pause: surface to human, halt further steps
        raise AgentBudgetExceeded(f"Session {session_id}: {current_tokens} tokens, budget {TOKEN_BUDGET_PER_SESSION}")
```

## The failure signals this catches

| Signal | What it reveals | Standard APM catches it? |
|--------|----------------|--------------------------|
| Token burn rate > threshold | Reasoning loop or circular tool use | No — API spend dashboards don't per-session |
| Tool selection eval = WRONG | Agent chose wrong tool for goal | No — no semantic signal |
| MCP span orphan rate | MCP server invoked without trace propagation | No — server spans exist but aren't linked |
| Latency spike in llm.call span | Model degradation or provider throttling | Partially — total latency visible, reason invisible |
| Eval pass rate drop over time | Gradual agent quality degradation | No — binary success metrics miss quality drift |

## Receipt

> Verified 2026-08-01 — Research sources: AgentMarketCap "The MCP Observability Gap" (Apr 2026, 70% blind spot stat); OpenTelemetry MCP semantic conventions (opentelemetry.io, 2026); MintMCP "OpenTelemetry for AI Agents" (Apr 2026); OWASP GenAI Agentic Security Initiative (2026). Code patterns synthesized from OTel SDK documentation and Phoenix (Arize) agent tracing guides. Not run against a live agent — Receipt pending.

## See also

- [S-1941 · The Agentic SLA Stack](s1941-the-agentic-sla-stack-when-your-agent-is-in-production-and-you-have-no-way-to-measure-it.md) — SLA definition and measurement; this chapter is the observability infrastructure that makes SLA commitments enforceable
- [S-1033 · The Behavioral Version Stack](s1033-the-behavioral-version-stack-when-your-git-log-is-clean-but-your-agent-is-broken.md) — the four-layer versioning problem that observability spans help reconstruct; trace history is the version log for agent behavior
- [S-1927 · The MCP Token Wall Stack](s1927-the-mcp-token-wall-stack-when-three-servers-consume-71-percent-of-your-context-before-your-agent-does-anything.md) — token burn is the silent cost driver; this chapter's Layer 4 is the detection layer for that problem
