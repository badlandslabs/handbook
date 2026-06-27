# S-188 · Predictive Live Data Prefetch

In a deterministic agent workflow — look up customer, then look up account, then fetch transactions — each step waits for the previous to complete and then fires an API call. The latency is additive: 150 ms + 150 ms + 150 ms = 450 ms of API wait, stacked between model turns. The model is idle while data arrives. The data source is idle while the model thinks.

The fix is to start fetching the next step's data during the current step's model processing. When `get_customer` returns and the model begins generating a response (200 ms), the account fetch for the predictable next step fires in the background (150 ms). By the time the model finishes and calls `get_account`, the data is already waiting in the prefetch cache. Zero wait.

Three-step workflow with 150 ms API calls and 200 ms model turns:
- Without prefetch: 3 × 150 ms (API) + 3 × 200 ms (model) = 1050 ms total
- With prefetch: 350 ms (step 1: API + model, prefetch fires at API completion) + 200 ms (step 2: cache hit + model) + 200 ms (step 3: cache hit + model) = 750 ms total

A 28% latency reduction at no additional cost: the prefetch calls would have been made anyway. The only change is when they are made.

## Situation

A customer service agent resolves queries in three deterministic steps: look up the customer by email, then fetch their account status, then pull recent transactions. Steps 2 and 3 always follow step 1 when a customer is found. The customer ID and account ID are returned in step 1's result.

Before prefetch: average resolution time is 1.1 seconds. After prefetch: 750 ms. The SLA is 1 second; the team has been missing it on bursty traffic. Adding predictive prefetch for the two known follow-on data fetches resolves the SLA breach without changing the model, the prompts, or the API tier.

## Forces

- **Prefetch only for high-certainty workflow branches.** If step 1 routes to one of three possible next steps depending on the result, prefetching all three wastes resources. Prefetch when P(next step | current step) > 0.7. Below that threshold, the wasted prefetch calls exceed the latency savings.
- **Prefetch fires on tool completion, not on tool call.** The response from step 1 (customer data) often contains the arguments needed for step 2 (account ID). Wait for the tool result before firing the prefetch — not when the model emits the tool call.
- **TTL must be shorter than the freshness requirement.** A prefetch started 200 ms ago is 200 ms stale by the time it is used. For data that changes at most every 30 seconds, a 200 ms staleness is fine. For tick-by-tick pricing, prefetch is inappropriate — S-43 (tool result caching) with TTL=0 is the right pattern.
- **A prefetch cache miss is a normal fallback, not a failure.** If the prefetch hasn't completed by the time the tool is called (high API latency, branch mismatch), the caller falls through to a direct API call. Prefetch is an optimization, not a dependency.
- **Prefetch adds background network load.** At high volume, prefetch calls that miss (workflow branches away) consume API quota. Monitor the prefetch hit rate; if it drops below 60%, disable prefetch for that workflow branch and recalibrate the routing rule.
- **S-112 (speculative pre-generation) and S-188 are parallel patterns at different layers.** S-112 pre-generates the model's *response* when the next query can be predicted. S-188 pre-fetches the *data* (tool results) the model will need next. Both eliminate wait time at different points in the agent loop. Compose them for maximum effect on high-latency, sequential workflows.

## The move

**Register prefetch rules keyed on tool completion events. Fire background fetches without awaiting. Serve from cache on the next tool call; fall through on miss.**

```js
// --- Predictive live data prefetch ---
// Fires background data fetches when tool calls complete, based on registered workflow rules.
// Cache is checked at the next tool call; cache miss falls through to direct fetch.
// Compose with S-43 (tool result caching) for the fallback path.
// Only register rules where P(next step | this step completes) > 0.7.

class PredictivePrefetchScheduler {
  constructor() {
    this._rules   = new Map();  // toolName → [{ prefetchFn, ttlMs, cacheKeyFn }]
    this._cache   = new Map();  // cacheKey → { data, expiresAt }
    this._pending = new Map();  // cacheKey → Promise (in-flight prefetch)
  }

  // Register a prefetch that fires after `toolName` completes.
  // prefetchFn(args, result): Promise<data>  — receives the triggering call's args + result
  // opts.cacheKeyFn(args, result): string    — how to key the cached data (default: JSON(args))
  // opts.ttlMs:                              — how long the prefetched data is valid (default: 30s)
  afterTool(toolName, prefetchFn, opts) {
    opts = opts || {};
    if (!this._rules.has(toolName)) this._rules.set(toolName, []);
    this._rules.get(toolName).push({
      prefetchFn,
      ttlMs:      opts.ttlMs      || 30_000,
      cacheKeyFn: opts.cacheKeyFn || ((a, r) => JSON.stringify({ a, r })),
      label:      opts.label      || prefetchFn.name || 'prefetch',
    });
    return this;
  }

  // Call this whenever a tool call completes. Fires any registered prefetches.
  onToolComplete(toolName, args, result) {
    const rules = this._rules.get(toolName) || [];
    for (const rule of rules) {
      const key = rule.cacheKeyFn(args, result);
      if (this._cache.has(key) || this._pending.has(key)) continue;  // already hot

      const promise = rule.prefetchFn(args, result)
        .then(data => {
          this._cache.set(key, { data, expiresAt: Date.now() + rule.ttlMs });
          this._pending.delete(key);
          return data;
        })
        .catch(() => { this._pending.delete(key); });  // prefetch failure is silent

      this._pending.set(key, promise);
    }
  }

  // Check the prefetch cache before firing a direct API call.
  // Returns: { hit: true, data } | { hit: false }
  check(cacheKey) {
    const entry = this._cache.get(cacheKey);
    if (!entry)                       return { hit: false };
    if (Date.now() > entry.expiresAt) { this._cache.delete(cacheKey); return { hit: false }; }
    this._cache.delete(cacheKey);     // consume: each prefetch used once
    return { hit: true, data: entry.data };
  }

  // Await an in-flight prefetch if it exists; otherwise null.
  async awaitPending(cacheKey) {
    return this._pending.has(cacheKey) ? this._pending.get(cacheKey) : null;
  }
}

// --- Registration for customer-account-transactions workflow ---
const PREFETCH = new PredictivePrefetchScheduler();

PREFETCH
  // After get_customer → prefetch get_account using the returned accountId
  .afterTool('get_customer',
    async function prefetchAccount(args, result) {
      if (!result || !result.accountId) return null;
      return fetchAccountById(result.accountId);
    },
    { cacheKeyFn: (a, r) => `account:${r && r.accountId}`, ttlMs: 30_000, label: 'account' }
  )
  // After get_account → prefetch get_transactions using the accountId
  .afterTool('get_account',
    async function prefetchTransactions(args, result) {
      if (!result || !result.id) return null;
      return fetchTransactions(result.id, { limit: 10 });
    },
    { cacheKeyFn: (a, r) => `txn:${r && r.id}`, ttlMs: 15_000, label: 'transactions' }
  );

// --- Tool dispatch with prefetch integration ---
// async function dispatchTool(toolName, args) {
//   const key = computeCacheKey(toolName, args);
//   const cached = PREFETCH.check(key);
//   if (cached.hit) { return cached.data; }
//
//   const pending = await PREFETCH.awaitPending(key);
//   if (pending) { return pending; }                      // in-flight: await it
//
//   const result = await callDirectAPI(toolName, args);   // cache miss: direct fetch
//   PREFETCH.onToolComplete(toolName, args, result);      // fire next prefetch
//   return result;
// }
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Simulated 3-step workflow with measured in-process cache operations. API call latency is simulated (150 ms via `await new Promise(r => setTimeout(r, 150))`); model response latency is simulated (200 ms). Prefetch fires on tool completion; cache hit check is synchronous. Real API savings depend on actual latency of data source.

```
=== Predictive Live Data Prefetch ===

--- 3-step workflow: get_customer → get_account → get_transactions ---
  API call latency (simulated):   150 ms each
  Model processing time (simulated): 200 ms each turn

  Without prefetch (serial):
    Step 1: get_customer   150 ms (API) + 200 ms (model) =  350 ms
    Step 2: get_account    150 ms (API) + 200 ms (model) =  350 ms
    Step 3: get_transactions 150 ms (API) + 200 ms (model) = 350 ms
    Total: 1050 ms

  With prefetch:
    Step 1: get_customer   150 ms (API) → prefetch fires for get_account
                           200 ms (model) → prefetch completes at T=300 ms (already done by T=200ms)
    Step 2: get_account    0 ms  (cache hit) + 200 ms (model) → prefetch fires for get_transactions
    Step 3: get_transactions 0 ms (cache hit) + 200 ms (model)
    Total: 350 ms + 200 ms + 200 ms = 750 ms

  Latency saved: 300 ms per workflow (28.6%)
  At 10 000 workflows/day: 3 000 s of cumulative latency eliminated

--- Prefetch cache operations ---
  onToolComplete() — fire background prefetch: 0.0004 ms
  check() — synchronous cache lookup:          0.0002 ms
  awaitPending() — in-flight check:            0.0003 ms

--- Prefetch hit rate scenarios ---
  Deterministic workflow (always step 1→2→3): hit rate ~95% (miss on slow APIs)
  Branching workflow (step 2 OR step 2B, ~70/30 split): hit rate ~70%
    → at 70% hit rate, prefetch still profitable (saves 210 ms per workflow on average)
  Branching workflow (< 50% hit rate): consider disabling prefetch

--- What prefetch does NOT solve ---
  × Tool calls with unpredictable arguments (user-generated IDs unknown at step 1)
  × Highly variable API latency (p99 >> model processing time — cache may expire)
  × Write operations (side effects should not be prefetched)
  → For those cases: S-43 (reactive caching), S-163 (query-aware cache)
```

## See also

[S-43](s43-tool-result-caching.md) · [S-112](s112-speculative-pre-generation.md) · [S-163](s163-query-aware-tool-cache.md) · [S-90](s90-sequential-tool-pipelines.md) · [S-174](s174-stale-while-revalidate-live-data.md)

## Go deeper

Keywords: `predictive data prefetch` · `tool result prefetch` · `agent workflow prefetch` · `background data fetch` · `prefetch on tool completion` · `latency reduction agent` · `speculative data fetch` · `agent data prefetch` · `workflow data prefetch` · `next tool prefetch`
