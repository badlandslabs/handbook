# F-134 · Extraction Ensemble Voter

[S-24](../stacks/s24-self-consistency.md) runs the same prompt N times at temperature > 0 and takes the mode answer — a single extractable value like a number or label. It operates on free-form answers, not structured JSON, and produces one majority answer for the full output. [F-78](f78-confidence-gated-delivery.md) uses sampling variance across N outputs to compute a confidence score, then abstains when confidence falls below a domain threshold. It gates the full response, not individual fields. [F-47](f47-multi-agent-result-aggregation.md) aggregates results from N different agents running different tasks in parallel — not the same task repeated.

None of these produce per-field confidence for a structured extraction output. When extracting a contract into a 10-field JSON schema, some fields are unambiguous (the counterparty name appears once, verbatim) while others are contested (the termination fee appears in two clauses with different values). A single extraction call on any model hides this variance — every field looks equally certain. Running the extraction N times and voting per field surfaces which fields the model agrees on and which it does not.

Extraction ensemble voting runs the same extraction prompt N=3 times on a cheap model (Haiku) in parallel. For each field, it finds the plurality winner and assigns a confidence tier: UNANIMOUS (all N agree), MAJORITY (at least 2 of 3 agree), or SPLIT (no majority). SPLIT fields are the ones that need a retry, a higher-capability model, or human review — not the whole extraction.

## Situation

A contract extraction pipeline processes 1 000 bilateral agreements per day. Each contract is extracted into a 6-field schema: `clause_id`, `termination_fee`, `parties`, `risk_level`, `effective_date`, `governing_law`. The pipeline runs on Sonnet at $0.003/extraction = $3.00/day.

Four months of production data show that 80% of extractions have no field-level disagreement — the document is clear and any model would return the same values. For the remaining 20%, one or two specific fields are ambiguous: `termination_fee` appears in both the main body and an amendment with different values, or `risk_level` is stated inconsistently across sections.

Switching to N=3 Haiku ensemble: cost per extraction = 3 × $0.000800 = $0.002400. Total: $2.40/day — 20% cheaper than single Sonnet. Per-field confidence tiers surface which fields need further attention. UNANIMOUS fields (80% of all field-extraction pairs) are accepted directly. SPLIT fields (rare, < 5% of fields in < 20% of contracts) are routed to Sonnet for targeted re-extraction of only those fields.

Net cost: $2.40/day ensemble + $0.003 × 1000 × 0.20 × 0.05 × (average 1.5 split fields / 6) ≈ $2.40 + $0.03/day in Sonnet re-extractions. Total: $2.43/day vs $3.00/day — 19% savings with per-field confidence as a bonus.

## Forces

- **Run the N calls in parallel.** Serial calls triple the latency; parallel calls add zero latency overhead over a single call. All three Haiku calls should start at the same time and return concurrently.
- **Vote on stringified values.** JSON.stringify is used as the comparison key. This means `["Alpha Corp","Beta LLC"]` and `["Beta LLC","Alpha Corp"]` are counted as different even if they represent the same parties. For fields where ordering is semantic (lists), this is correct. For fields where ordering is not semantic (party names), normalize before voting: sort arrays before stringifying if the field is known to be unordered.
- **SPLIT fields route to a targeted re-extraction, not a full retry.** A full Sonnet re-extraction on a SPLIT document costs $0.003 and re-extracts all 6 fields. A targeted re-extraction asks Sonnet for only the 2 contested fields, at proportionally lower output cost. Build the targeted prompt from the SPLIT field list.
- **MAJORITY means two of three agree, not that the value is correct.** Two wrong answers that agree are still MAJORITY. The confidence tier reflects ensemble agreement, not ground truth. Treat MAJORITY fields from ambiguous documents with the same care as SPLIT fields from clear documents — use F-116 (per-field extraction error rate) to track which fields systematically disagree with human review, regardless of their ensemble confidence.
- **N=3 is the minimum for meaningful majority.** N=2 allows only UNANIMOUS or SPLIT — no majority tier. N=5 adds a third level of confidence granularity but 67% higher cost. Start with N=3; move to N=5 for high-stakes domains (legal, medical) where the extra cost is justified by the confidence gradient.
- **Don't ensemble fields that are always UNANIMOUS.** If production data shows that `clause_id` is UNANIMOUS on 99% of documents, it doesn't benefit from N=3 runs. Log per-field SPLIT rates weekly (F-116). Fields with < 1% SPLIT rates are good candidates for single-pass extraction, keeping ensemble overhead only on the fields that need it.

## The move

**Run N=3 Haiku extractions in parallel. Vote per field. Route SPLIT fields to targeted Sonnet re-extraction.**

```js
// --- Extraction ensemble voter ---
// Runs the same extraction N=3 times on a cheap model in parallel.
// Per-field vote: UNANIMOUS (all agree) | MAJORITY (2+ agree) | SPLIT (no majority).
// SPLIT fields are routed to targeted re-extraction — not a full retry.
// Normalize before voting: sort unordered arrays, lowercase enums, etc.

class ExtractionEnsembleVoter {
  constructor(opts) {
    opts = opts || {};
    this._majorityNeeded = opts.majorityNeeded || 2;   // N=3 → 2 is a majority
  }

  // Vote across N extraction results. Each extraction is a {field: value} object.
  // Returns per-field: { value, confidence: 'UNANIMOUS'|'MAJORITY'|'SPLIT', votes, totalRuns, uniqueValues }
  vote(extractions) {
    if (!extractions || extractions.length === 0) return {};
    const fields = Object.keys(extractions[0]);
    const result = {};

    for (const field of fields) {
      const values = extractions.map(function(e) { return e[field]; });
      const counts = new Map();
      for (const v of values) {
        const key = JSON.stringify(v);
        counts.set(key, (counts.get(key) || 0) + 1);
      }

      // Find plurality winner (highest count)
      let maxCount = 0, winnerKey = null;
      for (const entry of counts) {
        if (entry[1] > maxCount) { maxCount = entry[1]; winnerKey = entry[0]; }
      }

      let confidence;
      if (counts.size === 1)               confidence = 'UNANIMOUS';
      else if (maxCount >= this._majorityNeeded) confidence = 'MAJORITY';
      else                                 confidence = 'SPLIT';

      result[field] = {
        value:        JSON.parse(winnerKey),
        confidence:   confidence,
        votes:        maxCount,
        totalRuns:    extractions.length,
        uniqueValues: counts.size,
      };
    }
    return result;
  }

  // Return field names where no majority was reached.
  splitFields(voted) {
    return Object.keys(voted).filter(function(f) { return voted[f].confidence === 'SPLIT'; });
  }
}

// --- Integration: parallel Haiku ensemble + targeted Sonnet follow-up ---

const VOTER = new ExtractionEnsembleVoter({ majorityNeeded: 2 });

async function extractWithEnsemble(document, schema, queryType) {
  // Step 1: Run N=3 Haiku extractions in parallel
  const [e1, e2, e3] = await Promise.all([
    extractOnce('claude-haiku-4-5-20251001', document, schema),
    extractOnce('claude-haiku-4-5-20251001', document, schema),
    extractOnce('claude-haiku-4-5-20251001', document, schema),
  ]);

  const voted = VOTER.vote([e1, e2, e3]);
  const splits = VOTER.splitFields(voted);

  if (splits.length === 0) {
    // All fields UNANIMOUS or MAJORITY — return voted result directly
    return { output: Object.fromEntries(Object.entries(voted).map(([f, r]) => [f, r.value])),
             confidence: voted, splitCount: 0 };
  }

  // Step 2: Targeted Sonnet re-extraction for SPLIT fields only
  const partialSchema = splits.reduce(function(s, f) { s[f] = schema[f]; return s; }, {});
  const sonnetResult  = await extractOnce('claude-sonnet-4-6', document, partialSchema);

  // Merge: Sonnet wins on SPLIT fields; voted value wins on UNANIMOUS/MAJORITY
  const merged = {};
  for (const [field, r] of Object.entries(voted)) {
    merged[field] = splits.includes(field) ? sonnetResult[field] : r.value;
  }

  return { output: merged, confidence: voted, splitCount: splits.length };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `vote()` timed over 100 000 iterations on a 4-field extraction with N=3 runs. Pricing: Haiku $0.80/$4.00 per M tok, Sonnet $3.00/$15.00 per M tok.

```
=== ExtractionEnsembleVoter timing (100 000 iterations) ===

vote() — 4 fields, N=3 extractions (mixed confidence): 0.0130 ms
vote() — 4 fields, N=3 unanimous:                      0.0121 ms

=== Scenario: 3 Haiku extractions of a bilateral contract ===

Extract 1: { clause_id: 'CL-042', termination_fee: '24500000', parties: [...], risk_level: 'HIGH' }
Extract 2: { clause_id: 'CL-042', termination_fee: '24500000', parties: [...], risk_level: 'MEDIUM' }
Extract 3: { clause_id: 'CL-042', termination_fee: '22000000', parties: [...], risk_level: 'HIGH' }

vote() result:

clause_id:
  value='CL-042'       confidence=UNANIMOUS  votes=3/3  uniqueValues=1
  → All three agree. Accept.

termination_fee:
  value='24500000'     confidence=MAJORITY   votes=2/3  uniqueValues=2
  → Extract 3 returned '22000000' (amendment clause). Route to monitoring (F-116).

parties:
  value=['Alpha Corp', 'Beta LLC']  confidence=UNANIMOUS  votes=3/3  uniqueValues=1
  → All three agree. Accept.

risk_level:
  value='HIGH'         confidence=MAJORITY   votes=2/3  uniqueValues=2
  → Extract 2 returned 'MEDIUM'. MAJORITY wins; log discrepancy.

splitFields(): []   ← no SPLIT fields in this document → return directly, no Sonnet needed

=== If termination_fee were SPLIT (3 different values) ===

  → Sonnet re-extract only: { termination_fee: schema.termination_fee }
  → Sonnet result replaces SPLIT field in merged output
  → All other fields from Haiku majority vote

=== Cost comparison: 500-tok input + 100-tok output per extraction ===

N=3 Haiku ensemble:  3 × $0.000800 = $0.002400
1 × Sonnet:                          $0.003000

Ensemble is 20% cheaper. Adds: per-field confidence, SPLIT detection.

At 1 000 extractions/day:
  N=3 Haiku ensemble:       $2.40/day
  + Sonnet on SPLIT fields: ~$0.03/day (5% SPLIT rate × 1.5 avg fields)
  Total:                    $2.43/day vs $3.00/day single Sonnet

=== Confidence tier summary ===

UNANIMOUS: all N agree          → accept with high confidence
MAJORITY:  2 of 3 agree         → accept; log minority for F-116 monitoring
SPLIT:     no majority           → route to targeted Sonnet re-extraction

=== S-24 vs F-78 vs F-134 ===

              │ S-24 (self-consistency)     │ F-78 (confidence-gated)       │ F-134 (ensemble voter)
──────────────┼─────────────────────────────┼───────────────────────────────┼──────────────────────────────
Granularity   │ Full output: one answer     │ Full output: abstain or deliver│ Per-field: UNANIMOUS/MAJORITY/SPLIT
Output type   │ Single extractable label    │ Any (gated holistically)       │ Structured JSON (field-value pairs)
Purpose       │ Correct answer under temp   │ Abstain on low confidence      │ Identify which fields disagree
Temperature   │ T > 0 required              │ T > 0 (sampling variance)      │ T=0 acceptable (structural variation)
N disagreement│ Not surfaced                │ Not surfaced                   │ Surfaced per field
```

## See also

[S-24](../stacks/s24-self-consistency.md) · [F-78](f78-confidence-gated-delivery.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-116](f116-per-field-extraction-error-rate-tracking.md) · [F-70](f70-structured-output-validation.md) · [F-47](f47-multi-agent-result-aggregation.md)

## Go deeper

Keywords: `extraction ensemble voting` · `per-field extraction confidence` · `majority vote field extraction` · `N-run extraction` · `structured output voting` · `field-level confidence extraction` · `Haiku ensemble extraction` · `parallel extraction voting` · `extraction disagreement detection` · `split field re-extraction`
