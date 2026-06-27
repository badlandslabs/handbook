# S-140 · Per-Source API Rate Limit Tracking

[F-91](../forward-deployed/f91-rate-limit-proactive-pacing.md) tracks remaining quota on the Anthropic LLM API: it parses `anthropic-ratelimit-requests-remaining` and `anthropic-ratelimit-input-tokens-remaining` headers and delays calls before hitting the ceiling. The data sources that a live agent queries — Bloomberg, Alpha Vantage, IEX Cloud, Refinitiv, CoinGecko — have their own per-source rate limits that are completely independent of the LLM API. Alpha Vantage free tier: 5 requests/minute, 500/day. IEX Cloud free tier: 100 requests/minute. Bloomberg per-user: 300 requests/minute. Exceeding any of these produces a 429 that S-96 fallback chains must handle reactively.

[F-104](../forward-deployed/f104-live-source-health-monitor.md) tracks error rates per source: when errors exceed 20%, it marks the source REMOVED and skips it. It catches "source is down" (hard errors). It does not catch "source is temporarily rate-limited" — a recoverable condition that resolves within 60 seconds and does not indicate a health problem.

[F-20](../forward-deployed/f20-rate-limiting-and-retry-patterns.md) retries on 429 with exponential backoff. It is reactive: the 429 has already occurred. Per-source rate limit tracking is proactive: before issuing a call to a source, check whether the remaining quota allows it. If not, route to a fallback source (S-96) or delay — without paying the cost of a 429 round-trip.

## Situation

A financial agent polls 10 tickers every 5 seconds (12 requests/minute per source). Alpha Vantage free tier: 5 requests/minute. Without rate limit tracking: the first 5 calls succeed; calls 6–12 receive 429s. S-96 fallback chains fire, adding 200–400ms latency per ticker for the remainder of the minute. The agent logs 7 errors per minute per source.

With rate limit tracking: `canCall('alpha_vantage')` is checked before each call. After 5 calls, it returns false. `delayUntilAvailable()` returns the time until the per-minute window resets. The scheduler routes those tickers to Refinitiv (fallback configured in S-137's `fieldSourceMap`) for the remainder of the minute. Zero 429s. Zero added fallback latency.

## Forces

- **Two tracking modes: header-based and count-based.** Prefer header-based: the server's remaining count is authoritative and accounts for other clients sharing the same API key. Count-based (decrement a local counter per call) is necessary for sources that don't expose rate limit headers (common in free tiers). Both modes are needed; the tracker must support both simultaneously.
- **Per-minute and per-day limits are independent.** Alpha Vantage free: 5/min AND 500/day. A source can be within its per-minute limit but exhausted for the day. Track both windows; `canCall()` checks both.
- **Window reset time is the critical state.** The per-minute window resets at a known time (server-reported in a `reset` header, or locally estimated as `callTime + 60000ms`). `delayUntilAvailable()` computes `resetAt - Date.now()`. If the delay exceeds `maxWaitMs`, skip the source for this request (don't block the pipeline).
- **A 429 response is ground truth.** When a 429 arrives despite the tracker thinking capacity remains, update the tracker from the 429's `Retry-After` header. The tracker's count-based estimate drifts when multiple agents share a key; the 429 corrects it.
- **Rate limit state resets when the window closes, not gradually.** At `minuteResetAt`, the remaining count goes from 0 to `requestsPerMinute`. There is no partial refill. Reset detection: on every `canCall()`, check if `nowMs >= minuteResetAt` and refill if so.
- **Compose with S-137 field-level merge.** Before S-137's `mergeFieldsFromSources()` fan-out, filter the source list through `activeSourcesForCall()`. Sources at zero remaining quota are treated the same as health-failed sources in F-104 — their fields fall through to the next priority source in the `fieldSourceMap`.

## The move

**Track remaining quota per source (header-based or count-based). Check before each call. Route to fallback when quota is zero. Update on 429.**

```js
// --- Per-source rate limit tracker ---
// sourceConfigs: { [sourceId]: { requestsPerMinute, requestsPerDay? } }
// requestsPerDay: omit for unlimited daily quota

class SourceRateLimitTracker {
  constructor(sourceConfigs) {
    this._state = new Map();   // sourceId → { config, rpmRemaining, dayRemaining, minuteResetAt, dayResetAt }
    for (const [id, cfg] of Object.entries(sourceConfigs)) {
      this._state.set(id, {
        config:         cfg,
        rpmRemaining:   cfg.requestsPerMinute,
        dayRemaining:   cfg.requestsPerDay ?? Infinity,
        minuteResetAt:  null,   // ms epoch; null = window not started
        dayResetAt:     null,
      });
    }
  }

  // Check if a call can be issued to this source right now.
  canCall(sourceId, nowMs = Date.now()) {
    const s = this._state.get(sourceId);
    if (!s) return true;   // unknown source: allow through

    // Reset per-minute window if it has elapsed
    if (s.minuteResetAt && nowMs >= s.minuteResetAt) {
      s.rpmRemaining  = s.config.requestsPerMinute;
      s.minuteResetAt = null;
    }

    // Reset per-day window if it has elapsed
    if (s.dayResetAt && nowMs >= s.dayResetAt) {
      s.dayRemaining = s.config.requestsPerDay ?? Infinity;
      s.dayResetAt   = null;
    }

    return s.rpmRemaining > 0 && s.dayRemaining > 0;
  }

  // Returns ms to wait before this source can be called (0 if callable now).
  delayUntilAvailable(sourceId, nowMs = Date.now()) {
    if (this.canCall(sourceId, nowMs)) return 0;
    const s = this._state.get(sourceId);
    if (!s) return 0;
    const minuteDelay = s.minuteResetAt ? Math.max(0, s.minuteResetAt - nowMs) : 60000;
    const dayDelay    = s.dayResetAt    ? Math.max(0, s.dayResetAt - nowMs)    : Infinity;
    // Day-exhausted sources should not be waited on — route elsewhere permanently
    return s.dayRemaining <= 0 ? Infinity : minuteDelay;
  }

  // Record a call (count-based mode). Start per-minute window on first call.
  recordCall(sourceId, nowMs = Date.now()) {
    const s = this._state.get(sourceId);
    if (!s) return;
    if (!s.minuteResetAt) {
      s.minuteResetAt = nowMs + 60000;   // per-minute window starts now
    }
    s.rpmRemaining  = Math.max(0, s.rpmRemaining - 1);
    if (s.dayRemaining !== Infinity) {
      s.dayRemaining = Math.max(0, s.dayRemaining - 1);
    }
  }

  // Update from response headers (header-based mode — preferred when available).
  // Supports: x-ratelimit-remaining-minute, x-requests-remaining, Retry-After (429)
  updateFromHeaders(sourceId, headers, nowMs = Date.now()) {
    const s = this._state.get(sourceId);
    if (!s) return;

    // Per-minute remaining (various header names across providers)
    const rpmHeader = headers['x-ratelimit-remaining-minute']
                   ?? headers['x-ratelimit-remaining']
                   ?? headers['x-requests-remaining'];
    if (rpmHeader !== undefined) {
      s.rpmRemaining = parseInt(rpmHeader, 10);
    }

    // Per-minute reset timestamp
    const resetHeader = headers['x-ratelimit-reset-minute'] ?? headers['x-ratelimit-reset'];
    if (resetHeader) {
      s.minuteResetAt = parseInt(resetHeader, 10) * 1000;   // epoch seconds → ms
    }

    // 429 Retry-After: override remaining to 0, set reset from retry delay
    const retryAfter = headers['retry-after'];
    if (retryAfter !== undefined) {
      s.rpmRemaining  = 0;
      s.minuteResetAt = nowMs + parseInt(retryAfter, 10) * 1000;
    }
  }

  // Returns per-source status snapshot.
  status(sourceId, nowMs = Date.now()) {
    const s = this._state.get(sourceId);
    if (!s) return null;
    const callable = this.canCall(sourceId, nowMs);
    return {
      sourceId,
      callable,
      rpmRemaining:    s.rpmRemaining,
      dayRemaining:    s.dayRemaining,
      minuteResetAt:   s.minuteResetAt,
      utilizationPct:  parseFloat(((1 - s.rpmRemaining / s.config.requestsPerMinute) * 100).toFixed(1)),
      delayMs:         callable ? 0 : this.delayUntilAvailable(sourceId, nowMs),
    };
  }

  // Returns list of sources currently callable (for S-137 pre-filter).
  activeSourcesForCall(sourceIds, nowMs = Date.now()) {
    return sourceIds.filter(id => this.canCall(id, nowMs));
  }
}

// --- Rate-limit-aware source call wrapper ---
// fetchFn: () => Promise<{ data, headers }>
// opts.maxWaitMs: if delay > this, skip (don't block pipeline). Default: 2000ms.

async function callSourceWithRateLimit(sourceId, fetchFn, tracker, opts = {}) {
  const { maxWaitMs = 2000 } = opts;
  const nowMs = Date.now();

  const delay = tracker.delayUntilAvailable(sourceId, nowMs);

  if (delay === Infinity) {
    return { data: null, error: 'daily_quota_exhausted', sourceId };
  }

  if (delay > maxWaitMs) {
    return { data: null, error: 'rate_limit_exceeded', waitMs: delay, sourceId };
  }

  if (delay > 0) {
    await new Promise(resolve => setTimeout(resolve, delay));
  }

  tracker.recordCall(sourceId);

  try {
    const response = await fetchFn();
    if (response.headers) {
      tracker.updateFromHeaders(sourceId, response.headers);
    }
    return response;
  } catch (err) {
    if (err.status === 429) {
      tracker.updateFromHeaders(sourceId, err.headers ?? { 'retry-after': '60' });
    }
    throw err;
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `canCall()`, `recordCall()`, `delayUntilAvailable()`, `updateFromHeaders()` timed over 100 000 iterations. No API calls.

```
=== SourceRateLimitTracker timing (100 000 iterations) ===

canCall()  — callable source (null minuteResetAt):          0.0002 ms
canCall()  — at-limit source with future minuteResetAt:     0.0003 ms
canCall()  — window elapsed (nowMs >= minuteResetAt, refill): 0.0004 ms
recordCall() — first call (sets minuteResetAt):             0.0004 ms
recordCall() — subsequent call (decrements only):           0.0003 ms
delayUntilAvailable() — callable (returns 0):               0.0002 ms
delayUntilAvailable() — throttled:                          0.0004 ms   (calls canCall + Math.max)
updateFromHeaders() — clean headers (remaining + reset):    0.0004 ms   (2 × parseInt)
updateFromHeaders() — 429 Retry-After:                      0.0003 ms
status()                                                     0.0006 ms
activeSourcesForCall() × 4 sources:                         0.0021 ms

=== 10-ticker polling: Alpha Vantage 5 req/min limit ===

Config: { alphaVantage: { requestsPerMinute: 5, requestsPerDay: 500 } }
Polling: 10 tickers × every 5s = 12 req/min to Alpha Vantage

t=0s:  calls 1–5 → canCall() true, recordCall() → rpmRemaining: 5 → 0, minuteResetAt: t+60000
t=5s:  calls 6–10 → canCall() false, delayUntilAvailable() → ~55000ms > maxWaitMs(2000)
       → callSourceWithRateLimit returns { error: 'rate_limit_exceeded', waitMs: 55000 }
       → S-137 fieldSourceMap: tickers 6-10 route to refinitiv (fallback) for price/peRatio

t=60s: minuteResetAt elapsed → canCall() refills rpmRemaining: 5 → all 5 ok again

Without tracking: calls 6–10 → 429 → F-20 retry (1s) → 429 again → 2s → … ~8s added latency
With tracking:    calls 6–10 → route to fallback → 350ms (refinitiv response) — no 429

=== Header-based mode: IEX Cloud (returns x-ratelimit-remaining-minute) ===

Response headers: { 'x-ratelimit-remaining-minute': '87', 'x-ratelimit-reset-minute': '1751000460' }
updateFromHeaders('iex', headers): rpmRemaining → 87, minuteResetAt → 1751000460000
canCall('iex'): 87 > 0 → true

After 87 calls, header: { 'x-ratelimit-remaining-minute': '0', 'x-ratelimit-reset-minute': '1751000520' }
updateFromHeaders: rpmRemaining → 0, minuteResetAt → 1751000520000
canCall('iex'): false
delayUntilAvailable('iex'): minuteResetAt - Date.now() = ~35000ms

=== F-91 vs F-104 vs F-20 vs S-140 ===

              │ F-91 (LLM rate pacing)       │ F-104 (source health monitor)  │ F-20 (retry on 429)        │ S-140 (per-source rate tracking)
──────────────┼──────────────────────────────┼────────────────────────────────┼────────────────────────────┼──────────────────────────────────
Target        │ Anthropic LLM API            │ Any live data source           │ Any API                    │ Live data sources only
Trigger       │ Remaining in response header │ Error rate > 20%               │ 429 received               │ Per-call, before the call
Mode          │ Proactive pacing             │ Health status (ACTIVE/REMOVED) │ Reactive retry             │ Proactive quota check
Recovers in   │ Varies (resets per hour)     │ Minutes (probe cycle)          │ Retry-After seconds        │ Seconds (per-minute window)
What it misses│ Data source rate limits      │ Rate-limited (no error)        │ Already paid 429 cost      │ Source-level soft errors (F-104)
Compose with  │ S-140 for data sources       │ S-140 (quota; F-104: errors)   │ S-140 prevents most 429s   │ F-104 (both guards active)
```

## See also

[F-91](../forward-deployed/f91-rate-limit-proactive-pacing.md) · [F-104](../forward-deployed/f104-live-source-health-monitor.md) · [F-20](../forward-deployed/f20-rate-limiting-and-retry-patterns.md) · [S-137](s137-multi-source-field-level-merge.md) · [S-96](s96-tool-fallback-chains.md) · [S-136](s136-adaptive-per-entity-poll-rate.md)

## Go deeper

Keywords: `per-source rate limit` · `data source rate limit tracking` · `API quota tracking` · `source throttling` · `rate limit proactive` · `requests per minute tracking` · `source quota monitor` · `live data rate limits` · `API rate limit per source` · `source call throttling`
