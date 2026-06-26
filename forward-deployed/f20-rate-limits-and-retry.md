# F-20 · Rate Limits and Retry Patterns

Every production agent hits a rate limit eventually — usually on its worst day, at its highest load, when the retry loop matters most. The pattern is not complicated, but getting it wrong is expensive: no retry loses work; unlimited retry burns budget and makes the provider's problem your problem. The pattern is exponential backoff with full jitter, a hard retry budget, and different handling for different HTTP status codes.

## Situation

Your agent starts failing at 3 am. The logs show a cascade of 429s. Someone added a retry loop that retries immediately with no backoff — now 50 requests per second are hammering the API, all failing, all burning tokens, all costing money. The agent isn't recovering; it's making the rate limit worse. A one-hour runaway costs over $100 in failed calls alone before anyone wakes up.

## Forces

- A 429 means "slow down" — retrying immediately tells the provider you didn't listen. Aggressive retry is the most reliable way to stay rate-limited longer.
- Pure exponential backoff (wait = base × 2^attempt) solves the "retry too fast" problem but creates a thundering herd: all clients that hit a 429 together will retry together at the same calculated interval, creating a coordinated spike that reproduces the original overload.
- Jitter (randomizing the wait within [0, cap]) breaks that coordination. Ten clients spread across a 2-second window look like ordinary traffic; ten clients hitting a single millisecond look like a DDoS.
- Not all HTTP errors are transient. Retrying a 400 (bad request) or 401 (auth failure) will never succeed — the problem is in your request, not the server's load. Retrying permanent failures burns budget and hides the root cause.
- A retry loop without a budget is a runaway. The agent will retry until context fills, a timeout fires, or an operator intervenes. At 50 requests per second, each burning 100 tokens, an hour of failure costs $109 in wasted API spend before a single successful call.
- Provider rate limit headers (`x-ratelimit-remaining-requests`, `retry-after`) are free real-time signals. Reading them is cheaper than learning from a 429.

## The move

**Full jitter exponential backoff:**
```
wait = random(0, min(cap, base × 2^attempt))
```
Base 1 second, cap 32 seconds covers most provider SLAs. Full jitter (uniform random in the whole range) outperforms decorrelated jitter and equal jitter at reducing coordinated retry spikes, as shown in the AWS "Exponential Backoff and Jitter" analysis.

**Hard retry budget per request:** 5 attempts for 429/503, 2 for 500, 0 for 400/401/403. After budget exhaustion, raise an exception — don't silently drop the request or loop forever.

**Route by status code, not by "error":**

| Code | Cause | Action |
|---|---|---|
| 429 | Rate limited | Backoff + jitter, max 5 retries; read `retry-after` header if present |
| 503 | Service unavailable | Backoff + jitter, max 3 retries |
| 500 | Server error | 1 retry after short delay, then escalate |
| 400 | Bad request | Do not retry — fix the request |
| 401 | Auth failure | Do not retry — alert and abort |
| 408/504 | Timeout | Retry with backoff; check idempotency first |

**Read the headers before you guess.** `retry-after: 5` tells you exactly when the provider will accept requests again — use it. `x-ratelimit-remaining-requests` lets you shed load proactively before the 429 arrives. Reading headers is free; learning from a 429 costs a failed call.

**Instrument the retry counter.** Log attempt number, wait duration, and final outcome for every retried call. A spike in retry counts is an early warning signal before errors surface to users — see [W-05](../workspace/w05-llmops-observability.md).

**Separate retry logic from business logic.** A retry decorator or middleware applied at the HTTP client layer is easier to test, audit, and tune than retry logic scattered across agent steps. One place, one policy.

## Receipt

> Verified 2026-06-26 — Node, deterministic seeded PRNG (no network calls). Thundering herd comparison: 10 simulated clients, attempt 1 after a 429. Runaway cost: 50 req/s × 100 tokens × $6.07/M (F-08, Q1'26). The retry schedule uses full-jitter implementation; actual wait times vary — the cap column is what's deterministic.

```
=== Thundering herd: 10 clients after shared 429 ===
No jitter:   all 10 clients retry at exactly 2000ms  (1 distinct time)
Full jitter: clients retry at [51–1989]ms  (~9 distinct 100ms buckets)

=== Retry schedule (base=1s, cap=32s, full jitter) ===
  attempt 1: wait   252ms  (cap=1s)
  attempt 2: wait   176ms  (cap=2s)
  attempt 3: wait  2309ms  (cap=4s)
  attempt 4: wait  1780ms  (cap=8s)
  attempt 5: wait  6010ms  (cap=16s)

=== Cost of runaway retry (no budget, 50 req/s all returning 429) ===
   1 min:   3,000 failed calls   $1.82 wasted
   5 min:  15,000 failed calls   $9.11 wasted
  60 min: 180,000 failed calls  $109.26 wasted
```

**What the receipt shows:**

- Without jitter, 10 clients retry at exactly 2000ms — one coordinated spike that reproduces the original overload. With full jitter, they spread across ~9 distinct 100ms buckets. Jitter converts a synchronized spike into ordinary traffic.
- The full-jitter schedule's early attempts can be surprisingly short (252ms, 176ms) while later attempts grow correctly. This is expected: jitter is uniform in [0, cap], so early caps are small and the range is tight. Average wait still grows exponentially.
- A runaway retry loop with no budget costs $109 in an hour on failed calls alone — before counting successful calls, tool costs, or the operator time to diagnose and fix it. The retry budget is not a nicety; it is a spending cap.

## See also

[F-11](f11-agent-reliability.md) · [F-15](f15-durable-execution.md) · [S-11](../stacks/s11-llm-gateway-fallback.md) · [W-05](../workspace/w05-llmops-observability.md) · [F-08](f08-agent-cost-control.md)

## Go deeper

Keywords: `exponential backoff` · `full jitter` · `thundering herd` · `429` · `rate limit` · `retry budget` · `retry-after header` · `x-ratelimit-remaining` · `transient vs permanent error` · `runaway retry`
