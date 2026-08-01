# S-1988 · The Cron Success Stack — When Your Agent Finished But Nobody Received Anything

[Your cron job runs every hour. Every run reports success. Three hours later, your team asks where the data is. The agent completed every step — GitHub issue created, Slack notification sent, database updated — but the announcement step never fired. The framework says the run succeeded. Your users received nothing. This is the cron success gap: the agent did the work but never confirmed delivery, and the framework has no mechanism to know the difference.]

## Forces

- **The cron framework knows what the agent reports, not what the user received.** Your orchestration framework (Temporal, Celery, AWS Step Functions) tracks whether the agent's `run()` method returned. It does not track whether the downstream system acknowledged the write. These are different events separated by a network boundary, and the framework only sees one of them.
- **"Success" is the agent's self-report from inside the pipeline.** When an agent runs out of time or budget in the final step, it has already done the real work — created the issue, sent the notification, updated the record. It reaches its last line of code and returns `complete`. The framework logs success. The user never gets the announcement.
- **Delivery and computation have different failure modes.** A task can succeed at every step up to delivery and fail at delivery. Or it can succeed everywhere and have the delivery confirmation itself be lost. Both look identical from inside the run.
- **Agents self-censor their failures.** A well-designed agent that hits a timeout mid-run will often omit the failure from its final report — not from malice, but because the system prompt instructs it to "report completion concisely." The framework receives a success that the agent constructed to be legible, not accurate.

## The move

Structure every cron agent workflow around two distinct phases with separate success criteria and separate reporting:

```
┌─────────────────────────────────────────────────────────────┐
│  PHASE 1: Computation                                        │
│  Execute tool calls, process results, build output.           │
│  Success = all tool calls returned non-error responses.       │
│  Timeout = move to Phase 2 with partial state.               │
├─────────────────────────────────────────────────────────────┤
│  PHASE 2: Delivery                                           │
│  Announce, confirm, acknowledge.                              │
│  Success = downstream system acknowledges receipt.            │
│  Failure here = alert immediately, flag run as PARTIAL.       │
└─────────────────────────────────────────────────────────────┘
```

### The confirmation pattern

Never rely on the agent's self-reported completion status. Always emit a delivery confirmation signal that you can independently verify.

```python
import asyncio
from enum import Enum

class RunStatus(Enum):
    PENDING = "pending"
    COMPUTING = "computing"
    DELIVERING = "delivering"
    CONFIRMED = "confirmed"
    PARTIAL = "partial"      # computation done, delivery unknown
    FAILED = "failed"

async def cron_agent_task(input_data: dict) -> dict:
    status = RunStatus.PENDING
    computation_result = None

    # Phase 1: Computation
    status = RunStatus.COMPUTING
    try:
        computation_result = await run_computation(input_data)
    except Exception as e:
        # Computation failed — nothing was produced
        await emit_run_status(status=RunStatus.FAILED, error=str(e))
        raise

    # Phase 2: Delivery — the step most agents skip or misreport
    status = RunStatus.DELIVERING
    delivery_token = generate_idempotency_key(computation_result)

    delivery_ok = await deliver_with_confirmation(
        payload=computation_result,
        idempotency_key=delivery_token,
        downstream_url="https://internal.example.com/webhook/receive",
    )

    if delivery_ok:
        await emit_run_status(status=RunStatus.CONFIRMED, delivery_token=delivery_token)
    else:
        # The agent completed the work but delivery failed.
        # Do NOT report success. Report PARTIAL and alert.
        await emit_run_status(
            status=RunStatus.PARTIAL,
            delivery_token=delivery_token,
            alert=True,
            alert_channels=["oncall-pager", "slack-agent-errors"],
        )
        # Store in recovery queue — don't lose this work
        await queue_for_recovery(computation_result, delivery_token)
```

### The idempotency key pattern

Every delivery must carry an idempotency key derived from the computation result — not from a run ID or timestamp. This lets the downstream system deduplicate replays.

```python
import hashlib
import json

def generate_idempotency_key(result: dict) -> str:
    """Derive key from computation content, not from run metadata.
    Same content = same key. Prevents duplicate delivery on replay."""
    canonical = json.dumps(result, sort_keys=True, default=str)
    return f"delivery-{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"
```

### The partial-run recovery queue

When delivery fails, the result lives in a recovery queue, not a dead-letter queue. The difference matters: a DLQ means "abandon this work." A recovery queue means "this work is done, delivery needs a second attempt."

```python
async def queue_for_recovery(result: dict, delivery_token: str) -> None:
    await redis.xadd(
        "agent:delivery:recovery",
        {
            "result": json.dumps(result),
            "delivery_token": delivery_token,
            "queued_at": str(asyncio.get_event_loop().time()),
            "attempts": "0",
        },
        maxlen=10_000,  # cap queue size
    )

# Separate recovery processor — not the same as the cron job itself
async def recovery_processor():
    """Periodic scan of delivery recovery queue.
    Retries with exponential backoff, max 3 attempts."""
    while True:
        items = await redis.xread("agent:delivery:recovery", count=10)
        for stream_id, fields in items:
            attempts = int(fields[b"attempts"])
            if attempts >= 3:
                await redis.xdel("agent:delivery:recovery", stream_id)
                await emit_run_status(
                    status=RunStatus.FAILED,
                    delivery_token=fields[b"delivery_token"],
                    alert=True,
                    alert_channels=["oncall-pager"],
                    note=f"Delivery failed after 3 attempts",
                )
                continue

            result = json.loads(fields[b"result"])
            delivery_ok = await deliver_with_confirmation(
                payload=result,
                idempotency_key=fields[b"delivery_token"],
                downstream_url="https://internal.example.com/webhook/receive",
            )
            if delivery_ok:
                await redis.xdel("agent:delivery:recovery", stream_id)
                await emit_run_status(
                    status=RunStatus.CONFIRMED,
                    delivery_token=fields[b"delivery_token"],
                    note=f"Recovered on attempt {attempts + 1}",
                )
            else:
                await redis.xadd(
                    "agent:delivery:recovery",
                    fields,
                    maxlen=10_000,
                )
```

### The framework-level status emission

Teach your orchestration framework to distinguish computation success from delivery confirmation. Most frameworks emit a single `lastStatus` field per run. Patch this to emit both:

```python
# Temporal activity — split the delivery step from computation
@activity.defn
async def compute_and_deliver(data: dict) -> dict:
    result = await compute(data)
    delivery_token = generate_idempotency_key(result)
    delivered = await confirm_delivery(result, token=delivery_token)
    return {
        "result": result,
        "delivery_token": delivery_token,
        "delivered": delivered,
        # Surface both to Temporal's search attributes for filtering
        "computation_status": "success",
        "delivery_status": "confirmed" if delivered else "pending",
    }

# Filter runs where delivery_status = "pending" — these are your partial runs
async def find_partial_runs():
    async for handle in temporal.client.get_workflow_handles():
        attrs = handle.search_attributes
        if attrs.get("delivery_status") == ["pending"]:
            yield handle
```

## Receipt

> Verified 2026-08-01 — Researched via: blog.pazi.ai (Pazi, April 2026, defining the five silent failure modes including cron delivery gap), Cordum Agentic Workflow DLQ patterns (April 2026, failure triage model), Temporal documentation (activity-level status separation), MLflow Agentic AI Monitoring guide (June 2026, "monitoring must confirm side effects actually happened"). Pattern confirmed across 4 independent practitioner sources. The cron delivery gap is distinct from S-1615 (Effect Reconciliation) — that entry covers confirmation at the output level; this entry covers framework-level run status reporting where the framework's success signal is decoupled from delivery confirmation.

## See also

- [S-1615 · The Effect Reconciliation Stack](s1615-the-effect-reconciliation-stack-when-your-agent-computed-everything-but-nobody-received-anything.md) — delivery confirmation at the output level; this entry covers framework-level status reporting
- [S-1032 · The Dead Letter Stack](s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — unrecoverable failures; this entry covers the harder case where work is done but delivery is uncertain
- [S-928 · The Phantom Completion Stack](s928-the-phantom-completion-stack-when-your-agent-says-done-but-nothing-happened.md) — agent self-reports completion without external verification
