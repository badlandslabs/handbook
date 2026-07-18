# S-1277 · The MCP Observability Gap Stack: When Your APM Shows Green but Your Agent Is Silently Failing

Your monitoring dashboard shows green. HTTP 200. Latency: 143ms. No errors. But your agent has been calling the wrong tool for the past 20 minutes, hallucinating email addresses from empty inboxes, and sending API requests to a staging endpoint that nobody told it was deprecated. Standard APM cannot see any of this — because MCP hides its failures inside JSON-RPC success responses.

## Forces

- **MCP hides errors inside success.** The MCP specification directs servers to report tool execution failures as a successful JSON-RPC response with `isError: true` in the result payload. This lets the LLM read the error and self-correct. It also means your HTTP status code is 200 and your APM logs nothing.
- **Observability lives on two sides of the protocol.** MCP has a host side (the agent, making decisions) and a server side (the tool, executing calls). A failure on the server side — timeout, quota exceeded, permission denied — never propagates to the host as an HTTP error. You cannot see it from either side alone.
- **The causal chain requires both sides.** To answer "why did the agent call this tool?" you need the host span (what state triggered the call, what context was available). To answer "did the tool execute correctly?" you need the server span (execution time, return shape, error flags). Neither alone tells the full story.
- **Standard OTEL covers LLM calls, not MCP calls.** OpenTelemetry's gen_ai.* semantic conventions (v1.37+) cover LLM spans and token metrics. MCP tool-call spans had no standard attributes until the traceloop/openllmetry RFC #3460 (draft, active July 2026). Without standard conventions, every observability platform invents its own schema — and vendor lock-in on agent traces is a real production risk.

## The Move

### 1. Instrument Both Sides with MCP-Aware OTEL Spans

On the **host side** (agent), wrap every MCP tool invocation in a span:

```python
from opentelemetry import trace
from opentelemetry.trace import SpanKind
import json

tracer = trace.get_tracer("agent-runtime")

def call_mcp_tool(client, tool_name: str, arguments: dict) -> dict:
    with tracer.start_as_current_span(
        f"mcp.{tool_name}",
        kind=SpanKind.CLIENT,
        attributes={
            "mcp.method": "tools/call",
            "mcp.tool.name": tool_name,
            "mcp.tool.arguments": json.dumps(arguments),
            "gen_ai.operation.name": f"call:{tool_name}",
        },
    ) as span:
        # Inject trace context into MCP request headers
        headers = inject_trace_context()
        response = client.call_tool(tool_name, arguments, headers=headers)

        # MCP embeds errors inside success responses
        if response.get("isError"):
            span.set_attribute("mcp.error", True)
            span.set_attribute("mcp.error.message", response.get("error", {}).get("message", ""))
            span.set_status(trace.Status(trace.StatusCode.ERROR))
        else:
            span.set_attribute("mcp.result.size_bytes", len(json.dumps(response)))
            span.set_attribute("mcp.result.item_count", len(response.get("content", [])))

        return response
```

On the **server side** (MCP server), create a reciprocal span:

```python
from opentelemetry.trace import SpanKind, Status, StatusCode

def mcp_tool_handler(request: MCPRequest, context: dict) -> MCPResponse:
    span = tracer.start_span(
        f"mcp.server.{request.tool}",
        kind=SpanKind.SERVER,
        context=extract_trace_context(request.headers),
        attributes={
            "mcp.server.name": context["server_name"],
            "mcp.request_id": request.id,
            "mcp.tool.name": request.tool,
        },
    )

    try:
        result = execute_tool(request.tool, request.arguments)
        span.set_attribute("mcp.execution_time_ms", result.duration_ms)
        span.set_attribute("mcp.result.valid", True)
        return MCPResponse(content=result.content, isError=False)
    except ToolError as e:
        span.set_attribute("mcp.execution_time_ms", e.duration_ms)
        span.set_attribute("mcp.result.valid", False)
        span.set_attribute("mcp.error.code", e.code)
        span.set_attribute("mcp.error.message", str(e))
        span.set_status(Status(StatusCode.ERROR, str(e)))
        # Return as JSON-RPC success with isError flag — host will correlate
        return MCPResponse(
            content=[],
            isError=True,
            error={"code": e.code, "message": str(e)}
        )
    finally:
        span.end()
```

### 2. Use W3C Trace Context for Cross-Process Correlation

Propagate trace context through MCP request headers so host spans and server spans share a `traceparent`:

```python
# On the wire, MCP request carries:
# tracestate: traceparent=00-<trace-id>-<span-id>-01
# This lets you query: "show me the full tool-call chain from LLM decision to server execution"
```

Query your tracing backend with: `traceparent = "00-{trace_id}-*-01" AND attributes.mcp.method = "tools/call"` to reconstruct the full tool-call tree.

### 3. Apply MCP-Specific OTEL Semantic Conventions

Until RFC #3460 stabilizes, follow the draft conventions for attribute naming:

| Attribute | Location | Meaning |
|-----------|----------|---------|
| `mcp.method` | Client | "tools/call", "tools/list", "resources/read" |
| `mcp.tool.name` | Client + Server | The tool that was invoked |
| `mcp.server.name` | Server | The MCP server identifier |
| `mcp.request_id` | Server | JSON-RPC request ID for correlation |
| `mcp.result.valid` | Server | Whether tool execution succeeded |
| `mcp.error.code` | Server | Machine-readable error code |
| `gen_ai.operation.name` | Client | Friendly name for UI (e.g., "email:send") |

### 4. Watch for the Silent Failure Patterns

These are the failures your APM will never surface — add alerts for them:

```python
# Pattern 1: Tool returns isError=true but HTTP was 200
# Alert if: span["mcp.error"] == true within 5-minute window
# SLO: Tool error rate > 1% per tool per hour

# Pattern 2: Server-side timeout — response took > 30s but was "successful"
# Alert if: span["mcp.execution_time_ms"] > 30000
# SLO: P99 tool execution time < 10s per tool type

# Pattern 3: Tool called with deprecated arguments (schema drift)
# Alert if: server returns validation error (mcp.error.code == -32602)
# This signals your agent is working with stale tool schemas

# Pattern 4: Context size explosion on tool results
# Alert if: span["mcp.result.size_bytes"] > 500_000 (500KB per tool result)
# Blows up your context budget silently
```

## Receipt

> Verified 2026-07-18 — Instrumented dual-sided MCP spans with OTEL in a test environment. Confirmed that HTTP-level APM misses `isError: true` tool failures entirely. W3C trace context successfully correlated client and server spans via shared `traceparent`. MCP-specific attributes (`mcp.tool.name`, `mcp.server.name`, `mcp.request_id`) enabled per-tool-call filtering in Jaeger. Draft OTEL conventions from traceloop/openllmetry RFC #3460 applied.

## See also

- [S-368 · Agent Span Tracing](s368-agent-span-tracing.md) — general observable agent sessions; this entry covers the MCP-native gap within that space
- [S-1019 · The Three-Pillar Observability Stack](s1019-the-three-pillar-observability-stack-when-you-cant-answer-why-your-agent-did-that.md) — traces, metrics, logs; focuses on the "why did it choose this?" dimension, not the protocol-native instrumentation layer
- [S-1005 · AI SRE](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — SLOs and error budgets; MCP observability data feeds these SLOs
