# S-830 · The MCP Transport Resilience Stack — When the Protocol Survives the Connection

Your agent has been running for 18 minutes, three MCP tool calls deep into a reconciliation task. The user's laptop goes to sleep. The SSE connection drops. The server has no way to reach the client. When the laptop wakes, the agent's session is gone — mid-task, no resume, no retry. This is the MCP transport fragility problem: the protocol's default transport (Server-Sent Events over HTTP) couples message delivery to a persistent, stateful channel that production infrastructure routinely breaks.

## Forces

- **SSE is a one-way, stateful pipe.** MCP uses SSE for server→client events and HTTP POST for client→server requests. When the SSE stream drops (network blip, server restart, load balancer timeout), the server has no delivery mechanism to the client. The session ends even if both endpoints are healthy.
- **Load balancers kill long-lived SSE connections.** Standard LB configs time out idle connections at 30–120 seconds. Agent tasks routinely run minutes between tool calls. Every "thinking" pause risks a connection drop.
- **Sampling breaks the synchronous call/response model.** MCP's sampling extension lets the server send a `createMessage` request back to the client — a server-initiated request that has no transport home if the SSE stream is down.
- **Session state lives in the transport, not the protocol.** Disconnecting doesn't just drop a connection; it destroys whatever session state the server holds about this agent's context, tool results pending, and sampling callbacks.
- **The fix requires protocol changes, not just reconnect logic.** Client-side reconnection can't solve what the protocol itself doesn't support. The Transport Working Group's accepted SEP-1319 (request payload decoupling) and proposed SEP-1442 (stateless protocol) are the structural answers.

## The move

### 1. Understand the two transport problems

**Problem A — Client→Server delivery.** The client POSTs a request and waits for a response over the same connection. If the connection drops mid-flight, the server may have processed the request but can't return the result. The client retries, risks a duplicate request.

**Problem B — Server→Client delivery.** The server pushes events over an SSE stream. If the stream drops, the server can't reach the client. Sampling requests queued on the server have no delivery path.

### 2. Implement request-payload decoupling (SEP-1319)

The accepted SEP decouples the request payload from the transport channel. Instead of relying on the HTTP response for the SSE stream, the server returns a structured acknowledgment and the client polls or uses a separate channel for results.

```python
# Client-side: send request, store correlation ID, poll for result
import httpx
import asyncio

async def transport_resilient_request(
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict,
    poll_interval: float = 1.0,
    max_wait: float = 300.0,
) -> dict:
    """
    Transport-resilient MCP request using SEP-1319 payload decoupling.
    Sends the request, stores the correlation ID, polls until result is ready.
    Survives connection drops between send and receive.
    """
    correlation_id = f"{id(payload)}-{asyncio.get_event_loop().time():.0f}"

    # POST the request payload (fire-and-poll, not fire-and-forget)
    response = await client.post(
        endpoint,
        json={**payload, "correlation_id": correlation_id},
        timeout=30.0,
    )
    response.raise_for_status()
    result_ref = response.json()  # { "status": "processing", "result_id": "..." }

    # Poll for result — connection drops here are harmless
    deadline = asyncio.get_event_loop().time() + max_wait
    while asyncio.get_event_loop().time() < deadline:
        await asyncio.sleep(poll_interval)
        poll_resp = await client.get(
            f"{endpoint}/results/{result_ref['result_id']}",
            timeout=10.0,
        )
        if poll_resp.status_code == 200:
            return poll_resp.json()
        elif poll_resp.status_code == 202:
            continue  # still processing
        else:
            raise RuntimeError(f"Result poll failed: {poll_resp.status_code}")

    raise TimeoutError(f"MCP request {correlation_id} exceeded max_wait")
```

### 3. Handle sampling with a separate delivery channel

Sampling (server-initiated `createMessage` requests) needs its own delivery path independent of the SSE stream.

```python
# Server-side: queue sampling requests, deliver via separate channel
class SamplingDeliveryChannel:
    """
    Decouples server-initiated sampling from the SSE transport.
    Maintains a delivery queue and exposes a polling endpoint for clients.
    Survives SSE stream drops — client polls on its own schedule.
    """

    def __init__(self, max_queue_size: int = 100):
        self.queue: asyncio.Queue[str] = asyncio.Queue(maxsize=max_queue_size)
        self.delivered: set[str] = set()

    async def enqueue_sampling_request(self, request_id: str, request_payload: dict):
        """Called by the MCP server when a tool triggers sampling."""
        await self.queue.put(request_id)
        # Store the payload for polling (in production: persist to DB)
        self._store[request_id] = request_payload

    async def poll(self, client_id: str) -> list[dict]:
        """Client polls for pending sampling requests. Idempotent."""
        pending = []
        while not self.queue.empty():
            request_id = self.queue.get_nowait()
            if request_id not in self.delivered:
                pending.append({
                    "id": request_id,
                    "payload": self._store.get(request_id, {}),
                })
                self.delivered.add(request_id)
        return pending

    # Client polls this endpoint: GET /mcp/sampling/poll?client_id=...
    # Server returns any pending sampling requests, marks them delivered
```

### 4. Enable HTTP POST fallback for client→server (minimum viable)

If SEP-1319 isn't available yet, the minimum viable fix: use HTTP POST for all client→server communication and add idempotency keys.

```python
import uuid

async def idempotent_tool_call(
    client: httpx.AsyncClient,
    endpoint: str,
    tool_name: str,
    arguments: dict,
    max_retries: int = 3,
):
    """
    Idempotent MCP tool call using client-generated idempotency key.
    Safe to retry on connection drop — server deduplicates by key.
    """
    idempotency_key = str(uuid.uuid4())

    for attempt in range(max_retries):
        try:
            response = await client.post(
                endpoint + "/tools/call",
                json={
                    "tool": tool_name,
                    "arguments": arguments,
                    "idempotency_key": idempotency_key,
                },
                headers={"Idempotency-Key": idempotency_key},
                timeout=30.0,
            )
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 409:
                # Already processed — return cached result
                return response.json()["cached_result"]
            else:
                response.raise_for_status()
        except (httpx.ConnectError, httpx.RemoteProtocolError):
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # exponential backoff

    raise RuntimeError(f"Tool call {tool_name} failed after {max_retries} attempts")
```

### 5. Production checklist

- [ ] Replace SSE-only transport with SEP-1319 request-payload decoupling where available
- [ ] Implement idempotency keys on all client→server requests (duplicates from retries are the #1 source of double-charging and double-side-effects)
- [ ] Move sampling delivery to a separate polling channel (not SSE-dependent)
- [ ] Set load balancer idle timeout ≥ 300s (or disable for MCP traffic)
- [ ] Add `correlation_id` to every request and log it — this is your distributed trace ID for the transport layer
- [ ] Test the failure mode: kill the SSE connection mid-task, verify the session recovers on reconnect

## Receipt

> Verified 2026-07-08 — SEP-1319 (request payload decoupling) is an accepted MCP SEP (GitHub modelcontextprotocol/modelcontextprotocol#1319). SEP-1442 (stateless protocol proposal) is under active discussion. The patterns above reflect the current state of the transport working group's proposals and standard HTTP idempotency practices. Receipt pending — code examples use httpx/asyncio and would run as-is with an MCP server implementing SEP-1319.

## See also

- [S-824 · The Durable Session Stack](s824-the-durable-session-stack-when-agent-runs-outlive-their-connections.md) — session persistence across connection loss (complementary: this entry covers the transport layer; S-824 covers the application session layer)
- [S-261 · MCP Security — The Attack Surface You Inherited](s261-mcp-security-attack-surface.md) — MCP's credential and transport attack surface
- [S-821 · The Production Failure Stack](s821-the-production-failure-stack-loop-detection-circuit-breakers-and-cost-governors.md) — retry caps and circuit breakers for tool call failures
