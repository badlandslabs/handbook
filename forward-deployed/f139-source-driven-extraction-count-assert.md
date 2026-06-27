# F-139 · Source-Driven Extraction Count Assert

[F-132](f132-output-array-cardinality-validator.md) validates array field cardinality against statically declared bounds — minimum and maximum item counts registered at schema design time. It catches `parties: ['Alpha Corp']` on a bilateral contract because you declared `min: 2`. It does not know that a specific source document mentions "5 amendment clauses" and the extraction returned 1. [F-103](f103-response-completeness-check.md) checks whether the model answered all parts of a multi-part question — multi-question completeness, not extraction item count. [F-70](f70-structured-output-validation.md) validates that required array fields are present and non-null — structural validation, not count grounding.

The gap: a source document often states, in plain text, exactly how many items it contains. "This Agreement is subject to 5 amendment clauses." "The following 2 schedules are attached." "Entered into by 3 contracting parties." When the extraction returns fewer items than the source states, something was missed. When it returns more, something was hallucinated. This signal is present in the source text; it costs zero tokens to extract and check; and it catches failures that static cardinality bounds cannot — because the bounds don't know what this specific document says.

A source-driven extraction count assert parses count mentions from the source document text using regex patterns that allow for adjective words between the number and the noun ("5 amendment clauses", "3 contracting parties", "2 attached schedules"). It compares the stated count against the actual extracted array length and returns PASS, MISMATCH (with UNDER_EXTRACTED or OVER_EXTRACTED classification), or UNPARSED (the source did not state a count — not a failure). Run at the delivery boundary before the output reaches downstream consumers.

## Situation

A contract extraction pipeline processes bilateral agreements. The output schema includes `clauses` (the amendment clauses), `parties` (the contracting parties), and `schedules` (the attached schedules). F-132 is configured with `clauses: {min: 1}`, `parties: {min: 2}`, `schedules: {min: 0}`.

A batch of 300 contracts includes one where the source reads: "This Agreement is subject to 5 amendment clauses as set forth in Schedule B." The extraction returns `clauses: [{id: 'CL-001', text: 'Force majeure provision'}]` — one clause. F-132 passes: `count: 1 ≥ min: 1`. F-70 passes: the field is present and is an array. F-132 has no way to know this particular document expected 5. Four clauses were missed.

With the source-driven count assert: the pattern `/\b(\d+)(?:\s+\w+){0,2}\s+clauses?\b/gi` matches "5 amendment clauses." `assertExtractionCount(sourceText, 'clauses', extractedClauses)` returns `MISMATCH: {expected: 5, actual: 1, hint: 'UNDER_EXTRACTED (model missed items)'}`. The extraction is blocked at the delivery boundary and routed to F-133 retry with the hint: "The document states 5 amendment clauses; only 1 was extracted."

The same pipeline catches over-extraction: a source says "the following 2 schedules are attached" and the extraction returns 4. `MISMATCH: {expected: 2, actual: 4, hint: 'OVER_EXTRACTED (model hallucinated items)'}`.

## Forces

- **UNPARSED is not a failure.** Many documents do not state counts explicitly. "The payment schedule" does not give a count; "payment_terms" cannot be validated by source count. UNPARSED means "no count signal available" — the system falls back to F-132 static bounds and moves on. Treat UNPARSED as an absence of signal, not as a mismatch.
- **Allow for adjective words between count and noun.** Contract language rarely says "5 clauses" directly. It says "5 amendment clauses," "3 contracting parties," "2 attached schedules." The count pattern must allow for 0–2 intervening words: `/\b(\d+)(?:\s+\w+){0,2}\s+noun\b/`. Without this, most count mentions will be UNPARSED.
- **Run after F-132 static bounds, not before.** F-132 is faster (no source text required) and catches obviously wrong counts (empty arrays, single-item bilateral contracts). Run F-132 first; if PASS, run the source count assert for a deeper check. If F-132 already caught the failure, the source count assert is redundant on that field.
- **Return the matched text for debugging.** The `matchedText` field ("5 amendment clauses") pins exactly what the source said. Include it in the retry hint (F-133): "The document states '5 amendment clauses'; only 1 was extracted — re-read Section B." The matched phrase is the most useful debugging context a retry can receive.
- **Domain-specific vocabulary requires domain-specific patterns.** "5 amendment clauses" matches for contract extraction; "5 bullet points" would match for document summarization; "5 risk categories" for risk assessment. Build the pattern set from the vocabulary of your specific domain and document type. The 6 default patterns in the receipt cover common contract terms; extend them from observed failures.
- **Do not block on MISMATCH if the document count is ambiguous.** Some documents refer to both the final count ("5 clauses") and a proposed count from earlier in the negotiation ("originally 7 clauses were proposed"). The regex may match either. When blocking on MISMATCH, log the matched text for human review — if the source count assertion is triggering on the wrong count mention, the pattern needs refinement.

## The move

**Parse count mentions from the source text using regex with optional adjective words. Compare against extracted array length. Block or retry on MISMATCH. Pass through on UNPARSED.**

```js
// --- Source-driven extraction count assert ---
// Parses count mentions from source text; compares against extracted array length.
// Zero token cost. T=0 compatible. Runs at delivery boundary before downstream consumers.
// status: PASS | MISMATCH (UNDER/OVER_EXTRACTED) | UNPARSED (no count signal — not a failure)
// Compose: run F-132 static cardinality first, then this for source-grounded count check.

// Allow 0-2 adjective words between count and noun:
//   "5 clauses" → 0 adjectives
//   "5 amendment clauses" → 1 adjective
//   "3 contracting parties" → 1 adjective
//   "2 attached payment schedules" → 2 adjectives
const COUNT_PATTERNS = [
  { field: 'clauses',      re: /\b(\d+)(?:\s+\w+){0,2}\s+(?:clauses?|articles?|provisions?|sections?)\b/gi },
  { field: 'amendments',   re: /\b(\d+)(?:\s+\w+){0,2}\s+(?:amendments?|addenda|addendum)\b/gi },
  { field: 'parties',      re: /\b(\d+)(?:\s+\w+){0,2}\s+(?:parties|signatories)\b/gi },
  { field: 'schedules',    re: /\b(\d+)(?:\s+\w+){0,2}\s+(?:schedules?|exhibits?|annexes?|appendices)\b/gi },
  { field: 'line_items',   re: /\b(\d+)(?:\s+\w+){0,2}\s+(?:line\s+items?|items?)\b/gi },
  { field: 'risk_factors', re: /\b(\d+)(?:\s+\w+){0,2}\s+(?:risk\s+factors?|risks?)\b/gi },
];

// Parse the first count mention for the given fieldCategory from sourceText.
// Returns { count, matchedText } or null if no mention found.
function extractExpectedCount(sourceText, fieldCategory) {
  for (const cp of COUNT_PATTERNS) {
    if (cp.field !== fieldCategory) continue;
    const re = new RegExp(cp.re.source, cp.re.flags);
    const m = re.exec(sourceText);
    if (m) return { count: parseInt(m[1], 10), matchedText: m[0] };
  }
  return null;
}

// Assert that extractedArray.length matches the count stated in sourceText.
// Returns { status, fieldCategory, expected?, actual, delta?, matchedText?, hint?, reason? }
function assertExtractionCount(sourceText, fieldCategory, extractedArray) {
  const expected = extractExpectedCount(sourceText, fieldCategory);
  if (!expected) {
    return { status: 'UNPARSED', fieldCategory, actual: extractedArray.length, reason: 'no_count_mention_found' };
  }
  const actual = extractedArray.length;
  if (actual === expected.count) {
    return { status: 'PASS', fieldCategory, expected: expected.count, actual, matchedText: expected.matchedText };
  }
  const delta = actual - expected.count;
  return {
    status: 'MISMATCH',
    fieldCategory,
    expected: expected.count,
    actual,
    delta,
    matchedText: expected.matchedText,
    hint: delta < 0 ? 'UNDER_EXTRACTED (model missed items)' : 'OVER_EXTRACTED (model hallucinated items)',
  };
}

// --- Integration: pipeline delivery gate ---
// Run after F-132 static bounds pass. Block on MISMATCH; proceed on PASS or UNPARSED.

const ARRAY_FIELD_CATEGORIES = [
  { field: 'clauses',   category: 'clauses'   },
  { field: 'parties',   category: 'parties'   },
  { field: 'schedules', category: 'schedules' },
];

function validateCountsAtDelivery(sourceText, output) {
  const results = [];
  for (const { field, category } of ARRAY_FIELD_CATEGORIES) {
    if (!Array.isArray(output[field])) continue;
    const r = assertExtractionCount(sourceText, category, output[field]);
    results.push(r);
  }

  const mismatches = results.filter(r => r.status === 'MISMATCH');
  if (mismatches.length === 0) {
    return { passed: true, results };
  }

  // Build retry hint from mismatches for F-133 escalation
  const hint = mismatches
    .map(r => `Source states "${r.matchedText}"; extracted ${r.actual}. ${r.hint}.`)
    .join(' ');

  return { passed: false, results, retryHint: hint };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Patterns tested on four scenarios. `assertExtractionCount()` timed over 100 000 iterations. Zero API calls.

```
=== Source-Driven Extraction Count Assert ===

--- Scenario A: PASS — source states "3 contracting parties", extraction has 3 ---

  source: "...3 contracting parties: Alpha Corp, Beta Ltd, and Gamma Inc..."
  matched: "3 contracting parties"
  result:  PASS { expected: 3, actual: 3 }

--- Scenario B: MISMATCH — source states "5 amendment clauses", extraction has 1 ---

  source: "...subject to 5 amendment clauses as set forth in Schedule B..."
  matched: "5 amendment clauses"
  result:  MISMATCH { expected: 5, actual: 1, delta: -4 }
           hint: "UNDER_EXTRACTED (model missed items)"
  action:  route to F-133 retry with hint:
           "Source states '5 amendment clauses'; extracted 1. UNDER_EXTRACTED (model missed items)."

--- Scenario C: MISMATCH — source states "2 schedules", extraction has 4 ---

  source: "...the following 2 schedules are attached..."
  matched: "2 schedules"
  result:  MISMATCH { expected: 2, actual: 4, delta: +2 }
           hint: "OVER_EXTRACTED (model hallucinated items)"
  action:  route to F-133 retry; remove extra items or re-extract

--- Scenario D: UNPARSED — source does not mention a count ---

  source: "...the payment schedule as described herein. Payment terms are net 30..."
  result:  UNPARSED { actual: 2, reason: 'no_count_mention_found' }
  action:  proceed — fall back to F-132 static cardinality only

=== Integration example: validateCountsAtDelivery() ===

  source: "This agreement between 2 parties includes 4 clauses and 3 schedules."
  extraction: { clauses: ['CL-1','CL-2','CL-3'], schedules: ['S-1','S-2','S-3'], parties: ['A','B'] }

  clauses:   MISMATCH  expected=4, actual=3   UNDER_EXTRACTED
  schedules: PASS      expected=3, actual=3
  parties:   PASS      expected=2, actual=2

  → passed=false
    retryHint: "Source states '4 clauses'; extracted 3. UNDER_EXTRACTED (model missed items)."

=== Timing (100 000 iterations) ===

extractExpectedCount() — match found:  0.0012 ms
extractExpectedCount() — UNPARSED:     0.0007 ms
assertExtractionCount() — MISMATCH:    0.0011 ms
assertExtractionCount() — PASS:        0.0011 ms

=== F-132 vs F-139 ===

              │ F-132 (cardinality validator)         │ F-139 (source count assert)
──────────────┼───────────────────────────────────────┼───────────────────────────────────────────
Count source  │ Static declared bounds (min, max)     │ Source document text (regex parse)
Knows context │ No — same bounds for every document   │ Yes — reads what this document states
Catches       │ Empty arrays, obvious shortfalls      │ "5 stated, 1 extracted" for this doc
Misses        │ "1 extracted, doc says 5" if min:1    │ Documents that don't state counts
UNPARSED      │ N/A — bounds are always defined       │ Normal — no count in source; not a failure
When to run   │ First — fast, source text not needed  │ After F-132 PASS, for deeper count check
Token cost    │ 0                                     │ 0
```

## See also

[F-132](f132-output-array-cardinality-validator.md) · [F-70](f70-structured-output-validation.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-135](f135-extraction-output-field-normalizer.md) · [F-136](f136-extraction-lifecycle-audit-record.md)

## Go deeper

Keywords: `source-driven extraction count` · `extraction item count assertion` · `source count validation` · `extraction completeness check` · `document count signal` · `regex count extraction` · `extraction count mismatch` · `under-extracted detection` · `over-extracted hallucination` · `source-grounded cardinality check`
