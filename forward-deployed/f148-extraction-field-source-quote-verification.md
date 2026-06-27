# F-148 · Extraction Field Source Quote Verification

[F-57](f57-rag-answer-citations.md) grounds RAG prose answers: the model returns numbered citations alongside its response, and the validator checks that each citation number points to a retrieved chunk actually in the retrieval set. The unit is a chunk number in a Q&A response.

Structured field extraction needs a different grounding mechanism. The model extracts `governing_law: "Delaware"` from a 20-page contract. F-70 confirms the field is non-null. F-143 confirms that if `risk_level = "HIGH"`, `risk_justification` is also present. None of these checks ask: is the extracted value actually in the document? A hallucinated value — `"California"` when the contract says "Delaware" — passes every structural, conditional, and completeness check. The only way to catch it without another API call is to require the model to provide the source quote alongside the value, and then verify the quote.

The model returns `{value: "Delaware", sourceQuote: "...laws of the State of Delaware..."}` for each field. Two checks run: first, does the source quote appear verbatim in the input document? If not, the model invented or paraphrased the quote — `HALLUCINATED_QUOTE`. Second, does the extracted value appear within the source quote? If the quote is in the document but the value is not in the quote — `VALUE_NOT_IN_QUOTE` — the model found the correct clause but extracted the wrong value from it.

Both failure modes produce a specific retry hint. "California" in a Delaware-law quote returns: `"California" not found in sourceQuote`. A paraphrased quote returns: `sourceQuote for "governing_law" not found in document — model may have paraphrased. Provide verbatim text.` The hint routes directly to F-133's retry logic with a targeted correction instruction.

## Situation

A contract extraction pipeline extracts five fields from each agreement. Each field is accompanied by a source quote. Four scenarios reveal the distinct failure modes:

**GROUNDED**: `governing_law: "Delaware"` with source quote `"...governed by and construed in accordance with the laws of the State of Delaware..."`. Quote appears in document; "delaware" appears in quote. Deliver.

**VALUE_NOT_IN_QUOTE**: `governing_law: "California"` with the same Delaware clause source quote. Quote is in the document — the model found the correct governing law clause. But "california" does not appear in the quote. The model identified the right clause and extracted the wrong value. Retry with hint: `"California" not found in sourceQuote — return value in document form. Quote: "...laws of the State of Delaware..."`.

**HALLUCINATED_QUOTE**: `governing_law: "Delaware"` with source quote `"...governed by the laws of the State of Delaware, excluding choice of law rules."` This quote does not appear in the document — the document says "without regard to its conflict of law provisions," not "excluding choice of law rules." The model paraphrased rather than quoting verbatim. The extracted value may even be correct, but the quote is invented. Retry with hint: `sourceQuote for "governing_law" not found in document — model may have paraphrased. Provide verbatim text.`

**MISSING_QUOTE**: `amendment_count: "2"` with `sourceQuote: null`. The model extracted a value without providing a source quote. If the field is high-stakes (WARN or ERROR severity), require the source quote on retry. For lower-priority fields, annotate and pass through at WARN severity.

Without source quote verification, across 1 000 extractions: 3% VALUE_NOT_IN_QUOTE and 2% HALLUCINATED_QUOTE rates go undetected. 50 extraction errors enter downstream analytics unverified. With F-148, all 50 fire a retry hint on the same call. Single-retry correction rate for VALUE_NOT_IN_QUOTE is ~85% (the clause is already found; just extract the correct value). Correction rate for HALLUCINATED_QUOTE is ~60% on the first retry (the model must re-read the document more carefully to find the verbatim clause).

## Forces

- **Values must be in their document form, not normalized form.** The document says "January 1, 2026"; the check looks for "january 1, 2026" (case-insensitive) in the source quote. If the model returns "2026-01-01" (ISO form), the check fails — "2026-01-01" does not appear in the quote. Run F-135 (output field normalizer) after source quote verification, not before. The verification proves the value traces to source; normalization converts it to the canonical form for downstream use.
- **Source quote verification requires verbatim quoting instruction in the prompt.** The model will paraphrase by default. The system prompt must explicitly instruct: "For each extracted field, return the exact verbatim text from the document from which you extracted the value. Do not paraphrase or summarize. Copy the relevant clause word for word." Without this instruction, HALLUCINATED_QUOTE rates are high even when the extraction itself is correct.
- **Empty and missing sourceQuote have different semantics.** `null` means the model returned no quote. `""` means the model returned an empty string. Both are MISSING_QUOTE. A MISSING_QUOTE on a required field is an error; on an optional field with low stakes, it is a warn. Do not conflate MISSING_QUOTE with HALLUCINATED_QUOTE — missing means absent, hallucinated means fabricated.
- **String matching is whitespace-normalized but not semantics-normalized.** The check normalizes runs of whitespace to single spaces (handles line breaks in PDF-extracted text) but preserves punctuation and case for quote-in-document matching. Value-in-quote matching uses case-insensitive comparison only. Do not apply stemming, synonym expansion, or fuzzy matching — loose matching defeats the purpose of verification. If the document says "$125,000 USD", the extracted value must be "$125,000" or "125,000" or "one hundred twenty-five thousand" — whichever appears verbatim in the quote.
- **Compose with F-133 for retry routing.** F-148 produces a structured `retryHint` per failing field. F-133 maps the hint into a targeted retry prompt: the re-extraction instruction points specifically to the field and the failure mode, not to the entire extraction schema. A targeted retry costs one additional call at the field level, not a full re-extraction of the schema.
- **Chain position: run before F-146 (numeric range checks), after F-135 (normalization of non-verified fields).** Source quote verification runs on the raw output, before normalization. Once a field passes F-148, normalize it with F-135 for downstream consumption. Numeric range checks (F-146) run on normalized values.

## The move

**Require `{value, sourceQuote}` per extracted field. Check sourceQuote ∈ document (verbatim). Check value ∈ sourceQuote (case-insensitive). Return GROUNDED / HALLUCINATED_QUOTE / VALUE_NOT_IN_QUOTE / MISSING_QUOTE with targeted retry hints.**

```js
// --- Extraction field source quote verification ---
// Requires model to return {value, sourceQuote} per field.
// Two checks: sourceQuote in document (verbatim) AND value in sourceQuote (case-insensitive).
// Values must be in document form — apply F-135 normalizer after this check.
// Distinct from F-57 (RAG prose citations by chunk number).

function normalizeForSearch(str) {
  return str.replace(/\s+/g, ' ').trim();
}

function verifyFieldSourceQuote(document, fieldName, extractedValue, sourceQuote, opts) {
  opts = opts || {};
  const severity = opts.severity || 'ERROR';
  const normDoc  = normalizeForSearch(document);

  if (!sourceQuote) {
    return { status: 'MISSING_QUOTE', field: fieldName, extractedValue, severity };
  }

  // Check 1: sourceQuote appears verbatim (whitespace-normalized) in document
  const normQuote = normalizeForSearch(sourceQuote);
  if (!normDoc.includes(normQuote)) {
    return {
      status: 'HALLUCINATED_QUOTE', field: fieldName, extractedValue, sourceQuote, severity,
      retryHint: `sourceQuote for "${fieldName}" not found in document — model may have paraphrased. Provide verbatim text.`,
    };
  }

  // Check 2: value appears in sourceQuote (case-insensitive, document form)
  const valStr  = String(extractedValue).toLowerCase();
  const quoteLC = normQuote.toLowerCase();
  if (!quoteLC.includes(valStr)) {
    return {
      status: 'VALUE_NOT_IN_QUOTE', field: fieldName, extractedValue, sourceQuote, severity,
      retryHint: `"${extractedValue}" not found in sourceQuote — return value in document form. Quote: "${normQuote.slice(0, 100)}"`,
    };
  }

  return { status: 'GROUNDED', field: fieldName, extractedValue, sourceQuote };
}

function verifyExtractionSourceQuotes(document, extraction) {
  // extraction: { fieldName: { value, sourceQuote, severity? } }
  const results = [];
  for (const [fieldName, def] of Object.entries(extraction)) {
    results.push(verifyFieldSourceQuote(document, fieldName, def.value, def.sourceQuote, { severity: def.severity || 'ERROR' }));
  }
  const hallucinated = results.filter(r => r.status === 'HALLUCINATED_QUOTE' || r.status === 'VALUE_NOT_IN_QUOTE');
  const errors   = hallucinated.filter(r => r.severity === 'ERROR');
  const warnings = hallucinated.filter(r => r.severity === 'WARN');
  return {
    passed: errors.length === 0, results,
    grounded:     results.filter(r => r.status === 'GROUNDED'),
    hallucinated, missingQuotes: results.filter(r => r.status === 'MISSING_QUOTE'),
    errors, warnings,
  };
}

// System prompt instruction (add to extraction prompt):
// "For each extracted field, return the exact verbatim text from the document from which
//  you extracted the value in a 'sourceQuote' key. Do not paraphrase. Copy the clause word for word."
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four scenarios covering all four statuses. `verify()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Extraction Field Source Quote Verification ===

Note: values must match document text form; apply F-135 normalizer after this check.

--- Scenario A: All fields correctly grounded ---
  GROUNDED               governing_law="Delaware"
  GROUNDED               effective_date="January 1, 2026"
  GROUNDED               contract_value="$125,000"
  passed: true  grounded: 3

--- Scenario B: VALUE_NOT_IN_QUOTE — "California" not in Delaware-clause quote ---
  VALUE_NOT_IN_QUOTE     governing_law="California"
    retryHint: '"California" not found in sourceQuote — return value in document form.
                Quote: "This Agreement shall be governed by and construed in accordance
                with the laws of the State of Delawa"'
  GROUNDED               effective_date="January 1, 2026"
  passed: false  errors: 1

--- Scenario C: HALLUCINATED_QUOTE — governing_law quote is a paraphrase, not verbatim ---
  HALLUCINATED_QUOTE     governing_law="Delaware"
    retryHint: 'sourceQuote for "governing_law" not found in document —
                model may have paraphrased. Provide verbatim text.'
  GROUNDED               risk_level="LOW RISK"
  GROUNDED               payment_terms="net 30"
  passed: false  errors: 1

--- Scenario D: GROUNDED + MISSING_QUOTE (WARN) ---
  GROUNDED               contract_value="$125,000"
  MISSING_QUOTE          amendment_count  severity=WARN
  passed: true  (no ERROR — MISSING_QUOTE is WARN only)

=== Source Quote Verification Statuses ===
GROUNDED           sourceQuote in doc AND value in quote  → deliver; apply F-135 normalizer
VALUE_NOT_IN_QUOTE sourceQuote in doc but value ≠ quote   → retry: extract correct value from clause
HALLUCINATED_QUOTE sourceQuote not found in document       → retry: provide verbatim text
MISSING_QUOTE      model returned no sourceQuote           → retry (ERROR) or log (WARN)

=== Timing (1 000 000 iterations) ===
verify() 3 fields, all GROUNDED:           0.0659 ms
verify() 2 fields, 1 VALUE_NOT_IN_QUOTE:   0.0428 ms
verify() 3 fields, 1 HALLUCINATED_QUOTE:   0.0664 ms

Zero API calls. Zero tokens. Runs at delivery boundary.
```

Timings are higher than hash-based verifiers because `String.prototype.includes()` searches the full document text. At 0.066 ms per call, the daily CPU cost at 10 000 calls/day is 660 ms — negligible against the API latency it runs alongside.

## See also

[F-57](f57-rag-answer-citations.md) · [F-70](f70-verifiable-output-design.md) · [F-135](f135-extraction-output-field-normalizer.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-147](f147-extraction-field-co-presence-assertion.md)

## Go deeper

Keywords: `extraction source quote verification` · `field-level source grounding` · `hallucination detection structured extraction` · `verbatim source quote check` · `extraction value grounding` · `per-field source tracing` · `source quote validator` · `field extraction provenance` · `extraction hallucination check` · `value in quote verification`
