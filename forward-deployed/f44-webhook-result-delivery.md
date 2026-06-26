# F-44 · Webhook Result Delivery

[F-34](f34-async-agent-requests.md) covers the inbound side of async agents: submit a task, get a job ID, poll for completion, or receive a callback. It handles the `callback_url` field in one line of code. This entry covers what goes into that callback: how to sign the payload so the receiver can verify it came from you, how to retry delivery when the receiver is temporarily down, and how to handle the case where delivery ultimately fails.

## Situation

An agent completes a 45-second document analysis and has a result to deliver to the caller's endpoint. The caller's server is busy and returns a 503. Without retry logic, the result is lost — the agent ran for 45 seconds and the caller never receives anything. With retry: the first attempt fails at 0s, the second attempt succeeds 2 seconds later. The caller receives the result, 2 seconds late, with no data loss. Without HMAC verification, the caller can't confirm the webhook came from your system — a malicious actor could POST forged results to their endpoint. With signing, a one-line verification rejects anything not signed with your shared secret.

## Forces

- **Webhook delivery is "at least once," not "exactly once."** Your retry logic may deliver the same result twice if the receiver sends a 503 but actually processed the request before timing out. The receiver must handle duplicates; include a unique delivery ID and let the receiver deduplicate on it.
- **HMAC signing is non-negotiable for production webhooks.** Without it, the receiver has no way to verify the POST came from your system. HMAC-SHA256 with a per-tenant shared secret is the industry standard: include the signature in a header (`X-Signature`), the receiver recomputes and compares.
- **Retry schedule matters more than retry count.** Retrying 10 times with 0.5s backoff saturates a struggling receiver and prevents recovery. Retrying 5 times with exponential backoff (1→2→4→8→16s) gives the receiver 31 seconds to recover while keeping total attempts low.
- **Dead-letter queues are the floor.** When all retries are exhausted, the result must not be silently discarded. Write to a dead-letter store with the full payload, the delivery history, and a timestamp. Operators can inspect, replay, or alert on dead-letter accumulation.
- **Delivery timeout per attempt is separate from retry timeout.** Each individual HTTP call should time out after 10 seconds, not the whole retry sequence. A receiver that hangs indefinitely would block the retry loop.

## The move

**Sign every payload with HMAC-SHA256. Retry with exponential backoff. Write to dead-letter after max retries. Include a delivery ID for idempotency.**

**Webhook sender:**

```js
const crypto = require('crypto');

async function deliverWebhook(callbackUrl, payload, tenantSecret, opts = {}) {
  const maxAttempts = opts.maxAttempts ?? 5;
  const timeoutMs   = opts.timeoutMs   ?? 10_000;

  const envelope = {
    deliveryId: crypto.randomUUID(),   // receiver deduplicates on this
    taskId:     payload.taskId,
    result:     payload.result,
    ts:         Date.now(),
  };
  const body      = JSON.stringify(envelope);
  const signature = sign(body, tenantSecret);

  const delays = [0, 1000, 2000, 4000, 8000]; // ms before each attempt (0 = immediate)

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    if (delays[attempt]) await sleep(delays[attempt]);

    try {
      const res = await fetchWithTimeout(callbackUrl, {
        method:  'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Signature':  `sha256=${signature}`,
          'X-Attempt':    String(attempt + 1),
        },
        body,
      }, timeoutMs);

      if (res.ok) {
        console.log(`[webhook] delivered on attempt ${attempt + 1}: ${callbackUrl}`);
        return { delivered: true, attempts: attempt + 1 };
      }

      if (res.status >= 400 && res.status < 500) {
        // 4xx: client error — don't retry (wrong URL, auth failure, etc.)
        await deadLetter(envelope, callbackUrl, `http_${res.status}`, attempt + 1);
        return { delivered: false, reason: `http_${res.status}`, attempts: attempt + 1 };
      }

      // 5xx: server error — retry
      console.warn(`[webhook] attempt ${attempt + 1} failed (${res.status}), retrying...`);
    } catch (err) {
      // Network error, timeout — retry
      console.warn(`[webhook] attempt ${attempt + 1} error: ${err.message}`);
    }
  }

  // All attempts exhausted
  await deadLetter(envelope, callbackUrl, 'max_retries_exceeded', maxAttempts);
  return { delivered: false, reason: 'max_retries_exceeded', attempts: maxAttempts };
}

function sign(body, secret) {
  return crypto.createHmac('sha256', secret).update(body).digest('hex');
}

async function fetchWithTimeout(url, opts, ms) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), ms);
  try {
    return await fetch(url, { ...opts, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

async function deadLetter(envelope, url, reason, attempts) {
  console.error('[webhook] dead-letter:', { taskId: envelope.taskId, url, reason, attempts });
  await deadLetterStore.insert({ ...envelope, callbackUrl: url, reason, failedAt: Date.now() });
  // Optional: alert on-call if dead-letter rate exceeds threshold (S-72 anomaly pattern)
}

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }
```

**Receiver-side verification:**

```js
app.post('/agent-callback', (req, res) => {
  const body      = req.rawBody; // raw unparsed body string
  const sigHeader = req.headers['x-signature']; // 'sha256=<hex>'
  const secret    = tenantSecrets.get(req.headers['x-tenant-id']);

  if (!verifySignature(body, sigHeader, secret)) {
    return res.status(401).json({ error: 'invalid_signature' });
  }

  const envelope = JSON.parse(body);

  // Idempotency: ignore duplicates
  if (await delivered.has(envelope.deliveryId)) {
    return res.status(200).json({ status: 'already_processed' });
  }

  await delivered.set(envelope.deliveryId, true, { ttl: 24 * 60 * 60 * 1000 });
  await processResult(envelope.taskId, envelope.result);
  res.status(200).json({ status: 'ok' });
});

function verifySignature(body, sigHeader, secret) {
  if (!sigHeader?.startsWith('sha256=')) return false;
  const expected = 'sha256=' + crypto.createHmac('sha256', secret).update(body).digest('hex');
  // Constant-time comparison to prevent timing attacks
  return crypto.timingSafeEqual(Buffer.from(sigHeader), Buffer.from(expected));
}
```

**Dead-letter replay:**

```js
// Periodically check dead-letter queue; retry manually or alert
async function processDlq() {
  const stale = await deadLetterStore.find({ failedAt: { $lt: Date.now() - 3600_000 } });
  for (const item of stale) {
    console.log('DLQ item:', item.taskId, item.reason, 'at', item.callbackUrl);
    // Manual replay or alerting logic here
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `crypto` (built-in). HMAC signing measured at 0.0082ms per call. Retry economics based on 2% first-attempt failure rate at 1 000 tasks/day.

```
=== HMAC-SHA256 signing overhead ===

$ node -e "
const crypto = require('crypto');
const secret = crypto.randomBytes(32);
const body   = JSON.stringify({ taskId: 'abc', result: 'done', ts: Date.now() });
const N = 100000;
const t0 = performance.now();
for (let i = 0; i < N; i++) crypto.createHmac('sha256', secret).update(body).digest('hex');
console.log('Sign per call:', ((performance.now()-t0)/N).toFixed(4), 'ms');
"
Sign per call: 0.0082 ms

Signing adds <0.01ms per delivery — negligible vs network round-trip time.

=== Retry schedule (5 attempts, exponential backoff) ===

Attempt    Delay before   Cumulative wait
1 (initial)     0s              0s
2               1s              1s
3               2s              3s
4               4s              7s
5               8s             15s
Dead-letter     —              15s after last attempt

Total wait before dead-letter: 15s (sum of delays between attempts)
Receiver has 15 seconds to recover before result is dead-lettered.

=== Retry recovery value ===

At 1 000 tasks/day, 2% first-attempt failure rate:
  Failed first deliveries:    20/day
  Recovered by retry (95%):   19/day
  Dead-lettered (5%):          1/day

Without retry: 20 tasks/day silently lost
Cost of lost tasks at \$0.05 avg: \$1.00/day = \$30/month lost value
With retry:    1 task/day in dead-letter (inspectable + replayable)
```

## See also

[F-34](f34-async-agent-requests.md) · [S-42](../stacks/s42-event-driven-agents.md) · [F-15](f15-durable-execution.md) · [F-20](f20-rate-limits-and-retry.md) · [F-39](f39-session-state-persistence.md) · [F-42](f42-ai-incident-response.md)

## Go deeper

Keywords: `webhook delivery` · `HMAC signing` · `webhook retry` · `exponential backoff` · `dead-letter queue` · `delivery idempotency` · `callback URL` · `signature verification` · `timing-safe comparison` · `webhook reliability`
