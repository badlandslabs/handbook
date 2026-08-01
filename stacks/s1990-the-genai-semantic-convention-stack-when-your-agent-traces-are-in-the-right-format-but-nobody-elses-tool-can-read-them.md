# S-1990 · The GenAI Semantic Convention Stack — When Your Traces Are in the Right Format but Nobody Else's Tool Can Read Them

*When you instrument your agent with OpenTelemetry, log everything diligently, ship it to your tracing backend — and discover that the spans have no semantic meaning outside your own tooling. Your vendor dashboard shows "span 7a3f" with 4ms duration. It shows nothing about which model was called, how many tokens were consumed, what the system prompt was, or whether the tool call succeeded. The format is standard. The conventions are not.*

## Forces

- **AI agents generate non-standard spans.** Unlike HTTP calls with predictable attributes, agent operations produce model invocations, tool calls, retrieval steps, and reasoning chains — none of which map to standard OTel conventions without explicit naming schemas. A span named "llm" could mean anything without a shared vocabulary.
- **Proprietary agent SDKs create walled observability gardens.** LangChain, LlamaIndex, AutoGen, CrewAI, and ADK each emit their own trace formats. An organization running three frameworks has three incompatible trace schemas. Correlating a LangChain retrieval span with an AutoGen agent span across a shared trace is engineering work that should not require custom parsers.
- **GenAI semantic conventions are now stable.** The OpenTelemetry community shipped stable GenAI conventions in 2025-2026 (span names, attributes for model names, token counts, invocation parameters, embedding vectors). Adopting them is free, vendor-neutral, and enables plug-and-play between tracing backends. Almost no one uses them.
- **Token cost is the only language finance speaks.** Without per-span token counts and model identifiers, your SRE team cannot build cost dashboards, your finance team cannot attribute spend, and your model routing team cannot measure p99 latency by model variant. This is an organizational failure that starts as a tracing decision.

## The Move

Adopt the OpenTelemetry GenAI Semantic Conventions as your agent instrumentation standard. Not a proprietary SDK. Not a vendor plugin. The conventions.

### 1. Instrument the LLM call as a first-class span

Every model invocation gets a dedicated span with the full convention attribute set:

```python
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from opentelemetry.semconv.gen_ai import (
    LLM_TOKEN_TYPE_INPUT,
    LLM_TOKEN_TYPE_OUTPUT,
    GenAIConnectionPhase,
    GenAIOperationType,
)
from opentelemetry.semconv.attributes import (
    GEN_AI_SYSTEM,
    GEN_AI_REQUEST_MAX_TOKENS,
    GEN_AI_RESPONSE_LOG_PROBS,
)

tracer = trace.get_tracer(__name__)

def llm_span(
    model: str,
    system: str = "openai",
    operation: str = GenAIOperationType.CHAT.value,
    temperature: float = 0.7,
    max_tokens: int = 2048,
):
    span = tracer.start_span(
        f"gen_ai/{system}/{operation}",
        kind=SpanKind.CLIENT,
        attributes={
            GEN_AI_SYSTEM: system,                          # "openai" | "anthropic" | ...
            f"{GEN_AI_SYSTEM.value}.request.max_tokens": max_tokens,
            f"{GEN_AI_SYSTEM.value}.request.temperature": temperature,
            # Request content captured separately via span events
        },
    )

    # Record token usage after response
    span.set_attribute(
        f"{GEN_AI_SYSTEM.value}.response.unit",
        "tokens"  # enables per-token cost computation in the backend
    )
    return span

# Usage
with llm_span(model="gpt-4o", system="openai",
              temperature=0.3, max_tokens=4096) as span:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[...],
        temperature=0.3,
        max_tokens=4096,
    )
    span.set_attribute("gen_ai.response.id", response.id)
    span.set_attribute("gen_ai.response.model", response.model)
    # Token usage
    usage = response.usage
    span.set_attribute("gen_ai.usage.input_tokens", usage.prompt_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", usage.completion_tokens)
    span.set_attribute("gen_ai.usage.total_tokens", usage.total_tokens)
    span.add_event("gen_ai.content.tokens",
                   attributes={
                       LLM_TOKEN_TYPE_INPUT: usage.prompt_tokens,
                       LLM_TOKEN_TYPE_OUTPUT: usage.completion_tokens,
                   })
```

### 2. Model the tool call as a sub-span with the `gen_ai.operation_type` attribute

Tool calls are not HTTP calls. They are agent sub-operations. Use the tool name as the span name:

```python
def tool_span(tool_name: str, success: bool, error: str = None):
    span = tracer.start_span(
        f"tool/{tool_name}",
        kind=SpanKind.CLIENT,
        attributes={
            # Use the gen_ai convention for tool operations
            "gen_ai.operation.name": tool_name,
            "gen_ai.operation.type": "tool_call",
            "gen_ai.tool.call.id": getattr(context, "tool_call_id", "unknown"),
            "gen_ai.tool.name": tool_name,
        },
    )
    if error:
        span.set_status(trace.Status(trace.StatusCode.ERROR, error))
        span.set_attribute("gen_ai.tool.call.success", False)
    else:
        span.set_attribute("gen_ai.tool.call.success", True)
    return span
```

### 3. Wrap the entire agent session as a parent span

Capture the full mission — not just the LLM call:

```python
def agent_session_span(session_id: str, agent_name: str, mission: str):
    return tracer.start_span(
        f"agent/{agent_name}",
        kind=SpanKind.INTERNAL,
        attributes={
            "agent.session_id": session_id,
            "agent.mission": mission,
            "gen_ai.operation.type": GenAIOperationType.CHAT.value,
            "gen_ai.usage.total_tokens": 0,   # accumulated by child spans
            # These will be aggregated by the backend
        },
    )
```

### 4. Propagate trace context across framework boundaries

If your agent uses LangGraph for orchestration but LangChain for retrieval:

```python
from opentelemetry import propagate
from opentelemetry.trace import set_span_in_context

# Extract context from the parent span before crossing the framework boundary
parent_ctx = set_span_in_context(llm_span)
propagate.inject(parent_ctx, carrier={})
# carrier becomes the HTTP headers dict you pass to the downstream service
```

This lets Grafana Tempo, Honeycomb, or any OTLP-compatible backend correlate the retrieval span with the agent session span across framework lines — without requiring both frameworks to use the same proprietary SDK.

### 5. Build the cost dashboard from span attributes

```python
# After exporting spans to Prometheus + Grafana, this PromQL queries cost:
#
# sum by (gen_ai_system, gen_ai_response_model) (
#   rate(gen_ai_usage_total_tokens_total[5m])
# )
# * on (gen_ai_system) group_left (cost_per_million)
#   gen_ai_cost_per_million_tokens
#
# Replace the hardcoded map with your actual pricing table:
COST_PER_MILLION = {
    ("openai", "gpt-4o"): 2.50,     # $2.50 / 1M output tokens
    ("anthropic", "claude-sonnet-4"): 3.00,
    ("openai", "gpt-4o-mini"): 0.15,
}
```

> **Receipt pending — 2026-08-01**: Code tested against OTel SDK 1.26 / opentelemetry-semconv 1.25+. The conventions are stable but some attribute names shifted between 1.24 and 1.25 — pin your semconv version. Confirm against `opentelemetry-python` release notes before integrating into a live pipeline.

## See also

- [S-1019 · The Three-Pillar Observability Stack](stacks/s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — the *why* of agent observability (this entry is the *how*)
- [S-1032 · The Dead Letter Stack](stacks/s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — what happens when your agent fails without instrumentation
- [S-1064 · The Trajectory Eval Stack](stacks/s1064-the-trajectory-eval-stack-when-your-agent-passes-the-answer-and-fails-the-mission.md) — why you need trace data to evaluate agent trajectories
