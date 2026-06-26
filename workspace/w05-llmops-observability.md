# W-05 · LLMOps and Agent Observability Tooling

Single-call logging ([W-04](w04-observability.md)) breaks down the moment you have more than one agent. A 10-step pipeline needs per-step attribution — which agent, which tool, what it cost — or the aggregate hides every problem.

## Forces
- Aggregate cost is useless: knowing a pipeline cost $0.40 doesn't tell you that step 7 alone cost $0.32 and can be cut
- Tool retries and re-plan events are invisible without explicit span tags
- Inter-agent messages are not LLM calls — they live between spans and fall out of basic OTel tracing
- Framework-specific tools (LangSmith) give the richest traces if you're already in that framework; framework-agnostic tools cost more to set up but survive a stack change

## The move

**Agentic span pattern — add these fields to every span W-04 doesn't cover:**

```python
with tracer.start_as_current_span("agent_step") as span:
    span.set_attribute("agent.id", agent_id)          # which agent
    span.set_attribute("agent.step", step_number)     # position in pipeline
    span.set_attribute("tool.name", tool_name)        # tool called, if any
    span.set_attribute("tool.retry_count", retries)   # retries on this tool call
    span.set_attribute("agent.replanned", replanned)  # True if agent changed plan
    span.set_attribute("cost.usd", step_cost_usd)     # per-step cost estimate
    result = run_step(...)
    span.set_attribute("tool.output_chars", len(str(result)))
```

Cost per step: `input_tokens × input_price + output_tokens × output_price`. Price constants live in one config file; pull them at startup.

**Tool comparison:**

| Tool | Open-source | Self-host | Per-step cost | Framework tie-in | Best for |
|---|---|---|---|---|---|
| LangSmith | No | No | Yes | LangGraph / LangChain | Teams already on LangGraph |
| Langfuse | Yes | Yes | Yes | SDK-agnostic | Framework-agnostic teams |
| Portkey | No | No | Yes (gateway) | Any (proxy layer) | Zero-instrumentation baseline |
| Arize Phoenix | Yes | Yes | Partial | SDK-agnostic | Eval + embedding inspection |

**Portkey** sits at the gateway — every API call passes through it, so you get latency, tokens, and cost with no code changes. Use it to get baseline visibility fast, then add OTel spans for the agentic signals above.

**Langfuse** is the default choice for framework-agnostic teams: open-source, self-hostable, SDK covers Python and JS, and per-span scoring lets you attach eval results to the same trace that shows cost.

**What to look for in production traces:**

1. Steps where `tool.retry_count > 1` — the tool is flaky or the prompt is ambiguous
2. Steps where `cost.usd` is an outlier — usually a synthesis step with oversized context
3. `agent.replanned = True` frequency — high replan rate signals a poorly-specified task or a weak planner model

## Receipt
> Sourced from Langfuse docs (langfuse.com/docs), LangSmith docs (docs.smith.langchain.com), Portkey docs (portkey.ai/docs), Arize Phoenix docs (docs.arize.com/phoenix). Tool comparison verified 2026-06-25. OTel span attribute names follow OpenTelemetry semantic conventions (opentelemetry.io/docs/specs/semconv/). Per-step cost formula is standard; prices change — pull from provider pricing pages at runtime.

## See also
[W-04](w04-observability.md) · [F-02](../forward-deployed/f02-evaluation-at-scale.md) · [S-05](../stacks/s05-multi-agent-patterns.md)

## Go deeper
Keywords: `OpenTelemetry semantic conventions` · `Langfuse SDK` · `LangSmith tracing` · `Portkey gateway` · `Arize Phoenix` · `per-step cost attribution` · `agentic tracing`
