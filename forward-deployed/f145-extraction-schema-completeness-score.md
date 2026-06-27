# F-145 · Extraction Schema Completeness Score

[F-70](f70-verifiable-output-design.md) validates required fields: if `parties` is declared required and the extraction returns `parties: null`, F-70 fires and blocks delivery. F-70 is binary — each field either passes or fails. It does not provide a measure of how complete the extraction is overall, nor does it weight fields by consequence. [F-127](f127-extraction-field-null-rate-monitor.md) tracks null rates per `(entityType, field)` pair across many calls over time — it identifies that `jurisdiction` is null 34% of the time on cross-border contracts. F-127 is aggregate: it describes the model's null behavior over a population of extractions, not the quality of a single extraction.

A different question arises at delivery time: given this specific extraction, how complete is it? A 10-field schema where all four HIGH-tier fields (the ones required for downstream legal and financial processing) are populated, but three LOW-tier fields (optional context fields) are null, is meaningfully different from an extraction where two HIGH-tier fields are null. Both might pass F-70 if the null LOW-tier fields were declared optional. But the second extraction is a worse outcome — the model failed to locate two fields the pipeline depends on.

An extraction schema completeness score assigns weights to each schema field by consequence tier (HIGH=3, MEDIUM=2, LOW=1) and computes the ratio of populated-field weight to total-schema weight for a single extraction. A score of 0.80 or above — weighted toward the fields that matter most — gates delivery as COMPLETE. Below 0.80 is PARTIAL; below 0.50 is SPARSE, indicating a likely extraction failure requiring retry or manual review.

## Situation

A contract extraction pipeline processes 10-field schema extractions. The schema declares four HIGH-tier fields (parties, effective_date, termination_date, governing_law), three MEDIUM-tier fields (contract_value, payment_terms, risk_level), and three LOW-tier fields (jurisdiction, amendment_count, notice_period).

Without completeness scoring: a batch of 200 extractions shows that 23 have two or more null HIGH-tier fields. These pass F-70 (the HIGH fields are declared required in F-70 but the model returns null for both, which F-70 catches if `required: true` — so actually F-70 would catch these). But in a schema where effective_date is optional (many documents pre-date formal effective clauses), F-70 doesn't fire. The completeness score does: HIGH null = -3 weight per field, and a score below 0.80 routes to retry.

With completeness scoring: each extraction is scored immediately after validation. A 4-HIGH-null extraction scores 0.43 (SPARSE) and routes to a targeted retry with an extraction hint. A 2-HIGH-null extraction scores 0.71 (PARTIAL) and routes to manual review. Extractions scoring COMPLETE (≥0.80) proceed to delivery. The review queue captures exactly the extractions where the model struggled — not based on required-field rules, but on weighted field coverage.

## Forces

- **Calibrate the threshold to the document type's natural null rate.** A routine domestic NDA usually populates 9/10 fields. A complex cross-border framework agreement may normally have jurisdiction null (located in an attached schedule, not the main body) — reducing baseline score to 0.93. Set thresholds per document type after measuring baseline completeness on a sample. The default 0.80 is a starting point, not a universal truth.
- **Weight reflects consequence, not importance.** HIGH does not mean "more important to the business." It means "more consequential when null — the downstream pipeline cannot proceed without this field." A LOW-tier field that is null is tolerable; a HIGH-tier null blocks the review queue or the financial model. Assign tiers based on what breaks when the field is missing, not on editorial judgment about the field's significance.
- **Use `missingRequired` as a hard gate alongside the score.** The score is a continuous quality measure; `missingRequired` is a binary gate. A field declared required (F-70) must be non-null for the extraction to be useful at all, regardless of the completeness score. Run both: block if `missingRequired.length > 0`, route to review if score < threshold. The score adds discrimination in the range where all required fields are present but optional fields have a pattern of gaps.
- **Empty arrays count as null.** A `parties: []` extraction is not a completion — the model found the field but extracted no parties. Treat arrays with length 0 the same as null when computing the score.
- **Report `missingHigh` in the retry hint.** When score is PARTIAL or SPARSE, the retry hint should name which HIGH-tier fields are null and, where possible, suggest where in the document they are typically located. "effective_date is null — check the introductory recitals or the signature block for the commencement date." The model extracted all the other fields; it missed this one. A targeted hint costs fewer tokens than a full retry prompt.
- **Distinguish SPARSE from PARTIAL in routing.** SPARSE (score < 0.50) usually indicates the model received the wrong document, a non-machine-readable scan, or an irrelevant file. Route SPARSE to a classification step before retry — the document may not be what the pipeline expects. PARTIAL (0.50–0.80) indicates the model received the right document but missed some fields. Route PARTIAL to prompt-targeted retry.

## The move

**Score each extraction by weighted field population. Gate on both `missingRequired` (binary) and completeness score (continuous). Route SPARSE to classification, PARTIAL to retry, COMPLETE to delivery.**

```js
// --- Extraction schema completeness score ---
// Computes a weighted fill ratio for a single extraction.
// Distinct from F-70 (binary required check) and F-127 (aggregate null rate over many calls).
// Compose: run after F-70 (required fields) → F-140 (date ordering) → F-145 (completeness score).

const TIER_WEIGHT = { HIGH: 3, MEDIUM: 2, LOW: 1 };

function scoreCompleteness(extraction, schemaDefs, opts) {
  opts = opts || {};
  const threshold = opts.threshold !== undefined ? opts.threshold : 0.80;

  let totalWeight = 0;
  let filledWeight = 0;
  const filledFields = [];
  const nullFields   = [];

  for (const def of schemaDefs) {
    const weight = TIER_WEIGHT[def.tier] || 1;
    totalWeight += weight;
    const val = extraction[def.field];
    const populated = val !== null && val !== undefined && val !== '' &&
                      !(Array.isArray(val) && val.length === 0);
    if (populated) {
      filledWeight += weight;
      filledFields.push({ field: def.field, tier: def.tier });
    } else {
      nullFields.push({ field: def.field, tier: def.tier, required: def.required });
    }
  }

  const score = totalWeight > 0 ? filledWeight / totalWeight : 1;
  const status = score >= threshold ? 'COMPLETE' : score >= 0.50 ? 'PARTIAL' : 'SPARSE';
  const missingRequired = nullFields.filter(f => f.required);
  const missingHigh     = nullFields.filter(f => f.tier === 'HIGH');

  return {
    status,
    score:           parseFloat(score.toFixed(3)),
    filledCount:     filledFields.length,
    totalCount:      schemaDefs.length,
    filledWeight,
    totalWeight,
    filledFields,
    nullFields,
    missingRequired,
    missingHigh,
    passed:          score >= threshold && missingRequired.length === 0,
  };
}

// --- Integration: delivery gate ---

// schemaDefs: declared once per pipeline, shared across extractions.
const CONTRACT_SCHEMA = [
  { field: 'parties',          tier: 'HIGH',   required: true  },
  { field: 'effective_date',   tier: 'HIGH',   required: true  },
  { field: 'termination_date', tier: 'HIGH',   required: true  },
  { field: 'governing_law',    tier: 'HIGH',   required: true  },
  { field: 'contract_value',   tier: 'MEDIUM', required: false },
  { field: 'payment_terms',    tier: 'MEDIUM', required: false },
  { field: 'risk_level',       tier: 'MEDIUM', required: false },
  { field: 'jurisdiction',     tier: 'LOW',    required: false },
  { field: 'amendment_count',  tier: 'LOW',    required: false },
  { field: 'notice_period',    tier: 'LOW',    required: false },
];

function deliverExtraction(extraction) {
  const check = scoreCompleteness(extraction, CONTRACT_SCHEMA);

  if (check.missingRequired.length > 0) {
    return { delivered: false, reason: 'MISSING_REQUIRED',
             fields: check.missingRequired.map(f => f.field) };
  }
  if (check.status === 'SPARSE') {
    return { delivered: false, reason: 'SPARSE_EXTRACTION',
             score: check.score,
             action: 'CLASSIFY_DOCUMENT' };
  }
  if (check.status === 'PARTIAL') {
    const hints = check.missingHigh.map(f => `${f.field} is null — check relevant document section`);
    return { delivered: false, reason: 'PARTIAL_EXTRACTION',
             score: check.score, hints,
             action: 'RETRY_WITH_HINTS' };
  }
  return { delivered: true, extraction, completenessScore: check.score };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 10-field contract schema, 4 scenarios. `scoreCompleteness()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Extraction Schema Completeness Score ===

--- Scenario A: Fully populated ---
  status: COMPLETE  score: 1.000  (21/21 weighted, 10/10 fields)  passed: true

--- Scenario B: HIGH fields filled, LOW/MEDIUM mostly null ---
  status: PARTIAL  score: 0.667  (14/21 weighted)  passed: false
  null fields: contract_value(MEDIUM), payment_terms(MEDIUM),
               jurisdiction(LOW), amendment_count(LOW), notice_period(LOW)
  Note: threshold=0.80 triggers PARTIAL even with all HIGH fields present.
  For document types with naturally-null LOW/MEDIUM fields, lower threshold to 0.65.

--- Scenario C: 2 HIGH fields null (extraction failures) ---
  status: PARTIAL  score: 0.714  (15/21 weighted)  passed: false
  missingHigh: effective_date, termination_date
  missingRequired: effective_date, termination_date
  → MISSING_REQUIRED gate fires first; score is secondary signal.

--- Scenario D: Nearly empty (SPARSE) ---
  status: SPARSE  score: 0.095  (2/21 weighted)  passed: false
  → Route to CLASSIFY_DOCUMENT before retry.

=== F-70 vs F-127 vs F-145 ===

  F-70:  binary per field — required=true fields must be non-null; no score, no weighting
  F-127: aggregate over N calls — null RATE per (entityType, field); not per-extraction
  F-145: per-extraction score — weighted fill ratio; gates delivery on completeness threshold

=== Timing (1 000 000 iterations) ===

scoreCompleteness() 10 fields, COMPLETE:  0.0018 ms
scoreCompleteness() 10 fields, PARTIAL:   0.0021 ms

Zero API calls. Zero tokens. Runs at delivery boundary after F-70 and F-140.
```

## See also

[F-70](f70-verifiable-output-design.md) · [F-127](f127-extraction-field-null-rate-monitor.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-103](f103-response-completeness-check.md) · [F-141](f141-extraction-class-distribution-monitor.md)

## Go deeper

Keywords: `extraction completeness score` · `schema fill rate` · `weighted field completeness` · `per-extraction quality score` · `null field completeness ratio` · `extraction coverage score` · `LLM extraction completeness gate` · `field population score` · `extraction schema completeness` · `weighted null field score`
