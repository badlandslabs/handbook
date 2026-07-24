# S-1538 · The OTel GenAI Conventions Stack — When You're Instrumenting Agents and the Standard Is Finally Here

You have an agent in production. Something went wrong — the agent burned 10× the expected tokens, routed a task to the wrong sub-agent, and produced a plausible but incorrect result. You open your logs and see `{"response": "I can help with that..."}`. No model name. No token count. No trace of which tool call triggered the spiral. No parent span. Just a timestamp and a prayer.

This is not a tooling gap. It is a _standardization_ gap — and it just closed.

## Forces

- **Fragmentation killed debugging.** Langfuse, LangSmith, Arize Phoenix, Helicone, and Traceloop all instrument agents, but each captured different attributes in incompatible schemas. Crossing tool boundaries — an OpenAI orchestrator calling an Anthropic sub-agent, or a supervisor agent delegating via MCP — produced disconnected trace trees with no coherent trace_id. You could observe each piece in isolation; you could not observe the whole.

- **The OTel GenAI semantic conventions are the convergence point.** OpenTelemetry's `gen_ai.*` namespace (v1.41, May 2026) standardizes attributes for every layer of an agent run: invocation, model calls, tool calls, retrieval, costs. MCP tracing was added in OTel v1.39 (`mcp.method.name`, `mcp.session.id`, `mcp.server.name`). But the conventions are still in Development status — attribute names can shift without a major version bump.

- **Agents fail in ways binary monitoring cannot see.** Well-formed but incorrect outputs, unnecessary tool calls, syntactically valid but semantically wrong actions — none of these produce 500s or error logs. Step-level tracing is the minimum viable signal. But a span tree with 200+ nodes (a 30-minute agent run) is practically unreadable without the right abstraction layers.

- **Cross-agent trace continuity is the last mile.** When Agent A calls Agent B over HTTP, the trace breaks. Each produces an isolated trace with its own `trace_id`. W3C TraceContext propagation (W3C TRACE-CONTEXT, distributed tracing for multi-agent architectures) is the fix — but it is not yet built into most agent frameworks (Traceloop SDK tracked this as an open feature request as of Feb 2026).

## The Move

The OTel GenAI conventions standardize _what_ you instrument and _how_ you name it. The stack has four layers:

### 1. The Three-Node Span Taxonomy

Every agent run produces a trace — a tree of nested spans. Three node types cover the full run:

| Span Type | Operation Name | Key Attributes | What It Tells You |
|---|---|---|---|
| **Agent span** | `invoke_agent` | `agent.name`, `agent.id`, `gen_ai.system` | Top-level: what agent ran, for which user, on what conversation |
| **Generation span** | `gen_ai.chat` or `gen_ai.completion` | `gen_ai.request.model`, `gen_ai.response.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.total_tokens`, `gen_ai.response.id` | Per-call: which model, how many tokens, how long |
| **Tool span** | `tool` | `tool.name`, `tool.call.id`, `tool.call.name` | Per-step: which tool fired, with what arguments, what it returned |

Sub-agents get their own `invoke_agent` span nested under the parent, preserving the full hierarchy.

### 2. The `gen_ai.*` Attribute Namespace

Every generation span emits these standardized attributes:

```
gen_ai.request.model       # e.g., "gpt-4o", "claude-sonnet-4-20250514"
gen_ai.response.model      # may differ from request (model routing)
gen_ai.usage.input_tokens
gen_ai.usage.output_tokens
gen_ai.usage.total_tokens
gen_ai.response.id         # for cross-referencing with provider logs
gen_ai.prompt.embedding   # for embedding calls
```

Tool spans emit `tool.name`, `tool.call.id`, `tool.call.name`, `tool.call.arguments` (JSON string), and `tool.call.duration` (ms).

Retrieval spans emit `retrieval.query`, `retrieval.embeddings`, `retrieval.documents.total`, and `retrieval.documents.filtered`.

### 3. MCP Tracing (OTel v1.39+)

When agents call MCP servers, spans capture the transport layer:

```
mcp.server.name            # e.g., "filesystem", "github"
mcp.session.id
mcp.method.name            # e.g., "tools/call", "resources/list"
mcp.tool.name              # which MCP tool was invoked
mcp.transport              # "stdio" or "http"
```

This connects the LLM's decision to make a tool call with the actual MCP invocation and its result — closing the gap between "the model decided to call `github_create_issue`" and "the call succeeded/failed."

### 4. Cross-Agent Trace Continuity via W3C TraceContext

For multi-agent (A2A) architectures, propagate W3C `traceparent` headers over HTTP when agents communicate:

```
traceparent: 00-<trace-id>-<span-id>-01
```

Each agent service extracts and continues the trace context instead of starting a new one. Without this, supervisor-agent → sub-agent calls produce two disconnected traces. With it, you get a single trace tree from the user request through every agent and tool call.

```
# Outbound A2A call from Agent A
headers["traceparent"] = current_span.traceparent

# Agent B inbound — extract and attach
trace_ctx = W3CTraceContext.extract(headers["traceparent"])
with tracer.start_span("invoke_agent", context=trace_ctx):
    ...
```

### 5. The Signal-to-Noise Layer (Span Abstraction)

A 30-minute agent run can produce 200+ spans. Raw span trees are unreadable. Two abstraction patterns help:

**Milestone spans** — manually emit named spans at architecturally significant steps: `plan_formed`, `tool_selection`, `subagent_dispatch`, `handoff_complete`. These become bookmarks in the trace tree.

**Per-turn labels** — attach `gen_ai.turn.label` (e.g., `"review_step"`, `"escalation"`) to generation spans so you can filter by role, not just time.

### 6. Stack Selection by Deployment Model

| Model | Recommendation |
|---|---|
| Self-hosted / data-sensitive | Langfuse (self-hostable), Arize Phoenix (self-hostable), OTel Collector → Jaeger/Prometheus |
| Managed SDK | LangSmith, Braintrust, Helicone |
| Proxy gateway | Traceloop (auto-instruments via decorator, zero code change) |
| Mixed / multi-provider | OTel Collector with gen_ai convention dual-emission — emit to multiple backends simultaneously |

> Dual-emission safety: since OTel GenAI conventions are still in Development status, emit with `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental` alongside the stable attributes. This preserves your data if convention names shift.

### 7. Minimum Viable Instrumentation

If you instrument nothing else, emit these three things per generation call:

```python
span.set_attribute("gen_ai.request.model", model)
span.set_attribute("gen_ai.usage.total_tokens", usage.total_tokens)
span.set_attribute("gen_ai.response.id", response.id)
```

This alone lets you correlate your LLM provider's cost logs with your agent's trace — the most common debugging gap in practice.

## Receipt

> Verified 2026-07-23 — Research: Digital Applied (May 27, 2026), AgentMarketCap (Apr 10, 2026), MorphLLM (Jun 26, 2026), Traceloop/OpenLLmetry GitHub issue #3683 (Feb 2026). OTel GenAI conventions v1.41 (Development status), MCP tracing added v1.39. Three-node span taxonomy confirmed across all sources. W3C TraceContext propagation for A2A confirmed as open feature gap in Traceloop as of early 2026.

## See also

- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — the organizational discipline that consumes OTel traces as its data source
- [S-1525 · The Reliability Surface Stack](s1525-the-reliability-surface-stack-when-your-single-pass-rate-is-the-wrong-number.md) — what to measure once you can trace; the metrics layer above the instrumentation layer
- [S-1528 · The Multi-Agent Coordination Surface Stack](s1528-the-multi-agent-coordination-surface-stack-when-your-supervisor-becomes-a-bottleneck.md) — topology decisions that W3C TraceContext propagation makes observable
