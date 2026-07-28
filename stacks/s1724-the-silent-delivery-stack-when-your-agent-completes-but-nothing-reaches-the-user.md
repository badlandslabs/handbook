# S-1724 · The Silent Delivery Stack — When Your Agent Completes Successfully and Nothing Reaches the User

You shipped the agent. The run log says `status: success`. The dashboard is green. Your user filed a ticket three hours later: "I never received anything." Somewhere between the agent's internal completion signal and your user's inbox, the work evaporated — and your monitoring architecture had no idea.

You reach for this when agent runs finish cleanly but your users report no output, when your success rate looks great but your delivery rate tells a different story, or when you discover that "complete" and "delivered" are two entirely different events your system treats as one.

## Forces

- **Completion is a self-reported event. Delivery is an external one.** The agent's natural termination signal — final LLM response, tool-return, or state-machine transition — marks internal completion. Whether the output reached the intended recipient (email, webhook, database, file store) lives on the other side of a trust boundary the agent never inspects. Standard APM assumes these are the same event. For agents, they almost never are.
- **Side-effect failures don't raise exceptions.** When a tool call fails with an HTTP 500, the agent can retry or escalate. When it returns 200 OK but the payload was silently dropped, routed to the wrong queue, or consumed by a downstream rate-limit, the agent sees success and terminates. Your run log has no idea anything went wrong.
- **The delivery step is often the most fragile part of the pipeline.** Outbound delivery (email, Slack, SMS, webhook, file write) runs outside the agent's control loop. It involves network hops, auth tokens, rate limits, and downstream systems that the agent has no visibility into and no retry budget for. It's the most likely place for silent failure and the hardest place to instrument.
- **Traditional APM answers the wrong question.** "Did the service respond within SLO?" vs "Did your agent's output actually reach the user?" are two completely different questions with completely different answers. APM was built for request-response cycles; agents are asynchronous, multi-step, and side-effect-driven.

## The Move

Treat delivery verification as a first-class concern, structurally separate from execution completion.

### 1. Split Completion from Delivery

Separate the agent's internal completion signal from the delivery confirmation. The agent owns execution; a delivery orchestrator owns the handoff to the user.

```
# Naive — completion ≈ delivery
agent.run(task) → "done" → email.send() → return 200

# Better — delivery is explicit, verified, and tracked
result = agent.run(task)
delivery = delivery_orchestrator.deliver(result, receipt_handle=result.id)
if not delivery.confirmed:
    retry_queue.enqueue(result, cause=delivery.failure_reason)
```

### 2. Implement Delivery Receipts as Durable Events

Use an idempotent delivery table, not a boolean flag. The receipt records what was delivered, where, when, and whether the downstream acknowledged receipt.

```python
from datetime import datetime, timedelta
import uuid

class DeliveryReceipt:
    def __init__(self, task_id: str, destination: str, payload_digest: str):
        self.id = str(uuid.uuid4())
        self.task_id = task_id
        self.destination = destination
        self.payload_digest = payload_digest  # SHA-256 of delivered content
        self.status = "pending"  # pending | confirmed | failed | unknown
        self.created_at = datetime.utcnow()
        self.confirmed_at: datetime | None = None
        self.failure_reason: str | None = None
        self.retry_count = 0

# Delivery orchestrator
async def deliver(result: AgentResult, receipt_handle: str | None = None) -> DeliveryReceipt:
    receipt = DeliveryReceipt(
        task_id=result.task_id,
        destination=result.user_channel,
        payload_digest=compute_digest(result.content)
    )

    # Check for duplicate delivery (idempotency)
    if existing := delivery_db.find(receipt.task_id, receipt.destination):
        if existing.payload_digest == receipt.payload_digest:
            return existing  # Already delivered, same content
        # Content changed — may need re-delivery decision
        return await handle_content_drift(existing, receipt)

    try:
        confirmed = await channel.send(receipt.destination, result.content)
        receipt.status = "confirmed"
        receipt.confirmed_at = datetime.utcnow()
    except DeliveryError as e:
        receipt.status = "failed"
        receipt.failure_reason = f"{e.code}: {e.message}"
        retry_queue.enqueue(receipt, delay=calculate_backoff(receipt.retry_count))
    except TimeoutError:
        receipt.status = "unknown"
        receipt.failure_reason = "timeout — confirmation not received"
        # Escalate to human review for unknown state

    delivery_db.save(receipt)
    return receipt
```

### 3. Instrument the Three-State Delivery Signal

A delivery status field needs three states, not two:

| Status | Meaning | Action |
|--------|---------|--------|
| `delivered` | Downstream acknowledged receipt | Done — close the run |
| `not-delivered` | Delivery attempted and failed (known reason) | Retry with backoff, alert on threshold |
| `not-requested` | No delivery was ever triggered | This is itself a failure mode — the agent never initiated delivery |

The third state (`not-requested`) is the most dangerous. It catches cases where the agent completed the task internally (created a GitHub issue, wrote to a database, generated a report) but never initiated the delivery step — often because the delivery step was out-of-band, or because the agent ran out of budget before reaching it.

### 4. Build a Delivery Confirmation Loop

For high-stakes outputs, implement a confirmation loop that waits for downstream acknowledgement before marking the run complete:

```python
async def deliver_with_confirmation(
    result: AgentResult,
    timeout: timedelta = timedelta(minutes=5),
    poll_interval: float = 10.0
) -> DeliveryReceipt:
    receipt = await deliver(result)

    if receipt.status == "confirmed":
        return receipt

    # For confirmed or known-failed, return immediately
    # For unknown state, wait for confirmation or timeout
    if receipt.status == "unknown":
        deadline = datetime.utcnow() + timeout
        while datetime.utcnow() < deadline:
            await asyncio.sleep(poll_interval)
            refreshed = delivery_db.find(receipt.task_id, receipt.destination)
            if refreshed.status == "confirmed":
                refreshed.status = "confirmed_late"
                delivery_db.save(refreshed)
                return refreshed

        # Timed out waiting for confirmation — escalate
        alert_oncall(
            f"Delivery unconfirmed after {timeout}: task={receipt.task_id}",
            severity="warning",
            channel="#agent-ops"
        )
        return receipt

    return receipt
```

### 5. Close the Loop with Delivery Rate Metrics

Track two separate rates:

- **Execution rate**: `tasks_completed / tasks_started` — what the agent reports internally
- **Delivery rate**: `outputs_received_by_user / tasks_completed` — what the user actually gets

A healthy agent system has execution rate ≈ delivery rate. A system with a silent delivery problem has execution rate >> delivery rate, and you only discover the gap when users complain. Alert on divergence between these two rates.

```
delivery_rate = delivery_confirmed_count / tasks_completed_count
if delivery_rate < 0.99:
    alert("Delivery divergence: {:.1%} of completed tasks not received by users".format(1 - delivery_rate))
```

## Receipt

> Verified 2026-07-27 — Sources: Pazi.ai "5 Silent Failure Modes in Production AI Agents" (Kevin Kamau, Apr 2026); AppScale Blog "AI Observability with OpenTelemetry" (2026); Galileo.ai "Agent Telemetry and the New Observability Model" (Jul 2026); NotiLens "AI Agents in Production: Silent Failures, Ghost Runs" (May 2026). Pattern confirmed across all four sources: the delivery/completion gap is the primary observability blind spot in 2026 agent deployments. Code example is a production-grade design pattern implemented by multiple teams per the Pazi.ai incident report (bug-triage cron, 300s timeout case).

## See also

- [S-817 · The Trajectory Eval Stack](s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — testing the agent's decision path, not just the output
- [S-1677 · The Phantom Receipt Stack](s1677-the-phantom-receipt-stack-when-your-agent-reports-a-done-that-never-happened.md) — when the agent fabricates a completion signal internally
- [S-1637 · The Execution Trace Attribution Stack](s1637-the-execution-trace-attribution-stack-when-your-agent-fails-silently.md) — localizing which step caused a silent failure
