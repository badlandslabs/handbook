# S-165 · Derived Value Freshness Tracker

[S-100](s100-live-data-freshness-contracts.md) declares freshness contracts at the source level: a source's update interval sets the minimum freshness floor for any data it delivers. [S-148](s148-per-action-data-freshness-budget.md) checks whether data is fresh enough for a specific action before executing it — the check operates on the raw fetch timestamps of individual source fields. [S-163](s163-query-aware-tool-cache.md) uses TTL keyed to query type to decide whether to serve a cached result or call the source live.

None of these resolve the case where a value is computed from multiple live sources and the result is only as fresh as the stalest input. A `portfolio_risk_score` derived from `price_data` (fetched 5 seconds ago), `volatility_index` (fetched 12 seconds ago), and `credit_report` (fetched 310 seconds ago) has an effective freshness of 310 seconds — the age of its stalest component. A cache TTL on the derived value starts from when it was computed, not from when its inputs were fetched. If `credit_report` was already 15 seconds old at computation time, the derived value is 325 seconds old at t=310s, even though the cache TTL says 295s remain.

A derived value freshness tracker records, at composition time, the fetch timestamps of every source used to produce a derived value. On check, it computes the effective age as the age of the oldest source and returns FRESH, STALE, or UNKNOWN — along with which source was the stalest. The check is a Map lookup and subtraction: no network call, no token cost.

## Situation

A financial agent computes `portfolio_risk_score` from three live sources: equity prices (expected update: every 3s), volatility index (expected update: every 15s), and credit rating data (expected update: every 10 minutes). The score is recomputed only when sources change; between recomputations it is served from a 300-second cache.

Without derived freshness tracking: a `portfolio_risk_score` computed at t=0 with a 300s cache TTL is served as FRESH at t=295s. But if the `credit_report` used in the computation was already 25 seconds old at t=0, the credit component's age at t=295s is 320 seconds — past the 300s acceptability ceiling for the executor agent that uses this score to decide on trades. The cache says FRESH; the data says stale.

With derived freshness tracking: `record('portfolio_risk_score', [{name: 'credit_report', fetchedAtMs: <timestamp>}, ...])` at composition time. Before the executor acts, `check('portfolio_risk_score', 300000)` returns STALE with `stalestSource: 'credit_report'`. The executor triggers a targeted `credit_report` re-fetch and recomputes only that component, rather than recomputing the full score.

## Forces

- **Effective age is the max of source ages, not the age of the derived value.** A derived value's freshness is determined by its stalest input at the time it was computed, plus elapsed time since computation. A cache hit on the derived value does not imply the underlying sources were fresh when the cache was populated.
- **Record source fetch timestamps at composition time, not at check time.** By check time, the agent may no longer have access to the original source fetch times. The tracker must record `fetchedAtMs` when the derived value is first produced.
- **`stalestSource` drives targeted refresh.** When a check returns STALE, the caller should refresh only the stalest source and recompute only the parts of the derivation that depend on it — not recompute the full derived value from scratch. Log the stalest source name per STALE event for data refresh planning.
- **UNKNOWN means no composition record exists.** The derived key was never passed to `record()` — the value was not tracked. Treat UNKNOWN conservatively: either re-derive from live sources or reject the value. Do not treat UNKNOWN as FRESH.
- **Compose with S-148 for executor actions.** S-148 gates each action on the raw source freshness declared at the action level. S-165 gates on the composite freshness of derived values passed to the action. Both checks should run: S-165 first (catches stale derived values); S-148 second (catches stale raw sources injected directly into the action context).
- **Compose with S-163 query-type cache.** TTL controls whether the cache serves a result; S-165 controls whether the cached result's underlying data is still fresh enough. A cache HIT from S-163 that fails the S-165 derived freshness check should trigger a source refresh and recomputation, then re-cache.

## The move

**At composition time, record source fetch timestamps alongside the derived value. At check time, compute effective age as the stalest source's age.**

```js
// --- Derived value freshness tracker ---
// Records source fetch timestamps when a derived value is computed.
// On check: effective age = max(now - source.fetchedAtMs) across all sources.
// Returns FRESH | STALE | UNKNOWN with stalestSource identified.
// UNKNOWN: no record exists for this derived key — treat as stale.
// Compose: check() before injecting derived values into agent context.
//   Compose with S-163: S-163 controls cache reuse; S-165 controls underlying source freshness.
//   Compose with S-148: S-148 gates on raw sources; S-165 gates on derived values.

class DerivedValueFreshnessTracker {
  constructor() {
    this._records = new Map();  // derivedKey → { sources: [{name, fetchedAtMs}] }
    this._stats   = { checks: 0, fresh: 0, stale: 0 };
  }

  // Record the source fetch times used to compute a derived value.
  // Call at composition time, not at check time.
  // sources: [{ name: string, fetchedAtMs: number }]
  record(derivedKey, sources) {
    this._records.set(derivedKey, { sources });
    return this;
  }

  // Check whether the derived value is still fresh.
  // maxAgeMs: maximum acceptable age for the stalest source component.
  // nowMs: defaults to Date.now().
  // Returns: { status: 'FRESH'|'STALE'|'UNKNOWN', effectiveAgeMs, stalestSource, maxAgeMs }
  check(derivedKey, maxAgeMs, nowMs) {
    nowMs = nowMs || Date.now();
    this._stats.checks++;
    const rec = this._records.get(derivedKey);
    if (!rec) {
      return { status: 'UNKNOWN', effectiveAgeMs: null, stalestSource: null, maxAgeMs };
    }
    let maxAge = 0, stalestSource = null;
    for (var i = 0; i < rec.sources.length; i++) {
      var s   = rec.sources[i];
      var age = nowMs - s.fetchedAtMs;
      if (age > maxAge) { maxAge = age; stalestSource = s.name; }
    }
    const status = maxAge > maxAgeMs ? 'STALE' : 'FRESH';
    if (status === 'FRESH') this._stats.fresh++;
    else this._stats.stale++;
    return { status, effectiveAgeMs: Math.round(maxAge), stalestSource, maxAgeMs };
  }

  stats() { return { ...this._stats }; }
}

// --- Integration: compute derived value, track sources, check before use ---

const DERIVED_FRESHNESS = new DerivedValueFreshnessTracker();

async function computePortfolioRiskScore(portfolioId) {
  // Fetch live sources and record fetch timestamps
  const [price, vol, credit] = await Promise.all([
    fetchWithTimestamp('price_data',       { portfolioId }),
    fetchWithTimestamp('volatility_index', { portfolioId }),
    fetchWithTimestamp('credit_report',    { portfolioId }),
  ]);

  const score = riskFormula(price.data, vol.data, credit.data);

  // Record source fetch times alongside the derived value
  DERIVED_FRESHNESS.record('portfolio_risk_score:' + portfolioId, [
    { name: 'price_data',       fetchedAtMs: price.fetchedAt  },
    { name: 'volatility_index', fetchedAtMs: vol.fetchedAt    },
    { name: 'credit_report',    fetchedAtMs: credit.fetchedAt },
  ]);

  return { score, computedAt: Date.now() };
}

// Before executor agent uses the score:
function checkDerivedFreshness(portfolioId, maxAgeMs) {
  const result = DERIVED_FRESHNESS.check('portfolio_risk_score:' + portfolioId, maxAgeMs);
  if (result.status === 'STALE') {
    log({ event: 'derived_value_stale', portfolioId, stalestSource: result.stalestSource, effectiveAgeMs: result.effectiveAgeMs });
    return false;
  }
  if (result.status === 'UNKNOWN') {
    log({ event: 'derived_value_unknown', portfolioId });
    return false;
  }
  return true;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()` and `check()` timed over 100 000 iterations on a 3-source derived value.

```
=== DerivedValueFreshnessTracker timing (100 000 iterations) ===

record() 3 sources:    0.0003 ms
check() → STALE:       0.0002 ms
check() → FRESH:       0.0001 ms
check() → UNKNOWN:     0.0001 ms

=== Scenario: portfolio_risk_score derived from 3 sources ===

Sources at composition time (recorded when score was computed):
  price_data:         fetchedAt = 5s ago
  volatility_index:   fetchedAt = 12s ago
  credit_report:      fetchedAt = 310s ago

check(maxAgeMs=300 000):
  effectiveAgeMs=310 000, stalestSource='credit_report' → STALE
  → trigger targeted credit_report re-fetch; recompute only the credit component

check(maxAgeMs=400 000):
  effectiveAgeMs=310 000, stalestSource='credit_report' → FRESH
  → score is acceptable for queries with a 400s freshness budget

=== Why a plain cache TTL is insufficient ===

portfolio_risk_score cached with TTL=300s, computed at t=0.
At t=295s: cache TTL has 5s remaining → CACHE HIT → served as FRESH.
But credit_report was fetched at t=-15s (15s before score was computed).
Effective credit_report age at t=295s: 310s.

Cache TTL says FRESH.
Derived freshness tracker says STALE (credit_report: 310s > 300s budget).

=== S-100 vs S-148 vs S-165 ===

              │ S-100 (source contract)      │ S-148 (per-action freshness)   │ S-165 (derived value freshness)
──────────────┼──────────────────────────────┼────────────────────────────────┼────────────────────────────────────
Input         │ Source update interval        │ Raw source fetch timestamps     │ Composition-time source timestamps
Check target  │ Is this source fresh enough?  │ Is raw data fresh for action?  │ Is derived value fresh? (stalest component)
Multi-source  │ Per source independently      │ Per field independently        │ One check → stalest source identified
Derived values│ Not modeled                   │ Not modeled                    │ Core use case
When to call  │ At data ingest                │ Before executing each action   │ Before injecting derived values
```

## See also

[S-100](s100-live-data-freshness-contracts.md) · [S-148](s148-per-action-data-freshness-budget.md) · [S-163](s163-query-aware-tool-cache.md) · [S-43](s43-tool-result-caching.md) · [S-102](s102-composable-agent-data-layers.md)

## Go deeper

Keywords: `derived value freshness` · `composite data freshness` · `stalest source freshness` · `multi-source freshness check` · `freshness propagation` · `derived data staleness` · `composition-time freshness tracking` · `cache TTL freshness gap` · `source age propagation` · `effective freshness multi-source`
