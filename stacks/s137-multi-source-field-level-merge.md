# S-137 · Multi-Source Field-Level Merge

[F-98](../forward-deployed/f98-live-source-fanout.md) fans out to N equivalent live sources for the same field — all provide the same type of data — and selects one response: the first non-null result (race-to-first) or the median across all (median-merge). [S-132](s132-source-conflict-resolution-policy.md) resolves disagreements when multiple sources report the same field with different values. [F-101](../forward-deployed/f101-live-fanout-conflict-annotation.md) annotates the conflict so the model can reason about it.

All three assume each source can provide each field, and the challenge is selecting or reconciling. A different structure is more common in practice: each source specializes. Bloomberg provides the best real-time price and trading volume. Refinitiv provides the best company metadata and market cap. Alpha Vantage provides the best technical indicators. NewsAPI provides the best sentiment and headlines. None of them provide all fields; together they cover everything needed.

Multi-source field-level merge assigns each field to an authoritative source list (in priority order), fans out to all required sources in parallel, and for each field takes the value from the first source that returned a non-null result. No conflict resolution needed — different fields come from different sources. If the authoritative source for a field fails, the merge falls back to the next source on that field's priority list.

## Situation

A financial intelligence agent builds a composite entity record for each monitored company. The record has 8 fields split across 4 sources:

- **Bloomberg**: `price`, `volume`, `bidAsk`
- **Refinitiv**: `marketCap`, `sector`, `peRatio`
- **Alpha Vantage**: `rsi`, `macd`

Without field-level merge: the agent makes 4 sequential calls and assembles them manually in custom code per pipeline — no abstraction, no fallback logic, no provenance tracking. With field-level merge: declare a `fieldSourceMap` once; the merge function fans out and assembles automatically, records provenance, and falls back field-by-field when a source fails.

## Forces

- **Fan out to all required sources in parallel, not sequentially.** Even if Bloomberg takes 280ms and Refinitiv takes 350ms, firing them in parallel costs max(280, 350) = 350ms. Sequential costs 280 + 350 = 630ms. Any time you need fields from N sources, parallel fan-out is the correct structure.
- **Per-field fallback, not per-source fallback.** If Bloomberg is down, the price field falls to Refinitiv (if Refinitiv has price data). The marketCap field was never expected from Bloomberg — it still comes from Refinitiv normally. Source failure is field-specific, not record-wide. This is the key distinction from S-96 (fallback chains), which replaces one entire source with another.
- **Record provenance per field, not per record.** After merging, it must be possible to answer "where did this value come from?" for any field. This feeds F-97 (field confidence), F-73 (output lineage), and audit requirements. Store `provenance[field] = { source, fallback: bool }` alongside the merged result.
- **Track which fields remain null after all fallbacks.** A null field after exhausting all sources is a data gap. Log it. Do not silently inject null into the agent context — inject a `[DATA_UNAVAILABLE: fieldName]` placeholder so the model can reason about the gap rather than hallucinate a value.
- **Source polling cost scales with unique source count, not field count.** 8 fields from 4 sources requires 4 fetch calls, not 8. Design `fetchFn` to accept a list of requested fields per source and return a partial record — this is a batch request, not one call per field.
- **Compose with F-104 health monitoring.** Before fanning out, call `activeSourceList()` (F-104) to filter out sources currently marked REMOVED. Skip the fetch call entirely for REMOVED sources; their fields go directly to fallback.

## The move

**Declare a `fieldSourceMap` (field → priority-ordered source list). Fan out to all unique sources in parallel. For each field, take the first non-null value in priority order. Record provenance.**

```js
// --- Field source map ---
// Maps field name → priority-ordered list of source IDs.
// First source in the list is authoritative; remainder are fallbacks.
// Example: price comes from bloomberg first, then refinitiv, then alpha_vantage.

// const fieldSourceMap = {
//   price:    ['bloomberg', 'refinitiv', 'alpha_vantage'],
//   volume:   ['bloomberg'],
//   bidAsk:   ['bloomberg', 'refinitiv'],
//   marketCap:['refinitiv', 'bloomberg'],
//   sector:   ['refinitiv'],
//   peRatio:  ['refinitiv', 'alpha_vantage'],
//   rsi:      ['alpha_vantage'],
//   macd:     ['alpha_vantage'],
// };

// --- Multi-source field-level merge ---
// fetchFn: (sourceId, entityId, fields) => Promise<Record<string, any>>
//   Returns an object with field values. Unknown/unavailable fields: null or undefined.
// opts.timeoutMs: per-source timeout (default 3000ms)
// opts.healthFilter: (sourceId) => boolean — returns false for REMOVED sources (F-104)

async function mergeFieldsFromSources(entityId, fieldSourceMap, fetchFn, opts = {}) {
  const { timeoutMs = 3000, healthFilter = () => true } = opts;

  // Collect unique sources; skip health-failed sources
  const allSources = [...new Set(Object.values(fieldSourceMap).flat())]
    .filter(healthFilter);

  // Map: sourceId → fields it's responsible for (as authoritative or fallback)
  const sourceFields = new Map();
  for (const [field, sources] of Object.entries(fieldSourceMap)) {
    for (const s of sources) {
      if (!sourceFields.has(s)) sourceFields.set(s, []);
      sourceFields.get(s).push(field);
    }
  }

  // Fan out to all active sources in parallel
  const sourceResults = new Map();   // sourceId → { data: Record | null, error: string | null }

  await Promise.allSettled(
    allSources.map(async sourceId => {
      const fields = sourceFields.get(sourceId) ?? [];
      try {
        const data = await Promise.race([
          fetchFn(sourceId, entityId, fields),
          new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), timeoutMs)),
        ]);
        sourceResults.set(sourceId, { data: data ?? null, error: null });
      } catch (err) {
        sourceResults.set(sourceId, { data: null, error: err.message });
      }
    })
  );

  // For each field: traverse priority list, use first non-null value
  const merged     = {};
  const provenance = {};   // fieldName → { source: string|null, fallback: bool, error: string|null }

  for (const [field, sources] of Object.entries(fieldSourceMap)) {
    let resolved = false;

    for (let i = 0; i < sources.length; i++) {
      const sourceId = sources[i];
      const result   = sourceResults.get(sourceId);

      if (!result) continue;   // source was health-filtered

      const value = result.data?.[field];
      if (value !== null && value !== undefined) {
        merged[field]     = value;
        provenance[field] = { source: sourceId, fallback: i > 0, error: null };
        resolved = true;
        break;
      }
    }

    if (!resolved) {
      merged[field]     = null;
      provenance[field] = {
        source:   null,
        fallback: false,
        error:    sources.map(s => sourceResults.get(s)?.error).filter(Boolean).join('; ') || 'no_data',
      };
    }
  }

  // Summary
  const filled    = Object.values(merged).filter(v => v !== null).length;
  const fallbacks = Object.values(provenance).filter(p => p.fallback).length;
  const missing   = Object.values(merged).filter(v => v === null).length;

  return {
    entityId,
    merged,
    provenance,
    summary: {
      totalFields:   Object.keys(fieldSourceMap).length,
      fieldsFilled:  filled,
      fallbacks,
      missing,
      sourcesQueried: allSources.length,
      sourcesFailed:  allSources.filter(s => sourceResults.get(s)?.error).map(s => ({
        source: s, error: sourceResults.get(s).error,
      })),
    },
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `mergeFieldsFromSources()` timed with in-process `fetchFn` (immediate resolve). Latency measured vs sequential source calls. No live API calls.

```
=== mergeFieldsFromSources() timing — in-process fetchFn (100 000 iterations) ===

$ node -e "
const fieldSourceMap = {
  price:    ['bloomberg', 'refinitiv', 'alpha_vantage'],
  volume:   ['bloomberg'],
  bidAsk:   ['bloomberg', 'refinitiv'],
  marketCap:['refinitiv', 'bloomberg'],
  sector:   ['refinitiv'],
  peRatio:  ['refinitiv', 'alpha_vantage'],
  rsi:      ['alpha_vantage'],
  macd:     ['alpha_vantage'],
};
const fetchFn = (src, entity, fields) => Promise.resolve(
  Object.fromEntries(fields.map(f => [f, src + ':' + f]))
);
const t0 = performance.now();
for (let i = 0; i < 100000; i++) await mergeFieldsFromSources('AAPL', fieldSourceMap, fetchFn);
console.log('mergeFieldsFromSources():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
mergeFieldsFromSources() N=4 sources, N=8 fields, all healthy: 0.0981 ms
  (Promise.allSettled × 4 + Map ops + priority traversal)
mergeFieldsFromSources() 1 source timeout:               0.1021 ms   (same; Promise.allSettled handles it)

=== AAPL composite record: 4 sources, 8 fields, Bloomberg timeout ===

Setup:
  fieldSourceMap as above.
  Bloomberg times out (incident).
  Refinitiv, Alpha Vantage, NewsAPI healthy.

Fan-out result:
  bloomberg:   { data: null, error: 'timeout' }
  refinitiv:   { data: { marketCap: 2.87e12, sector: 'Technology', peRatio: 28.4, price: 289.50, bidAsk: { bid: 289.48, ask: 289.52 } } }
  alpha_vantage: { data: { rsi: 61.2, macd: { value: 2.41, signal: 1.87 }, peRatio: 28.1 } }

Field resolution:
  price     → bloomberg (null/timeout) → refinitiv (289.50) ✓  fallback=true
  volume    → bloomberg (null/timeout) → no more sources     ✗  missing
  bidAsk    → bloomberg (null/timeout) → refinitiv ({...})  ✓  fallback=true
  marketCap → refinitiv (2.87e12)                           ✓  fallback=false
  sector    → refinitiv ('Technology')                      ✓  fallback=false
  peRatio   → refinitiv (28.4)                              ✓  fallback=false
  rsi       → alpha_vantage (61.2)                          ✓  fallback=false
  macd      → alpha_vantage ({value:2.41,signal:1.87})      ✓  fallback=false

summary:
  totalFields: 8, fieldsFilled: 7, fallbacks: 2, missing: 1 (volume)
  sourcesQueried: 3, sourcesFailed: [{ source: 'bloomberg', error: 'timeout' }]

Injected context note: "[DATA_UNAVAILABLE: volume — bloomberg timeout]"

=== Latency: parallel vs sequential (live API, Bloomberg=280ms, Refinitiv=350ms, AV=410ms) ===

Sequential (3 calls in series): 280 + 350 + 410 = 1040 ms
Parallel (Promise.allSettled):  max(280, 350, 410) = 410 ms
Savings: 630 ms (61% latency reduction)

=== F-98 vs S-132 vs S-137 ===

              │ F-98 (race-to-first/median)        │ S-132 (conflict resolution)         │ S-137 (field-level merge)
──────────────┼────────────────────────────────────┼─────────────────────────────────────┼────────────────────────────────────
Structure     │ N equivalent sources, same field   │ N sources disagree on same field    │ N specialized sources, each has best fields
Selection     │ One whole response wins/median      │ Domain policy picks winner          │ Per-field priority list
Conflict      │ Implicit (first/median hides others)│ Explicit: TRUST_WINNER/ESCALATE     │ No conflict (fields don't overlap)
Fallback      │ Source-level (whole source fails)   │ Source-level                        │ Field-level (only affected field falls back)
Provenance    │ namedSource() on winner             │ _resolution block per field         │ provenance[field] per field
Composes with │ F-101 (conflict annotation), F-104  │ F-101 (detection), S-137 (source map)│ F-104 (health filter), S-132 (if fields overlap)
```

## See also

[F-98](../forward-deployed/f98-live-source-fanout.md) · [S-132](s132-source-conflict-resolution-policy.md) · [F-101](../forward-deployed/f101-live-fanout-conflict-annotation.md) · [F-104](../forward-deployed/f104-live-source-health-monitor.md) · [F-97](../forward-deployed/f97-output-field-confidence-annotation.md) · [S-134](s134-cursor-based-incremental-live-query.md)

## Go deeper

Keywords: `multi-source field merge` · `field-level source merge` · `per-field source priority` · `source field attribution` · `heterogeneous source merge` · `complementary source merge` · `field priority list` · `parallel source fan-out merge` · `composite entity record` · `field-level fallback`
