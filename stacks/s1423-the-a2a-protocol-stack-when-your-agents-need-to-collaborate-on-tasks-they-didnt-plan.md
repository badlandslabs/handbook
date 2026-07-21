# S-1423 · The A2A Protocol Stack — When Your Agents Need to Collaborate on Tasks They Didn't Plan

You built three specialized agents. Each is good at one thing. Now the triage agent needs to hand off to the researcher, which needs a human to approve a medical claim, which needs to route back to the executor. Nobody planned the handshake. A2A v1.0.0 (150+ supporters, April 2026) is the protocol that makes this work without custom integration code for every pair.

## Forces

- Custom point-to-point agent integrations cost 2–4 weeks each and break whenever either side changes — the integration tax is unsustainable at any scale
- A2A v1.0.0 ships a shared task state machine, AgentCard discovery, and streaming — teams that treat it as "just another API" miss the architectural implications
- MCP gives agents their *hands* (tool access); A2A gives agents their *colleagues* (collaborative handoff) — both are necessary, neither is sufficient alone

## The move

### The AgentCard: capability advertisement before connection

Every A2A agent exposes an AgentCard at `/.well-known/agent.json`. This is the discovery primitive — before any task is sent, a client queries the card to understand capabilities, supported input/output modes, and authentication requirements.

```json
{
  "name": "claims-researcher",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "stateTransitionTo": ["submitted", "approved", "escalated"]
  },
  "skills": [
    { "id": "med-claim-review", "name": "Medical Claim Review" },
    { "id": "policy-lookup", "name": "Policy Lookup" }
  ],
  "authentication": { "schemes": ["bearer", "api-key"] }
}
```

The AgentCard eliminates the "does this agent support what I need?" guesswork. Query it at startup or at task-submission time. If the required skill isn't listed, don't send the task.

### The shared task state machine

A2A v1.0.0 formalizes a task lifecycle that both sides share:

```
working → submitting-submit → submitted → completed
                         ↘           ↘
                          input-required → escalated
```

| State | Who drives it | When it fires |
|-------|---------------|---------------|
| `working` | Server | Task accepted, processing started |
| `input-required` | Server | Needs human data, external lookup, or approval |
| `submitted` | Server | Task delivered to downstream agent |
| `completed` | Server | Terminal success state |
| `failed` | Server | Terminal failure, includes error |

The critical state is `input-required` — this is A2A's native human-in-the-loop primitive. When an agent hits a policy threshold (e.g., claim > $10,000), it transitions to `input-required` and sends a push notification. The human provides the needed input via `tasks/pushNotificationSubscribe`; the agent resumes.

```python
# A2A task submission (client side)
from a2a.client import A2AClient

async def submit_claim_for_review(claim_id: str, amount: float):
    client = A2AClient("http://researcher-agent:8000")

    # Discovery: check AgentCard first
    card = await client.get_agent_card()
    if "med-claim-review" not in {s["id"] for s in card["skills"]}:
        raise ValueError("Agent doesn't support med-claim-review")

    # Submit with streaming so we get state transitions live
    task = await client.send_task(
        task={
            "taskId": f"claim-{claim_id}",
            "skills": ["med-claim-review"],
            "input": {"claim_id": claim_id, "amount": amount},
        },
        stream=True
    )

    async for event in task.stream():
        if event["type"] == "state-transition":
            if event["state"] == "input-required":
                print(f"⚠️  Agent needs human input: {event['data']}")
                # Trigger HIL flow — don't block
            elif event["state"] == "completed":
                print(f"✅ Result: {event['data']}")
```

### Push notifications: the async rescue

Long-running agent tasks can't rely on HTTP request-response. A2A v1.0.0 uses Server-Sent Events (SSE) for push notifications. Subscribe once; receive all state transitions:

```python
# Server-side: publish state transitions
from a2a.server import A2AServer, push_notification

class ClaimsResearcherAgent(A2AServer):
    async def handle_task(self, task):
        claim = await self.fetch_claim(task.input["claim_id"])

        if claim.amount > 10_000:
            # Human approval required — transition state and push
            await self.transition_state(task.id, "input-required", {
                "reason": "amount-above-threshold",
                "approver_role": "senior-adjuster",
                "input_schema": {"type": "object", "properties": {
                    "approved": {"type": "boolean"},
                    "notes": {"type": "string"}
                }}
            })
            await push_notification(
                subscriber_url=task.subscriber_url,
                event={"state": "input-required", "taskId": task.id}
            )
            return  # Resume after human provides input via tasks/resubmit

        result = await self.review_claim(claim)
        await self.transition_state(task.id, "completed", {"verdict": result})
```

### Streaming: partial results without waiting for completion

A2A streaming lets the client receive partial results as the agent generates them — critical for UX on long tasks and for monitoring progress:

```python
async def monitor_claim_task(task_id: str):
    client = A2AClient("http://researcher-agent:8000")

    async for chunk in client.stream_task(task_id):
        if chunk["type"] == "textdelta":
            print(chunk["text"], end="", flush=True)
        elif chunk["type"] == "artifact":
            print(f"\n📎 Artifact: {chunk['name']}")
        elif chunk["type"] == "state-transition":
            log_metric("a2a_state_transition", {"task": task_id, "state": chunk["state"]})
```

### Opaque execution: what A2A does NOT share

A2A is explicit about boundaries: agents collaborate without exposing internal state, memory, tool definitions, or reasoning traces. This is not a limitation — it's a security and encapsulation guarantee. Two agents can collaborate on a task while each maintaining its own context window and tool access. The only shared surface is the task input/output and the AgentCard capability manifest.

## Receipt

> Verified 2026-07-20 — A2A v1.0.0 specification (a2a-protocol.org, April 2026); AgentCard schema from official spec; task state machine from a2aproject/A2A GitHub; streaming and push notification patterns from maheshwark.com interoperability post (February 2026) and techbytes.app cheat sheet (July 2026). Code patterns synthesized from A2A Python SDK structure and MCP+A2A integration examples. Production usage confirmed by agentmarketcap.ai (April 2026) and gheware.com DevOps blog (multi-agent Kubernetes, 2026). Not end-to-end tested in live environment.

## See also

- [S-1040 · The Protocol Gap](s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP + A2A overview; this entry is the wire-level companion
- [S-10 · MCP](s10-mcp.md) — MCP for tool access; A2A handles what MCP doesn't
- [S-1414 · The Stochastic-Deterministic Boundary](s1414-the-stochastic-deterministic-boundary-stack-when-your-llm-outputs-become-actions.md) — SDB formalizes the decision boundary; A2A formalizes the collaboration boundary
- [S-1023 · The Recovery Ladder](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — `input-required` is the A2A-native equivalent of the `needs-human` recovery step
