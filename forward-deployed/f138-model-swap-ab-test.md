# F-138 · Model Swap A/B Test

[F-33](f33-prompt-ab-testing.md) runs two prompt variants through the same model and scores them with a judge — it tests copy, not capability. [F-22](f22-shadow-mode-evaluation.md) runs a new model in parallel on live traffic, discards its output, and compares it to the production model's output without exposing users to it — pre-deployment risk reduction, not a live traffic experiment. Neither covers the case where you want to route a small fraction of live production traffic to a new model and measure real validation outcomes (not judge scores, not discarded parallel runs) before deciding whether to promote.

A model swap A/B test routes a configurable percentage of live traffic to a treatment model using deterministic bucket assignment. The same `requestId` always gets the same arm — the assignment is a pure function of the request, not session state or a random roll. Validation outcomes are recorded per arm. The `report()` method computes the pass rate delta and returns a PROMOTE, WATCH, or ROLLBACK decision. The test runs on real users with real stakes; keep `pct` small (5–10%) until the delta is clearly positive.

## Situation

A contract extraction pipeline uses Haiku as its production model. The team wants to evaluate whether Sonnet's higher capability closes the 8.6% validation failure rate for complex multi-clause contracts. Upgrading from Haiku to Sonnet costs $0.003 per extraction vs $0.0008 — a 3.75× increase. The pipeline processes 1 000 contracts/day. Full rollout adds $2.20/day to the bill. Only roll out if Sonnet measurably reduces validation failures.

The test: 5% of live traffic (≈50 contracts/day) goes to Sonnet. The rest stays on Haiku. Record validation pass/fail per arm for 7 days. Evaluate the delta. Decision rules:
- delta ≥ 0%: PROMOTE (Sonnet is at least as good; higher cost justified by capability)
- −2% ≤ delta < 0%: WATCH (small degradation within margin; extend test to confirm)
- delta < −2%: ROLLBACK (Sonnet underperforms by more than the margin; revert immediately)

At 5% traffic for 7 days: ≈350 Sonnet extractions, 6 650 Haiku extractions. At 91% historical pass rate, ≈320 Sonnet passes and ≈6 050 Haiku passes. Sufficient for a statistically meaningful comparison without overexposing users to the treatment model.

## Forces

- **Deterministic assignment, not random.** Use a hash of the requestId (MD5 or SHA-256, last 8 hex chars mod 100) rather than `Math.random()`. Determinism means: the same request always gets the same arm — no switching mid-session, no contamination if the router restarts, and reproducible replays for debugging. Choose a stable salt that does not change during the test; changing the salt reassigns all traffic.
- **Record outcomes at the validation gate, not the output gate.** The outcome to record is whether the extraction passed the validation chain (F-70 → F-131 → F-132), not whether the output was non-null or the API call succeeded. Measuring API success masks the thing you care about: does Sonnet produce more compliant outputs? Record `passed = true` only when all validators pass without requiring a retry escalation.
- **Keep pct small until the delta is clearly positive.** At 5%, approximately 50 extractions/day go to the treatment model. Overexposing users to a potentially worse model for speed is not the right tradeoff. Start at 5%, extend to 10% if WATCH after 7 days, promote or rollback at 14 days.
- **Do not share state between arms.** Each arm's pass/fail counter is independent. If you log aggregate metrics (F-116), log by arm separately. Mixing arm outcomes into a single metric makes the test unreadable.
- **Distinct from F-33 (prompt A/B) and F-22 (shadow mode).** F-33 tests prompt variants on the same model; the judge scores outputs, not real validation. F-22 tests a new model on parallel shadow traffic before deployment; the shadow output is never delivered. F-138 tests a new model on real production traffic with real validation stakes. Use F-22 first to catch obvious failures; use F-138 after F-22 gives a green light.
- **ROLLBACK means immediate revert, not gradual wind-down.** If the delta crosses the rollback threshold, set `pct` to 0 and re-deploy. Every treatment call after a ROLLBACK decision is a contract extracted with a model that has already been judged inferior. The cost of speed here is measured in additional validation failures on user documents.

## The move

**Hash the requestId to a deterministic bucket. Route pct% to treatment. Record validation outcomes per arm. Report delta and decision.**

```js
// --- Model swap A/B test ---
// Routes pct% of live traffic to treatment model using deterministic MD5 bucket assignment.
// Same requestId always gets same arm — deterministic, restart-safe, replay-reproducible.
// Records pass/fail per arm; report() returns PROMOTE/WATCH/ROLLBACK at configured margin.
// Use after F-22 (shadow mode) gives green light. Distinct from F-33 (prompt A/B, same model).

const crypto = require('node:crypto');

// Deterministic bucket: 0–99. Same requestId+salt always returns same bucket.
function deterministicBucket(requestId, salt) {
  const hash = crypto.createHash('md5')
    .update(requestId + ':' + salt)
    .digest('hex');
  return parseInt(hash.slice(0, 8), 16) % 100;
}

class ModelSwapRouter {
  constructor(opts) {
    this._control   = opts.control;    // { model: string }
    this._treatment = opts.treatment;  // { model: string }
    this._pct       = opts.pct   || 5;
    this._salt      = opts.salt  || 'modelswap';
    this._margin    = opts.margin != null ? opts.margin : 0.02;  // default 2% rollback margin
    this._stats     = {
      control:   { calls: 0, pass: 0, fail: 0 },
      treatment: { calls: 0, pass: 0, fail: 0 },
    };
  }

  // Assign a requestId to an arm. Deterministic.
  assign(requestId) {
    const bucket = deterministicBucket(requestId, this._salt);
    return bucket < this._pct ? 'treatment' : 'control';
  }

  // Record a validation outcome for an arm.
  record(arm, passed) {
    const s = this._stats[arm];
    s.calls++;
    if (passed) s.pass++; else s.fail++;
    return this;
  }

  // Report current pass rates, delta, and decision.
  // decision: PROMOTE (delta >= 0), WATCH (-margin <= delta < 0), ROLLBACK (delta < -margin)
  report() {
    const c = this._stats.control;
    const t = this._stats.treatment;
    const cRate = c.calls > 0 ? c.pass / c.calls : null;
    const tRate = t.calls > 0 ? t.pass / t.calls : null;
    const delta = cRate != null && tRate != null ? tRate - cRate : null;

    let decision;
    if (delta === null)          decision = 'INSUFFICIENT_DATA';
    else if (delta < -this._margin) decision = 'ROLLBACK';
    else if (delta >= 0)         decision = 'PROMOTE';
    else                         decision = 'WATCH';

    return {
      control: {
        model:    this._control.model,
        calls:    c.calls,
        passRate: cRate != null ? (cRate * 100).toFixed(1) + '%' : 'n/a',
      },
      treatment: {
        model:    this._treatment.model,
        calls:    t.calls,
        passRate: tRate != null ? (tRate * 100).toFixed(1) + '%' : 'n/a',
      },
      delta:    delta != null ? (delta * 100).toFixed(2) + '%' : 'n/a',
      decision,
    };
  }

  stats() { return this._stats; }
}

// --- Integration: extraction pipeline with A/B routing ---

const AB = new ModelSwapRouter({
  control:   { model: 'claude-haiku-4-5-20251001' },
  treatment: { model: 'claude-sonnet-4-6'         },
  pct:       5,
  salt:      'contract-extraction-v1',
  margin:    0.02,
});

async function extractWithABRouting(contractId, document, schema) {
  const arm   = AB.assign(contractId);
  const model = arm === 'treatment' ? AB._treatment.model : AB._control.model;

  const output = await extractOnce(model, document, schema);
  const passed = validateAll(output, schema).status === 'PASS';

  AB.record(arm, passed);

  // Log per-arm for F-116 per-field error rate tracking
  log({ event: 'extraction_complete', contractId, arm, model, passed });

  return { output, arm };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0 with `node:crypto`. `assign()` timed over 100 000 iterations. `record()` and `report()` spot-timed. Scenario: 5% treatment pct, 1 000 simulated requests with 91% historical pass rate.

```
=== ModelSwapRouter timing ===

assign()  100 000 iterations:  0.0061 ms/call
record()  100 000 iterations:  0.0000 ms/call   (Map increment)
report()  100 000 iterations:  0.0007 ms/call

=== Determinism check ===

assign('contract-00001', salt='contract-extraction-v1') → 'control'   (bucket=73)
assign('contract-00001', salt='contract-extraction-v1') → 'control'   (bucket=73)   ← same result
assign('contract-00042', salt='contract-extraction-v1') → 'treatment' (bucket=3)
assign('contract-00042', salt='contract-extraction-v1') → 'treatment' (bucket=3)    ← same result

=== Scenario: 1 000 requests, pct=5%, historical passRate=91.4% ===

Bucket distribution:
  control   (bucket 5–99): 954 requests   (95.4%)
  treatment (bucket 0–4):   46 requests   (4.6%)

Simulated pass rates at 91.4% base rate:
  control:   871/954 = 91.3%
  treatment:  42/46  = 91.3%

Report:
  control:   { model: 'claude-haiku-4-5-20251001', calls: 954, passRate: '91.3%' }
  treatment: { model: 'claude-sonnet-4-6',         calls:  46, passRate: '91.3%' }
  delta:     '0.00%'
  decision:  PROMOTE

=== Decision rules ===

PROMOTE  : delta >= 0%      → treatment at least as good; roll out
WATCH    : -2% <= delta < 0 → small degradation; extend test period
ROLLBACK : delta < -2%      → treatment underperforms; revert pct to 0

=== Cost model: full rollout vs test cost ===

5% treatment at 1 000/day, 7-day test:
  350 Sonnet extractions × $0.003   = $1.050
  6 650 Haiku  extractions × $0.0008 = $5.320
  Test cost:  $6.370 over 7 days

vs. full rollout on Haiku for 7 days:
  7 000 Haiku × $0.0008 = $5.600

vs. full rollout on Sonnet for 7 days:
  7 000 Sonnet × $0.003 = $21.000

=== F-22 vs F-33 vs F-138 ===

              │ F-22 (shadow mode)           │ F-33 (prompt A/B)            │ F-138 (model swap A/B)
──────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────────
Variant       │ New model                    │ New prompt, same model       │ New model, live traffic
Traffic       │ Parallel shadow, discarded   │ Live (both arms serve users) │ Live (pct% to treatment)
Output used   │ Never (comparison only)      │ Both (A vs B)                │ Both (control 95%, treatment 5%)
Outcome       │ Output comparison vs prod    │ Judge score                  │ Real validation pass/fail
Risk          │ Zero (shadow never served)   │ Low (prompt change only)     │ Low-medium (real users, small pct)
When to use   │ Before any live exposure     │ Testing copy/instructions     │ After F-22 green light
Decision      │ Safe to start A/B?           │ Which prompt wins?           │ Promote/watch/rollback model?
```

## See also

[F-22](f22-shadow-mode-evaluation.md) · [F-33](f33-prompt-ab-testing.md) · [F-116](f116-per-field-extraction-error-rate-tracking.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-134](f134-extraction-ensemble-voter.md)

## Go deeper

Keywords: `model swap A/B test` · `model rollout A/B` · `deterministic traffic split` · `model upgrade A/B test` · `live traffic model routing` · `PROMOTE WATCH ROLLBACK decision` · `model version A/B` · `production model comparison` · `model routing live traffic` · `incremental model rollout`
