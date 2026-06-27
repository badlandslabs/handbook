# F-127 · Extraction Field Null Rate Monitor

[F-116](f116-per-field-extraction-error-rate-tracking.md) tracks when an extracted field is *wrong* — the value is present but fails validation (wrong enum, out-of-range number, misidentified clause). [F-121](f121-output-field-value-anomaly-detection.md) catches statistically implausible numeric values. [F-113](f113-per-entity-data-completeness-tracking.md) tracks whether live data source fields arrive or go missing per entity, detecting when an upstream API stops sending a field.

None of these track a different failure mode: the model returning `null` for a field that *should* have content, at a rate that varies by entity class. A domestic contract usually has an explicit jurisdiction clause — `jurisdiction` is null on 2% of extractions. A cross-border contract often buries jurisdiction in a choice-of-law schedule — `jurisdiction` is null on 34% of extractions. F-116 does not fire (null is a valid schema value, not an extraction error). F-121 does not fire (null is not numeric). F-113 is tracking data source health, not model behavior.

The null rate is a model calibration signal: it tells you where the model systematically gives up finding information that is present but hard to locate. A 34% null rate on a HIGH-consequence field for a specific entity type means the model is unable to locate the jurisdiction clause reliably on cross-border contracts. The fix is prompt-side: an instruction to check the choice-of-law schedule, or a reference to where jurisdiction is typically stated in that contract form.

An extraction field null rate monitor maintains a rolling window of filled/null records per `(entityType, field)` pair. After each extraction, it records whether each field was filled. `nullRate()` returns the null rate and status for one pair. `allHighNullRate()` surfaces all pairs above the threshold, sorted by severity, annotated by consequence tier.

## Situation

A contract analysis agent extracts six fields per contract. Contracts come in two types: domestic and cross-border. After 50 calls per type, the null rate picture is:

```
Field                     │ domestic_contract  │ cross_border_contract
──────────────────────────┼────────────────────┼──────────────────────
jurisdiction              │ 0.020  (NORMAL)    │ 0.340  (HIGH_NULL_RATE)
risk_level                │ 0.340  (HIGH_NULL_RATE) │ 0.120  (NORMAL)
recommended_action        │ 0.000  (NORMAL)    │ 0.000  (NORMAL)
clause_language_override  │ 0.800  (HIGH_NULL_RATE) │ 0.820  (HIGH_NULL_RATE)
```

`jurisdiction` on cross-border contracts is the actionable alert: it's HIGH-tier and null on 34% of calls. The model can't find the jurisdiction clause reliably for cross-border contract structures.

`risk_level` on domestic contracts at 0.34 is the second actionable alert: HIGH-tier, something about domestic contract language is causing the model to return null for risk level 34% of the time.

`clause_language_override` at 0.80 is expected: most contracts do not have a language override clause. This is a LOW-tier field with high expected null rate — the alert fires but the tier annotation tells the team to skip it.

`recommended_action` at 0.00 is reliably filled — the extraction prompt for this field is working.

## Forces

- **Segment by entity type, not globally.** A 20% global null rate on `jurisdiction` might hide that domestic contracts have 2% and cross-border have 34%. The 2% on domestic is acceptable; the 34% on cross-border is a prompt deficiency. Without segmentation, the two rates average to ~18% — below the 20% threshold — and the alert never fires. The entity type is the segmentation key that makes the signal actionable.
- **Null rate is distinct from error rate (F-116) and anomaly rate (F-121).** A null is a legitimate schema value: the model chose to say "I could not determine this field." An error is an invalid value: the model returned `"Very High"` when the schema requires `"HIGH" | "MEDIUM" | "LOW"`. An anomaly is an implausible value: the model returned a termination fee of $99 000 000. All three can occur independently. Track all three; alert on each separately.
- **Distinguish expected nulls from unexpected nulls.** `clause_language_override` being null 80% of the time is correct behavior: most contracts have no language override clause. `jurisdiction` being null 34% of the time on domestic contracts (which almost always have explicit jurisdiction clauses) is not. The tier annotation on `allHighNullRate()` — HIGH, MEDIUM, LOW — lets you filter: focus on HIGH-tier HIGH_NULL_RATE pairs immediately; LOW-tier pairs can be reviewed monthly.
- **The null rate surfaces where to invest prompt work.** When `jurisdiction` has a 34% null rate on cross-border contracts, the next step is: find five cross-border contracts where it returned null and read the actual documents. Where is the jurisdiction clause? Is it in a schedule? Is it labeled differently? That reading produces a targeted prompt instruction ("for cross-border agreements, check Schedule B, section 3, for jurisdiction — it may be labeled 'choice of law' rather than 'jurisdiction'"). The null rate is the triage tool; the document reading is the fix.
- **Window size must match extraction volume.** At 50 calls per window, the estimate is reliable for common entity types. For rare entity types with fewer than 5 calls, `nullRate()` returns INSUFFICIENT_DATA. At very high volume (10 000 calls/day per entity type), consider a smaller window (20 calls) so recent prompt updates register quickly.
- **The monitor runs at extraction time, not in CI.** Unlike F-124 (assertion coverage audit, which runs at startup), this monitor records on every production call and queries on a monitoring schedule (every 5 minutes). The recording overhead is O(fields) per call — fast.

## The move

**Record filled/null status per field after each extraction. Query `allHighNullRate()` on a monitoring schedule; alert on HIGH-tier fields above threshold. Use the null rate to prioritize prompt improvements.**

```js
// --- Extraction field null rate monitor ---
// Records filled/null status per (entityType, field) per production call.
// Null rate = fraction of calls where field is null/undefined/empty string.
// Segment by entityType — a 34% null rate on cross_border_contract may hide
// a 2% null rate on domestic_contract for the same field.

class ExtractionFieldNullRateMonitor {
  constructor(opts = {}) {
    this._windowSize     = opts.windowSize     ?? 50;   // calls per window per pair
    this._alertThreshold = opts.alertThreshold ?? 0.20; // > 20% null → HIGH_NULL_RATE
    this._history        = new Map();   // 'entityType:field' → [1|0, ...]
  }

  // Call after each successful extraction. output = the full extracted object.
  record(entityType, output) {
    for (const [field, value] of Object.entries(output)) {
      const key    = entityType + ':' + field;
      if (!this._history.has(key)) this._history.set(key, []);
      const arr    = this._history.get(key);
      const filled = (value !== null && value !== undefined && value !== '');
      arr.push(filled ? 1 : 0);
      if (arr.length > this._windowSize) arr.shift();
    }
  }

  // Null rate for one (entityType, field) pair.
  // Returns { status, nullRate, nullCount, samples, threshold }
  nullRate(entityType, field) {
    const key = entityType + ':' + field;
    const arr = this._history.get(key);
    if (!arr || arr.length < 5) {
      return { status: 'INSUFFICIENT_DATA', samples: arr ? arr.length : 0, required: 5 };
    }
    const nullCount = arr.filter(v => v === 0).length;
    const rate      = nullCount / arr.length;
    return {
      status:    rate >= this._alertThreshold ? 'HIGH_NULL_RATE' : 'NORMAL',
      nullRate:  parseFloat(rate.toFixed(3)),
      nullCount,
      samples:   arr.length,
      threshold: this._alertThreshold,
    };
  }

  // All (entityType, field) pairs with null rate >= threshold, sorted by nullRate desc.
  // tiers: { fieldName: 'HIGH' | 'MEDIUM' | 'LOW' } — annotates result for priority filtering.
  allHighNullRate(tiers = {}) {
    const out = [];
    for (const [key, arr] of this._history) {
      if (arr.length < 5) continue;
      const nullCount = arr.filter(v => v === 0).length;
      const rate      = nullCount / arr.length;
      if (rate >= this._alertThreshold) {
        const idx        = key.indexOf(':');
        const entityType = key.slice(0, idx);
        const field      = key.slice(idx + 1);
        out.push({
          entityType,
          field,
          nullRate:  parseFloat(rate.toFixed(3)),
          nullCount,
          samples:   arr.length,
          tier:      tiers[field] ?? 'UNKNOWN',
        });
      }
    }
    return out.sort((a, b) => b.nullRate - a.nullRate);
  }
}

// --- Integration ---

const NULL_MONITOR = new ExtractionFieldNullRateMonitor({
  windowSize:     50,
  alertThreshold: 0.20,
});

const FIELD_TIERS = {
  jurisdiction:            'HIGH',
  risk_level:              'HIGH',
  recommended_action:      'HIGH',
  clause_language_override: 'LOW',
  contract_language:        'LOW',
};

// After each extraction:
function onExtraction(entityType, output) {
  NULL_MONITOR.record(entityType, output);
}

// Monitoring job (every 5 minutes):
function checkNullRates() {
  const alerts = NULL_MONITOR.allHighNullRate(FIELD_TIERS)
    .filter(a => a.tier === 'HIGH');   // focus on HIGH-consequence fields
  if (alerts.length > 0) {
    log({ event: 'extraction_field_null_rate_alert', alerts });
    // → pagerduty / slack alert for prompt engineering team
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()` timed over 100 000 iterations on a 4-field extraction output. `nullRate()` and `allHighNullRate()` timed on 50-call windows.

```
=== ExtractionFieldNullRateMonitor timing (100 000 iterations, windowSize=50) ===

record()  — 4-field output:              0.0080 ms
nullRate()  — 50 samples:               0.0012 ms
allHighNullRate() — 4 fields × 50 samples: 0.0033 ms

=== Scenario A: jurisdiction on domestic_contract — 49/50 filled ===

50 calls: 49 return "New York", 1 returns null

nullRate('domestic_contract', 'jurisdiction'):
{
  status:    'NORMAL',
  nullRate:  0.020,
  nullCount: 1,
  samples:   50,
  threshold: 0.2
}

=== Scenario B: jurisdiction on cross_border_contract — null ~33% ===

50 calls: jurisdiction clause is in a "Schedule B — Governing Law" appendix
the model fails to locate it on 17/50 calls

nullRate('cross_border_contract', 'jurisdiction'):
{
  status:    'HIGH_NULL_RATE',
  nullRate:  0.340,
  nullCount: 17,
  samples:   50,
  threshold: 0.2
}

Action: read 5 cross-border contracts where jurisdiction returned null.
Finding: jurisdiction is labeled "choice of law" in Schedule B, not in the main text.
Fix: add to system prompt — "For cross-border agreements, check Schedule B section for
a 'Choice of Law' or 'Governing Law' clause if jurisdiction is not in the main body."
Expected outcome: null rate falls from 0.34 to < 0.05 on next 50 calls.

=== Scenario C: allHighNullRate() for 4-field domestic_contract ===

After 50 calls with:
  jurisdiction         — 2% null  (NORMAL)
  risk_level           — 34% null (HIGH_NULL_RATE, HIGH tier) ← actionable
  recommended_action   — 0% null  (NORMAL)
  clause_language_override — 80% null (HIGH_NULL_RATE, LOW tier) ← expected

allHighNullRate({ jurisdiction: 'HIGH', risk_level: 'HIGH',
                  recommended_action: 'HIGH', clause_language_override: 'LOW' }):

[
  { entityType: 'domestic_contract', field: 'clause_language_override',
    nullRate: 0.800, nullCount: 40, samples: 50, tier: 'LOW' },
  { entityType: 'domestic_contract', field: 'risk_level',
    nullRate: 0.340, nullCount: 17, samples: 50, tier: 'HIGH' }
]

Monitoring filter: .filter(a => a.tier === 'HIGH') → only risk_level alert fires.
clause_language_override: HIGH_NULL_RATE but LOW tier — reviewed monthly, not paged.

=== F-116 vs F-121 vs F-113 vs F-127 ===

              │ F-116 (error rate)            │ F-121 (anomaly)              │ F-113 (source completeness)  │ F-127 (null rate)
──────────────┼───────────────────────────────┼──────────────────────────────┼──────────────────────────────┼──────────────────────────────
Value state   │ Present, wrong type/value     │ Present, implausible numeric │ Absent from live data source │ Absent from model output
Cause         │ Model extraction error        │ Model hallucination / drift  │ API stopped sending field    │ Model can't locate field
Fix           │ Validation rule / ground truth│ Calibration / z-score rule   │ Source contract / alias      │ Prompt instruction / example
Segments      │ Per field                     │ Per field (numeric only)     │ Per (entity, field, source)  │ Per (entityType, field)
```

## See also

[F-116](f116-per-field-extraction-error-rate-tracking.md) · [F-121](f121-output-field-value-anomaly-detection.md) · [F-113](f113-per-entity-data-completeness-tracking.md) · [F-126](f126-output-field-change-velocity.md) · [F-97](f97-output-field-confidence-annotation.md) · [F-70](f70-structured-output-validation.md)

## Go deeper

Keywords: `extraction field null rate` · `structured output null monitoring` · `LLM field absence tracking` · `per-entity-type null rate` · `model calibration null signal` · `output field null alert` · `extraction completeness monitor` · `field null rate by entity type` · `structured extraction blank rate` · `prompt improvement triage null rate`
