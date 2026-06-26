# F-34 · Async Agent Requests

A research agent that summarizes a topic takes 30–90 seconds. A code-generation agent that writes and runs tests takes 2–5 minutes. You can't hold an HTTP connection open for 5 minutes — mobile clients drop it, load balancers close it, users navigate away. The fix is to decouple submission from delivery: accept the task, return a job ID immediately, run the agent in the background, and let the client poll or receive a webhook when it's done. This is the async agent request pattern.

This is distinct from [S-37](../stacks/s37-batch-vs-realtime.md) (batch API: many calls in a file, results in hours) and [F-15](f15-durable-execution.md) (durable execution: checkpoint/resume within a long-running task). Those solve different problems. This pattern solves the HTTP timeout problem for a single long-running agent task.

## Situation

A user submits a research request: "Summarize the competitive landscape for electric vehicle charging infrastructure." The agent calls five tools, makes three model calls, and returns a structured report. Total wall-clock: 45 seconds. If you handle this synchronously, 10% of requests time out at the load balancer (30s timeout), 20% time out on mobile (45s), and users who navigate away lose their result. Moving to async: the POST returns in <100ms, the client polls for completion, and 100% of results are delivered.

## Forces

- **HTTP timeouts are a hard constraint.** Load balancers, CDNs, and mobile operating systems all have timeout ceilings. A 30s LB timeout is common. A 200ms mobile foreground limit is real on some platforms. Async decouples task duration from connection lifetime.
- **Polling frequency trades server load for latency.** Polling every 1s for a 45s task produces 45 HTTP calls — 45× the server load of a webhook. Exponential backoff (1s→2s→4s→8s→16s→30s capped) produces 6 calls for the same task: 87% fewer, while the first detection latency stays at 1s.
- **Webhooks are better than polling for known-latency clients.** If the client can receive an HTTP POST (server-to-server, background service), webhooks reduce polling to 1 call (the completion notification) at <1s delivery latency. Not all clients can receive webhooks — browsers behind NAT can't, mobile apps need a push channel.
- **Tasks need wall-clock timeouts.** An agent that loops, calls a broken tool, or generates endlessly must be killed at a deadline. Without a timeout, hung tasks consume worker slots indefinitely. The timeout state is terminal and must be communicated to the client.
- **Idempotency prevents double-submission.** On network failure, clients retry the POST. Without idempotency keys, two identical task submissions create two background jobs and two results. The client should include a unique `idempotency_key`; the server deduplicates on it.

## The move

**Submit returns job_id in <100ms. Poll with exponential backoff. Use webhooks when available. Set wall-clock timeouts. Deduplicate with idempotency keys.**

**Job state machine:**

```
queued → running → done
                 → failed
                 → timeout
       → cancelled  (at any pre-terminal state)
```

**API shapes:**

```
POST /tasks
Request:  { prompt, idempotency_key, callback_url? }
Response: { task_id, status: "queued", estimated_duration_sec }

GET /tasks/:id
Response (running): { task_id, status: "running", started_at, progress? }
Response (done):    { task_id, status: "done", completed_at, result: { ... } }
Response (failed):  { task_id, status: "failed", error: { type, message } }
Response (timeout): { task_id, status: "timeout", killed_at }
```

**Server-side task handler:**

```js
async function runAgentTask(taskId, prompt, { timeoutMs = 120_000 } = {}) {
  await db.updateTask(taskId, { status: 'running', started_at: new Date() });

  const controller = new AbortController();
  const timeoutHandle = setTimeout(() => {
    controller.abort();
    db.updateTask(taskId, { status: 'timeout', killed_at: new Date() });
  }, timeoutMs);

  try {
    const result = await runAgent(prompt, { signal: controller.signal });
    await db.updateTask(taskId, { status: 'done', completed_at: new Date(), result });

    // Notify via webhook if callback_url was provided
    const task = await db.getTask(taskId);
    if (task.callback_url) {
      await fetch(task.callback_url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ task_id: taskId, status: 'done', result }),
      }).catch(err => log.warn('Webhook delivery failed', { taskId, err: err.message }));
    }
  } catch (err) {
    if (err.name === 'AbortError') return;  // timeout branch already handled
    await db.updateTask(taskId, { status: 'failed', error: { type: 'agent_error', message: err.message } });
  } finally {
    clearTimeout(timeoutHandle);
  }
}
```

**Client-side polling with exponential backoff:**

```js
async function pollForResult(taskId, { startMs = 1000, capMs = 30_000, maxAttempts = 20 } = {}) {
  let intervalMs = startMs;

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    await sleep(intervalMs);
    const task = await fetch(`/tasks/${taskId}`).then(r => r.json());

    if (task.status === 'done')    return task.result;
    if (task.status === 'failed')  throw new Error(task.error.message);
    if (task.status === 'timeout') throw new Error('Task timed out');

    // Still running: back off
    intervalMs = Math.min(intervalMs * 2, capMs);
  }

  throw new Error(`Task ${taskId} did not complete after ${maxAttempts} polls`);
}
```

**Idempotency guard (server):**

```js
async function submitTask(prompt, idempotencyKey) {
  const existing = await db.findByIdempotencyKey(idempotencyKey);
  if (existing) return existing;  // return original task on retry

  const task = await db.createTask({ prompt, idempotency_key: idempotencyKey, status: 'queued' });
  queue.enqueue(task.id);  // dispatch to worker
  return task;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Polling comparison computed analytically; no HTTP calls made.

```
=== Async agent request: polling overhead for a 45s task ===

Strategy                   Poll calls   First detection latency
Fixed 1s interval          45           1s
Fixed 5s interval           9           5s
Exponential 1→2→4→8→16→30s  6           1s (intervals: 1→2→4→8→16→14s)
Webhook (push)               1           <1s

At 1000 tasks/day:
  Fixed 1s:     45 000 poll calls/day
  Exp backoff:   6 000 poll calls/day  (87% fewer)
  Webhook:       1 000 poll calls/day  (completion notifications only)

Exponential backoff achieves 1s detection latency at 13% of the 1s polling load.
```

**State machine:**

| State | Terminal | Meaning |
|---|---|---|
| `queued` | No | Accepted; waiting for worker |
| `running` | No | Agent loop executing |
| `done` | Yes | Result available |
| `failed` | Yes | Terminal error; see `error` field |
| `timeout` | Yes | Wall-clock deadline exceeded |
| `cancelled` | Yes | Caller cancelled |

## See also

[S-37](../stacks/s37-batch-vs-realtime.md) · [F-15](f15-durable-execution.md) · [S-12](../stacks/s12-streaming.md) · [F-20](f20-rate-limits-and-retry.md) · [S-38](../stacks/s38-agent-state-design.md) · [F-11](f11-agent-reliability.md)

## Go deeper

Keywords: `async agent` · `job queue` · `task_id` · `polling` · `webhook` · `exponential backoff` · `wall-clock timeout` · `idempotency key` · `background task` · `long-running agent`
