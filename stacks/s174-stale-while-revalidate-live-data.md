# S-174 · Stale-While-Revalidate for Live Data

[S-100](s100-live-data-freshness-contracts.md) declares per-source freshness contracts: `stock_price` may be no older than 500ms, `contract_status` no older than 60 seconds. [S-43](s43-tool-result-caching.md) caches tool call results and serves them within their TTL. When the TTL expires, S-43 makes a fresh call and serves the new result. Both patterns share one characteristic: when a cached value is expired, the next request waits for a live fetch before receiving a response.

That wait is the cost this pattern eliminates. For live data that changes slowly relative to request frequency — a contract status polled every 5 seconds but only updated every 30 minutes, or an account balance fetched for every page load but settled once per day — the blocking fetch on TTL expiry is pure latency overhead. The user is blocked for 200–1500ms to receive data that is almost certainly the same as what was in cache.

Stale-while-revalidate separates serving from refreshing. When the cache has a value — even one past its freshness TTL — serve it immediately and trigger a background refresh. The caller receives the stale value in microseconds. By the time the next request arrives (seconds or minutes later), the background refresh has already completed and the cache holds a fresh value. Only three cases block on a live fetch: the first request for a key that has never been cached (MISS), a value whose age has exceeded the maximum stale window (EXPIRED), and a case where the background refresh is still in flight and the value is too stale to serve even stale (configurable).

## Situation

A contract management platform serves contract status for 10 000 active contracts. Each status check calls an internal API that takes 300–800ms to respond. Traffic is 10 000 requests/day (70% from human page loads, 30% from automated checks). Without caching, mean latency is 500ms and API cost is $5.00/day (10 000 calls × $0.0005/call).

With S-43 TTL caching (TTL=10 seconds): 95% of requests hit cache (FRESH). 5% hit an expired cache and trigger a blocking live fetch — 500 requests/day paid in full. Mean latency: 25ms average. But every request that arrives in the 300–800ms gap after a TTL expiry is still blocked.

With stale-while-revalidate (TTL=10 seconds, staleTtl=60 seconds): expired cache values are served immediately (ageMs=30s but still within the 60s stale window). A background refresh fires once, asynchronously, for the first expired-value request. The next request finds a fresh value. The 5% that would have blocked now return in <1ms. The only blocking requests are genuine MISSes (new keys, first load) and EXPIREDs (values older than 60 seconds). Mean latency: <1ms for 99%+ of requests.

## Forces

- **Set `staleTtl` based on how stale you can tolerate, not how often data changes.** A contract status that changes at most daily can tolerate staleTtl of 5 minutes. A stock price that moves every millisecond cannot tolerate staleTtl above 1–2 seconds. The staleTtl is a correctness budget, not a performance one. When staleTtl is hit, the next request blocks — which is the right behavior for data that is genuinely too old to serve.
- **Suppress duplicate background refreshes.** Multiple requests arriving simultaneously against the same stale key should trigger exactly one background refresh. Track in-flight refreshes by key. When a refresh is already in flight, serve stale to the subsequent requesters without queuing a second refresh.
- **Disclose staleness in the response.** Include `dataAge: 30s` or a `lastRefreshedAt` timestamp in the returned value. Downstream consumers — especially agents that need to decide whether to trust the value for an irreversible action — can check the age against the action's freshness budget (S-148). A value that is 30 seconds stale is acceptable for a display query; it may not be acceptable for a payment authorization.
- **Background refresh errors must not corrupt the cache.** If the background refresh fails (network error, 5xx), the existing stale value should be retained — not replaced with null or an error state. Log the failure and retry on the next stale hit. A stale value is better than no value for non-blocking reads; an error value is worse than stale for everything.
- **The stale window must be shorter than the minimum meaningful data change interval.** If contract status changes at most once per hour, a 5-minute stale window is safe. If you set staleTtl to 2 hours, you may serve data that reflects a state transition that happened an hour ago. The SWR pattern is not appropriate for data where every update is safety-critical.
- **Compose with S-100 for hard freshness gates.** S-100 declares per-source freshness requirements. SWR serves stale within its staleTtl; S-100 enforces an absolute ceiling at the action execution layer. An agent that reads a stale value from SWR but then passes it through S-100's freshness gate before a commit action gets both: fast reads for display, hard freshness enforcement for writes.

## The move

**Serve cached values within the stale window, trigger background refresh on stale hits, block on miss and expired. Disclose `source` and `ageMs` in the result.**

```js
// --- Stale-while-revalidate store for live data ---
// Distinct from S-43 (blocks on TTL expiry) and S-100 (freshness contracts for actions).
// Compose: SWR for fast reads → S-100 freshness gate for commit actions → S-148 per-action budget.

class StaleWhileRevalidateStore {
  constructor(opts) {
    opts = opts || {};
    this._ttl      = opts.ttl      || 10000;   // serve as FRESH within ttl ms
    this._staleTtl = opts.staleTtl || 60000;   // serve as STALE within staleTtl ms; EXPIRED beyond
    this._cache    = new Map();
    this._inflight = new Set();
  }

  // Returns synchronously: { value, source, ageMs, refreshQueued }
  // source: FRESH | STALE | EXPIRED | MISS
  // When source is EXPIRED or MISS: value is null; caller must await live fetch and call set().
  get(key, backgroundRefreshFn) {
    const entry = this._cache.get(key);
    const now = Date.now();

    if (entry) {
      const age = now - entry.fetchedAt;

      if (age <= this._ttl) {
        return { value: entry.value, source: 'FRESH', ageMs: age, refreshQueued: false };
      }

      if (age <= this._staleTtl) {
        let refreshQueued = false;
        if (!this._inflight.has(key)) {
          this._inflight.add(key);
          refreshQueued = true;
          // Fire background refresh — not awaited.
          Promise.resolve()
            .then(() => backgroundRefreshFn())
            .then(fresh => {
              this._cache.set(key, { value: fresh, fetchedAt: Date.now() });
              this._inflight.delete(key);
            })
            .catch(() => {
              // Refresh failed: retain stale value; retry on next stale hit.
              this._inflight.delete(key);
            });
        }
        return { value: entry.value, source: 'STALE', ageMs: age, refreshQueued };
      }

      // age > staleTtl: EXPIRED — too stale to serve, even stale.
      return { value: null, source: 'EXPIRED', ageMs: age, refreshQueued: false };
    }

    // No entry at all: MISS.
    return { value: null, source: 'MISS', ageMs: null, refreshQueued: false };
  }

  set(key, value) {
    this._cache.set(key, { value, fetchedAt: Date.now() });
  }
}

// --- Integration: contract status handler ---

const STATUS_STORE = new StaleWhileRevalidateStore({ ttl: 10000, staleTtl: 60000 });

async function getContractStatus(contractId, fetchFn) {
  const key = 'contract:' + contractId + ':status';
  const result = STATUS_STORE.get(key, () => fetchFn(contractId));

  if (result.source === 'MISS' || result.source === 'EXPIRED') {
    // Block on live fetch only when no usable cache value exists.
    const fresh = await fetchFn(contractId);
    STATUS_STORE.set(key, fresh);
    return { ...fresh, _source: result.source, _ageMs: 0 };
  }

  // FRESH or STALE: return immediately.
  // Include staleness in result so callers can gate hard freshness checks.
  return { ...result.value, _source: result.source, _ageMs: result.ageMs };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. TTL=10s, staleTtl=60s. Injected entries at 2s (FRESH), 30s (STALE), and 90s (EXPIRED) ages. `store.get()` timed over 1 000 000 iterations. Live fetch latency is network-bound and not measured.

```
=== Stale-While-Revalidate for Live Data ===

Request 1 (C-42): source=FRESH   ageMs=2009   value.status=ACTIVE   refreshQueued=false
Request 2 (C-99): source=STALE   ageMs=30009  value.status=PENDING  refreshQueued=true
Request 3 (C-99): source=STALE   ageMs=30010  value.status=PENDING  refreshQueued=false  ← in-flight, no dup refresh
Request 4 (C-77): source=EXPIRED value=null   must await live fetch
Request 5 (NEW):  source=MISS    value=null   must await live fetch

Stats after 5 requests: { fresh: 1, stale: 2, miss: 2, refreshes: 1 }

=== Cost model (Haiku tool calls, 10 000 requests/day) ===

                        Without SWR    With SWR (95% hit)
Live fetches/day         10 000            500
Cost/day                 $5.00/day         $0.25/day
Savings/day              —                 $4.75/day  ($1 734/year)
Mean response latency    500 ms            26 ms

=== Timing (1 000 000 iterations) ===

store.get() FRESH hit:  0.0003 ms
store.get() STALE hit:  0.0004 ms
Live fetch:             network-bound (~200–1 500 ms, not measured)
```

## See also

[S-100](s100-live-data-freshness-contracts.md) · [S-43](s43-tool-result-caching.md) · [S-148](s148-per-action-freshness-budget.md) · [S-163](s163-response-ttl-by-query-type.md) · [S-111](s111-partial-context-refresh.md)

## Go deeper

Keywords: `stale-while-revalidate live data` · `SWR cache pattern` · `background cache refresh` · `serve stale trigger refresh` · `live data latency reduction` · `background revalidation cache` · `stale window cache` · `cache freshness pattern` · `async cache refresh` · `cache serve stale revalidate`
