# F-155 · Extraction Array Field Uniqueness Check

Array fields in extraction schemas should have unique values. They often don't.

A contract document lists Acme Corporation as buyer in one clause and as guarantor in another. The model, extracting faithfully, places Acme in the `parties` array twice — once per role. The downstream deduplication step that removes the double entry was added two weeks after the first customer reported Acme signing a contract with itself. A clause ID that appears in the contract body and again in the schedule appendix gets extracted twice into `clause_ids`, causing downstream processing to apply the clause twice and double-bill one provision. A payment milestone ID appears under two different payment schedules; the model extracts both, producing two `M-01` entries with different amounts, and the reconciliation step silently keeps one.

These failures share a structure: the model is extracting faithfully from a document that contains the same entity in multiple locations, and the schema does not forbid duplicates. The model sees two occurrences and records two entries. The schema allows it. The extraction is technically correct and substantively wrong.

The array field uniqueness check runs after extraction and before any downstream use of the arrays. It inspects each registered array field for duplicate values, using a normalize function to catch case-insensitive variants ("ACME CORPORATION" == "Acme Corporation"), and for object arrays a `keyFn` that extracts the identity field (milestone ID, clause ID) rather than comparing whole objects. Each registered field carries a severity: ERROR for identifier arrays where a duplicate is always wrong, WARN for name arrays where slight differences may be intentional. The `retryHint` on each violation is composed to feed directly into F-154's field-level retry prompt.

## Situation

A legal AI pipeline extracts `parties`, `clause_ids`, and `payment_milestones` from multi-party agreements. Common failure modes in production:

- Acme Corporation appears as buyer and as guarantor: extracted twice into `parties`. WARN — the data is technically informative but wrong as a list of distinct parties.
- Clause CL-01 is cited in the body and in the schedule appendix: extracted twice into `clause_ids`. ERROR — the downstream clause processor will execute the clause twice.
- Milestone M-01 appears in the main payment schedule and in an amendment: extracted with two different amounts. ERROR — the payment system receives contradictory amounts for the same milestone.

Running `ExtractionArrayUniquenessChecker` catches all three before the data leaves the extraction layer.

## Forces

- **F-132 (array cardinality check) does not catch this.** F-132 verifies that arrays have the right count: `parties` must have 2–10 entries. Two Acme entries satisfies the cardinality check. Uniqueness is a separate invariant.
- **F-70 (structural validation) does not catch this.** F-70 checks required fields, types, and enum values. A `clause_ids` array with two `"CL-01"` strings is structurally valid JSON.
- **Normalize before comparing.** LLMs produce casing variations: "ACME CORPORATION", "Acme Corporation", "acme corporation". Without normalization, each case variant passes the uniqueness check and lands in the downstream data as a distinct party. Default normalization: `String(v).trim().toLowerCase()`.
- **For object arrays, compare the identity field, not the whole object.** A `payment_milestones` entry is `{ milestone_id: "M-01", amount: 5000, due_date: "2026-03-01" }`. Two entries with `milestone_id: "M-01"` and different amounts are duplicates on the identity key. Comparing the full object would not catch this. Pass `keyFn: item => item.milestone_id`.
- **Severity by field type.** Identifier arrays (clause IDs, milestone IDs, party IDs) use ERROR — a duplicate is always a data integrity failure. Name arrays (party names) use WARN — two entries for the same party may carry intent (buyer vs guarantor role). The severity choice is a schema decision, not a runtime one. Register it once in the checker.
- **retryHint feeds F-154 directly.** When a violation is found, the retryHint names the field, the duplicate values, and the correction instruction. F-154's `composeFieldRetryPrompt()` picks up ERROR violations and builds the targeted retry. No translation required.
- **Empty and null arrays skip cleanly.** If the field is null, absent, or empty, the check returns SKIP. Presence validation belongs to F-70 and F-147; the uniqueness check does not double-validate presence.

## The move

**Register each array field with a normalize function and severity. Inspect after extraction. Route ERROR violations through F-154's field-level retry.**

```js
// --- Extraction array field uniqueness check ---
// Detects duplicate values in array fields after extraction.
// Compose with:
//   F-132 (cardinality check) — min/max array length
//   F-70  (structural validation) — required/type/enum
//   F-154 (field-level retry) — pass ERROR retryHints to composeFieldRetryPrompt()
// Register fields once at app startup; call check() on every extraction output.

function isPresent(val) { return val !== null && val !== undefined && val !== ''; }

class ExtractionArrayUniquenessChecker {
  constructor() { this._rules = []; }

  // field:    name of the array field in the extraction output
  // opts.normalize: (value) → string key. Default: case-insensitive string compare.
  // opts.keyFn:     for object arrays, extract the identity field before normalizing.
  //                 Example: item => item.milestone_id
  // opts.severity:  'ERROR' (identifier arrays) or 'WARN' (name arrays). Default: 'ERROR'.
  registerField(field, opts) {
    opts = opts || {};
    this._rules.push({
      field,
      normalize: opts.normalize || (v => String(v).trim().toLowerCase()),
      keyFn:     opts.keyFn     || null,
      severity:  opts.severity  || 'ERROR',
    });
    return this;
  }

  check(output) {
    const results = this._rules.map(rule => {
      const arr = output[rule.field];
      if (!isPresent(arr))     return { status: 'SKIP',  field: rule.field, reason: 'field null or absent' };
      if (!Array.isArray(arr)) return { status: 'SKIP',  field: rule.field, reason: 'not an array' };
      if (arr.length === 0)    return { status: 'UNIQUE', field: rule.field, count: 0 };

      const seen = new Map();
      const duplicates = [];

      for (let i = 0; i < arr.length; i++) {
        const raw = rule.keyFn ? rule.keyFn(arr[i]) : arr[i];
        if (raw === null || raw === undefined) continue;
        const key = rule.normalize(raw);
        if (seen.has(key)) {
          duplicates.push({ value: arr[i], index: i, firstIndex: seen.get(key) });
        } else {
          seen.set(key, i);
        }
      }

      if (duplicates.length === 0) {
        return { status: 'UNIQUE', field: rule.field, count: arr.length };
      }

      const dupDescriptions = duplicates.map(d => {
        const label = rule.keyFn
          ? rule.keyFn(d.value)
          : (typeof d.value === 'string' ? d.value : JSON.stringify(d.value));
        return `"${label}" (index ${d.index}, first at ${d.firstIndex})`;
      });

      return {
        status:    'DUPLICATE_FOUND',
        field:     rule.field,
        severity:  rule.severity,
        count:     arr.length,
        duplicates,
        retryHint: `${rule.field}: ${duplicates.length} duplicate value(s) found — ` +
                   dupDescriptions.join('; ') +
                   '. Each entry should appear at most once regardless of how many roles or sections it appears in.',
      };
    });

    const violations = results.filter(r => r.status === 'DUPLICATE_FOUND');
    const errors     = violations.filter(r => r.severity === 'ERROR');
    return {
      passed:   errors.length === 0,
      results,
      violations,
      errors,
      warnings: violations.filter(r => r.severity === 'WARN'),
    };
  }
}

// Register once at startup
const CHECKER = new ExtractionArrayUniquenessChecker()
  .registerField('parties',            { severity: 'WARN' })
  .registerField('clause_ids',         { severity: 'ERROR' })
  .registerField('payment_milestones', { keyFn: item => item && item.milestone_id, severity: 'ERROR' });

// Call on every extraction output
const result = CHECKER.check(extractionOutput);
if (!result.passed) {
  const prompt = composeFieldRetryPrompt(result.errors);  // F-154
  // ... retry or escalate via F-133
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Five scenarios covering: all unique, party duplicate (WARN), clause ID + milestone duplicate (ERROR×2), case-insensitive duplicate, null fields. Timed over 1 000 000 iterations. Zero API calls.

```
=== Extraction Array Field Uniqueness Check ===

--- Scenario A: all arrays unique ---
  UNIQUE         parties            count=3
  UNIQUE         clause_ids         count=3
  UNIQUE         payment_milestones count=2
  passed: true

--- Scenario B: parties duplicate (same party as buyer + guarantor) ---
  DUPLICATE_FOUND  parties            count=3  WARN
    retryHint: "parties: 1 duplicate value(s) found — "Acme Corporation"
               (index 2, first at 0). Each entry should appear at most once
               regardless of how many roles or sections it appears in."
  UNIQUE           clause_ids         count=2
  UNIQUE           payment_milestones count=2
  passed: true  (WARN — delivery not blocked; parties list cleaned before use)

--- Scenario C: clause_ids duplicate + payment_milestones duplicate ---
  UNIQUE           parties            count=2
  DUPLICATE_FOUND  clause_ids         count=5  ERROR
    "CL-01" (index 3, first at 0); "CL-03" (index 4, first at 2) — 2 duplicates
  DUPLICATE_FOUND  payment_milestones count=2  ERROR
    "M-01" (index 1, first at 0) — 1 duplicate (different amounts: 5000 vs 7500)
  passed: false  errors: 2  warnings: 0

--- Scenario D: case-insensitive duplicate (same party, different casing) ---
  DUPLICATE_FOUND  parties  count=3  WARN
    "ACME CORPORATION" normalized == "acme corporation" at index 0
  passed: true  (WARN — normalize catches case variants before downstream dedup)

--- Scenario E: null array fields (F-70/F-147 handles presence; F-155 skips) ---
  SKIP           parties            (field null or absent)
  UNIQUE         clause_ids         count=1
  SKIP           payment_milestones (field null or absent)

=== Timing (1 000 000 iterations) ===
check() 3 fields, all UNIQUE (Scenario A):  0.0029 ms
check() 3 fields, 2 DUPLICATE (Scenario C): 0.0051 ms
Zero API calls. Zero tokens.
```

## See also

[F-132](f132-extraction-array-cardinality-check.md) · [F-154](f154-extraction-field-level-retry.md) · [F-70](f70-verifiable-output-design.md) · [F-147](f147-extraction-field-presence-check.md) · [F-133](f133-extraction-retry-escalation-policy.md)

## Go deeper

Keywords: `extraction array uniqueness check` · `duplicate array value detection` · `extraction deduplication` · `array field uniqueness validator` · `LLM extraction duplicate detection` · `case-insensitive dedup` · `extraction array validator` · `keyFn object array uniqueness` · `array uniqueness retryHint` · `extraction output array integrity`
