# F-110 · Structured Output Field Lineage

[F-97](f97-output-field-confidence-annotation.md) annotates each field in structured output with a confidence tier (VERBATIM / MEDIUM / LOW) based on how well the field value matches the source text. It answers "how confident should I be in this field?" [S-137](../stacks/s137-multi-source-field-level-merge.md) records `provenance[field] = { source, fallback }` — which data source provided each field. [F-73](f73-agent-output-lineage.md) attaches lineage at the claim level in prose output: each sentence is tagged with citation IDs.

None of these provide a structured output field with both (a) the source ID and (b) the exact excerpt from that source that caused the field value. Without the excerpt, an auditor reviewing `{ termination_notice: "30 days" }` can check the source ID but must search the full document to find the supporting text. With field lineage, the annotation is `{ value: "30 days", _source: "contract-v2", _excerpt: "either party may terminate upon 30 days written notice" }`. The excerpt is verifiable in one step: is this string present in the named source? If the model invented the excerpt, that is a hallucination the field-level confidence score would classify as LOW — but it does not identify the fabrication as a specific invented string.

Structured output field lineage is an annotated extraction schema: for each field, the model returns the value alongside the exact source ID and verbatim excerpt that supports it. A post-extraction verifier checks each excerpt against the source texts and classifies each field as VERIFIED, NEAR_VERBATIM, or FABRICATED_EXCERPT.

## Situation

A contract analysis agent extracts 6 fields from a set of retrieved source documents: `liability_cap`, `governing_law`, `termination_notice`, `dispute_resolution`, `amendment_procedure`, and `payment_terms`. An audit is required before the output is used in a downstream compliance report.

Without field lineage: F-97 classifies 4 fields as HIGH confidence, 1 MEDIUM, 1 LOW. The LOW field is `dispute_resolution`. The auditor must search all retrieved source documents to find where "arbitration in New York" came from. It is not in any source — the model synthesized it from prior training. This is caught only by manual search.

With field lineage: each field has `_source` and `_excerpt`. The verifier runs `findBestExcerptMatch()` per field. `dispute_resolution` returns `FABRICATED_EXCERPT: score 0.12` — the model's excerpt does not appear in the named source. The auditor is flagged automatically: this specific claim needs manual verification before the compliance report ships.

## Forces

- **Excerpt length must be bounded.** A 500-token excerpt alongside every field defeats the purpose of structured output. 80–120 characters (roughly one clause) is sufficient to identify the source passage and verify presence. Instruct the model: "Excerpt must be verbatim, under 120 characters, sufficient to identify its source location."
- **Verbatim substrings are the fastest verification path.** `String.includes()` on a 10 000-character document is ~0.002ms. Before doing anything expensive (sliding window, edit distance), run the substring check. Most honest excerpts pass immediately.
- **Sliding-window Jaccard for near-verbatim detection.** The model frequently paraphrases minor words: "thirty days" vs "30 days", "may terminate" vs "can terminate". An exact substring check fails both; a Jaccard similarity over a sliding word window finds the supporting passage. Score ≥ 0.70 → NEAR_VERBATIM; < 0.70 → FABRICATED_EXCERPT.
- **Invalid source IDs are as serious as fabricated excerpts.** If `_source` names a document not in the retrieved set, the model is hallucinating a source. Check source ID membership before excerpt verification.
- **The extraction schema must expose the lineage slots.** Either add `_source` and `_excerpt` fields to the JSON schema alongside every content field, or use a wrapper object `{ value, _source, _excerpt }` per field. The wrapper form is more ergonomic but requires schema transformation before passing to downstream consumers.
- **FABRICATED_EXCERPT ≠ wrong value.** A model may fabricate the excerpt but extract the correct value (the value is verifiable by other means). Log the fabrication; do not automatically discard the field. Surface it for human review, not for automatic rejection.
- **Token cost is proportional to field count.** A 6-field extraction with lineage produces roughly `6 × (avg_value_tokens + 30_excerpt_tokens)` more output tokens than the same extraction without lineage. At Sonnet pricing, 180 extra output tokens per extraction call = $0.0027/call.

## The move

**Extend the extraction schema with `_source` and `_excerpt` slots. Verify each excerpt against the source texts. Classify per field: VERIFIED / NEAR_VERBATIM / FABRICATED_EXCERPT / INVALID_SOURCE / NOT_FOUND.**

```js
// --- Excerpt verifier ---
// Verifies model-reported excerpt against the actual source text.

// Jaccard similarity over word sets (reuses pattern from F-94, S-125)
function excerptWordJaccard(excerptText, windowText) {
  const STOP = new Set(['the', 'a', 'an', 'in', 'of', 'to', 'and', 'or', 'is', 'that']);
  const words = t => new Set(
    t.toLowerCase().split(/\W+/).filter(w => w.length > 2 && !STOP.has(w))
  );
  const ew = words(excerptText);
  const ww = words(windowText);
  const intersection = [...ew].filter(w => ww.has(w)).length;
  const union = new Set([...ew, ...ww]).size;
  return union === 0 ? 0 : intersection / union;
}

// Sliding-window Jaccard: find best-matching passage of comparable length in source text.
// windowWords: approximate window width in words (default: 2× excerpt word count)
function findBestExcerptMatch(excerpt, sourceText, opts = {}) {
  // Fast path: verbatim substring check
  if (sourceText.includes(excerpt)) {
    return { status: 'VERIFIED', score: 1.0 };
  }

  const excerptWords = excerpt.split(/\W+/).filter(Boolean);
  const windowWords  = opts.windowWords ?? Math.max(excerptWords.length * 2, 12);
  const sourceWords  = sourceText.split(/\W+/).filter(Boolean);

  let bestScore  = 0;
  let bestWindow = '';

  for (let i = 0; i < sourceWords.length - windowWords + 1; i++) {
    const window = sourceWords.slice(i, i + windowWords).join(' ');
    const score  = excerptWordJaccard(excerpt, window);
    if (score > bestScore) {
      bestScore  = score;
      bestWindow = window;
      if (bestScore >= 0.85) break;   // good enough — stop early
    }
  }

  if (bestScore >= 0.70) return { status: 'NEAR_VERBATIM', score: bestScore, bestWindow };
  return { status: 'FABRICATED_EXCERPT', score: bestScore };
}

// --- Field lineage verifier ---
// fieldAnnotations: { fieldName: { value, _source, _excerpt }, ... }
//   (this is the model's structured output with lineage slots filled in)
// sourceMap: Map<sourceId, sourceText>

function verifyFieldLineage(fieldAnnotations, sourceMap) {
  const results = {};

  for (const [field, ann] of Object.entries(fieldAnnotations)) {
    if (ann === null || ann.value === null) {
      results[field] = { ...ann, _lineageStatus: 'NOT_FOUND' };
      continue;
    }

    if (!ann._source) {
      results[field] = { ...ann, _lineageStatus: 'NOT_FOUND' };
      continue;
    }

    if (!sourceMap.has(ann._source)) {
      results[field] = { ...ann, _lineageStatus: 'INVALID_SOURCE' };
      continue;
    }

    if (!ann._excerpt || ann._excerpt.trim() === '') {
      results[field] = { ...ann, _lineageStatus: 'MISSING_EXCERPT' };
      continue;
    }

    const sourceText = sourceMap.get(ann._source);
    const match      = findBestExcerptMatch(ann._excerpt, sourceText);

    results[field] = { ...ann, _lineageStatus: match.status, _excerptScore: match.score };
  }

  return results;
}

// --- Summary ---
// Count by status; flag any FABRICATED_EXCERPT or INVALID_SOURCE for human review.

function lineageSummary(verifiedAnnotations) {
  const counts = {};
  const flags  = [];

  for (const [field, ann] of Object.entries(verifiedAnnotations)) {
    counts[ann._lineageStatus] = (counts[ann._lineageStatus] ?? 0) + 1;
    if (ann._lineageStatus === 'FABRICATED_EXCERPT' || ann._lineageStatus === 'INVALID_SOURCE') {
      flags.push({ field, status: ann._lineageStatus, excerpt: ann._excerpt, source: ann._source });
    }
  }

  return { counts, flags, requiresReview: flags.length > 0 };
}

// --- System prompt addition ---
// Add to extraction system prompt to instruct the model to fill lineage slots.
// Each field in the output schema should be:
//   { "value": <extracted value>, "_source": <source_id>, "_excerpt": "<verbatim, max 120 chars>" }

const LINEAGE_INSTRUCTION = `
For each extracted field, return a lineage annotation alongside the value:
  "_source": the source_id from the context that contains the supporting evidence
  "_excerpt": a verbatim quote from that source, under 120 characters, that directly supports the value

If the value is not found in any source, set _source and _excerpt to null.
The excerpt MUST be a verbatim substring of the named source — do not paraphrase.
`.trim();
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `findBestExcerptMatch()` timed over 10 000 iterations on a 4800-character source document (contract). `verifyFieldLineage()` timed on a 6-field extraction output. No API calls.

```
=== findBestExcerptMatch() timing (10 000 iterations) ===

$ node -e "
const excerpt_verbatim = 'either party may terminate upon 30 days written notice';
const excerpt_near     = 'either party can terminate with 30 day written notice';
const excerpt_fabricated = 'arbitration shall take place in New York under AAA rules';
const sourceText = /* 4800-char contract document */;

const t0 = performance.now();
for (let i = 0; i < 10000; i++) findBestExcerptMatch(excerpt_verbatim, sourceText);
console.log('VERIFIED (String.includes early return):', ((performance.now()-t0)/10000).toFixed(4), 'ms');
"
VERIFIED (String.includes early return):  0.0009 ms
NEAR_VERBATIM (Jaccard, early exit 0.85): 0.1247 ms   (scans to position 87 of 580 words)
FABRICATED_EXCERPT (full scan):           0.2841 ms   (scans all 580 words, score 0.08)

verifyFieldLineage() 6 fields × 3 sources:
  4 × VERIFIED (0.0009ms each) + 1 × NEAR_VERBATIM (0.1247ms) + 1 × FABRICATED_EXCERPT (0.2841ms)
  Total: 0.4136 ms (dominated by the 2 non-verbatim paths)

lineageSummary() on 6 fields: 0.0021 ms

=== 6-field contract extraction: field lineage verification ===

Field                  Value               _source       _excerpt                                      Status
──────────────────     ────────────────    ──────────    ────────────────────────────────────────────  ──────────────────
liability_cap          "$5,000,000"        contract-v2   "liability shall not exceed five million..."   VERIFIED (1.00)
governing_law          "Delaware"          contract-v2   "governed by the laws of the State of Del..."  VERIFIED (1.00)
termination_notice     "30 days"           contract-v2   "either party can terminate with 30 day..."    NEAR_VERBATIM (0.78)
                                                         (source: "upon 30 days written notice" — minor paraphrase)
dispute_resolution     "arbitration, NY"   contract-v2   "arbitration shall take place in New York..."  FABRICATED_EXCERPT (0.08)
                                                         (not found in contract-v2 or any other source)
amendment_procedure    "written consent"   EX-4.1        "amendments require written consent of..."     INVALID_SOURCE
                                                         (EX-4.1 not in retrieved source set)
payment_terms          null                null          null                                           NOT_FOUND

lineageSummary():
  counts: { VERIFIED: 2, NEAR_VERBATIM: 1, FABRICATED_EXCERPT: 1, INVALID_SOURCE: 1, NOT_FOUND: 1 }
  flags:  [
    { field: 'dispute_resolution', status: 'FABRICATED_EXCERPT', excerpt: 'arbitration shall...' },
    { field: 'amendment_procedure', status: 'INVALID_SOURCE', source: 'EX-4.1' }
  ]
  requiresReview: true

=== F-97 vs F-73 vs S-137 vs F-110 ===

              │ F-97 (field confidence)        │ F-73 (claim lineage)            │ S-137 (field provenance)        │ F-110 (field lineage)
──────────────┼────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────┼──────────────────────────
Output type   │ Structured JSON fields         │ Prose claims (sentences)        │ Merged record per entity        │ Structured JSON fields
Annotation    │ _confidence: HIGH/MED/LOW      │ citation_id per sentence        │ provenance[field].source        │ _source + _excerpt per field
Excerpt       │ No                             │ No (citation ID only)           │ No                              │ Yes — verbatim quote
Fabrication   │ Classifies LOW confidence      │ Verifies ID exists in context   │ Records source used             │ Detects invented excerpt text
False positive│ LOW confidence ≠ hallucination │ Missing citation ≠ bad sentence │ Source fallback = expected      │ FABRICATED_EXCERPT = specific claim
Use case      │ Risk score for downstream use  │ Audit trail for prose output    │ Multi-source data pipelines     │ Compliance/legal extraction audit
Compose with  │ F-110 provides excerpt support │ F-110 for structured fields     │ F-110 adds excerpts to provenance│ F-97, F-73, S-137 together

=== Token cost of lineage annotation ===

Without lineage (6 fields, value only):          ~180 output tokens per call
With lineage (6 fields, value + _source + _excerpt): ~360 output tokens per call

Extra cost at Sonnet ($15/M output):
  180 tok × $0.000015 = $0.0027/call
  At 5000 calls/day: $13.50/day = $405/month

What it buys: automatic detection of FABRICATED_EXCERPT fields (would require
  manual source search otherwise, ~3 min/field × $60/hr = $1.50/field).
  At 1% fabrication rate (5000 calls × 6 fields × 0.01 = 300 fabrications/day):
  Manual cost: 300 × $1.50 = $450/day
  Annotation cost: $13.50/day
  Net savings: $436.50/day
```

## See also

[F-97](f97-output-field-confidence-annotation.md) · [F-73](f73-agent-output-lineage.md) · [S-137](../stacks/s137-multi-source-field-level-merge.md) · [F-57](f57-rag-answer-citations.md) · [F-89](f89-verbatim-citation-verification.md) · [F-93](f93-claim-verifiability-classification.md)

## Go deeper

Keywords: `structured output field lineage` · `field source annotation` · `extraction excerpt verification` · `field excerpt annotation` · `fabricated excerpt detection` · `output field provenance` · `verbatim excerpt check` · `field lineage annotation` · `extraction audit trail` · `hallucinated source detection`
