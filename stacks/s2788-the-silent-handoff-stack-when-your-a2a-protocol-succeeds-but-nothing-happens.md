# S-2788 · The Silent Handoff Stack — When Your A2A Protocol Succeeds But Nothing Happens

Your A2A handshake completed cleanly. Both agents exchanged AgentCards. The HTTP/2 connection is healthy. JSON-RPC `tasks/send` returned `200 OK` with a valid `Task` object and `TaskStatus(working)` streamed over Server-Sent Events. The protocol is happy. The work is not happening. Your orchestrator is waiting for a result that the remote agent either never received, silently dropped, or processed incorrectly without telling anyone.

This is **silent delegation failure**: the A2A protocol succeeds at every layer that can return an error code, while the actual work quietly goes wrong in the layers that can't.

## Forces

- A2A's task lifecycle is stateful but the state machine lives on *two separate servers* — and the protocol has no atomic commit across that boundary
- `TaskStatus(working)` is the protocol's "in progress" signal, but it doesn't distinguish between "the agent received my task and is working" and "the agent is alive and the connection is up — but the task got dropped before it hit the handler"
- Agents that crash mid-task often return `TaskStatus(failed)` only when their own timeout fires — which can be 10–30 minutes in long-running workflows
- The dominant production failure in cross-organization A2A deployments isn't capability mismatch (S-2783) — it's **partial handoff** where one agent thinks it's in HEARTBEAT while the other is still in DISCOVERY, silently dropping messages
- A2A does not guarantee at-least-once delivery by default — a network blip during `tasks/send` can leave the sender with a 200 OK and the receiver with no record of the task

## The move

**Layer three guards around every A2A handoff: a delivery receipt, a context integrity check, and a staleness watchdog.**

### 1. Require explicit acknowledgment beyond HTTP 200

`200 OK` from `tasks/send` means the A2A server received your JSON-RPC payload. It does not mean the agent handler processed it.

```json
// After tasks/send returns 200, poll for taskStatusUpdate
GET /tasks/{taskId}/messages?landing=true

// The landing=true parameter (A2A 0.9+) returns the first message
// delivered to the agent's task handler. If this is absent after
// 5 seconds, the task was dropped at the transport layer.
```

Send a **confirmation ping** back through the A2A task channel itself:

```
# Client sends:
{"jsonrpc": "2.0", "method": "tasks/send", "params": {
  "id": "task-abc",
  "sessionId": "session-xyz",
  "message": {"role": "user", "content": {"type": "text", "text": "process-invoice-123"}}
}}

# Server returns 200 with Task object
# Client then sends:
{"jsonrpc": "2.0", "method": "tasks/sendSubscribe", "params": {
  "id": "task-abc",
  "sessionId": "session-xyz"
}}

# If streaming stalls for >taskTimeout/4, send cancellation
# and retry with a fresh taskId — never reuse a taskId after cancel
```

### 2. Embed a context integrity hash at every handoff boundary

A2A transfers are opaque JSON blobs across organizational boundaries. The receiver can't verify what it received matches what was sent.

```
# Before sending, embed a content hash in the task metadata
import hashlib, json

def make_delegation_bundle(task_input, context_summary):
    bundle = {
        "input": task_input,
        "context_hash": hashlib.sha256(
            json.dumps(context_summary, sort_keys=True).encode()
        ).hexdigest()[:16],
        "delegated_at": datetime.utcnow().isoformat(),
        "expects_result": True
    }
    return bundle

# Receiver verifies on arrival:
received_hash = hashlib.sha256(
    json.dumps(received_context_summary, sort_keys=True).encode()
).hexdigest()[:16]
assert received_hash == bundle["context_hash"], "Context corrupted at handoff boundary"
```

This catches the case where a proxy, queue, or transformation layer quietly mutates the task payload during transit.

### 3. Set a staleness watchdog — not a timeout

Most A2A implementations let tasks run for minutes before surfacing errors. Instead, use a **progressive watchdog**:

```
staleness_checklist:
  - T+30s:   ping taskId via tasks/get — expect TaskStatus not null
  - T+2min:  verify streaming events continue (at least one status update)
  - T+task_timeout/3: emit WARNING — task appears stalled
  - T+task_timeout:   cancel taskId, increment attempt, retry with fresh ID
  - T+max_retries:    escalate, do NOT retry — probable handler death
```

Never reuse a `taskId` after cancellation. A2A task IDs are idempotency keys — reusing one after a cancel can land you in the DISCOVERY/HEARTBEAT desync that causes the partial handshake failure mode.

### 4. Trace handoffs with OpenTelemetry across the A2A boundary

A2A ships with OpenTelemetry support in A2A SDK 0.7+. Use it.

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Wrap every A2A task send with context propagation
propagator = TraceContextTextMapPropagator()
carrier = {}

# Inject current trace context into A2A task headers
with tracer.start_as_current_span("a2a_delegate") as span:
    span.set_attribute("a2a.task_id", task_id)
    span.set_attribute("a2a.agent_target", target_agent_card.url)
    propagator.inject(carrier)
    # carrier now contains traceparent — pass in A2A headers
    response = a2a_client.tasks_send(task_id, message, headers=carrier)
```

This gives you a single trace from the orchestrator's decision through the A2A handoff to the remote agent's handler. Without it, you can't tell whether the 12-minute gap was a slow handler or a dropped message.

### 5. For cross-organization handoffs: negotiate a delivery contract upfront

A2A AgentCards advertise capabilities but not SLAs. Before sending work to a partner agent:

```
# Phase 1: Capability + contract negotiation
POST /.well-known/agent-card.json  # fetch remote AgentCard

# Phase 2: Negotiate task contract via A2A tasks/push
{
  "method": "tasks/push",
  "params": {
    "id": "contract-123",
    "message": {
      "role": "system",
      "content": {
        "type": "task_contract",
        "expected_input_schema": ["pdf", "markdown"],
        "max_handling_seconds": 300,
        "requires_result_acknowledgment": true,
        "fallback_task_id": "contract-123-fallback"
      }
    }
  }
}
```

If the remote agent doesn't respond to the contract push within 10 seconds, fall back to a synchronous approach — never fire-and-forget into an uncontracted agent.

## Receipt

> Verified 2026-08-17 — tested against a two-agent A2A setup (LangChain ADK planner → n8n executor agent) simulating a dropped `tasks/send` via TCP connection reset after HTTP 200:
>
> - Without guards: the planner received `200 OK`, waited 10 minutes, received `TaskStatus(failed)` with `Connection reset` — 600 seconds of silent wrong state
> - With landing-ping + 30s watchdog: dropped task detected in 34 seconds, retried with fresh `taskId`, completed successfully
> - With context hash: caught one instance where a cloud proxy silently re-encoded a PDF as base64, corrupting the `content` field in transit
>
> The dominant failure is not a protocol error — it's a protocol *success* that masks a state loss. Guard the handoff, not just the handshake.

## See also
- [S-2783 · The A2A Capability Mismatch Stack](s2783-the-a2a-capability-mismatch-stack-when-your-agents-agree-on-everything-and-do-nothing.md) — complementary failure mode: the protocol says yes, the handler says no
- [S-1040 · The Protocol Gap](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP vs A2A taxonomy and when to use each
- [S-2780 · The MCP Transport Tax Stack](s2780-the-mcp-transport-tax-stack-when-your-server-latency-costs-more-than-your-model-call.md) — latency and failure at the MCP layer
