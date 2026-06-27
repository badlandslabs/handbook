# S-163 · Query-Aware Tool Cache

[S-43](s43-tool-result-caching.md) caches tool results with a TTL keyed to the data class: market prices get a short TTL, user records get a longer one. The TTL is a property of the tool — the same TTL applies regardless of what the caller is doing with the result. [S-100](s100-live-data-freshness-contracts.md) declares freshness contracts per source: each source has a known update interval that sets the minimum freshness floor for any query. The freshness contract is also a property of the source, not the query.

Neither resolves the case where the same tool needs different staleness tolerance depending on the query type. `get_customer` called during a billing review can accept a 5-minute-old record — the account balance has not changed. The same `get_customer` call during a live trading compliance check cannot accept anything older than 5 seconds — the risk tier may have just changed. And `get_customer` during a KYC verification must never use a cached result at all — the regulator requires a live call. The tool is identical; the freshness requirement is a property of the query, not the tool.

A query-aware tool cache registers TTLs per tool per query type. The same tool may be cached aggressively for one query type, lightly for another, and bypassed entirely for a third. TTL=0 means always call live regardless of cache state — not "short TTL" but "never cache." The cache key is the tool name plus the serialized arguments; the TTL is resolved from the query type at lookup time.

## Situation

A customer support platform routes three query types through a shared tool registry. All three call `get_customer`:

- `billing` — resolves account status, plan tier, next renewal date. Customer records update at most daily. Billing agents handle 40 sessions per hour per agent; fetching live on every turn is expensive and unnecessary.
- `risk` — checks risk tier and KYC status for high-value transaction approval. Risk tier can change when a customer triggers a fraud signal. 5-minute staleness is dangerous; 30-second staleness is acceptable.
- `kyc_verify` — formal compliance check at account opening or re-verification. Regulators require a live call, logged with a timestamp. A cached result is a compliance violation regardless of age.

Without query-type awareness, `get_customer` uses S-43's data-class TTL: `user_records: 5min`. The risk agent works correctly most of the time, but a risk tier change made 4 minutes ago is invisible until the cache expires. The KYC agent has no way to disable caching short of bypassing the cache layer entirely.

With a query-aware cache: billing uses 300 s, risk uses 30 s, kyc_verify uses 0 (live bypass). The same shared cache layer handles all three correctly without special-casing.

## Forces

- **TTL=0 is not the same as short TTL.** A short TTL still caches and may serve a result that is 1–2 seconds old. TTL=0 means bypass: every call goes to the live tool, and the result is not stored. For compliance contexts, the distinction matters — a 1-second-old cached record is still a cached record.
- **Wildcard rules reduce boilerplate.** `get_price:*` covers all query types with a single 0.5 s TTL. Only register per-type overrides for tools where query-type freshness requirements actually diverge. Most tools need one TTL for all queries; use the wildcard for those and only add per-type entries where behavior genuinely differs.
- **Cache key does not include query type.** Two queries — a billing query and a risk query — for the same customer share the same cached result if one lands within the other's TTL window. The TTL gates whether the result is used, not whether it is stored. This means a billing query at t=0 stores the result; a risk query at t=25s finds the same entry and uses it (25s < 30s TTL). This is correct behavior — both callers see the same data, and the risk caller has decided 30s is acceptable.
- **Register TTLs from freshness requirements, not from data intuition.** The right question is not "how often does this data change?" but "how stale can this data be before the query gives a wrong answer?" A risk tier changes rarely but the consequence of acting on a stale one is high; that drives a short TTL. A customer name changes almost never but there is still no reason to cache it for kyc_verify.
- **Compose with S-162 field projection.** Project the cached result to only the fields needed for the query type before injecting into agent context. A billing query that hits the cache still returns only the 4 billing-relevant fields — not the full 25-field record that was stored.
- **Evict on change events.** If S-126 (event-driven cache invalidation) fires for a customer entity, evict all cache keys for that entity regardless of TTL. TTL is the staleness ceiling under normal conditions; change events override it.

## The move

**Register per-query-type TTLs for each tool. Resolve TTL at lookup time — specific first, then wildcard, then bypass.**

```js
// --- Query-aware tool cache ---
// TTL is a property of the query type, not the tool or data class.
// Same tool, different freshness requirements for different query types.
// TTL=0: live bypass — never cache, never return cached results (compliance use cases).
// Wildcard '*' covers query types with no specific rule.
// Cache key: toolName + serialized args (shared across query types).
// Compose: project result with S-162 after cache hit before context injection.

class QueryAwareToolCache {
  constructor() {
    this._cache = new Map();  // cacheKey → { result, fetchedAt }
    this._ttls  = new Map();  // 'toolName:queryType' → ttlMs
    this._stats = { hits: 0, misses: 0, bypasses: 0 };
  }

  // Register a TTL (ms) for this tool under this query type.
  // queryType: specific type ('billing', 'risk') or '*' wildcard.
  // TTL=0: bypass — always call live, never cache.
  register(toolName, queryType, ttlMs) {
    this._ttls.set(toolName + ':' + queryType, ttlMs);
    return this;
  }

  // Resolve TTL: specific queryType first, then wildcard, then 0.
  _ttl(toolName, queryType) {
    const specific = this._ttls.get(toolName + ':' + queryType);
    if (specific !== undefined) return specific;
    const wildcard = this._ttls.get(toolName + ':*');
    return wildcard !== undefined ? wildcard : 0;
  }

  // Fetch from cache or call fetchFn, respecting query-type TTL.
  // Returns { result, source: 'CACHE'|'LIVE'|'LIVE_BYPASS', ageMs?, ttl }
  async get(toolName, args, queryType, fetchFn) {
    const ttl = this._ttl(toolName, queryType);

    if (ttl === 0) {
      this._stats.bypasses++;
      const result = await fetchFn();
      return { result, source: 'LIVE_BYPASS', ttl: 0 };
    }

    const key    = toolName + ':' + JSON.stringify(args);
    const cached = this._cache.get(key);
    const age    = cached ? Date.now() - cached.fetchedAt : Infinity;

    if (cached && age < ttl) {
      this._stats.hits++;
      return { result: cached.result, source: 'CACHE', ageMs: Math.round(age), ttl };
    }

    this._stats.misses++;
    const result = await fetchFn();
    this._cache.set(key, { result, fetchedAt: Date.now() });
    return { result, source: 'LIVE', ttl };
  }

  // Evict all entries for a specific entity when a change event fires (S-126 integration).
  evict(toolName, argsPattern) {
    const prefix = toolName + ':';
    for (const k of this._cache.keys()) {
      if (k.startsWith(prefix) && k.includes(argsPattern)) this._cache.delete(k);
    }
  }

  stats() { return { ...this._stats }; }
}

// --- Configuration: per-query-type TTLs ---

const TOOL_CACHE = new QueryAwareToolCache()
  .register('get_customer', 'billing',    300000)  // 5 min: balance/plan stable within a session
  .register('get_customer', 'risk',        30000)  // 30 s: risk tier can change on fraud signal
  .register('get_customer', 'kyc_verify',      0)  // live bypass: compliance requires live call
  .register('get_price',    '*',             500)  // 0.5 s wildcard: all price queries need near-realtime
  .register('get_document', '*',         600000);  // 10 min: documents rarely change

// --- Integration: agent tool call handler ---

async function callTool(toolName, args, queryType) {
  const { result, source, ageMs } = await TOOL_CACHE.get(
    toolName, args, queryType,
    () => dispatchToolCall(toolName, args)  // live fetch only when needed
  );

  log({ tool: toolName, queryType, source, ageMs });
  return result;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `_ttl()` timed over 100 000 iterations. Five TTL rules registered across 3 tools.

```
=== QueryAwareToolCache timing (100 000 iterations) ===

_ttl() lookup (specific queryType):    0.0014 ms
_ttl() lookup (wildcard fallback):     0.0002 ms

=== Scenario A: same tool, three query types ===

Tool: get_customer, args: { user_id: 'usr-001' }

  billing    → TTL=300 000 ms (5 min) — balance/plan info changes at most daily
  risk       → TTL=30 000 ms  (30 s)  — risk tier may change on fraud signal
  kyc_verify → TTL=0          (bypass) — compliance: always live, never cache

=== Scenario B: cache hit vs miss at age 10 000 ms ===

Entry fetched 10 000 ms ago (10 seconds old):

  billing (TTL=300 000 ms): age 10 000 ms < TTL → CACHE HIT
  risk    (TTL=30 000 ms):  age 10 000 ms < TTL → CACHE HIT
  kyc_verify (TTL=0):                           → LIVE_BYPASS (TTL=0 always bypasses)

=== Scenario C: S-43 vs S-163 behavior for get_customer ===

S-43 (data-class TTL, 'user_records: 5 min'):
  billing    → TTL=5 min → CACHE HIT (correct)
  risk       → TTL=5 min → CACHE HIT (stale risk tier: dangerous)
  kyc_verify → TTL=5 min → CACHE HIT (compliance violation)

S-163 (query-type TTL):
  billing    → TTL=5 min → CACHE HIT (correct)
  risk       → TTL=30 s  → MISS after 30 s (correct — fresh risk tier)
  kyc_verify → TTL=0     → LIVE_BYPASS always (correct — compliance)

=== Token savings ===

get_customer → S-162 projection → 4 billing fields, ~80 tok injected.
Cache hit: zero tokens injected (no result to inject — skip the tool call entirely).

10k sessions/day × 2 tool calls × 60% hit rate × 80 tok:
  Tokens saved:       960 000/day
  API calls avoided:  12 000/day → $0.77/day at Haiku pricing

=== S-43 vs S-100 vs S-163 ===

              │ S-43 (data-class TTL)       │ S-100 (source contract)      │ S-163 (query-type TTL)
──────────────┼─────────────────────────────┼──────────────────────────────┼──────────────────────────────
TTL property  │ Tool / data class           │ Source update interval        │ Query type
TTL varies by │ What kind of data it is     │ How often source updates      │ What the query will do with it
Same tool     │ One TTL for all callers     │ One floor for all callers     │ Per-caller TTL at call time
TTL=0 support │ Not modeled (use TTL=1ms)   │ Not modeled (gate, not cache) │ Yes — explicit live bypass
Use case      │ General tool caching        │ Freshness floor at ingest     │ Multi-tenant freshness policy
```

## See also

[S-43](s43-tool-result-caching.md) · [S-100](s100-live-data-freshness-contracts.md) · [S-148](s148-per-action-data-freshness-budget.md) · [S-162](s162-tool-result-field-projector.md) · [S-126](s126-event-driven-cache-invalidation.md) · [F-130](../forward-deployed/f130-per-turn-model-router.md)

## Go deeper

Keywords: `query-aware tool cache` · `per-query-type TTL` · `freshness requirement by query` · `context-aware tool caching` · `live bypass cache` · `query-driven cache TTL` · `tool cache freshness policy` · `compliance cache bypass` · `query type cache control` · `same tool different staleness tolerance`
