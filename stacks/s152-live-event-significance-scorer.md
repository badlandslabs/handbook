# S-152 · Live Event Significance Scorer

[S-104](s104-event-stream-agent-integration.md) filters a live event stream with binary rules: an event either meets one of the conditions (velocity exceeds threshold, value delta exceeds threshold, geo flag is set) or it is dropped. Binary rules are fast to write and easy to audit. They also miss the case where no single condition fires but two or three moderate signals arrive together — and the combination is exactly what makes an event worth dispatching to the agent.

A live event significance scorer replaces the binary pass/fail with a continuous 0.0–1.0 score. Each incoming event is measured against a set of named feature extractors. Each extractor returns a raw value that is clamped to [0, 1]. The clamped values are weighted and summed, then normalized by the total weight. If the resulting score exceeds a threshold (default 0.30), the event is dispatched. Below threshold, it is discarded. The score is returned with a per-feature breakdown for observability.

The key gap from S-104: a fraud signal with `velocity=0.4, value_change=0.4, geo_anomaly=0` produces no binary match (each is below the hardcoded threshold for its own rule). The weighted sum `0.4×0.50 + 0.4×0.30 + 0×0.20 = 0.32` exceeds the 0.30 dispatch threshold. The combination fires. S-104 misses it; this scorer catches it.

## Situation

A fraud detection agent watches a real-time transaction event stream. Three binary rules cover obvious cases: velocity spike (>18 tx/60s), large value swing (>$500 delta), or new country. Between sessions, these rules miss the soft-signal case: a customer transacts 16 times in 60 seconds, moves $120 (not $500), from a known country. Each signal is elevated but individually below threshold. Combined score: `(0.8×0.50) + (0.24×0.30) + (0×0.20) = 0.472 > 0.30`. Dispatched.

The breakdown returned per event (`velocity_factor: {clamped: 0.8, weighted: 0.40}, value_change_pct: {clamped: 0.24, weighted: 0.072}, geo_anomaly: {clamped: 0, weighted: 0}`) identifies which features drove the dispatch, which feeds directly into the agent's alert summary and into the per-feature weight calibration cycle.

## Forces

- **Feature weights encode policy, not statistics.** Weights are assigned by the team based on the consequence of missing a signal, not by optimizing on historical data. `velocity_factor` weight=0.50 means "we care most about speed of transaction accumulation." Change weights when business priorities change, not when the model underperforms.
- **Clamp before weighting, not after.** `extractor()` may return any float. Clamping to [0, 1] before applying weights prevents a single runaway feature from dominating the sum regardless of what the other features say. An extractor that returns `10.0` is a bug; clamping makes the scorer robust to it.
- **Threshold 0.30 is a starting point, not a law.** At 0.30, the scorer dispatches when weighted signal is roughly 30% of maximum. In a high-precision context (where agent compute per dispatch is expensive), raise to 0.50. In a high-recall context (where misses are costly), lower to 0.15. Track `dispatch_rate` over 7 days; if it's above 60%, raise the threshold.
- **Score breakdown is required for trust.** A dispatcher without a breakdown is a black box. The `breakdown` object in the return value is what makes the score debuggable: when an event is dispatched that a human would have dropped (or vice versa), the per-feature breakdown shows exactly where the calibration is wrong.
- **Compose with S-104's binary rules, not replace them.** Binary rules catch the easy cases (velocity=25, far above any threshold) in O(1). Use binary rules as a fast pre-filter: if any rule fires hard, dispatch immediately. Run the scorer only when no binary rule fires — it handles the combination cases the binary rules miss. Two-stage: binary OR scored ≥ threshold → dispatch.
- **Extractor errors should return 0, not throw.** An extractor that raises an exception because an event field is missing will halt the scoring loop. Wrap extractor calls in try/catch; on error, treat the feature as 0 (not present). Log the error for later review but do not drop the event entirely — other features may still produce a sufficient score.

## The move

**Define features as (name, extractor, weight) triples. Score each event by extracting and weighting each feature. Dispatch when score ≥ threshold.**

```js
// --- Live event significance scorer ---
// Each feature: { name, extractor(event, context) → 0..1, weight }
// score() returns { score, dispatch, breakdown, threshold }
// Compose with binary rules: dispatch on any hard binary hit; score the rest.

class EventSignificanceScorer {
  constructor(features, opts = {}) {
    this._features    = features;
    this._totalWeight = features.reduce((s, f) => s + f.weight, 0);
    this._threshold   = opts.threshold ?? 0.30;
  }

  score(event, context) {
    let sum = 0;
    const breakdown = {};
    for (const f of this._features) {
      let raw;
      try { raw = f.extractor(event, context); }
      catch (_) { raw = 0; }                            // missing field → silent zero
      const clamped = Math.max(0, Math.min(1, raw));
      breakdown[f.name] = {
        clamped:  parseFloat(clamped.toFixed(3)),
        weighted: parseFloat((clamped * f.weight).toFixed(3)),
      };
      sum += clamped * f.weight;
    }
    const score = sum / this._totalWeight;
    return {
      score:     parseFloat(score.toFixed(4)),
      dispatch:  score >= this._threshold,
      breakdown,
      threshold: this._threshold,
    };
  }
}

// --- Fraud detection scorer ---
// Context shape: { knownCountries: string[] }
// Event shape:   { txCount60s, valueDelta, country }

const FRAUD_SCORER = new EventSignificanceScorer([
  {
    name:      'velocity_factor',
    weight:    0.50,
    extractor: (ev) => Math.min(1, ev.txCount60s / 20),       // 20 tx/60s = fully saturated
  },
  {
    name:      'value_change_pct',
    weight:    0.30,
    extractor: (ev) => Math.min(1, Math.abs(ev.valueDelta) / 500),  // $500 = fully saturated
  },
  {
    name:      'geo_anomaly',
    weight:    0.20,
    extractor: (ev, ctx) => ctx.knownCountries.includes(ev.country) ? 0 : 1,
  },
], { threshold: 0.30 });

// --- Integration: binary pre-filter + significance score ---
// Hard binary rules for obvious cases; scorer for soft-signal combinations.

function shouldDispatch(event, context) {
  // Fast path: hard binary hits dispatch immediately
  if (event.txCount60s > 22) return { dispatch: true, reason: 'BINARY_VELOCITY' };
  if (Math.abs(event.valueDelta) > 600) return { dispatch: true, reason: 'BINARY_VALUE' };
  if (event.flagged) return { dispatch: true, reason: 'BINARY_FLAG' };

  // Slow path: weighted multi-signal score
  const result = FRAUD_SCORER.score(event, context);
  return { dispatch: result.dispatch, reason: 'SCORED', score: result.score, breakdown: result.breakdown };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `score()` timed over 100 000 iterations with 3 features. Event values are representative of a real-time financial transaction stream.

```
=== EventSignificanceScorer timing (100 000 iterations) ===

score() — 3 features:    0.0048 ms per call

=== Feature weights: velocity=0.50, value_change=0.30, geo_anomaly=0.20 ===
Threshold: 0.30

=== Scenario A: Velocity spike (txCount60s=16, valueDelta=$120, country=US) ===

{ score: 0.472, dispatch: true }
breakdown:
  velocity_factor:  clamped=0.80  weighted=0.400   ← primary driver
  value_change_pct: clamped=0.24  weighted=0.072
  geo_anomaly:      clamped=0.00  weighted=0.000

Dispatched. S-104 binary rule would miss (threshold txCount60s > 22).
Weighted combination catches it.

=== Scenario B: Routine event (txCount60s=3, valueDelta=$45, country=US) ===

{ score: 0.102, dispatch: false }
breakdown:
  velocity_factor:  clamped=0.15  weighted=0.075
  value_change_pct: clamped=0.09  weighted=0.027
  geo_anomaly:      clamped=0.00  weighted=0.000

Not dispatched. Low signal on all three features.

=== Scenario C: Geo anomaly only (txCount60s=3, valueDelta=$45, country=RU) ===

{ score: 0.302, dispatch: true }
breakdown:
  velocity_factor:  clamped=0.15  weighted=0.075
  value_change_pct: clamped=0.09  weighted=0.027
  geo_anomaly:      clamped=1.00  weighted=0.200   ← single strong signal

Dispatched. Single-feature hard anomaly crosses threshold even with low others.
A binary rule for 'unknown country' would also catch this — both agree.

=== Scenario D: Multi-signal moderate — no single binary rule fires ===

txCount60s=8, valueDelta=$200, country=US

{ score: 0.320, dispatch: true }
breakdown:
  velocity_factor:  clamped=0.40  weighted=0.200
  value_change_pct: clamped=0.40  weighted=0.120
  geo_anomaly:      clamped=0.00  weighted=0.000

Dispatched. 0.40 + 0.40 + 0 = 0.320 > 0.30 threshold.
Each signal individually below any binary threshold.
Combination caught only by the scorer.

=== Batch (1000 events, random parameters) ===

1000 events scored in 5.81 ms.
dispatch_rate: 83 % — threshold may need tuning upward for this event distribution.

=== S-104 vs S-152 ===

              │ S-104 (binary rules)              │ S-152 (significance scorer)
──────────────┼───────────────────────────────────┼────────────────────────────────────
Logic         │ IF velocity > N OR delta > M       │ Weighted sum of N feature scores
Miss          │ Moderate on multiple signals        │ Nothing with combined score < threshold
Tuning        │ Edit thresholds per rule           │ Edit feature weights + global threshold
Observability │ Which rule fired                   │ Score + per-feature breakdown
Compose       │ First: binary fast path            │ Second: soft-signal fallback
Setup cost    │ Minutes per rule                   │ Feature engineering per domain
```

## See also

[S-104](s104-event-stream-agent-integration.md) · [S-137](s137-multi-source-field-level-merge.md) · [F-98](../forward-deployed/f98-live-source-fanout.md) · [F-104](../forward-deployed/f104-live-source-health-monitor.md) · [S-124](s124-api-response-change-rate-monitor.md) · [F-114](../forward-deployed/f114-source-response-time-slos.md)

## Go deeper

Keywords: `live event significance scorer` · `event stream dispatch threshold` · `weighted event scoring` · `multi-signal event detection` · `soft threshold event filter` · `agent event dispatch scoring` · `event feature weighting` · `real-time event significance` · `combination signal detection` · `event stream significance filtering`
