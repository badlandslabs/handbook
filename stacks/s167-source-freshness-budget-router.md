# S-167 · Source Freshness Budget Router

[S-102](s102-composable-agent-data-layers.md) structures data access as three tiers — static KB, near-realtime cache, live API — and routes queries to the cheapest tier that meets the freshness requirement. The three tiers are architecturally different (vector search, Redis, external REST); S-102 does not model the case where multiple live API providers supply the same data. [S-147](s147-entity-source-priority-override.md) stores per-entity source priority lists as manual configuration — it expresses preference rules, not freshness-budget optimization. [S-96](s96-tool-fallback-chains.md) falls back on error or timeout — availability routing, not freshness-cost selection.

In practice, a system often has multiple providers of the same data type: Bloomberg, Reuters, and IEX all provide equity prices. Bloomberg updates within 50ms, charges $0.0002/call. Reuters updates within 200ms, charges $0.0001/call. IEX updates within 500ms, charges $0.00003/call. For a `billing` query that accepts data up to 5 minutes old, all three meet the budget — but IEX is 6.7× cheaper than Bloomberg. For a `trade` query that requires data no older than 100ms, only Bloomberg meets the requirement.

A source freshness budget router registers providers of the same data type with their maximum delay guarantee and cost. Given a query's freshness budget (`maxAgeMs`), it selects the cheapest provider whose guarantee meets the budget. The list is sorted cheapest-first; the first match wins. If no provider meets the budget, it returns the freshest available with a `BEST_AVAILABLE_OVER_BUDGET` flag — the caller decides whether to proceed or abort.

## Situation

A financial agent platform serves three query types on equity price data, each with a different freshness requirement:

- `billing` — generates account statements. Price data accurate to within 5 minutes is sufficient.
- `risk` — checks portfolio risk before a non-urgent alert. Price data must be within 30 seconds.
- `trade` — executes a limit order. Price data must be within 100ms or the order is mispriced.

All three query types share the same tool (`get_equity_price`) and the same provider pool (Bloomberg, Reuters, IEX). Without a router, every call uses Bloomberg — the fastest, but also 6.7× more expensive than IEX. Billing queries, which represent 80% of all calls, pay the Bloomberg rate unnecessarily.

With the freshness budget router: billing and risk queries route to IEX (maxDelay=500ms, well within 30s and 300s budgets). Trade queries route to Bloomberg (maxDelay=50ms, the only provider within the 100ms budget). At 10 000 price queries/day with an 80/20 billing-to-trade ratio, budget routing saves $1.36/day (68%) vs always using Bloomberg.

## Forces

- **Sort providers cheapest-first; iterate from the front.** The router returns the first provider whose maxDelay is within budget. Sorting cheapest-first ensures that when multiple providers meet the budget, the cheapest wins without a second pass. A secondary sort by maxDelay (ascending) among tied-cost providers adds recency preference at no additional iteration cost.
- **maxDelayMs is the provider's SLA, not the observed latency.** Use the contractual maximum delay, not the p50 or p99 observed. The SLA is what the provider guarantees; observed latency is often better but never relied on as a ceiling. Register what you can depend on.
- **BEST_AVAILABLE_OVER_BUDGET requires a caller decision.** The router does not decide whether stale data is acceptable for this specific request — that is the caller's domain. For `trade` queries under HFT constraints, the right action on BEST_AVAILABLE may be to abort and log. For risk queries in degraded conditions, it may be acceptable to proceed with a disclosure. The router returns the flag; the caller acts.
- **Compose with S-100 freshness contracts per provider.** S-100 declares each source's update interval and minimum freshness floor. Pair each provider's `maxDelayMs` in S-167 with its S-100 freshness contract: the contract confirms that the API actually returns data fresher than `maxDelayMs`; the router selects which provider to call. S-167 selects; S-100 verifies.
- **Compose with S-148 per-action freshness budget.** S-148 checks whether data is fresh enough for a specific action after it has been fetched. S-167 selects the right provider before fetching. Run S-167 at the call layer (which source to use?), run S-148 at the action layer (is this fetched data fresh enough to act on?).
- **Re-sort when costs change.** Provider contracts change. Build the sorted list from a configuration object and expose a `reconfigure()` method. A cost change from IEX (from $0.00003 to $0.0001) that puts it above Reuters in cost should re-sort the list automatically on the next configuration reload.

## The move

**Sort providers cheapest-first. Select the first whose maxDelay fits the freshness budget. Return BEST_AVAILABLE if none qualifies.**

```js
// --- Source freshness budget router ---
// Register providers of the same data type sorted by cost (cheapest first).
// select(toolName, maxAgeMs) → cheapest provider whose maxDelayMs <= maxAgeMs.
// BEST_AVAILABLE_OVER_BUDGET: no provider meets budget — return freshest with flag.
// Compose: S-167 selects provider → S-100 verifies freshness → S-148 checks action-level budget.

class SourceFreshnessBudgetRouter {
  constructor() {
    this._sources = new Map();  // toolName → [{name, maxDelayMs, costPerCall}] sorted cheapest first
  }

  // Register providers for a tool. Sources are sorted cheapest-first automatically.
  // maxDelayMs: provider's SLA — the maximum delay from event to API availability.
  // costPerCall: cost in USD per call.
  register(toolName, sources) {
    const sorted = sources.slice().sort(function(a, b) {
      if (a.costPerCall !== b.costPerCall) return a.costPerCall - b.costPerCall;
      return a.maxDelayMs - b.maxDelayMs;  // tie-break: fresher first among same cost
    });
    this._sources.set(toolName, sorted);
    return this;
  }

  // Select the cheapest provider whose maxDelayMs is within the freshness budget.
  // Returns { source, reason: 'BUDGET_MET' | 'BEST_AVAILABLE_OVER_BUDGET' | 'NO_SOURCES_REGISTERED' }
  select(toolName, maxAgeMs) {
    const sources = this._sources.get(toolName);
    if (!sources || sources.length === 0) {
      return { source: null, reason: 'NO_SOURCES_REGISTERED' };
    }
    for (let i = 0; i < sources.length; i++) {
      if (sources[i].maxDelayMs <= maxAgeMs) {
        return { source: sources[i], reason: 'BUDGET_MET' };
      }
    }
    // No source meets budget — return the freshest available
    const freshest = sources.reduce(function(a, b) {
      return a.maxDelayMs < b.maxDelayMs ? a : b;
    });
    return { source: freshest, reason: 'BEST_AVAILABLE_OVER_BUDGET' };
  }

  sources(toolName) { return this._sources.get(toolName) || []; }
}

// --- Configuration ---

const PRICE_ROUTER = new SourceFreshnessBudgetRouter()
  .register('get_equity_price', [
    { name: 'bloomberg', maxDelayMs:  50,  costPerCall: 0.0002  },
    { name: 'reuters',   maxDelayMs:  200, costPerCall: 0.0001  },
    { name: 'iex',       maxDelayMs:  500, costPerCall: 0.00003 },
  ]);

// --- Integration: tool call handler ---

async function getEquityPrice(ticker, queryType) {
  const freshnessBudgets = { billing: 300000, risk: 30000, trade: 100 };
  const maxAgeMs = freshnessBudgets[queryType] || 30000;

  const { source, reason } = PRICE_ROUTER.select('get_equity_price', maxAgeMs);

  if (reason === 'BEST_AVAILABLE_OVER_BUDGET') {
    if (queryType === 'trade') return { error: 'NO_FRESH_SOURCE', source: source.name };
    log({ event: 'stale_source_used', queryType, source: source.name, maxAgeMs });
  }

  const data = await callProvider(source.name, 'price', { ticker });
  return { data, source: source.name, costUsd: source.costPerCall };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `select()` timed over 100 000 iterations on a 3-provider pool.

```
=== SourceFreshnessBudgetRouter timing (100 000 iterations) ===

select() — cheapest wins (IEX):   0.0001 ms
select() — only Bloomberg fits:    0.0001 ms
select() — BEST_AVAILABLE:         0.0002 ms

=== Sources registered: get_equity_price (sorted cheapest first) ===

  iex:       maxDelay=  500ms  cost=$0.00003/call
  reuters:   maxDelay=  200ms  cost=$0.00010/call
  bloomberg: maxDelay=   50ms  cost=$0.00020/call

=== Query scenarios ===

billing  (maxAgeMs=300 000ms) → iex ($0.00003/call)  [BUDGET_MET]    — 500ms < 300 000ms
risk     (maxAgeMs= 30 000ms) → iex ($0.00003/call)  [BUDGET_MET]    — 500ms <  30 000ms
trade    (maxAgeMs=     100ms) → bloomberg ($0.00020/call) [BUDGET_MET] — 50ms < 100ms
hft      (maxAgeMs=      10ms) → bloomberg ($0.00020/call) [BEST_AVAILABLE_OVER_BUDGET] — 50ms > 10ms

=== Cost savings: 10 000 price queries/day, 80% billing, 20% trade ===

Always Bloomberg:  10 000 × $0.0002 = $2.00/day
Budget-routed:     8 000 × $0.00003 (IEX) + 2 000 × $0.0002 (Bloomberg) = $0.64/day
Savings:           $1.36/day (68%)

=== S-96 vs S-102 vs S-147 vs S-167 ===

              │ S-96 (fallback chain)       │ S-102 (composable tiers)    │ S-147 (entity override)       │ S-167 (freshness budget router)
──────────────┼─────────────────────────────┼─────────────────────────────┼───────────────────────────────┼────────────────────────────────────
Selection     │ Error/timeout triggered     │ Data type (KB vs cache vs API)│ Manual per-entity config      │ Freshness budget + cost optimization
Providers     │ Different implementations   │ Different tier types         │ Same or different, per-entity  │ Equivalent providers, same data type
Trigger       │ Failure in primary          │ Cache miss / staleness       │ Entity-specific rules          │ Query's maxAgeMs budget
Cost model    │ Not modeled                 │ Tier cost comparison         │ Not modeled                    │ Explicit per-provider cost per call
```

## See also

[S-100](s100-live-data-freshness-contracts.md) · [S-148](s148-per-action-data-freshness-budget.md) · [S-102](s102-composable-agent-data-layers.md) · [S-163](s163-query-aware-tool-cache.md) · [S-96](s96-tool-fallback-chains.md)

## Go deeper

Keywords: `source freshness budget router` · `provider freshness selection` · `cheapest source freshness` · `data provider cost selection` · `multi-provider freshness routing` · `freshness budget source selection` · `equivalent source routing` · `cost-freshness tradeoff` · `provider tier selection` · `live data provider cost optimization`
