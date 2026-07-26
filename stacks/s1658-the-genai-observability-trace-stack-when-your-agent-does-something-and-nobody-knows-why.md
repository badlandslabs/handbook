# S-1658 · The GenAI Observability Trace Stack — When Your Agent Does Something and Nobody Knows Why

Your multi-agent pipeline broke at 3 AM. The supervisor agent routed a task wrong, the worker agent spent 40 minutes on the wrong tool, and your bill jumped $2,000. The final output looks plausible. There are no error logs. Nobody can reproduce it. This is not a debugging problem — it is an observability problem. You were flying blind.

The canonical observability stack for microservices (counters, histograms, error rates) was built for deterministic programs. Agents are not deterministic. They are probabilistic state machines with tool calls, multi-turn reasoning, and non-monotonic memory. You need to see the full trace — every LLM call, every tool invocation, every decision point — before you can debug it.

## Forces

- **Agents fail invisibly.** A degraded agent produces outputs that look correct. Standard APM (error rates, latency histograms) was designed for crashes — it cannot detect behavioral regressions where the agent keeps responding and keeps spending tokens. SRE teams built for 500 errors have no vocabulary for "the agent's tool call sequence drifted after step 7."
- **The tooling landscape fragmented before the conventions stabilized.** LangSmith, Langfuse, Arize, AgentOps, Honeycomb, and Traceloop each emit different attribute schemas. Switching providers means rewriting instrumentation. OpenTelemetry's GenAI conventions are the standardization layer — but they remain experimental (as of July 2026, no committed 1.0 date), and the conventions moved to a dedicated repository in v1.42.0 (June 2026), breaking existing documentation links.
- **Agent coordination traces require cross-span correlation.** When two agents disagree on state (S-1013), the failure lives in the handoff — a tool call whose output one agent saw and another didn't. This requires correlating spans across multiple service boundaries with shared conversation IDs. Standard distributed tracing handles the RPC layer; the GenAI conventions handle the reasoning layer.

## The move

### 1. Instrument with the GenAI semantic conventions

The OpenTelemetry GenAI conventions (open-telemetry/semantic-conventions-genai, v1.41.1) define five agent span operations that map to the agent lifecycle:

| Span | Kind | What it wraps |
|------|------|--------------|
| `create_agent` | CLIENT | Agent instantiation |
| `invoke_agent_client` | CLIENT | Caller-side agent invocation |
| `invoke_agent_internal` | INTERNAL | Agent's own processing |
| `create_task` | CLIENT | Task or turn creation |
| `invoke_task` | CLIENT/INTERNAL | Task execution |

Key `gen_ai.*` attributes to emit on every LLM call span:

```
gen_ai.system: openai | anthropic | azure
gen_ai.request.model: gpt-4o | claude-sonnet-4-5
gen_ai.response.model: (populated by provider)
gen_ai.token.type: input | output | usage
gen_ai.usage.input_tokens: 1200
gen_ai.usage.output_tokens: 840
gen_ai.usage.total_tokens: 2040
gen_ai.response.finish_reason: stop | max_tokens | content_filter
```

Use Traceloop (open-telemetry/instrumentation-llm) or the LangChain OpenTelemetry integration to emit these automatically — do not hand-roll attribute emission for every LLM call.

### 2. Emit conversation IDs for cross-agent correlation

Agents fail across agent boundaries. Attach a stable `conversation.id` (W3C TraceContext `tracestate` or custom span attribute) that persists across all spans for a given user session or task instance. This lets you reconstruct the full agentic call graph from a single trace ID.

```
span.set_attribute("gen_ai.correlation.id", session_id)
```

### 3. Instrument tool calls as child spans

Each tool invocation should be a child span of the parent agent span, with tool-specific attributes:

```
gen_ai.tool.name: get_customer_record
gen_ai.tool.call.id: call_abc123
gen_ai.tool.call.parameters: {"customer_id": "C-4492"}
gen_ai.tool.response.status: success | error | timeout
```

LangGraph, AutoGen, and smolagents support OpenTelemetry span propagation natively. For custom orchestration, use `opentelemetry.trace.Tracer.start_as_current_span()` with `links=[parent_span_context]` to maintain the trace tree.

### 4. Send to a backend that supports agent timelines

LangSmith (near-zero overhead, best for LangChain/LangGraph-native teams), Langfuse (open source, self-hostable, strong prompt management), Arize (best for tracing + evaluation co-location), Honeycomb (agent timeline visualization for cross-span debugging), and AgentOps (session-level replay). Choose based on team size and regulatory requirements — self-hosted Langfuse covers EU data residency; LangSmith covers teams that want zero-infrastructure.

### 5. Define signal types, not just traces

Traces capture structure. You also need:

- **Cost attribution** — aggregate `gen_ai.usage.*` per agent, per session, per user. AgentOps and Langfuse compute this from span attributes automatically.
- **Quality signals** — emit a `gen_ai.event.feedback` event (per the GenAI events spec) when a human thumbs-down or approves a response. This closes the observability → evaluation feedback loop without moving to a separate system.
- **Latency SLOs** — set p50/p95/p99 thresholds on `invoke_agent_internal` spans. Alert on p95 > 2× baseline. An agent that starts taking 30 seconds per step instead of 3 is not failing — it is degrading, and degradation is the failure mode you cannot see.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from traceloop.sdk.otel import Telemetry

# Auto-instrument all LLM calls with gen_ai.* attributes
telemetry = Telemetry.init_traceloop("my-agent-service")
tracer = trace.get_tracer(__name__)

# Correlate spans across agent boundaries
with tracer.start_as_current_span("agent_coordinator") as parent:
    parent.set_attribute("gen_ai.correlation.id", session_id)
    parent.set_attribute("gen_ai.agent.role", "supervisor")
    
    # Tool calls become child spans automatically via instrumentation
    result = agent.run(task, tools=tool_registry)
    
    # Emit a feedback event if human signal is available
    if user_feedback is not None:
        parent.add_event("gen_ai.event.feedback", {
            "gen_ai.feedback.type": "thumbs" if user_feedback else "thumbs_down",
            "gen_ai.feedback.step": current_step,
        })
```

## Receipt

> Receipt pending — 2026-07-26

The GenAI semantic conventions remain in Development/experimental status as of July 2026 with no committed 1.0 timeline. The June 2026 repository restructure (v1.42.0) means existing documentation links are broken; always reference the canonical repo at github.com/open-telemetry/semantic-conventions-genai. Framework instrumentation libraries (Traceloop, LangChain OTel integration) abstract the attribute schema churn — prefer those over raw span APIs. AIMultiple's July 2026 benchmark shows LangSmith has ~0% instrumentation overhead vs. 5-40% for other platforms on multi-agent workloads; factor this into your production tradeoff decisions.

## See also

- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — eval and observability are the same feedback loop; traces feed eval pipelines
- [S-1003 · The Agent Failure Recovery Stack](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — recovery requires trace replay; you cannot recover what you cannot reproduce
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — observability is the substrate for AI SRE; without traces, SLOs are guesses
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — cross-agent state disagreement lives in span correlation, not in individual agent logs
