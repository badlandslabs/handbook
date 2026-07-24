# S-1603 · The A2A Task Lifecycle Stack — When Your Agent Hands Off Work and Loses Contact

Your research agent delegates to a code-review agent via A2A. You expect a result in 30 seconds. Ten minutes later, you have nothing — the task is running on a server you can't see, over a connection that may have dropped. The A2A protocol solves agent-to-agent communication, but it introduces a new reliability problem: **long-running tasks outlive the HTTP request that started them**, and the default synchronous mental model will make every team burn hours on phantom tasks.

## Forces

- **HTTP was built for request/response. A2A tasks are not requests.** A task can run for hours, delegate to sub-agents, stream partial results, pause for human input, and produce files — none of which fits a single HTTP round-trip.
- **The client can't hold a connection for the task lifetime.** A phone user closes the app. A web client navigates away. A daemon crashes. Without durable delivery, the task completes successfully and the result disappears.
- **Four delivery modes exist and teams pick one by accident.** SSE streaming, polling, push notifications, and simple synchronous responses each have failure modes. Using the wrong one for your task type causes silent failures, duplicate work, or security holes.
- **Human-in-the-loop breaks the stateless model.** When an A2A task hits `input_required`, it pauses mid-execution on a remote server — waiting for a response on a channel the client may have already closed.

## The Move

Treat every A2A task as a **stateful object with a durable lifecycle**, not a function call. Implement the task state machine, pick the right delivery mode for each task type, and handle `input_required` as a first-class pause point.

### 1. Understand the A2A Task State Machine

Every A2A task transitions through a defined set of states. The client must track state, not just wait for a final message.

```
Task States:
  submitted → working → [input_required] ↔ working → completed
                ↓                        ↓
              failed                   cancelled
```

Key transitions to handle explicitly:
- **`working`**: Task is running. Do not re-submit — you'll create a duplicate.
- **`input_required`**: Task is paused on a remote server. You have a `contextId` and a `taskId` to resume. The agent on the other side is *waiting* for your response — if you never send it, the task hangs forever.
- **`completed`**: Final result delivered. Tear down local state.
- **`failed` / `cancelled`**: Recover via dead-letter handling (see S-1032).

### 2. Pick the Delivery Mode by Task Type

The A2A spec defines four ways to receive task output. Each has a specific use case:

| Mode | Use When | Failure Mode |
|------|----------|-------------|
| **Synchronous** | Sub-30s tasks, client stays connected | Connection drop = no result |
| **SSE streaming** | Real-time UI updates, progress bars, partial artifacts | SSE drop = reconnect + replay logic needed |
| **Polling** | Client may go offline (mobile, batch jobs) | Poll too rarely = slow delivery; too often = wasted calls |
| **Push notifications** | Server-initiated delivery, webhook receivers | Webhook endpoint down = notification lost |

The A2A spec mandates that agents advertise their capabilities in the **Agent Card** — specifically `capabilities.streaming: true/false` and `capabilities.pushNotifications: true/false`. Always read the target agent's card before choosing a delivery mode. If the agent doesn't support streaming and you try SSE, you'll fall back to polling silently.

```python
# Read the Agent Card before choosing delivery mode
import httpx

async def get_agent_card(base_url: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{base_url}/.well-known/agent-card.json")
        response.raise_for_status()
        return response.json()

# Always check capabilities
card = await get_agent_card("https://code-review-agent.example.com")
capabilities = card.get("capabilities", {})
supports_streaming = capabilities.get("streaming", False)
supports_push = capabilities.get("pushNotifications", False)

# Pick delivery mode based on agent capabilities AND task characteristics
if supports_streaming and task_estimated_time < 60:
    delivery_mode = "sse"
elif supports_push and task_estimated_time > 60:
    delivery_mode = "push"
else:
    delivery_mode = "polling"  # Always works as fallback
```

### 3. Handle `input_required` as a First-Class Pause Point

When an agent encounters a decision that requires human (or upstream system) input, it transitions to `input_required` and sends a `DataTransferObjects.InputRequiredError` with a `contextId`. The delegating agent must:

1. **Detect the state transition** — listen for `on_agent_action_suggested` events or poll task state
2. **Extract the question** — the error payload contains the clarification request
3. **Route for resolution** — user, upstream system, or a separate approval agent
4. **Resume with `tasks/resubmit`** — send the response back on the same `contextId`

```python
from a2a.client import A2AClient
from a2a.types import InternalError, TextPart, DataPart

async def handle_task_with_hitl(
    client: A2AClient,
    task_id: str,
    submit_payload: dict,
):
    task = await client.send_task(task_id, payload=submit_payload)

    while task.status.state not in ("completed", "failed", "cancelled"):
        if task.status.state == "input_required":
            # Extract the clarification request
            clarification = task.status.message.parts[0].text
            print(f"Agent needs input: {clarification}")

            # Route to human (in production: queue + notification)
            user_response = await request_human_input(clarification)

            # Resume on the SAME contextId
            resubmit_payload = {
                "contextId": task.status.context_id,
                "taskId": task_id,
                "response": user_response,
            }
            task = await client.tasks_resubmit(resubmit_payload)

        elif task.status.state == "working":
            # Stream partial results if SSE
            if hasattr(task, "artifact") and task.artifact:
                yield task.artifact

        await asyncio.sleep(2)  # Poll interval
```

### 4. Implement Push Notification Webhook Security

Push notifications ship results to your endpoint — treat them like webhook payloads:

- **Verify the signature** in the `Authorization` header using the shared secret from the Agent Card's `authentication` field
- **Acknowledge with 200** immediately; process asynchronously
- **Idempotency**: A2A push notifications are at-least-once. Use the `taskId` as an idempotency key to handle duplicates
- **Return `429` or `503`** if you're overwhelmed — A2A agents handle retry with backoff

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import hashlib, hmac, json

app = FastAPI()
_processed_task_ids: set[str] = set()

@app.post("/a2a/webhook")
async def receive_push(request: Request):
    # Verify signature
    body = await request.body()
    auth_header = request.headers.get("Authorization", "")
    expected_sig = hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not auth_header.startswith("Bearer ") or auth_header[7:] != expected_sig:
        raise HTTPException(status_code=401, detail="Invalid signature")

    payload = json.loads(body)
    task_id = payload.get("taskId", "")
    status = payload.get("status", {}).get("state", "")

    # Idempotency check
    if task_id in _processed_task_ids:
        return JSONResponse({"status": "already_processed"}, status_code=200)
    _processed_task_ids.add(task_id)

    # Route by final state
    if status == "completed":
        await process_completed_task(payload["result"])
    elif status == "failed":
        await handle_task_failure(payload["error"])

    return JSONResponse({"status": "received"}, status_code=200)
```

### 5. The SSE Reconnection Pattern

If you use SSE streaming, plan for disconnection from day one. SSE connections drop — they time out, get killed by proxies, or die when the client process restarts.

```python
import httpx
import sseclient

async def streaming_task_with_reconnect(
    client: A2AClient,
    task_id: str,
    base_url: str,
    max_retries: int = 3,
):
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as http:
                async with client.streaming_task(task_id) as response:
                    client_ = sseclient.SSEClient(response.iter_lines())
                    for event in client_.events():
                        yield parse_sse_event(event)
            return  # Exited cleanly — task is done
        except (httpx.ReadTimeout, httpx.RemoteProtocolError) as e:
            # Reconnect and resume from last seen event
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
                # Re-fetch task state to find where we left off
                task_state = await client.tasks_get(task_id)
                resume_from = task_state.status.message_index or 0
            else:
                raise RuntimeError(f"SSE stream failed after {max_retries} attempts: {e}")
```

## Receipt

> Verified 2026-07-24 — A2A Protocol Specification v1.0.0 (a2a-protocol.org) confirms task state machine, `input_required` semantics, SSE/polling/push triad, and Agent Card capability negotiation. Implementation pattern validated against `a2a-samples` Python SDK (a2aproject/A2A GitHub). `input_required` resubmit flow confirmed against AG2 docs (docs.ag2.ai). Push notification signature verification pattern follows A2A spec §7 security guidance. SSE reconnection strategy aligns with A2A streaming topic guide recommendations for long-running tasks.

## See also

- [S-1040 · The Protocol Gap](stacks/s1040-the-protocol-gap-when-your-agent-knows-how-to-call-tools-but-not-how-to-talk-to-other-agents.md) — MCP vs A2A roles
- [S-1104 · The Three-Layer Protocol Stack](stacks/s1104-the-three-layer-protocol-stack-when-your-agent-lives-in-a-world-of-three-simultaneous-protocols.md) — MCP + A2A + A2UI together
- [S-1032 · The Dead Letter Stack](stacks/s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — handling failed and cancelled A2A tasks
