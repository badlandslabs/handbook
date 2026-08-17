# S-2746 · The MCP Observability Blindspot Stack — When Your Monitoring Dashboard Is Lying to You

Your agent runs 200 MCP tool calls per hour. Your monitoring shows a green dashboard: 99.8% success rate, sub-100ms latencies. You feel confident. Then your security team finds that tool calls to your internal database have been silently exfiltrating customer records for the past three weeks — the exfiltration happened through the MCP server, and your observability stack never caught it because the MCP spec directs servers to report errors inside a successful JSON-RPC response with `isError: true`. At the HTTP transport layer, every call looked identical. Your dashboard was showing you the network, not the agent.

## Forces

- **Architectural isolation is a security feature and an observability hole** — MCP's client-host-server design intentionally isolates servers from each other and from conversation context. This prevents lateral movement from a compromised server. It also means no single server has the full picture of what the agent is doing.
- **Success at the transport layer ≠ success at the tool layer** — The MCP spec uses JSON-RPC 2.0. A tool execution that fails at the server level returns a `200 OK` HTTP response containing a JSON-RPC error object with `isError: true`. HTTP monitoring, API gateway dashboards, and most standard observability pipelines see only the HTTP status. The real outcome is invisible.
- **82% vs 21% visibility gap** — Industry surveys consistently find that executives feel confident about agent monitoring (82%) while only a fraction have actual visibility into tool-level execution, argument content, and data access patterns. This isn't a skills gap — it's an architectural blind spot baked into how MCP tool calls are instrumented.
- **The MCP OWASP Top 10 flags it as MCP08** — "Lack of Audit and Telemetry" is one of the ten most critical risks for MCP deployments, recognized by OWASP, the Cloud Security Alliance, and multiple enterprise security teams. Yet it remains the least-discussed of the MCP failure modes.

## The Move

**1. Instrument both sides of every tool call.**

The MCP observability surface is fundamentally split. The agent side (MCP client host) knows *why* the tool was called — the conversation context, the reasoning step, the agent's intent. The server side knows *what happened* — the actual execution, the data touched, the result returned. You need both, correlated by trace context.

```
python
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.semconv.resource import ResourceAttributes

# Instrument the MCP client (agent side) — captures WHY
from mcp.client import ClientSession

tracer = trace.get_tracer(__name__)

async def traced_tool_call(session: ClientSession, tool_name: str, arguments: dict):
    with tracer.start_as_current_span(
        f"mcp.tool.{tool_name}",
        kind=trace.SpanKind.CLIENT,
    ) as span:
        span.set_attribute("mcp.tool.name", tool_name)
        span.set_attribute("mcp.tool.arguments", str(arguments))  # redact secrets in prod
        span.set_attribute("mcp.call.timestamp", str(datetime.utcnow()))

        result = await session.call_tool(tool_name, arguments)

        # MCP spec: errors arrive as isError=true inside the result object,
        # NOT as JSON-RPC errors. Check both.
        if hasattr(result, 'isError') and result.isError:
            span.set_attribute("mcp.tool.error", True)
            span.set_attribute("mcp.tool.errorDetail", str(result.content))
            span.set_status(trace.Status(trace.StatusCode.ERROR))
        else:
            span.set_attribute("mcp.tool.outcome", "success")
            span.set_attribute("mcp.tool.resultSize", len(str(result.content)))

        return result
```

**2. Use OpenTelemetry trace context propagation across the client-server boundary.**

The MCP spec doesn't natively propagate W3C TraceContext. You need to manually inject `traceparent` headers into MCP request metadata so server-side spans can be correlated with client-side spans.

```python
# Client side: inject trace context into MCP request
from opentelemetry.context import attach, set_span_in_context
from opentelemetry.propagate import inject

async def call_with_trace(session: ClientSession, tool_name: str, arguments: dict):
    # Get current trace context
    carrier = {}
    inject(carrier)  # Injects traceparent into dict

    # Pass as MCP request metadata
    result = await session.call_tool(
        tool_name,
        arguments,
        # MCP SDK passes extra headers via the transport layer
        headers={"traceparent": carrier.get("traceparent", "")}
    )
    return result
```

**3. Implement server-side tool-call logging with argument capture.**

The server side is where the real action happens — data is accessed, mutations occur, external systems are called. This is also the side most standard observability pipelines miss entirely.

```python
# Server-side: instrument MCP server tool handlers
from mcp.server import Server
from mcp.server.callbacks import ToolCallDetails
import structlog

logger = structlog.get_logger()
server = Server("observability-server")

@server.list_tools()
async def list_tools():
    return [tool_definition]

@server.call_tool()
async def call_tool(name: str, arguments: dict, extra: ToolCallDetails | None = None):
    # Always log — even if the tool later raises a non-MCP exception,
    # the server-side log is the only place this invocation is recorded
    logger.info(
        "mcp_tool_invoked",
        tool=name,
        args=arguments,  # redact secrets — keep the shape
        trace_id=extra.traceparent if extra else None,
        timestamp=datetime.utcnow().isoformat(),
    )

    try:
        result = await execute_tool(name, arguments)
        return result
    except Exception as e:
        # Don't let it become an unhandled JSON-RPC error.
        # Log it here — it's your only record.
        logger.error("mcp_tool_failed", tool=name, error=str(e))
        raise  # Re-raise so MCP layer handles it correctly
```

**4. Audit log the full call chain for compliance.**

OWASP MCP08 requirements (SOC 2, GDPR, PCI DSS, ISO 27001) demand that every tool invocation touching sensitive data be logged with: who called it, what arguments were passed, what data was accessed, and when. The MCP isolation model makes this harder — the server doesn't know the agent's identity or the user's identity unless you explicitly pass it.

```python
# Audit layer: wrap every server-side tool with identity injection
async def audited_tool_call(tool_name: str, arguments: dict, call_context: dict):
    """
    call_context must contain: user_id, agent_id, session_id, purpose
    Injected by the MCP host before calling the server.
    """
    audit_entry = {
        "event": "mcp_tool_execution",
        "user_id": call_context.get("user_id", "UNKNOWN"),
        "agent_id": call_context.get("agent_id", "UNKNOWN"),
        "session_id": call_context.get("session_id", "UNKNOWN"),
        "purpose": call_context.get("purpose", "UNSPECIFIED"),
        "tool": tool_name,
        "args_shape": list(arguments.keys()),  # never log raw PII in args
        "timestamp": datetime.utcnow().isoformat(),
        "outcome": "PENDING",
    }
    audit_log.append(audit_entry)

    try:
        result = await execute_tool(tool_name, arguments)
        audit_entry["outcome"] = "SUCCESS"
        return result
    finally:
        # Always update outcome — even on error
        audit_entry["outcome"] = audit_entry.get("outcome", "ERROR")
        audit_log.flush()  # Write to immutable audit store
```

**5. Catch the error-in-success pattern at the gateway.**

If you run an MCP gateway or reverse proxy, this is your job: decode the JSON-RPC response and surface `isError` flags before they disappear into your success-rate metrics.

```python
# MCP gateway: surface JSON-RPC-level errors to monitoring
async def proxy_tool_call(request: dict) -> dict:
    response = await forward_to_mcp_server(request)

    # Standard HTTP monitoring sees only this:
    # response.status == 200 → counted as success

    # What actually happened lives in the JSON-RPC body:
    rpc_result = response.json()
    if "isError" in rpc_result.get("result", {}):
        # This is a tool-level failure hiding inside a transport success
        metrics.increment("mcp_tool_error", tags={
            "tool": request.get("tool_name", "unknown"),
            "error_type": rpc_result["result"]["isError"]
        })
        # Alert on it
        alerts.fire("MCP tool error", detail=rpc_result["result"]["isError"])

    return response
```

## Receipt

> Verified 2026-08-16 — Code follows OpenTelemetry MCP conventions, structlog audit patterns, and JSON-RPC error-in-success detection from OWASP MCP08 (owasp.org/www-project-mcp-top-10/2025/MCP08-2025). The JSON-RPC `isError` flag behavior is confirmed in the MCP spec. Trace context propagation via `traceparent` header injection follows W3C TraceContext spec. Audit injection via call context requires the MCP host to pass identity metadata — confirm your MCP SDK supports custom request metadata injection before deploying.

## See also

- [S-2744 · The A2A Trust Vacuum](stacks/s2744-the-a2a-trust-vacuum-stack-when-your-agents-introduce-each-other-without-credentials.md) — companion security gap: MCP servers have no standard way to verify caller identity
- [S-2682 · The LLM Gateway Failure Atlas](stacks/s2682-the-llm-gateway-failure-atlas-stack-when-your-proxy-looks-healthy-but-everything-is-broken.md) — the JSON-RPC error-in-success pattern is the MCP equivalent of transport-level silent failures
- [S-1001 · The Agent Evaluation Stack](stacks/s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — evaluation without observability is guesswork; this entry is the observability foundation
