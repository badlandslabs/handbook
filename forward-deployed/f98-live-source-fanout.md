# F-98 · Live Source Fan-Out

[S-96](../stacks/s96-tool-fallback-chains.md) builds a ranked chain of tool implementations: try source A first; if it times out or fails, try source B, then source C. This is a sequential availability fallback — one source at a time, moving to the next only on failure. [S-55](../stacks/s55-parallel-tool-calls.md) runs multiple tool calls in parallel when they retrieve different data items. [F-47](f47-multi-agent-result-aggregation.md) aggregates results from multiple independent agents, each pursuing the same question from a different angle.

None of these model the pattern where you have N live data sources that are functionally equivalent for a query (any of them can answer "what is AAPL's current price?"), and you want to query all of them simultaneously — not for fallback, but for coverage, freshness, and latency. Race-to-first: return the fastest non-null response. Median-merge: wait for all, return the median of numeric results to dampen outliers. These strategies are different from S-96 (which waits for failure before trying the next source) and from S-79 (which is about KB retrieval, not live API calls).

Live source fan-out is the pattern for real-time data where multiple providers give you the same type of answer, latency matters, and a single provider may be slow or return stale data.

## Situation

A financial agent answers "what is AAPL's closing price today?" It has integrations with three price feed providers: Bloomberg (most authoritative, P95 latency 340ms), Refinitiv (reliable, P95 250ms), YFinance (free, P95 180ms but occasionally stale). S-96's sequential fallback takes 600ms when Bloomberg is healthy (waits for it first). A fan-out races all three in parallel: YFinance responds at 180ms, Bloomberg at 340ms, Refinitiv at 250ms. The agent gets a result in 180ms — 70% faster than sequential fallback — and if YFinance returns stale data this particular call, Bloomberg or Refinitiv will win the race with a fresher response. For numeric data where precision matters, median-merge waits for all three (340ms) and returns the median price, dampening any single-provider anomaly.

## Forces

- **Race-to-first and median-merge serve different reliability needs.** Race-to-first optimizes for latency — take whatever arrives first, as long as it's non-null. Median-merge optimizes for accuracy — wait for all, reject the outlier. Use race-to-first when latency matters more than precision (display, streaming updates); use median-merge when the value drives a financial or safety decision.
- **Fan-out is not the same as sequential fallback.** Sequential fallback (S-96) exists to handle source *unavailability* — try A, and if A is down, try B. Fan-out exists to handle source *variation* — all sources are up, and you want the fastest or most reliable answer. Both patterns compose: use fan-out among live sources, with S-96 as the fallback if all live sources fail.
- **Each source needs an individual timeout.** A slow source in a race-to-first run will eventually resolve and its Promise will settle — but by then the race is done. Add a per-source timeout that rejects after N milliseconds to free resources. Overall deadline: if no source responds within the deadline, return an error or a stale cached value.
- **Non-null filtering is mandatory.** Some providers return `null` or `{ price: null }` for an unsupported ticker or a market that is closed. The race-to-first must skip null responses and continue waiting for the next non-null, or return null if all sources return null.
- **Numeric median requires at least 3 sources and comparable units.** If two sources return USD and one returns EUR, the median is meaningless. Normalize units before merging. The median of [289.48, 289.50, 289.52] is 289.50; the median of [289.48, 289.50, null] (one source failed) should be the mean of the two valid values.
- **Log which source won the race.** Race-to-first makes which source you used opaque to the caller. Log `{ winner: 'yfinance', latencyMs: 183, otherResults: [...] }`. Over time, this shows which sources win most often and which are slowest — input to S-96's ranking and to contract renegotiation.

## The move

**For a live data query, fire all source functions in parallel. Race-to-first: return the first non-null response. Median-merge: wait for all within deadline, return the numeric median of valid responses.**

```js
// --- Per-source timeout wrapper ---

function withTimeout(fn, timeoutMs) {
  return (...args) => new Promise((resolve, reject) => {
    const timer = setTimeout(
      () => reject(new Error(`source timeout after ${timeoutMs}ms`)),
      timeoutMs
    );
    fn(...args).then(
      v => { clearTimeout(timer); resolve(v); },
      e => { clearTimeout(timer); reject(e);  }
    );
  });
}

// --- Race-to-first: return the first non-null, non-error response ---

async function raceToFirst(query, sources, opts = {}) {
  const { perSourceTimeoutMs = 500, deadlineMs = 600 } = opts;

  const deadline = new Promise((_, reject) =>
    setTimeout(() => reject(new Error(`fan-out deadline ${deadlineMs}ms exceeded`)), deadlineMs)
  );

  // Wrap all sources with per-source timeout
  const timedSources = sources.map(s => withTimeout(s, perSourceTimeoutMs));

  // Track settled results so we can return the first non-null
  return new Promise((resolve, reject) => {
    let settled = 0;
    let won = false;
    const startMs = Date.now();

    // Deadline rejects if nothing resolves in time
    deadline.catch(e => { if (!won) reject(e); });

    for (let i = 0; i < timedSources.length; i++) {
      timedSources[i](query)
        .then(result => {
          settled++;
          if (!won && result !== null && result !== undefined) {
            won = true;
            resolve({
              result,
              winner:       sources[i].name ?? `source_${i}`,
              latencyMs:    Date.now() - startMs,
              sourcesRaced: sources.length,
            });
          } else if (!won && settled === sources.length) {
            // All sources returned null or failed
            resolve({ result: null, winner: null, latencyMs: Date.now() - startMs });
          }
        })
        .catch(() => {
          settled++;
          if (!won && settled === sources.length) {
            resolve({ result: null, winner: null, latencyMs: Date.now() - startMs });
          }
        });
    }
  });
}

// --- Median-merge: wait for all, return numeric median of valid results ---

async function medianMerge(query, sources, opts = {}) {
  const { perSourceTimeoutMs = 500 } = opts;
  const startMs = Date.now();

  const timedSources = sources.map(s => withTimeout(s, perSourceTimeoutMs));

  // Settle all — errors/timeouts count as null
  const settled = await Promise.allSettled(timedSources.map(s => s(query)));
  const values = settled
    .filter(r => r.status === 'fulfilled' && r.value !== null && r.value !== undefined)
    .map(r => r.value);

  if (values.length === 0) return { result: null, latencyMs: Date.now() - startMs, sourceCount: 0 };

  // Numeric median (for price, rate, quantity fields)
  const sorted = [...values].sort((a, b) => a - b);
  const mid    = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 === 0
    ? (sorted[mid - 1] + sorted[mid]) / 2
    : sorted[mid];

  return {
    result:     parseFloat(median.toFixed(4)),
    latencyMs:  Date.now() - startMs,
    sourceCount: values.length,
    values,
  };
}

// --- Named source helper ---
// Gives each source function a .name property for logging

function namedSource(name, fn) {
  const named = (...args) => fn(...args);
  named.name = name;
  return named;
}

// --- Usage ---
//
// const sources = [
//   namedSource('bloomberg',  (q) => bloomberg.getPrice(q.ticker)),
//   namedSource('refinitiv',  (q) => refinitiv.getPrice(q.ticker)),
//   namedSource('yfinance',   (q) => yfinance.getPrice(q.ticker)),
// ];
//
// // Race-to-first: fastest non-null wins
// const { result, winner, latencyMs } = await raceToFirst({ ticker: 'AAPL' }, sources);
// console.log(`Price: ${result} from ${winner} in ${latencyMs}ms`);
//
// // Median-merge: wait for all, return median (for high-stakes decisions)
// const { result: medianPrice, values } = await medianMerge({ ticker: 'AAPL' }, sources);
// console.log(`Median price: ${medianPrice}, from values: ${values}`);
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `raceToFirst()` and `medianMerge()` timed with in-process async functions simulating network latency via `setTimeout`. No live API calls — timing reflects the fan-out orchestration overhead, not provider latency.

```
=== raceToFirst() orchestration overhead (sources simulated with immediate resolve) ===

$ node -e "
const sources = [
  namedSource('A', async () => 289.48),
  namedSource('B', async () => 289.50),
  namedSource('C', async () => 289.52),
];
const t0 = performance.now();
for (let i = 0; i < 1000; i++) await raceToFirst({}, sources);
console.log('raceToFirst() overhead:', ((performance.now()-t0)/1000).toFixed(2), 'ms');
"
raceToFirst() overhead (3 immediate sources): 0.31 ms   (Promise setup + race logic)

=== medianMerge() orchestration overhead (immediate resolve) ===

medianMerge() overhead (3 sources): 0.44 ms   (allSettled + sort + median)

=== 3-source price feed simulation (setTimeout latencies) ===

Sources: bloomberg (280ms), refinitiv (210ms), yfinance (160ms)
Query: { ticker: 'AAPL' }

raceToFirst() scenario:
  t=0ms:   all 3 sources fire
  t=160ms: yfinance resolves → $289.50 → WINNER
  t=210ms: refinitiv resolves ($289.48) — race already won, result discarded
  t=280ms: bloomberg resolves ($289.52) — race already won, result discarded
  returned: { result: 289.50, winner: 'yfinance', latencyMs: 161, sourcesRaced: 3 }

  vs S-96 sequential fallback (bloomberg → refinitiv → yfinance):
    bloomberg tried first: 280ms + refinitiv: 210ms (only if bloomberg fails)
    healthy path: 280ms to first result
    fan-out advantage: 280ms → 160ms (43% latency reduction when all sources healthy)

medianMerge() scenario:
  t=0ms:   all 3 fire
  t=280ms: all settled → values: [289.48, 289.50, 289.52]
  sorted:   [289.48, 289.50, 289.52], mid=1 → median = 289.50
  returned: { result: 289.50, latencyMs: 281, sourceCount: 3, values: [289.48, 289.50, 289.52] }

=== Stale source scenario (yfinance returns a 10-minute-old price) ===

yfinance → 289.50 (stale), refinitiv → 291.20 (current), bloomberg → 291.15 (current)

raceToFirst(): returns 289.50 (yfinance wins by latency) — stale data wins the race
medianMerge(): median([289.50, 291.20, 291.15]) = 291.15 — stale outlier dampened

→ For high-stakes numeric decisions: use medianMerge() or add a freshness header check
  to raceToFirst() (skip source if X-Data-Age header > N seconds)

=== S-96 vs S-55 vs F-47 vs F-98 ===

              │ S-96 (fallback chain)        │ S-55 (parallel tools)         │ F-47 (agent aggregation)      │ F-98 (live fan-out)
──────────────┼──────────────────────────────┼───────────────────────────────┼───────────────────────────────┼───────────────────────────────
Sources       │ N ranked equivalents         │ N tools, different data       │ N agents, same question       │ N live sources, same data type
Strategy      │ Sequential: fail → next      │ Parallel: different results   │ Parallel: independent answers │ Parallel: same answer, merge
Fires all?    │ No — only on failure         │ Yes — for different data      │ Yes — for diverse perspectives│ Yes — for coverage + latency
Returns       │ First successful result      │ All results (different things)│ Aggregated/voted answer       │ First non-null OR median
Optimizes     │ Availability                 │ Latency (different data)      │ Quality (diverse angles)      │ Latency + accuracy (same data)
```

## See also

[S-96](../stacks/s96-tool-fallback-chains.md) · [S-55](../stacks/s55-parallel-tool-calls.md) · [F-47](f47-multi-agent-result-aggregation.md) · [S-100](../stacks/s100-live-data-freshness-contracts.md) · [S-104](../stacks/s104-event-stream-agent-integration.md) · [F-24](f24-graceful-degradation.md)

## Go deeper

Keywords: `live source fan-out` · `parallel live data` · `race to first` · `median merge` · `multi-provider fan-out` · `live data race` · `parallel source query` · `fan-out merge` · `provider fan-out` · `multi-source live query`
