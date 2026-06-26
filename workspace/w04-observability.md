# W-04 · Observability

Log what the model does, what it costs, and when it fails. You can't improve what you can't measure.

## Forces
- LLM calls are black boxes by default — you see input and output, not what happened in between
- Token costs accumulate invisibly until the invoice arrives
- Failures are silent in agentic systems unless you add tracing
- Too much logging is noise; too little and you're debugging blind

## The move

**Minimum viable logging for every LLM call:**
```python
import time, logging

logger = logging.getLogger("llm")

def traced_call(client, **kwargs):
    start = time.monotonic()
    response = client.messages.create(**kwargs)
    elapsed = time.monotonic() - start

    logger.info({
        "model": kwargs.get("model"),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
        "latency_ms": round(elapsed * 1000),
        "stop_reason": response.stop_reason,
    })
    return response
```

**What to log, always:**
- Model name
- Input + output token count
- Latency (wall clock)
- Stop reason (natural vs. max_tokens vs. tool_use)
- Any tool calls made

**What to log for agentic systems:**
- Agent ID and step number (to trace multi-step flows)
- Tool name + input + output (truncated)
- Retry count
- Total cost estimate (input_tokens × input_price + output_tokens × output_price)

**Production standard: OpenTelemetry**

OpenTelemetry (OTel) is the standard for structured trace/metric/log export to Grafana, Datadog, or any backend. Most agent frameworks (LangSmith, Langfuse, Arize) emit OTel-compatible traces.

```python
from opentelemetry import trace

tracer = trace.get_tracer("llm-agent")

with tracer.start_as_current_span("llm_call") as span:
    span.set_attribute("model", "claude-sonnet-4-6")
    response = client.messages.create(...)
    span.set_attribute("input_tokens", response.usage.input_tokens)
```

**Managed options:** Langfuse (open-source, self-hostable), LangSmith (hosted), Arize Phoenix (open-source).

## Receipt
> Receipt pending — 2026-06-25. Logging pattern above is standard Python. OpenTelemetry span structure follows OTel Python SDK docs. Verify with a live trace before relying on it.

## See also
[F-02](../forward-deployed/f02-evaluation-at-scale.md) · [F-03](../forward-deployed/f03-failure-modes.md) · [S-05](../stacks/s05-multi-agent-patterns.md)

## Go deeper
Keywords: `OpenTelemetry` · `Langfuse` · `LangSmith` · `Arize Phoenix` · `token cost tracking` · `LLM tracing` · `distributed tracing`
