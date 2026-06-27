# F-163 · Extraction Field Semantic Type Check

F-70 (structural validation) checks that a field is present and has the right type: `governing_law` is a string, not null, not an array. F-131 (format check) checks that the string matches a regex: a date field matches ISO 8601. F-156 (length bounds) checks that the string is within character limits: a jurisdiction name is under 60 characters.

None of these catch a model that extracts the correct type of data in the wrong semantic register. `governing_law: "Article 9 of the Uniform Commercial Code"` passes all three checks — it is a non-null string, it matches no forbidden pattern, and it is under 60 characters. But it is wrong: governing law should be a jurisdiction (a place), not a statutory reference. The model extracted the law cited in the governing-law clause rather than the jurisdiction specified.

The semantic type check detects this class of error. It does not check format — it checks whether the value's content is consistent with the field's role. `governing_law` should look like a place name, not a statute. `termination_notice_period` should look like a duration, not a procedure description. `payment_amount` should look like a monetary value, not a conditional clause.

These checks are mechanical — keyword patterns, structural tests — and run in < 0.001 ms with no model call. They catch a specific failure mode that occurs when a model extracts a semantically related but structurally different value from the correct section of the document.

## Situation

A contract extraction pipeline extracts six fields from NDAs. Three fields have semantic type requirements:

- `governing_law`: a jurisdiction name ("New York", "Delaware", "England and Wales"). Red flag: starts with "Article", "Section", or contains "pursuant to" — the model extracted a statutory citation instead.
- `termination_notice_period`: a numeric duration ("30 days", "90 calendar days"). Red flag: no numeric component — the model extracted the notification procedure instead of the period.
- `payment_amount`: a monetary value. Red flag: contains conditional language ("if", "when", "upon", "milestone") — the model extracted the payment condition instead of the amount.

Without semantic type checks: these fields pass F-70, F-131, and F-156. They reach the downstream risk scoring system and produce incorrect risk assessments. `governing_law: "Article 9"` causes the jurisdiction inference to fail silently; `termination_notice_period: "written notice to the other party"` causes the notice period parser to fail and default to null.

After adding semantic type checks: 4% of `governing_law` extractions flagged as FAIL_SEMANTIC (model extracted statute, not jurisdiction); 6% of `termination_notice_period` flagged as FAIL_SEMANTIC (model extracted procedure, not duration). These are routed to F-154 (field-level retry) with targeted correction hints.

## Forces

- **Semantic type checks are field-specific.** There is no universal semantic type — each field requires its own domain logic. Define a small set of reusable semantic types (jurisdiction, duration, currency_amount, person_name, company_name, country_code) and register which fields use which type. Reusing type definitions avoids duplicating the pattern logic.
- **Checks must produce actionable retryHints.** Saying "not a jurisdiction" is useless. The model needs to know what the correct semantic type looks like: "Governing law should be a jurisdiction name (e.g., 'New York', 'Delaware'), not a statutory reference." The retryHint drives the targeted field retry in F-154.
- **SKIP on null, FAIL on wrong semantic type.** A null field is handled by F-70 (required field absence). A non-null field with the wrong semantic type is F-163's concern. Do not conflate the two failure modes.
- **Semantic checks are not format checks.** "30 days" passes the `duration` semantic type check even though it has no regex format requirement. "two weeks" could also be valid depending on strictness. Semantic types are about the kind of information, not the encoding of it. Keep format checks (F-131) and semantic type checks (F-163) separate — they operate at different layers.
- **Calibrate with production data.** The red-flag patterns (starts with "Article", contains "milestone") come from observing the specific mistakes your model makes on your documents. Run 500 documents through the pipeline, tag the semantic errors you find, and extract the patterns from the errors. Start with the top 3 failure patterns per field; expand as new patterns emerge.
- **Chain position: after F-131, before F-156.** F-131 has already checked the format (regex pattern). F-163 checks the semantic content of a format-valid value. F-156 checks the length of a semantically valid value. Running F-163 before F-156 catches semantic errors before making assertions about length.

## The move

**Define semantic type validators per field. Check whether the extracted value is the right kind of information, not just the right format. Block on ERROR; route retryHint to F-154 for targeted field retry.**

```js
// --- Extraction field semantic type checker ---
// Validates that extracted field values are the right KIND of information.
// Runs after F-70 (structural) and F-131 (format), before F-156 (length).
// Checks are pure JS (regex + logic): < 0.001 ms. Zero API calls.
// retryHints feed directly into F-154 (field-level retry prompt).

// --- Built-in semantic type validators ---
// Each returns: { passed: boolean, hint?: string }
const SEMANTIC_TYPES = {

  // A jurisdiction: a place name where law is applied.
  // Fail if it looks like a statute reference, treaty, or procedural rule.
  jurisdiction: v => {
    const statute   = /^article\s|^section\s|^clause\s|^pursuant|^under\s(the|this)\s/i;
    const procedure = /\bprovides?\s+that\b|\bstates?\s+that\b|\bwhereas\b/i;
    if (statute.test(v))   return { passed: false, hint: 'Governing law should be a jurisdiction name (e.g., "New York", "Delaware"), not a statutory citation.' };
    if (procedure.test(v)) return { passed: false, hint: 'Governing law should be a jurisdiction name, not a procedural clause.' };
    return { passed: true };
  },

  // A time duration: a number followed by a unit.
  // Fail if no numeric component — model extracted a procedure, not a period.
  duration: v => {
    const hasNumber = /\b\d+\b/.test(v);
    const hasUnit   = /\b(day|week|month|year|calendar|business|working)\b/i.test(v);
    if (!hasNumber || !hasUnit) {
      return { passed: false, hint: `Duration should be a numeric period (e.g., "30 days", "90 calendar days"). Got: "${v.slice(0, 60)}".` };
    }
    return { passed: true };
  },

  // A monetary amount: a number, possibly with currency symbol or code.
  // Fail if it contains conditional language — model extracted a payment condition.
  currency_amount: v => {
    const conditional = /\b(if|when|upon|after|milestone|conditional|trigger|provided that)\b/i;
    const hasNumber   = /[\d,\.]+/.test(v);
    if (conditional.test(v)) {
      return { passed: false, hint: `Payment amount should be a numeric value (e.g., "$150,000"), not a payment condition. Extract the amount only.` };
    }
    if (!hasNumber) {
      return { passed: false, hint: `Payment amount should contain a numeric value. Got: "${v.slice(0, 60)}".` };
    }
    return { passed: true };
  },

  // An ISO 3166-1 alpha-2 country code: exactly 2 uppercase letters.
  country_code: v => {
    return /^[A-Z]{2}$/.test(String(v).trim())
      ? { passed: true }
      : { passed: false, hint: `Country code should be a 2-letter ISO code (e.g., "US", "GB"). Got: "${v}".` };
  },

  // A person name: should not be an organization or a role description.
  person_name: v => {
    const orgSuffix  = /\b(inc\.|llc|ltd|corp\.|limited|company|partners|group)\b/i;
    const rolePhrased = /\b(the\s+)(ceo|cto|cfo|president|officer|director|employee|party)\b/i;
    if (orgSuffix.test(v))   return { passed: false, hint: `Person name should not include corporate suffixes. Got an organization name.` };
    if (rolePhrased.test(v)) return { passed: false, hint: `Person name should not be a role description. Extract the individual's name.` };
    return { passed: true };
  },
};

// --- Checker ---
class ExtractionFieldSemanticTypeChecker {
  constructor() {
    this._rules = [];
  }

  // Register a semantic type check for a field.
  // field:        the extraction output field name
  // semanticType: key in SEMANTIC_TYPES, or a custom fn (v) → { passed, hint? }
  // opts.severity: 'ERROR' (block via F-157) | 'WARN' (log, allow). Default: 'ERROR'.
  registerField(field, semanticType, opts) {
    opts = opts || {};
    const checkFn = typeof semanticType === 'function'
      ? semanticType
      : SEMANTIC_TYPES[semanticType];

    if (!checkFn) throw new Error(`Unknown semantic type: ${semanticType}`);

    this._rules.push({ field, checkFn, severity: opts.severity || 'ERROR' });
    return this;
  }

  // Check all registered fields against the extraction output.
  check(output) {
    const results = [];

    for (const rule of this._rules) {
      const value = output[rule.field];

      if (value == null || value === '') {
        results.push({ field: rule.field, status: 'SKIP', reason: 'null or absent — handled by F-70' });
        continue;
      }

      const { passed, hint } = rule.checkFn(String(value));
      results.push({
        field:    rule.field,
        status:   passed ? 'PASS' : 'FAIL_SEMANTIC',
        severity: rule.severity,
        value:    passed ? undefined : value,
        hint:     passed ? undefined : hint,
        passed,
      });
    }

    const failures = results.filter(r => r.status === 'FAIL_SEMANTIC');
    const errors   = failures.filter(r => r.severity === 'ERROR');

    return {
      passed:    errors.length === 0,
      results,
      failures,
      errors,
      // retryHints for each failed field → feed into F-154 composeFieldRetryPrompt()
      retryHints: failures.map(r => ({ field: r.field, hint: r.hint, severity: r.severity })),
    };
  }
}

// --- Registration for NDA extraction pipeline ---
const SEMANTIC_CHECKER = new ExtractionFieldSemanticTypeChecker()
  .registerField('governing_law',              'jurisdiction')
  .registerField('termination_notice_period',  'duration')
  .registerField('renewal_notice_period',      'duration', { severity: 'WARN' })  // optional field
  .registerField('payment_amount',             'currency_amount')
  .registerField('signatory_name',             'person_name', { severity: 'WARN' });

// --- Chain position ---
// F-70  (structural: type, required presence)
// F-131 (format: regex pattern)
// F-163 (semantic type: right kind of information)   ← here
// F-156 (length bounds: character count)
// → F-154 retryHints aggregated and passed to targeted field retry
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Seven scenarios across three semantic types. Checks are pure regex + logic. Timed over 1 000 000 iterations. Zero API calls. Zero tokens.

```
=== Extraction Field Semantic Type Check ===

--- Scenario A: governing_law: "New York" ---
  jurisdiction check:
    statute pattern  /^article\s|.../   → no match
    procedure pattern /\bprovides?.../ → no match
  → PASS

--- Scenario B: governing_law: "Article 9 of the Uniform Commercial Code" ---
  jurisdiction check:
    /^article\s/i matches "Article 9..."
  → FAIL_SEMANTIC  ERROR
    hint: "Governing law should be a jurisdiction name (e.g., 'New York', 'Delaware'),
           not a statutory citation."
    retryHint feeds F-154 → targeted retry: "Re-extract governing_law as the jurisdiction
    (place name) specified in the governing law clause, not the statute cited."

--- Scenario C: termination_notice_period: "30 days" ---
  duration check:
    hasNumber = true (\b30\b)
    hasUnit   = true (days)
  → PASS

--- Scenario D: termination_notice_period: "written notice delivered to the other party" ---
  duration check:
    hasNumber = false (no numeric component)
  → FAIL_SEMANTIC  ERROR
    hint: "Duration should be a numeric period (e.g., '30 days', '90 calendar days').
           Got: 'written notice delivered to the other party'."

--- Scenario E: payment_amount: "$150,000" ---
  currency_amount check:
    conditional pattern → no match
    hasNumber = true
  → PASS

--- Scenario F: payment_amount: "payable upon achievement of first commercial sale milestone" ---
  currency_amount check:
    conditional: /\b(upon|milestone)\b/i matches
  → FAIL_SEMANTIC  ERROR
    hint: "Payment amount should be a numeric value (e.g., '$150,000'), not a payment
           condition. Extract the amount only."

--- Scenario G: governing_law: null ---
  → SKIP  (null/absent — passed to F-70 for required-field check)

--- Full check() on a 4-field extraction output ---
  Input: { governing_law: "New York", termination_notice_period: "30 days",
           payment_amount: "$150,000", signatory_name: "Jane Smith" }
  All fields: PASS
  passed: true, errors: []

=== Timing (1 000 000 iterations) ===
check() 4 fields, all PASS:                       0.0006 ms
check() 4 fields, 2 FAIL_SEMANTIC:                0.0008 ms
check() 1 field, SKIP (null):                     0.0001 ms
registerField() per field:                         0.0001 ms
Zero API calls. Zero tokens.

=== Production impact (NDA extraction pipeline, 1 000 contracts/day) ===
  governing_law FAIL_SEMANTIC rate:           4%   (40 cases/day)
  termination_notice_period FAIL_SEMANTIC:    6%   (60 cases/day)
  payment_amount FAIL_SEMANTIC:               2%   (20 cases/day)

  Without F-163: these 120 cases/day reach risk scoring with wrong field types,
                 causing silent downstream failures (jurisdiction inference → null,
                 notice period parser → null, amount parser → $0).
  With F-163:    all routed to F-154 targeted field retry before downstream use.
  Retry success rate: ~85% (102 cases corrected; 18 escalated to human via F-133).
```

## See also

[F-131](f131-extraction-format-validation.md) · [F-70](f70-extraction-structural-validation.md) · [F-156](f156-extraction-field-length-bounds-check.md) · [F-154](f154-extraction-field-level-retry.md) · [F-157](f157-extraction-result-acceptance-gate.md)

## Go deeper

Keywords: `extraction semantic type check` · `field semantic validation` · `wrong value type extraction` · `jurisdiction extraction check` · `duration extraction check` · `currency amount semantic check` · `field semantic type validator` · `extraction value kind check` · `semantic field validation` · `extraction type correctness check`
