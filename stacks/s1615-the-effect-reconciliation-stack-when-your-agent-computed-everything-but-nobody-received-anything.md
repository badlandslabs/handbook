# S-1615 · The Effect Reconciliation Stack — When Your Agent Computed Everything But Nobody Received Anything

Your agent ran for 47 minutes. It queried 12 databases, cross-referenced three external APIs, compiled a 4,200-word analysis, and wrote it to your reporting dashboard. Status: complete. Three hours later, your team asks where the report is. The dashboard is blank. The agent completed its work — it just never confirmed delivery. This is the effect reconciliation problem: agents that compute everything correctly and confirm nothing to the outside world.

## Forces

- **Execution success is not delivery confirmation.** An agent that reaches its final line of code has not necessarily delivered its output. The delivery step — writing to a file, posting to a webhook, sending a message — is the most likely failure point, and the least monitored.
- **Agents self-report from inside the pipeline.** The agent's internal log says "complete" because it reached the last instruction. It has no way to know whether that instruction's side effects actually propagated to the recipient. The status field reflects the computation, not the delivery.
- **Delivery failures are silent by design.** Most delivery mechanisms (webhooks, file writes, HTTP POSTs) return a 200/OK to the caller even when the downstream system silently drops the payload. The agent receives a success signal from a system that itself failed.
- **The cron/job-runner layer makes this invisible.** Cron frameworks track job completion, not output reception. A run that processes 3,000 records, builds a perfect report, and then hits a Slack rate limit on delivery will show as "delivered: true" in the job record — because the framework recorded what the agent told it, not what the channel received.

## The move

**Treat delivery as a distinct step with its own confirmation loop.** Separate concerns: compute → output → deliver → confirm. Each step has a failure mode, and the delivery step's failure mode is invisible if you don't instrument it specifically.

### 1. Unbundle the final step

Don't mix computation and delivery in the same function. Keep them sequential and explicit:

```python
# Bad: delivery buried in the compute step
async def run_report(request):
    data = await gather_data(request)
    report = compile(data)
    await webhook.post(report)  # silently fails → run looks "complete"
    return {"status": "done"}

# Good: delivery as a distinct phase with its own contract
async def run_report(request):
    data = await gather_data(request)
    report = compile(data)
    delivery = await deliver_to_webhook(report, idempotency_key=f"report-{request.id}")
    if not delivery.confirmed:
        raise DeliveryError(f"Report {request.id} computed but not delivered: {delivery.reason}")
    return {"status": "delivered", receipt: delivery.receipt_id}
```

### 2. Idempotency-key every delivery

The biggest risk in a delivery-confirmation gap is double-delivery on retry. Assign a stable idempotency key at the start of the run and check delivery status before attempting it:

```python
async def deliver_to_webhook(payload: dict, idempotency_key: str) -> DeliveryResult:
    # Check if already delivered
    existing = await delivery_log.get(idempotency_key)
    if existing and existing.confirmed:
        return DeliveryResult(confirmed=True, receipt_id=existing.receipt_id, skipped=True)
    
    # Attempt delivery
    try:
        response = await http.post(WEBHOOK_URL, json=payload, timeout=10)
        receipt_id = response.headers.get("X-Delivery-ID")
        await delivery_log.put(idempotency_key, DeliveryRecord(
            confirmed=True,
            receipt_id=receipt_id,
            delivered_at=datetime.utcnow()
        ))
        return DeliveryResult(confirmed=True, receipt_id=receipt_id)
    except DeliveryError as e:
        await delivery_log.put(idempotency_key, DeliveryRecord(
            confirmed=False,
            reason=str(e),
            attempted_at=datetime.utcnow()
        ))
        raise
```

### 3. Heartbeat confirmation for async delivery

For delivery mechanisms that don't return a receipt inline (fire-and-forget webhooks, message queues, email), add a heartbeat that polls for confirmation:

```python
async def deliver_with_heartbeat(payload: dict, channel: DeliveryChannel) -> bool:
    # Fire the delivery
    delivery_id = await channel.dispatch(payload)
    
    # Heartbeat: wait for upstream confirmation (max 30s)
    for attempt in range(6):
        await asyncio.sleep(5)
        status = await channel.check_status(delivery_id)
        if status == "delivered":
            return True
        if status == "failed":
            raise DeliveryFailed(f"Channel {channel.name} failed delivery {delivery_id}")
    
    # Heartbeat exhausted: surface this explicitly
    raise DeliveryUnconfirmed(
        f"Delivery {delivery_id} dispatched but not confirmed after 30s. "
        f"Check {channel.status_url.format(delivery_id)} manually."
    )
```

### 4. Three-state delivery tracking

Model delivery as a three-state machine, not a boolean:

```
NOT_REQUESTED → DISPATCHED → CONFIRMED
                        ↘ FAILED
```

Only CONFIRMED means the recipient actually has the output. Track all three states in your job record:

```python
@dataclass
class DeliveryRecord:
    state: Literal["not_requested", "dispatched", "confirmed", "failed"]
    delivery_id: Optional[str] = None
    confirmed_at: Optional[datetime] = None
    reason: Optional[str] = None
```

## Receipt

> Verified 2026-07-25 — Pattern identified from production failure reports:
> - Hermes Agent cron delivery bug (#5861): `last_status = "ok"` even when Discord/Telegram delivery fails
> - OpenClaw cron delivery bug (#59709): logs show `delivered: true` but no push notification received
> - Pazi.ai incident: "cron that creates side effects but runs out of budget before the announce step still serializes as delivered"
> These three independent reports across different agent runtimes confirm the pattern is structural, not incidental.

## See also

- [S-928 · Phantom Completion: When Your Agent Says Done and Nothing Happened](s928-phantom-completion-when-your-agent-says-done-and-nothing-happened.md) — tool returns success, nothing happened; sibling failure mode
- [S-1023 · The Recovery Ladder: When Your Agent Thinks It Succeeded But Didn't](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — agent misjudges its own success; this entry covers delivery failure where agent is correct about computation
- [S-1614 · The Agentic Failure Gate: When Your Agent Doesn't Crash But Spends 35 Minutes Doing Nothing Wrong](s1614-the-agentic-failure-gate-stack-when-your-agent-doesnt-crash-but-spends-35-minutes-doing-nothing-wrong.md) — loop/stall detection; complementary to delivery confirmation
- [S-988 · The Agent Fleet Resilience Stack: When Your Orchestrator Dies But Your Agents Keep Running](s988-the-agent-fleet-resilience-stack-when-your-orchestrator-dies-but-your-agents-keep-running.md) — mid-flight failures; same production-reality gap as delivery reconciliation
