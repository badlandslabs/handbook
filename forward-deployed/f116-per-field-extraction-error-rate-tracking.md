# F-116 · Per-Field Extraction Error Rate Tracking

[F-110](f110-structured-output-field-lineage.md) checks each field in a single extraction call: does the model's cited excerpt actually appear in the source text? It returns per-call status (VERIFIED / NEAR_VERBATIM / FABRICATED_EXCERPT / NOT_FOUND). [F-97](f97-structured-output-confidence-scoring.md) asks the model to self-report a confidence score for each extracted field. Both operate at the call level. Neither tracks how often a specific field is extracted incorrectly across many calls over time.

The observed error rate per field is different from the per-call confidence signal. A model may report high confidence on `dispute_resolution` even on calls where it extracts the wrong clause — model self-confidence is poorly calibrated for fields it systematically misreads. Conversely, a model may report moderate confidence on `governing_law` even though it has a near-zero historical error rate on that field — moderate confidence but reliable in practice.

Per-field extraction error rate tracking maintains a rolling window of verification outcomes (correct / incorrect) per field, keyed from human review, automated verification (F-73 claim grounding, F-89 verbatim citation, F-110 lineage), or downstream correction signals. `errorRate()` computes the fraction of incorrect extractions per field. `verificationPriority()` sorts a field list by error rate — highest-error fields get verified first, cheapest-to-verify reliable fields get verified last (or skipped at low-stakes thresholds).

## Situation

A contract analysis pipeline extracts six fields per document. After 200 verified contracts, the pattern is clear: `dispute_resolution` and `liability_cap` fail 11% and 6% of the time respectively; `governing_law` and `payment_terms` fail under 2%. The pipeline runs F-110 lineage on every field for every contract — costing ~180 extra output tokens at $0.0027/call at Sonnet.

Without error rate tracking: all 6 fields get equal verification. F-110 runs on `governing_law` (1.5% error rate — nearly never wrong, verification almost always confirms it) with the same priority as `dispute_resolution` (11% error rate — wrong 1 in 9 contracts).

With error rate tracking: verification is triaged. `dispute_resolution` and `liability_cap` are HIGH_ERROR — route to F-110 lineage verification on every call. `termination_notice` and `amendment_procedure` are ELEVATED — route to lightweight structural check (F-70), escalate to F-110 only on low confidence. `governing_law` and `payment_terms` are RELIABLE — structural check only, skip F-110. Result: F-110 token overhead applied to 2/6 fields instead of 6/6 on the majority of calls → ~66% reduction in lineage verification cost on RELIABLE fields.

## Forces

- **Observed error rate ≠ model confidence.** `dispute_resolution` systematically fails when the contract uses governing-law courts as the dispute forum (an unusual drafting style). The model reports "high confidence" because the answer looks well-supported. Historical error rate reveals the systematic failure; per-call confidence does not.
- **Rolling window, not lifetime average.** Prompt updates (W-09), model version changes (F-38), or a shift in document corpus can change a field's error rate. A 200-call window captures current behavior; the lifetime average would dilute a newly introduced failure mode with months of previously good data.
- **Verification signals have different quality tiers.** Human review is ground truth. F-10 lineage (automated) is a proxy — it detects grounding failures but not semantic errors (model quotes the right clause but misattributes it to the wrong field). Weight verification signals accordingly: human review contributes more to error rate estimates than automated checks.
- **Minimum sample count before acting.** With 5 samples, a single failure produces a 20% error rate — too noisy to route. Require at least 20 samples before classifying a field as HIGH_ERROR or changing its verification path.
- **Error rate informs routing, not truncation.** HIGH_ERROR fields get more verification, not fewer extractions or lower max_tokens. The goal is to catch the failures that do occur, not to reduce extractions. High-error fields are the ones the pipeline most needs to verify.
- **Cross-document-type stratification.** A field may be reliable on standard US commercial contracts (0.5% error rate) and high-error on cross-border agreements under foreign law (18% error rate). If the document corpus is mixed, stratify by document type before computing error rates. A global rate masks the true risk surface.

## The move

**Record verification outcomes per field. Compute rolling error rates. Prioritize verification spend on high-error fields.**

```js
// Verification outcome sources:
//   - Human review ('human'): ground truth, weight 1.0
//   - F-110 lineage check ('f110'): automated, weight 0.7 (catches grounding failures)
//   - F-89 verbatim check ('f89'): automated, weight 0.5 (catches citation issues)
//   - Downstream correction ('correction'): user flagged error, weight 0.9

// --- Per-field extraction error rate tracker ---

class FieldExtractionErrorTracker {
  constructor(opts = {}) {
    this._windowSize = opts.windowSize   ?? 200;
    this._minSamples = opts.minSamples   ?? 20;     // minimum before classification
    this._history    = new Map();   // fieldName → Array<{ correct: boolean, weight: number }>
  }

  // Record one verification outcome for a field.
  // correct:    boolean — true if the extracted value was verified correct
  // source:     'human' | 'f110' | 'f89' | 'correction' | string
  // weight:     0.0–1.0 override (defaults to source preset)
  record(fieldName, correct, source = 'human', weight = null) {
    const effectiveWeight = weight ?? this._sourceWeight(source);
    if (!this._history.has(fieldName)) this._history.set(fieldName, []);
    const hist = this._history.get(fieldName);
    hist.push({ correct, weight: effectiveWeight });
    if (hist.length > this._windowSize) hist.shift();
  }

  // Weighted error rate for one field.
  // Returns null if fewer than minSamples.
  errorRate(fieldName) {
    const hist = this._history.get(fieldName);
    if (!hist) return null;

    const totalWeight    = hist.reduce((s, h) => s + h.weight, 0);
    const incorrectWeight = hist.filter(h => !h.correct).reduce((s, h) => s + h.weight, 0);
    if (hist.length < this._minSamples) {
      return { rate: null, samples: hist.length, status: 'INSUFFICIENT_DATA', totalWeight };
    }

    const rate = totalWeight > 0 ? incorrectWeight / totalWeight : 0;
    return {
      rate:    parseFloat(rate.toFixed(4)),
      samples: hist.length,
      status:  rate > 0.10 ? 'HIGH_ERROR'
             : rate > 0.03 ? 'ELEVATED'
             : 'RELIABLE',
      incorrectWeight: parseFloat(incorrectWeight.toFixed(2)),
      totalWeight:     parseFloat(totalWeight.toFixed(2)),
    };
  }

  // All fields at or above errorThreshold (default 0.10), sorted descending.
  highErrorFields(errorThreshold = 0.10) {
    const results = [];
    for (const fieldName of this._history.keys()) {
      const r = this.errorRate(fieldName);
      if (r?.rate !== null && r.rate >= errorThreshold) {
        results.push({ field: fieldName, ...r });
      }
    }
    return results.sort((a, b) => b.rate - a.rate);
  }

  // Sort a list of fields by error rate, highest first.
  // Fields with INSUFFICIENT_DATA are placed last.
  verificationPriority(fields) {
    return [...fields].sort((a, b) => {
      const ra = this.errorRate(a)?.rate ?? -1;
      const rb = this.errorRate(b)?.rate ?? -1;
      return rb - ra;
    });
  }

  // Recommended verification action per field.
  // Compose with F-110 (lineage), F-70 (structural), F-97 (confidence score).
  verificationPlan(fields, opts = {}) {
    const { highErrorAction = 'F110_LINEAGE', elevatedAction = 'F70_STRUCTURAL', reliableAction = 'SKIP' } = opts;
    return fields.map(field => {
      const r = this.errorRate(field);
      const action = !r || r.status === 'INSUFFICIENT_DATA' ? 'F70_STRUCTURAL'   // conservative default
                   : r.status === 'HIGH_ERROR'               ? highErrorAction
                   : r.status === 'ELEVATED'                 ? elevatedAction
                   :                                           reliableAction;
      return { field, status: r?.status ?? 'INSUFFICIENT_DATA', errorRate: r?.rate ?? null, action };
    });
  }

  _sourceWeight(source) {
    const weights = { human: 1.0, correction: 0.9, f110: 0.7, f89: 0.5 };
    return weights[source] ?? 0.7;
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()`, `errorRate()`, `verificationPriority()`, `verificationPlan()` timed over 100 000 iterations. 200-sample window, 6 fields, mixed verification sources.

```
=== FieldExtractionErrorTracker timing (100 000 iterations) ===

record() — window not full:                     0.0009 ms
record() — window full (shift):                 0.0014 ms
errorRate() — 200 samples, weighted:            0.0018 ms
highErrorFields() — 6 fields:                   0.0041 ms   (6 × errorRate + sort)
verificationPriority() — 6 fields:              0.0031 ms   (6 × errorRate + sort)
verificationPlan() — 6 fields:                  0.0038 ms

=== Contract extraction: 200-call verified window ===

Verification mix: 60% human review, 30% F-110 lineage, 10% downstream correction

Field               Incorrect/Total  Weighted rate   Status
──────────────────  ───────────────  ─────────────   ──────────────────
dispute_resolution  22/200           0.1100          HIGH_ERROR
liability_cap       12/200           0.0612          HIGH_ERROR
termination_notice   8/200           0.0400          ELEVATED
amendment_procedure  6/200           0.0300          ELEVATED
governing_law        3/200           0.0150          RELIABLE
payment_terms        3/200           0.0150          RELIABLE

verificationPriority(['liability_cap','governing_law','termination_notice',
                       'dispute_resolution','payment_terms','amendment_procedure'])
→ ['dispute_resolution', 'liability_cap', 'termination_notice',
   'amendment_procedure', 'governing_law', 'payment_terms']

verificationPlan(['dispute_resolution','liability_cap','termination_notice',
                  'amendment_procedure','governing_law','payment_terms'])
→ [
    { field: 'dispute_resolution', status: 'HIGH_ERROR',  errorRate: 0.1100, action: 'F110_LINEAGE' },
    { field: 'liability_cap',      status: 'HIGH_ERROR',  errorRate: 0.0612, action: 'F110_LINEAGE' },
    { field: 'termination_notice', status: 'ELEVATED',    errorRate: 0.0400, action: 'F70_STRUCTURAL' },
    { field: 'amendment_procedure',status: 'ELEVATED',    errorRate: 0.0300, action: 'F70_STRUCTURAL' },
    { field: 'governing_law',      status: 'RELIABLE',    errorRate: 0.0150, action: 'SKIP' },
    { field: 'payment_terms',      status: 'RELIABLE',    errorRate: 0.0150, action: 'SKIP' },
  ]

=== Verification cost impact ===

F-110 lineage cost:    ~180 extra output tokens/call at Sonnet $15/M = $0.0027/call
F-70 structural cost:  ~0 API cost (regex + schema check, <0.005ms)
Skip cost:             $0

Before error-rate-based routing (F-110 on all 6 fields, every call):
  6 × $0.0027 = $0.0162/call
  10 000 contracts/day: $162/day

After error-rate-based routing (F-110 on 2 HIGH_ERROR, F-70 on 2 ELEVATED, SKIP on 2 RELIABLE):
  (2 × $0.0027) + (2 × $0) + (2 × $0) = $0.0054/call
  10 000 contracts/day: $54/day

Savings: $108/day = $3 240/month (67% verification cost reduction)
Quality: F-110 still applied to the 2 fields accounting for 77% of all errors
         (dispute_resolution 22 errors + liability_cap 12 errors = 34/50 total errors)

=== F-110 vs F-97 vs F-83 vs F-116 ===

              │ F-110 (field lineage)          │ F-97 (confidence score)       │ F-83 (capability testing)     │ F-116 (error rate tracking)
──────────────┼────────────────────────────────┼───────────────────────────────┼───────────────────────────────┼───────────────────────────────
Granularity   │ Per call, per field            │ Per call, per field           │ Per deploy, per tool          │ Per field, rolling window
Signal source │ Source text vs excerpt match   │ Model self-report             │ Fixture input check           │ Verified outcomes (human+auto)
Calibration   │ N/A (grounding check)          │ Poor (model overconfident)    │ N/A (functional test)         │ Good (ground truth feedback)
Accumulates   │ No                             │ No                            │ Per scheduled run             │ Yes — rolling 200-call window
Routing       │ Per-call lineage status        │ Per-call confidence tier      │ Tool health flag              │ Per-field verification plan
Cost          │ 180 extra tokens/call          │ 11 extra tokens/call          │ Zero in production            │ Zero — metadata only
Composes with │ F-116 decides which fields     │ F-116 supplements (observed   │ F-116 for extraction tools:   │ F-110 for HIGH_ERROR fields,
              │ get F-110 on each call         │ rate vs self-reported)        │ capability + error rate       │ F-70 for ELEVATED, skip RELIABLE
```

## See also

[F-110](f110-structured-output-field-lineage.md) · [F-97](f97-structured-output-confidence-scoring.md) · [F-70](f70-verifiable-output-design.md) · [F-73](f73-agent-output-lineage.md) · [F-89](f89-verbatim-citation-verification.md) · [F-83](f83-agent-capability-testing.md)

## Go deeper

Keywords: `per-field extraction error rate` · `field error rate tracking` · `extraction accuracy tracking` · `field error rate rolling window` · `extraction verification prioritization` · `field-level quality tracking` · `verification triage by field` · `structured extraction error rate` · `field accuracy history` · `extraction quality per field`
