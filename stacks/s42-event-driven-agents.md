# S-42 · Event-Driven Agent Architecture

An agent does not have to be called by a human. Most production agents are triggered by events: a PR opens, a form is submitted, an alert fires, a file lands in a bucket. The trigger mechanism determines latency, cost, and complexity. Getting it wrong by defaulting to polling costs 14× more and responds 38× slower.

## Situation

A team builds a PR-review agent. The simplest implementation: a cron job calls the agent every 60 seconds with "check if any new PRs need review." Most calls return nothing. After a week, the token bill is 14× higher than expected and PRs still wait 30 seconds on average for review to start. The correct implementation: a GitHub webhook fires the agent the moment a PR is opened, passing the payload directly.

## Forces

- Polling is simple to implement and easy to reason about. Its cost is proportional to the poll interval, not to the event rate. At low event frequency, most polls are empty — pure waste.
- Event-driven agents are more complex: you need a webhook endpoint, event parsing, idempotency handling, and retry logic for failed deliveries. The operational overhead is real.
- Latency is the hidden cost of polling. At a 60-second interval, the average event waits 30 seconds before the agent even starts. For review, alerting, and support use cases, 30 seconds is often unacceptable.
- Not all events are equal. Idempotency is non-negotiable: webhook delivery systems guarantee "at least once," not "exactly once." An agent triggered by a webhook must be safe to run twice on the same event.
- Some events should not trigger an agent immediately. High-frequency events (log lines, sensor readings, user keystrokes) need aggregation before an agent is useful. Event-driven does not mean every-event.
- Polling is sometimes correct: when the external system has no push API, when the agent needs to scan a batch of items on a schedule, or when aggregation before processing is required.

## The move

**Default to event-driven for reactive work; use polling only when the external system has no push API or when batch aggregation is required.**

**Event-driven pattern:**
```
Event source ──webhook→ Ingress endpoint ──enqueue→ Queue ──dequeue→ Agent
```

1. **Ingress endpoint** — receives the webhook, validates the signature (HMAC), returns 200 immediately. Never block the webhook response waiting for agent completion; the source has a delivery timeout.
2. **Queue** — decouples delivery from processing. If the agent is slow or fails, the event is not lost. Standard choice: SQS, Pub/Sub, or any reliable queue with at-least-once delivery.
3. **Agent** — consumes from the queue. Processes the event payload directly; no "check if there is work" step.

**Idempotency gate** — before processing, check if this event ID has been seen:
```js
async function handleEvent(event) {
  const seen = await cache.get(`event:${event.id}`);
  if (seen) return; // duplicate delivery — skip
  await cache.set(`event:${event.id}`, 1, { ttl: 86400 });
  // process
}
```

**Event aggregation** — for high-frequency events, collect into micro-batches before invoking the agent. A metric event arriving 10,000×/second does not need 10,000 agent calls; it needs one agent call per aggregation window with the batch summary.

**When polling is the right choice:**
- The source has no webhook API (legacy system, S3 bucket scan, scheduled feed)
- The agent must process a batch of items at once (daily report, weekly digest)
- The event rate is high enough that a push system would overwhelm the agent, and aggregation is not available

**Payload discipline** — inject the event payload directly as the agent's first message. Do not ask the agent to "go check what happened" — the event already contains what happened. Pass the structured payload; let the agent extract what it needs.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. PR-review agent simulation: 20 PRs/day, 60-second poll interval. Token counts modeled from real prompt measurements; latency figures are order-of-magnitude estimates (webhook delivery ~200ms + agent cold start ~600ms = ~800ms; poll average wait = interval/2).

```
=== Polling vs event-driven: PR review agent (20 PRs/day) ===

Polling (1,440 LLM calls/day):
  1,420 empty polls × 40 tok  = 56,800 tokens
  20 real reviews   × 434 tok =  8,680 tokens
  Daily cost: $0.40

Event-driven (20 LLM calls/day):
  20 PR webhooks × 234 tok = 4,680 tokens
  Daily cost: $0.03

Waste ratio:    14× more expensive to poll
Monthly delta: $11.07 saved by switching to event-driven

Latency:
  Polling (60s interval):  avg 30s wait before review starts
  Event-driven (webhook):  ~800ms to first token
  Responsiveness gain:     38× faster
```

The cost difference is real but the latency difference is the sharper argument for most teams. A PR waiting 30 seconds for automated review is invisible in most workflows; 800ms is instant.

## See also

[S-37](s37-batch-vs-realtime.md) · [S-35](s35-latency-budget.md) · [F-15](../forward-deployed/f15-durable-execution.md) · [F-20](../forward-deployed/f20-rate-limits-and-retry.md) · [S-19](s19-agent-loop.md)

## Go deeper

Keywords: `event-driven agents` · `webhook agent` · `polling vs push` · `at-least-once delivery` · `idempotency` · `event aggregation` · `agent triggers` · `GitHub webhook` · `serverless agent`
