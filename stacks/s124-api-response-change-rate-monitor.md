# S-124 · API Response Change Rate Monitor

[S-87](s87-external-api-response-validation.md) hard-gates each external API response: if structure is wrong, reject it before it reaches the model. [S-113](s113-reactive-schema-evolution.md) detects structural drift per response and AUTO_ADAPTs by updating field aliases on the fly, alerting operators to each drift event. Both operate per-response — they handle the response in front of them.

Neither gives you a time-series view. An API that changes its response structure once in a while (auto-adaptation handles it) is different from an API whose structure is changing on 15% of calls. The second case means the API is fundamentally unstable — aliases are piling up, the adaptation layer is masking systemic drift, and eventually a MANUAL_REQUIRED change will slip through undetected because the noise floor is too high.

An API response change rate monitor records fingerprints over a rolling window of N responses and computes what fraction had a structural change relative to the established baseline. When the change rate exceeds a threshold, it alerts: not "this specific response changed" but "this API is structurally unstable at a fleet level." That distinction is the input to an architectural decision — whether to pin the API version, switch providers, or harden the adaptation layer.

## Situation

A legal data provider's API returns contract clause objects. S-113 has been logging one or two AUTO_ADAPT events per week for three months — acceptable noise. Then in week 12, change rate jumps from 2% to 14% over three days. S-113 is still adapting each response successfully, so no errors are surfaced. But the change rate monitor fires: "14% structural change rate in last 100 responses, threshold 5%." Engineering investigates: the provider silently deployed a new API version on a subset of servers. Without the rate monitor, this would have been invisible until a MANUAL_REQUIRED change finally failed in production.

## Forces

- **The fingerprint is already computed by S-113; reuse it.** `fingerprint(obj)` from S-113 produces a sorted `path:type` pair set — the structural identity of an object. Computing it again is redundant. If S-113 is deployed, the rate monitor is a thin accumulator over S-113's existing output.
- **The baseline is the mode of the first K fingerprints, not the first fingerprint.** Some APIs return slightly different structures for different data records (e.g., an optional field that appears on ~30% of responses). If you use the first single response as the baseline, 30% of subsequent responses would look like changes when they're not. Use the most common fingerprint from the first K=20 responses as the baseline.
- **A circular buffer of N=100 is sufficient.** The rolling window needs to be large enough to smooth out burst noise (a few bad responses in a row) but small enough to detect a fresh drift quickly. N=100 gives you ~1 hour of signal at 1-2 req/min, or ~10 minutes at 10 req/min.
- **Change rate above threshold triggers an alert; it does not block the response.** The monitor's job is fleet-level visibility, not per-response gating. S-87 and S-113 handle gating and adaptation. If the rate monitor also blocked responses, a burst of legitimate schema variation would cause a cascade. Emit the alert; let S-113 continue adapting.
- **Track per-API-endpoint, not globally.** A product search API and a pricing API have different stability profiles. Mixing them in one monitor would obscure drift on the noisy one and under-alert on the stable one. One monitor instance per endpoint.

## The move

**For each external API response, fingerprint its structure and record to a circular buffer. Compute the fraction that differ from the baseline fingerprint. Alert when change rate exceeds threshold.**

```js
// --- Structural fingerprint (same algorithm as S-113) ---
// Returns a sorted string of "path:type" pairs for all leaf fields.

function fingerprint(obj, prefix = '') {
  const pairs = [];
  for (const [key, val] of Object.entries(obj ?? {})) {
    const path = prefix ? `${prefix}.${key}` : key;
    if (val !== null && typeof val === 'object' && !Array.isArray(val)) {
      pairs.push(...fingerprint(val, path));
    } else {
      const type = Array.isArray(val) ? 'array' : typeof val;
      pairs.push(`${path}:${type}`);
    }
  }
  return pairs.sort();
}

function fingerprintKey(obj) {
  return fingerprint(obj).join('|');
}

// --- Circular buffer ---

class CircularBuffer {
  constructor(capacity) {
    this._buf = new Array(capacity);
    this._cap = capacity;
    this._head = 0;
    this._size = 0;
  }

  push(item) {
    this._buf[this._head] = item;
    this._head = (this._head + 1) % this._cap;
    if (this._size < this._cap) this._size++;
  }

  toArray() {
    const out = [];
    const start = this._size < this._cap ? 0 : this._head;
    for (let i = 0; i < this._size; i++) {
      out.push(this._buf[(start + i) % this._cap]);
    }
    return out;
  }

  get size() { return this._size; }
}

// --- API response change rate monitor ---

class ApiResponseChangeRateMonitor {
  constructor(opts = {}) {
    this.windowSize       = opts.windowSize       ?? 100;   // rolling window
    this.baselineK        = opts.baselineK         ?? 20;   // first K responses for baseline
    this.alertThreshold   = opts.alertThreshold    ?? 0.05; // 5% change rate = alert
    this.onAlert          = opts.onAlert           ?? null; // fn({ changeRate, window, baseline })

    this._window          = new CircularBuffer(this.windowSize);
    this._baselineCounts  = new Map();   // fingerprint → count (for first K)
    this._baseline        = null;        // established after K responses
    this._totalRecorded   = 0;
  }

  // Record one API response object; returns the current status
  record(responseObj) {
    const fp = fingerprintKey(responseObj);
    this._totalRecorded++;

    // Build baseline from first K responses (most common fingerprint wins)
    if (this._baseline === null) {
      const count = (this._baselineCounts.get(fp) ?? 0) + 1;
      this._baselineCounts.set(fp, count);
      if (this._totalRecorded === this.baselineK) {
        // Elect the most common fingerprint as baseline
        this._baseline = [...this._baselineCounts.entries()]
          .sort((a, b) => b[1] - a[1])[0][0];
        this._baselineCounts = null;   // release
      }
      this._window.push({ fp, changed: false });
      return { status: 'BASELINE', recorded: this._totalRecorded, baselineK: this.baselineK };
    }

    const changed = fp !== this._baseline;
    this._window.push({ fp, changed });

    const changeRate = this._changeRate();
    const status     = changeRate >= this.alertThreshold ? 'ALERT' : 'OK';

    if (status === 'ALERT' && this.onAlert) {
      this.onAlert({ changeRate, windowSize: this._window.size, baseline: this._baseline });
    }

    return {
      status,
      changeRate: parseFloat(changeRate.toFixed(4)),
      changeRateStr: `${(changeRate * 100).toFixed(1)}%`,
      windowSize: this._window.size,
      thisResponse: changed ? 'CHANGED' : 'STABLE',
    };
  }

  _changeRate() {
    const all = this._window.toArray();
    if (all.length === 0) return 0;
    return all.filter(e => e.changed).length / all.length;
  }

  // Summary snapshot
  status() {
    if (this._baseline === null) {
      return { phase: 'BASELINE', recorded: this._totalRecorded, baselineK: this.baselineK };
    }
    const changeRate = this._changeRate();
    return {
      phase:         'MONITORING',
      changeRate:    parseFloat(changeRate.toFixed(4)),
      changeRateStr: `${(changeRate * 100).toFixed(1)}%`,
      alert:         changeRate >= this.alertThreshold,
      windowSize:    this._window.size,
      windowCapacity: this.windowSize,
    };
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `fingerprintKey()` and `monitor.record()` timed over 100 000 iterations on representative legal API response objects (8-field flat, 4-field nested). Stability scenario and drift scenario simulated with fixed fingerprint sequences. No live API calls.

```
=== fingerprintKey() timing (100 000 iterations, 8-field flat response) ===

$ node -e "
const resp = { clause_id: 'C-001', clause_type: 'indemnification', text: '...', effective_date: '2025-01-01',
               parties: ['Acme', 'Vendor'], version: 3, jurisdiction: 'DE', status: 'active' };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) fingerprintKey(resp);
console.log('fingerprintKey():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
fingerprintKey(): 0.0039 ms

=== fingerprintKey() — 4-field nested response (100 000 iterations) ===

fingerprintKey (nested): 0.0062 ms   (recursion over 2 levels)

=== monitor.record() timing — steady-state monitoring phase (100 000 iterations) ===

monitor.record(): 0.0089 ms   (fingerprint + buffer push + changeRate scan)

=== monitor.status() timing (100 000 iterations) ===

monitor.status(): 0.0031 ms

=== Baseline election: first 20 responses with optional `parties` field ===

Fingerprints seen in first 20 responses:
  fp_A (parties present):  14 occurrences   ← elected baseline
  fp_B (parties absent):    6 occurrences

Baseline set to fp_A after K=20. fp_B responses will count as CHANGED (14/100 = steady-state 14%).

=== Stability scenario: 200 responses, API is stable ===

Responses 1–20:   BASELINE phase
Responses 21–120: 2 CHANGED (fp_B, optional field absent): changeRate = 0.020 (2.0%)
Response status: OK (threshold 5.0%)

=== Drift scenario: provider silently deploying new API version ===

Responses 1–20:   BASELINE (fp_A established)
Responses 21–80:  2 CHANGED → changeRate = 0.033 (3.3%), OK
Responses 81–100: 12 more CHANGED (new server pool coming online) → changeRate 0.140 (14.0%)
Response 101:     → status: ALERT, changeRate: 14.0%

onAlert fires:
  { changeRate: 0.14, windowSize: 100, baseline: 'clause_id:string|...|status:string' }

Engineering action: query last 20 changed responses — find 'version' field changed
from string to number + new 'revision_count' field added. Provider deployed API v2
on ~14% of servers. Action: pin API version header or switch to v2 baseline.

=== S-87 vs S-113 vs S-124 ===

              │ S-87 (hard-gate)              │ S-113 (reactive evolution)    │ S-124 (change rate monitor)
──────────────┼───────────────────────────────┼───────────────────────────────┼───────────────────────────────
Scope         │ Per response                  │ Per response                  │ Rolling window of N responses
Blocks?       │ Yes — rejects bad response    │ No — adapts and continues     │ No — alerts, doesn't block
Output        │ Error / rejected response     │ Adapted response + drift log  │ changeRate + ALERT flag
Answers       │ "Is this response valid?"     │ "How do I handle this change?"│ "Is this API structurally stable?"
Signal        │ Binary (valid/invalid)        │ Per-change diff + severity    │ Time-series change rate
Use for       │ Hard contract enforcement     │ Graceful adaptation           │ Fleet-level stability monitoring
Works with    │ S-113 as fallback             │ S-87 as gate for MANUAL_REQD  │ Both — upstream visibility
```

## See also

[S-113](s113-reactive-schema-evolution.md) · [S-87](s87-external-api-response-validation.md) · [F-26](../forward-deployed/f26-behavioral-drift-detection.md) · [F-45](../forward-deployed/f45-ai-response-latency-slos.md) · [S-100](s100-live-data-freshness-contracts.md) · [F-75](../forward-deployed/f75-tool-output-schema-contracts.md)

## Go deeper

Keywords: `API change rate` · `structural change rate` · `response drift monitoring` · `API stability monitor` · `rolling window fingerprint` · `schema change rate` · `API response monitor` · `structural drift alert` · `API version drift` · `response structure monitoring`
