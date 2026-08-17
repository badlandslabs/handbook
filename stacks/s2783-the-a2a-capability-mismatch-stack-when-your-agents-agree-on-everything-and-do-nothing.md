# S-2783 · The A2A Capability Mismatch Stack — When Your Agents Agree on Everything and Do Nothing

Your A2A handshake completed in 45ms. Both agents exchanged AgentCards. Negotiation succeeded. The task envelope shipped cleanly over HTTP/2 with JSON-RPC framing. No errors. No timeouts. No protocol violations. The orchestrator handed off the document processing task to the remote agent and waited.

Twelve minutes later: the remote agent returned `Task.Status.FAILED` with reason `"unsupported input format"`. The orchestrator had sent `{"format": "pdf", "content": "..."}`. The remote agent's AgentCard advertised `"capabilities": ["pdf-processing"]` — but its actual runtime handler only accepted `"markdown"` or `"html"`. The protocol said yes. The agent said no.

This is the **A2A Capability Mismatch**: the gap between what an AgentCard advertises at handshake time and what an agent's runtime handler actually accepts. The handshake is semantic. The failure is syntactic. The protocol doesn't know the difference.

## Forces

- **The AgentCard is a schema contract, not a runtime spec.** It declares that an agent *can* process PDFs in general. It doesn't specify *which* PDF variants, *what* input schema, or *what* preconditions must hold. Capability advertisement and capability invocation live at different abstraction levels.
- **Negotiation is a one-time event; task execution is continuous.** A2A's capability negotiation happens at handshake. If the actual task input diverges from what the AgentCard anticipated — different format version, missing required fields, unexpected encoding — the protocol has no mechanism to re-negotiate mid-stream.
- **Agents retry locally on mismatch without telling their peer.** When an agent receives input it can't process, it attempts a local fallback strategy (e.g., convert to markdown). It does *not* send a `CapabilityRefused` message back to the orchestrator. The orchestrator waits, gets a silent timeout, and retries the same payload.
- **Schema compatibility is structural, not semantic.** Two agents can both advertise `"capabilities": ["pdf-processing"]` and have zero overlap in their actual supported formats. The A2A spec defines the message envelope shape; it says nothing about semantic compatibility of the payloads inside it.
- **The $40,000 failure mode.** One production team lost $40K in a single incident because an A2A handshake succeeded between a document-ingestion agent and a PDF-analysis agent — both published `document-analysis` in their AgentCards — but the analysis agent required `application/json` input while the ingestion agent sent `multipart/form-data`. No protocol error. No retry backoff. Just silence and compounding downstream failures.

## The move

**Add a semantic compatibility layer above the A2A negotiation handshake.**

The core insight: capability advertisement at handshake time ≠ capability compatibility at invocation time. Treat the gap as a first-class failure mode.

### 1. Schema-anchored capability declarations

Extend AgentCard entries with runtime compatibility metadata, not just capability names:

```json
{
  "capabilities": [
    {
      "name": "document-analysis",
      "input_schemas": ["application/json", "multipart/form-data"],
      "supported_formats": ["pdf-1.7", "pdf/a", "markdown", "html"],
      "max_input_size_mb": 50,
      "required_fields": ["content", "task_id"]
    }
  ]
}
```

Without this, AgentCards are marketing materials, not contracts.

### 2. Pre-flight compatibility check before sending

Before every A2A task push, validate the payload against the receiver's declared schema compatibility:

```python
import a2a

async def safe_task_push(
    client: a2a.A2AClient,
    task: dict,
    receiver_card: dict
) -> a2a.TaskStatus:
    cap = next(
        (c for c in receiver_card["capabilities"]
         if c["name"] == task["skill"]),
        None
    )
    if not cap:
        raise CapabilityMismatchError(
            f"Receiver does not advertise {task['skill']}"
        )

    # Check structural compatibility
    if task["content_type"] not in cap.get("input_schemas", []):
        raise CapabilityMismatchError(
            f"Content-Type {task['content_type']} not in "
            f"{cap['input_schemas']} for skill {task['skill']}"
        )

    # Check semantic compatibility
    if task["content_format"] not in cap.get("supported_formats", []):
        raise CapabilityMismatchError(
            f"Format {task['content_format']} not in "
            f"{cap['supported_formats']}"
        )

    return await client.send_task(task)
```

### 3. Treat CapabilityRefused as a protocol-level error

If the receiver can't process the input, it must return a `CapabilityRefused` response — not attempt a silent local fallback or return `FAILED` without explanation:

```python
class CapabilityRefused(Exception):
    """Receiver can't process this input format."""
    def __init__(self, skill, offered, accepted, fallback_hint=None):
        self.skill = skill
        self.offered = offered
        self.accepted = accepted
        self.fallback_hint = fallback_hint

# In the remote agent's handler:
if not _can_handle(content_type, content_format):
    raise CapabilityRefused(
        skill="document-analysis",
        offered={"content_type": content_type, "format": content_format},
        accepted={"content_type": cap["input_schemas"], "format": cap["supported_formats"]},
        fallback_hint="convert_to_markdown"  # what the sender should try
    )
```

The `fallback_hint` field lets the sender attempt the right fallback without guessing.

### 4. Negotiate at task level, not just at handshake level

If pre-flight fails, enter a lightweight re-negotiation:

```python
async def negotiate_capability(
    client: a2a.A2AClient,
    remote_agent_id: str,
    skill: str,
    payload: dict
) -> tuple[str, dict]:
    """Request a compatible handler variant from the peer agent."""
    response = await client.send_message(
        to=remote_agent_id,
        type="CapabilityNegotiation",
        body={
            "skill": skill,
            "offered_payload": {
                "content_type": payload["content_type"],
                "format": payload["format"],
                "size_mb": payload.get("size_mb", 0)
            }
        }
    )
    negotiated = response["body"]["agreed_capability"]
    return negotiated["handler_name"], negotiated["transform_hint"]
```

This is a lightweight JSON-RPC exchange, not a full handshake — it runs in milliseconds and can be cached per (agent, skill, format) tuple.

### 5. Instrument the handshake-to-execution gap

Add a dedicated trace span for capability negotiation resolution:

```
span: a2a_negotiation
  ├── handshake: COMPLETED (45ms)
  ├── capability_check: PASSED (schema level)
  ├── pre_flight_check: FAILED (semantic level)
  │     ├── offered: {format: "pdf", content_type: "multipart/form-data"}
  │     └── accepted: {format: ["markdown","html"], content_type: ["application/json"]}
  ├── re_negotiation: AGREED (12ms)
  │     └── transform_hint: "convert_to_markdown"
  └── task_execution: SUCCESS (2.3s)
```

Without this trace, the mismatch is invisible — you see a 45ms handshake, then a 2.3s execution, and no signal that there was a negotiation round in between.

## See also

- [S-1040 · The Protocol Gap](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — the foundational A2A/MCP split this entry extends
- [S-1042 · The Protocol Stack](s1042-the-protocol-stack-when-your-agent-needs-to-talk-to-agents-and-tools.md) — the two-layer protocol model
- [S-1140 · The Protocol Sandwich](s1140-the-protocol-sandwich-stack-when-mcp-alone-isnt-enough-and-a2a-alone-is-too-much.md) — when to layer MCP + A2A together
