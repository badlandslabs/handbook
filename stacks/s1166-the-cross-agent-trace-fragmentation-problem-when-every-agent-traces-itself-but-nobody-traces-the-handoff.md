# S-1166 · The Cross-Agent Trace Fragmentation Problem — When Every Agent Traces Itself but Nobody Traces the Handoff

Multi-agent pipelines that work beautifully in staging arrive in production as black boxes. One agent hands off to the next over A2A. Both agents emit traces. Neither trace knows about the other. When the pipeline fails — wrong output, wrong escalation, wrong delegation — you have N isolated trace trees and no way to stitch them into a causal chain. This is trace fragmentation: the dominant observability failure mode in multi-agent systems, and the one that directly blocks EU AI Act Article 12 compliance.

## Forces

- **A2A handoffs sever trace context.** The A2A protocol (v1.0, Linux Foundation, April 2026) ships without mandatory trace context propagation. When Agent A delegates to Agent B, Agent B starts a fresh trace tree unless you explicitly inject the W3C `traceparent` header. Most implementations don't — so your cross-agent flow produces N independent traces with zero shared lineage.

- **89% of teams have observability tooling but only 52% have cross-agent correlation.** — Raft Labs multi-agent production report. The gap is widest at handoff boundaries, not inside individual agents. You can see that Agent A called the right tool; you cannot see that Agent B received bad input from Agent A.

- **Context artifacts don't carry trace IDs.** A2A task envelopes (`TaskEnvelope`, `TaskSubmissionParams`) pass context as structured data — user intent, extracted entities, intermediate results. None of these fields carry the upstream trace ID. When a downstream agent fails, you cannot query your tracing system for "all traces that received this input from Agent A" because the link was never encoded.

- **OpenTelemetry span links work but require explicit wiring.** OTel's `Links` API (`span.addLink(traceId, spanId, attributes)`) is the correct mechanism for cross-boundary traces. It requires: (1) Agent A to expose its active trace ID in the handoff payload, (2) Agent B to extract it and call `addLink()` before processing, and (3) your tracing backend to render linked spans as a single causal tree. All three are opt-in and easily missed.

- **EU AI Act Article 12 (enforceable August 2, 2026) requires causal chains.** High-risk AI systems must record events throughout their operational lifetime sufficient to reconstruct the causal chain for any output. Fragmented traces don't satisfy this requirement. You cannot prove Agent A delegated to Agent B, what data passed between them, and what Agent B decided — because those events live in separate, unlinked trace trees.

- **Context window state bleeds across the trace gap.** Even when traces are technically linked, the *semantic* context that Agent A built — what it decided was important, what it filtered, what assumptions it made about the user's intent — lives in the conversation transcript, not in structured attributes. A linked span tells you Agent A called Agent B; it doesn't tell you why Agent A chose that delegation path.

## The move

### 1. Propagate W3C Trace Context through every A2A handoff

Standardize on the W3C `traceparent` header (`{version}-{trace-id}-{parent-id}-{trace-flags}`) embedded in the A2A task envelope's `metadata` field:

```python
# Agent A — before sending delegation
from opentelemetry import trace

tracer = trace.get_tracer(__name__)
current_span = trace.get_current_span()
span_context = current_span.get_span_context()

traceparent = (
    f"{span_context.trace_version:02x}-"
    f"{span_context.trace_id.hex[:32]}-"
    f"{span_context.span_id:016x}-"
    f"{01 if span_context.is_remote else 00}"
)

await a2a_client.send_task({
    "taskId": task_id,
    "metadata": {
        "traceparent": traceparent,
        "delegation_reason": "specialist_required",  # semantic context
        "upstream_trace_id": span_context.trace_id.hex,
    }
})
```

```python
# Agent B — on receiving delegation
span_context = W3CTraceContext.extract_from_envelope(metadata)
if span_context:
    tracer.start_span(
        "a2a.receive",
        links=[Link(span_context, attributes={"handoff.source": "agent-a"})]
    )
    # Now this span is linked to Agent A's trace tree
```

Every A2A client library should inject `traceparent` automatically — treat it as a protocol-level concern, not an application-level concern.

### 2. Encode causal handoff events as structured spans, not just metadata

Beyond trace context propagation, emit a first-class `agent.handoff` span at every delegation boundary:

```
Span: agent.handoff
  Attributes:
    handoff.source = "orchestrator-agent"
    handoff.target = "specialist-agent"
    handoff.task_id = "task_abc123"
    handoff.input_schema_version = "2.1"
    handoff.artifact_type = "extracted_entities"
    handoff.delegation_rationale = "gpc_extraction_required"
    handoff.trust_level = "authenticated_peer"  # ATN maturity level
```

This span survives even if downstream agents don't propagate `traceparent` — it creates a cross-agent causal link independent of OTel linkage.

### 3. Mirror handoff artifacts into the trace store, not just the message bus

A2A artifacts (the actual data passed between agents) are often logged to a message bus or object store but *not* to the tracing backend. Add an explicit artifact reference to the trace span:

```python
span.set_attribute("handoff.artifact_ref", f"s3://artifacts/{run_id}/{task_id}.json")
span.set_attribute("handoff.artifact_hash", compute_sha256(artifact))
```

This lets you answer: "show me the exact input Agent B received for trace XYZ" — without cross-referencing two separate logging systems.

### 4. Implement cross-agent trace correlation queries in your backend

OTel backends (Jaeger, Tempo, Honeycomb) can render linked spans as a single causal tree, but you must query for it explicitly. Build a correlation query that reconstructs the full delegation chain:

```python
async def get_full_delegation_chain(task_id: str, trace_id: str) -> dict:
    """
    Reconstruct the complete causal chain for an A2A delegation:
    - Upstream trace: all spans from the originating agent
    - Handoff span: the delegation event itself
    - Downstream trace: all spans from the receiving agent(s)
    - Artifact: the structured data that crossed the boundary
    """
    upstream = await otel_client.query_spans(
        trace_id=trace_id,
        span_name="agent.handoff"
    )
    handoff_event = upstream[0]
    
    # Follow the traceparent to the downstream agent
    downstream_trace_id = handoff_event.attributes.get("downstream_trace_id")
    downstream_spans = await otel_client.query_spans(
        trace_id=downstream_trace_id,
        span_name="a2a.receive"
    ) if downstream_trace_id else []
    
    return {
        "chain": [upstream, handoff_event, downstream_spans],
        "artifact": await fetch_artifact(handoff_event.attributes["handoff.artifact_ref"])
    }
```

### 5. Treat trace fragmentation as an EU AI Act Article 12 compliance gap

Audit requirements under Article 12 map directly to cross-agent trace completeness:

| Article 12 Requirement | Trace Gap | Fix |
|---|---|---|
| Record events throughout operational lifetime | Each agent logs independently | Unified trace with handoff spans |
| Reconstruct causal chain for any output | Traces don't cross A2A boundaries | `traceparent` propagation + causal links |
| Capture data inputs affecting output | Artifacts not in trace store | Artifact refs in span attributes |
| Attribute decisions to specific agents | No agent identity in traces | `agent_id` + ATN credential hash in span attributes |

The `agent_id` attribute on every span — populated from the A2A Agent Card's `authentication` field — satisfies the Article 12 requirement that actions be attributable to a specific AI system.

### 6. Default to trace context propagation in your A2A client factory

Don't rely on developers to remember to propagate context. Implement it at the client factory level:

```python
class A2AClientFactory:
    def create(self, agent_id: str) -> A2AClient:
        client = A2AClient(agent_id=agent_id)
        
        # Automatically inject trace context on every outgoing delegation
        original_send = client.send_task
        def tracing_send_task(payload, *args, **kwargs):
            current_span = trace.get_current_span()
            payload["metadata"] = payload.get("metadata", {})
            payload["metadata"]["traceparent"] = build_traceparent(current_span)
            payload["metadata"]["span_id"] = str(current_span.span_id)
            return original_send(payload, *args, **kwargs)
        
        client.send_task = tracing_send_task
        return client
```

This makes cross-agent trace correlation the default, not the opt-in.

## Tradeoffs

- **Trace volume increases** — linked spans and artifact references add overhead. Gate artifact logging on a sampling policy (log artifacts for high-risk task types, sample others).
- **Schema coupling** — adding `traceparent` to the A2A envelope is a protocol extension. Until it ships natively, use `metadata` as a forward-compatibility shim.
- **Downstream agents must cooperate** — if Agent B doesn't extract and use `traceparent`, you still get a one-way link (Agent A → Agent B) but not a two-way causal tree. Advocate for this in A2A SDK contributions.

## See also

- [S-535 · Agent Audit Trail Engineering: Meeting EU AI Act Article 12](s535-agent-audit-trail-engineering-eu-ai-act-article-12.md) — the regulatory requirement driving this
- [S-196 · OTel GenAI Telemetry](s196-otel-genai-telemetry.md) — OpenTelemetry instrumentation for agentic systems
- [S-764 · The Observability Gap: Why Tracing Agents Is a Different Problem](s764-the-observability-gap-why-tracing-agents-is-a-different-problem.md) — broader observability context
- [S-382 · The Multi-Agent Handoff Problem](s382-the-multi-agent-handoff-problem.md) — the handoff failure landscape
- [S-409 · The Inter-Agent Message Envelope](s409-the-inter-agent-message-envelope.md) — message envelope design
- [S-691 · The Agent Handoff Problem Is Where Multi-Agent Systems Die](s691-the-agent-handoff-problem-is-where-multi-agent-systems-die.md) — failure taxonomy
