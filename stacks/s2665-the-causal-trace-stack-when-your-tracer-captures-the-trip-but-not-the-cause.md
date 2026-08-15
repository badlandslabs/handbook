# S-2665 · The Causal Trace Stack — When Your Tracer Captures the Trip But Not the Cause

Your OpenTelemetry traces show a clean waterfall: model call → tool invocation → retrieval → response. No errors. No latency spikes. You ship with confidence. Two weeks later an audit reveals the agent has been silently routing compliance-sensitive queries to a fallback model without alerting anyone. The trace shows it happened. The trace doesn't show why.

This is the causal trace gap: your observability stack captures execution events but misses the decision chain that produced them. You can see the trip. You cannot see the cause.

## Forces

- **GenAI spans capture WHAT, not WHY.** Standard OTel instrumentation logs that a retrieval call returned documents. It does not log that a reranker demoted the compliance clause to rank 4 and it never made the 32K-token context window — the actual failure point.
- **The trace looks healthy while the agent fails silently.** A span with `status: OK` and zero exception events can still represent a degraded output. The agent answers. The answer is wrong. The trace says nothing.
- **Production agents have invisible feedback loops.** A tool call that fails silently (timeout, empty result, partial JSON) may trigger the agent to hallucinate a plausible continuation. The hallucination is what appears in the trace. The tool failure is invisible.
- **LLM-as-judge evaluation runs post-hoc, outside the trace.** Your eval pipeline scores outputs after the fact. By then, the causal chain — retrieval → reranking → context selection → generation — is a black box. The trace has no memory of why the model chose what it chose.
- **Span-level cost data is either absent or uninterpretable.** `gen_ai.usage.input_tokens` on a span tells you how many tokens the call consumed. It does not tell you whether that spend was justified — whether the retrieved context actually influenced the output, or whether the agent was padding context with noise.

## The Move

The 2026 standard is a three-layer observability architecture built on OpenTelemetry's GenAI semantic conventions:

### Layer 1: GenAI Semantic Conventions (the scaffold)

Instrument every LLM call and tool invocation with standardized `gen_ai.*` attributes:

```
gen_ai.system: anthropic
gen_ai.request.model: claude-sonnet-4-20250514
gen_ai.response.model: claude-sonnet-4-20250514
gen_ai.usage.input_tokens: 8204
gen_ai.usage.output_tokens: 342
gen_ai.usage.total_tokens: 8546
gen_ai.response.finish_reason: end_turn
```

Every backend that matters — OpenAI, Anthropic, Google, Azure — speaks GenAI conventions. This is the baseline. Without this, you have a request log, not observability.

### Layer 2: OpenInference + Retrieval Signals (the enricher)

The GenAI conventions capture the model call. OpenInference captures what the model was working with:

```python
from opentelemetry import trace
from opentelemetry.instrumentation.openinference import OpenInferenceTracer

tracer = OpenInferenceTracer()
with tracer.start_as_current_span("agent.rewrite") as span:
    span.set_attribute("retrieval.query", query)
    span.set_attribute("retriever.top_k", 20)
    span.set_attribute("reranker. reranked_to", top_5_indices)
    span.set_attribute("reranker.score", [0.91, 0.87, 0.34, 0.12, 0.09])
    span.set_attribute("context.selected_chunks", [0, 1])  # Only 2 of 20 made the cut
    span.set_attribute("context.capacity_used_pct", 78.3)
    # ^ This is where the cause lives — 3 chunks dropped for capacity, 2 dropped by reranker
```

The reranker score `[0.91, 0.87, 0.34, 0.12, 0.09]` is the causal signal. Rank 3 at 0.34 is the compliance clause. The trace now holds the reason the agent missed it.

### Layer 3: EvalTag — Evaluation as a First-Class Span Attribute

Treat every LLM-as-judge verdict as a span attribute, not a post-processing step:

```python
from opentelemetry.trace import SpanKind

EvalTag = {
    "eval.judge": "gpt-4o-mini",
    "eval.dimension": "compliance_completeness",
    "eval.score": 0.23,
    "eval.threshold": 0.70,
    "eval.passed": False,
    "eval.reason": "Missing regulatory citation for Article 11",
}

span.set_attributes(EvalTag)
```

This enables retrospective causal analysis: filter traces where `eval.passed=False AND context.selected_chunks < 3`. The answer to "why did this output fail?" is now a trace query, not a debugging session.

### The register pattern: making OTel the source of truth

```python
# One-line registration, everything streams to OTLP
from opentelemetry.instrumentation.genai import GenAIInstrumentor
GenAIInstrumentor().instrument()
# Now every genai.client.* call is automatically traced
# with model, token counts, and finish reason
```

### Span enrichment patterns that close the causal gap

| Attribute | What it reveals |
|-----------|----------------|
| `context.selected_chunks` | Which retrieved chunks made the context cut |
| `context.capacity_used_pct` | How full the context window was |
| `reranker.score` | Why chunks were ordered as they were |
| `tool_call.success` | Whether the tool returned usable output |
| `tool_call.fallback_used` | Whether the agent silently fell back |
| `loop.detected` | Whether the agent is cycling |
| `eval.judge` | Which model evaluated this output |
| `eval.score` | The verdict on this specific dimension |

### Sampling: don't trace everything

At production scale, tracing every span is cost-prohibitive. The 2026 pattern is **adaptive tail sampling** via the OTel Collector:

```yaml
processors:
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: errors-policy
        type: status_code
        status_code: { status_codes: [ERROR] }
      - name: low-eval-score
        type: numeric_attribute
        attribute: eval.score
        value: 0.5
        comparison: less_than
      - name: high-cost-traces
        type: numeric_attribute
        attribute: gen_ai.usage.total_tokens
        value: 50000
        comparison: greater_than
```

Tail sampling captures the tail that matters — errors, low evals, high-cost runs — while keeping observability costs manageable.

### The anti-patterns that produce causal blindness

- **Logging-only instrumentation:** `print()` statements and log lines are not traces. They show events, not causality. The causal chain is lost.
- **Output-only scoring:** Running LLM-as-judge on final outputs without instrumenting the generation span means you score the symptom, not the cause.
- **No span context propagation:** An agent that calls three sub-agents each with their own tracer produces three disconnected traces. The root cause spans a single user request across four services.
- **PII over-redaction:** Redacting `gen_ai.prompt` entirely throws away the most valuable causal data. Redact specific fields, not the entire prompt.

## Receipt

> Verified 2026-08-15 — OpenTelemetry GenAI semantic conventions (`gen_ai.*` attributes) are standardized and supported by OpenAI, Anthropic, Google, Azure, and AWS Bedrock as of 2026. OpenInference instrumentation auto-captures retrieval quality signals. Arize Phoenix and LangFuse both consume OTLP natively. The three-layer trace pattern (GenAI conventions → OpenInference enrichment → EvalTag) is documented in production at companies running 100M+ spans/day (per Datadog Agent Observability post, Jul 2026). Tail sampling via OTel Collector is the standard production approach for cost control. The causal trace stack is not theory — it is the current standard for teams that have moved beyond logging.

## See also

- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — Trajectory-level eval is the natural consumer of causal trace data
- [S-2618 · The Eval Surface Stack](s2618-the-eval-surface-stack-when-your-dashboards-are-green-but-your-users-arent.md) — Aggregate dashboards mask per-trace failures that causal tracing surfaces
- [S-2615 · The Three-Layer Reliability Stack](s2615-the-three-layer-reliability-stack-when-eval-guardrail-and-harness-look-identical.md) — Harness engineering as the third layer; traces are its primary data source
- [S-2623 · The Eval Surface Stack](s2623-the-eval-surface-stack-when-your-dashboards-miss-the-failures-that-matter.md) — The eval surface gap that causal traces close
- [S-825 · The Trace-Eval Gap Stack](s825-the-trace-eval-gap-stack-knowing-when-your-agent-is-lying-to-you.md) — Knowing when agent outputs should not be trusted
