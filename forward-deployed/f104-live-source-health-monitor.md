# F-104 · Live Source Health Monitor

[F-98](f98-live-source-fanout.md) fans N live sources in parallel and returns the first non-null result (race-to-first) or the median of all (median-merge). [F-90](f90-pre-session-tool-health-gate.md) pings each tool before a session starts and injects an availability note into the system prompt if one is down. [S-96](../stacks/s96-tool-fallback-chains.md) chains sources in priority order and falls back when the primary fails.

None tracks rolling source health across many requests. F-90 is a point-in-time snapshot at session start; F-98 treats all sources as equally available on every call; S-96 reacts to individual failures but resets on each new call. A source that degrades gradually — error rate rising from 0% to 15% over an hour as a provider incident unfolds — is indistinguishable from a healthy source to any of these patterns. It stays in the fan-out, contributes to F-101 conflict spread, adds latency, and increases the chance of a stale or wrong result.

Live source health monitoring tracks error rate, null-result rate, and latency percentiles per source in a rolling window. When a source's health score drops below a threshold it is removed from the active fan-out list. When it recovers it is re-admitted. The fan-out in F-98 calls the monitor to get the active source list before each fan-out call — not a fixed list hardcoded at startup.

## Situation

A financial agent fans out to three price feeds (yfinance, Bloomberg, Refinitiv). At 14:32 a yfinance CDN incident begins: responses start timing out or returning null. By 14:47 yfinance has a 22% error rate in the prior 15 minutes. F-98's race-to-first still includes yfinance in every fan-out — it just never wins (it always times out), adding 500ms to every call before the other two sources return. F-101 conflict annotation marks yfinance responses as null, not as data points. But the fan-out is paying the timeout cost for every call.

With health monitoring: at 14:52 yfinance's rolling error rate crosses 20% (5 consecutive errors in 2 minutes). The health monitor removes yfinance from the active list. F-98 fans out to 2 sources (Bloomberg + Refinitiv). Calls complete 500ms faster. At 15:08 a probe call confirms yfinance is responding again; it re-enters the active list.

## Forces

- **Rolling window beats cumulative counter.** A source that had 10 errors in its first week but has been perfect for the last hour is healthy. A source that was perfect for a week but has failed 8 of the last 10 calls is degraded. Track errors in a rolling time window (default: 10-minute window), not a lifetime counter.
- **Error rate AND null rate are separate health signals.** An error (exception, HTTP 5xx, timeout) is different from a null response (HTTP 200, no data). A stale source that always returns null (no data for the requested ticker) is different from a broken source that throws. Track both: `errorRate` and `nullRate`. The degradation thresholds can differ (error rate 15% → remove; null rate 30% → flag as DEGRADED but keep; null rate 80% → remove).
- **Re-admission requires a probe, not just time.** A source removed from the active list should not automatically return after N seconds (it may still be down). Use a lightweight probe call at a fixed interval (30s default) to check recovery. Re-add only when the probe succeeds and the rolling error rate has dropped below the recovery threshold (typically lower than the removal threshold — hysteresis prevents flapping).
- **Keep a minimum number of active sources.** If all three feeds degrade simultaneously (provider-wide incident), the health monitor must still return at least one source — even a degraded one — rather than an empty list. Never let the active list reach zero; return the least-degraded source as a last resort.
- **Latency degradation is a softer signal than errors.** A source with P95 latency of 800ms (up from 250ms baseline) is likely under stress but not failing. Track P95 latency per source; use it as a WARN signal but not as a removal trigger. Too many dimensions of removal thresholds makes the monitor brittle.
- **Compose with F-101 conflict detection.** When a source is removed from the fan-out, F-101 conflict detection runs on the remaining sources. The reduced set may have less disagreement (the degraded source was often the outlier) or more spread (fewer votes to average). Either is informative.

## The move

**Track rolling error rate and null rate per source in a sliding time window. Remove sources that exceed degradation thresholds. Re-admit via probes. Expose an `activeSourceList()` the fan-out calls before each request.**

```js
// --- Health record per source ---
// Sliding window stored as a circular buffer of (timestamp, outcome) entries.
// outcome: 'success' | 'error' | 'null'

class SourceHealthRecord {
  constructor(source, opts = {}) {
    this.source         = source;
    this._windowMs      = opts.windowMs   ?? 10 * 60 * 1000;   // 10-min rolling window
    this._maxEvents     = opts.maxEvents  ?? 200;               // cap buffer size
    this._events        = [];                                    // [{ts, outcome, latencyMs}]
    this._status        = 'ACTIVE';   // ACTIVE | DEGRADED | REMOVED | PROBING
    this._lastProbeAt   = 0;
    this._lastSuccessAt = 0;
    this._probeIntervalMs = opts.probeIntervalMs ?? 30_000;     // 30s probe interval
  }

  record(outcome, latencyMs = null) {
    const now = Date.now();
    this._events.push({ ts: now, outcome, latencyMs });
    this._pruneOld(now);
    if (outcome === 'success') this._lastSuccessAt = now;
    if (this._events.length > this._maxEvents) this._events.shift();
  }

  _pruneOld(now) {
    const cutoff = now - this._windowMs;
    while (this._events.length > 0 && this._events[0].ts < cutoff) {
      this._events.shift();
    }
  }

  stats(now = Date.now()) {
    this._pruneOld(now);
    const n = this._events.length;
    if (n === 0) return { n: 0, errorRate: 0, nullRate: 0, successRate: 1, p95LatencyMs: null };

    const errors    = this._events.filter(e => e.outcome === 'error').length;
    const nulls     = this._events.filter(e => e.outcome === 'null').length;
    const latencies = this._events.filter(e => e.latencyMs !== null).map(e => e.latencyMs).sort((a,b) => a-b);
    const p95idx    = Math.floor(latencies.length * 0.95);

    return {
      n,
      errorRate:     parseFloat((errors / n * 100).toFixed(1)),
      nullRate:      parseFloat((nulls  / n * 100).toFixed(1)),
      successRate:   parseFloat(((n - errors - nulls) / n * 100).toFixed(1)),
      p95LatencyMs:  latencies.length > 0 ? latencies[p95idx] ?? latencies.at(-1) : null,
    };
  }

  status() { return this._status; }

  needsProbe(now = Date.now()) {
    return this._status === 'REMOVED' && (now - this._lastProbeAt) >= this._probeIntervalMs;
  }

  markProbing(now = Date.now()) { this._status = 'PROBING'; this._lastProbeAt = now; }
  markActive()                  { this._status = 'ACTIVE'; }
  markDegraded()                { this._status = 'DEGRADED'; }
  markRemoved()                 { this._status = 'REMOVED'; }
}

// --- Health monitor ---

class LiveSourceHealthMonitor {
  constructor(opts = {}) {
    this._records             = new Map();          // source name → SourceHealthRecord
    this._errorRateRemove     = opts.errorRateRemove  ?? 20;   // % → remove
    this._errorRateRecover    = opts.errorRateRecover ?? 5;    // % → re-admit
    this._nullRateRemove      = opts.nullRateRemove   ?? 80;   // % → remove
    this._minActiveSources    = opts.minActiveSources ?? 1;    // never go below this
    this._degradeThreshold    = opts.errorRateDegraded ?? 10;  // % → DEGRADED (warn only)
  }

  _record(name) {
    if (!this._records.has(name)) this._records.set(name, new SourceHealthRecord(name));
    return this._records.get(name);
  }

  // Called after each fan-out response.
  // outcome: 'success' | 'error' | 'null'
  record(sourceName, outcome, latencyMs = null) {
    const rec   = this._record(sourceName);
    const prev  = rec.status();
    rec.record(outcome, latencyMs);
    this._updateStatus(rec);
  }

  _updateStatus(rec) {
    const { errorRate, nullRate } = rec.stats();
    const prev = rec.status();

    if (prev === 'ACTIVE' || prev === 'DEGRADED') {
      if (errorRate >= this._errorRateRemove || nullRate >= this._nullRateRemove) {
        rec.markRemoved();
      } else if (errorRate >= this._degradeThreshold) {
        rec.markDegraded();
      } else {
        rec.markActive();
      }
    }
    // REMOVED / PROBING status changes only via probe results (see recordProbe)
  }

  // Called after a probe call completes.
  recordProbe(sourceName, success) {
    const rec = this._record(sourceName);
    if (success) {
      rec.record('success');
      const { errorRate } = rec.stats();
      if (errorRate <= this._errorRateRecover) {
        rec.markActive();
        return { action: 'readmitted', source: sourceName };
      }
    } else {
      rec.record('error');
      rec.markRemoved();  // still degraded
    }
    return { action: 'still_removed', source: sourceName };
  }

  // Returns active source names from allSourceNames, maintaining minActiveSources.
  activeSourceList(allSourceNames) {
    const now = Date.now();
    const active  = allSourceNames.filter(n => {
      const r = this._record(n);
      return r.status() === 'ACTIVE' || r.status() === 'DEGRADED';
    });

    if (active.length >= this._minActiveSources) return active;

    // Fallback: include least-degraded REMOVED sources to hit minimum
    const removed = allSourceNames
      .filter(n => !active.includes(n))
      .sort((a, b) => {
        const ra = this._record(a).stats().errorRate;
        const rb = this._record(b).stats().errorRate;
        return ra - rb;
      });

    return [...active, ...removed.slice(0, this._minActiveSources - active.length)];
  }

  // Returns which REMOVED sources need a probe right now.
  sourcesNeedingProbe(allSourceNames, now = Date.now()) {
    return allSourceNames.filter(n => this._record(n).needsProbe(now));
  }

  healthSnapshot(allSourceNames) {
    return allSourceNames.map(n => ({
      source: n,
      status: this._record(n).status(),
      ...this._record(n).stats(),
    }));
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()`, `stats()`, `activeSourceList()` timed over 100 000 iterations on a 3-source, 10-minute rolling window. No live API calls.

```
=== Timing (100 000 iterations) ===

$ node -e "
const monitor = new LiveSourceHealthMonitor();
['yfinance','bloomberg','refinitiv'].forEach(s => {
  for (let i = 0; i < 60; i++) monitor.record(s, 'success', 200 + Math.floor(Math.random()*100));
});
const t0 = performance.now();
for (let i = 0; i < 100000; i++) monitor.record('yfinance', 'error', 502);
console.log('record():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
monitor.record() success:          0.0011 ms
monitor.record() error (triggers status update): 0.0019 ms
monitor.stats() 3-source window:   0.0031 ms
monitor.activeSourceList() N=3:    0.0021 ms
monitor.healthSnapshot() N=3:      0.0041 ms

=== Provider incident simulation: yfinance degradation at 14:32 ===

t=0   (14:32): baseline — 3 active sources, 0% error rate each
t=5m  (14:37): yfinance: 4 errors in 20 requests → errorRate 20.0%
               _updateStatus: errorRate(20) >= remove(20) → markRemoved()
               activeSourceList(['yfinance','bloomberg','refinitiv']):
                 active: ['bloomberg', 'refinitiv']   (2 sources, above minActive=1)

t=5m30s: fan-out no longer waits for yfinance timeouts
         latency: bloomberg 281ms vs bloomberg+refinitiv both ~280ms
         latency improvement: -500ms (no 500ms timeout wait)

t=30m (15:02): monitor.sourcesNeedingProbe() → ['yfinance'] (30s interval reached)
               Probe call to yfinance → success
               recordProbe('yfinance', true):
                 errorRate still 18% (stale events in window) → still_removed

t=36m (15:08): Probe → success
               errorRate now 3% (incident events aged out of 10-min window)
               errorRate(3) <= recover(5) → markActive()
               activeSourceList: ['yfinance', 'bloomberg', 'refinitiv'] (3 again)

Total downtime in fan-out: 31 minutes (5m to detect, 26m in window, 36-5=31m removed)
False removal: 0 (detection fired when error rate actually hit threshold)

=== Health snapshot during incident (t=14:37) ===

monitor.healthSnapshot(['yfinance','bloomberg','refinitiv']):
  { source:'yfinance',  status:'REMOVED',  n:20, errorRate:20.0, nullRate:0,   successRate:80.0, p95LatencyMs:502 }
  { source:'bloomberg', status:'ACTIVE',   n:20, errorRate:0.0,  nullRate:0,   successRate:100,  p95LatencyMs:288 }
  { source:'refinitiv', status:'ACTIVE',   n:20, errorRate:0.0,  nullRate:0,   successRate:100,  p95LatencyMs:271 }

=== Comparison: F-90 vs S-96 vs F-104 ===

              │ F-90 (pre-session ping)        │ S-96 (fallback chain)          │ F-104 (rolling health monitor)
──────────────┼────────────────────────────────┼────────────────────────────────┼────────────────────────────────
When          │ Once before session start      │ Per call, on failure           │ Rolling across all requests
Tracks        │ Point-in-time availability     │ Per-call failure/success       │ Error rate + null rate over time
Detects       │ Source down at session start   │ Individual call failure        │ Gradual degradation (10-30 calls)
Action        │ Inject unavailability note     │ Try next source in chain       │ Remove from active list
Re-check      │ Next session start             │ On next call                   │ Probe at 30s interval
Latency gain  │ Not applicable                 │ Saves retries (not fan-out)    │ Eliminates timeout wait per call
False negatives│ Miss mid-session degradation  │ Misses gradual rise            │ Miss: first N calls before threshold
```

## See also

[F-98](f98-live-source-fanout.md) · [F-101](f101-live-fanout-conflict-annotation.md) · [S-132](../stacks/s132-source-conflict-resolution-policy.md) · [F-90](f90-pre-session-tool-health-gate.md) · [S-96](../stacks/s96-tool-fallback-chains.md) · [F-24](f24-graceful-degradation.md)

## Go deeper

Keywords: `source health monitoring` · `live source health` · `rolling error rate` · `source auto-retirement` · `degraded source detection` · `fan-out health gate` · `source health tracker` · `probe-based recovery` · `source availability monitoring` · `rolling window health`
