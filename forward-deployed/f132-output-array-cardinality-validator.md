# F-132 · Output Array Field Cardinality Validator

[F-70](f70-structured-output-validation.md) validates that required array fields are present and that field types are correct — it confirms `line_items` is an array, not a string. [F-131](f131-output-field-string-pattern-validator.md) validates that string fields match registered format patterns. [F-92](f92-agent-output-arithmetic-invariants.md) validates that numeric fields satisfy arithmetic invariants like `total = sum(line_items amounts)`.

None of these validate how many items an array field contains. F-70 confirms `line_items` is a non-null array — it does not confirm the array has at least one item. F-92 can check that the total equals the sum of the array's numeric values, but only when the items are present to sum. If `line_items` is `[]`, the sum is 0 — which F-92 accepts as arithmetically correct — but the empty array itself means the extraction failed to find any items in the invoice.

Array cardinality validation registers minimum and maximum item counts per field and checks non-null array fields against these bounds. A `line_items: []` is too few for an invoice extraction. A `citations` array with 25 items when the output schema allows at most 20 is too many. A `parties` array with 1 item on a bilateral contract is a known failure mode: the model extracted the first party but missed the second.

## Situation

A contract extraction pipeline processes bilateral agreements. The output schema includes:
- `line_items`: array of items in a schedule (min 1, max 100)
- `citations`: source references supporting the output (min 1, max 20)
- `parties`: contracting parties (min 2, max 10 — a bilateral contract requires at least 2)
- `risk_factors`: list of identified risk factors (min 0, max 10 — WARN if too many)
- `payment_terms`: list of payment schedules (min 1)

A batch of 200 contracts reveals: 12 extractions return `parties: ['Alpha Corp']` — one party only. F-70 accepts this as a valid non-null array. F-131 does not apply (parties are names, not fixed-format strings). But a one-party contract is not a contract — the second party was missed, most likely because the model stopped reading before the counterparty signature block.

Without cardinality validation, these 12 extractions proceed to routing. The downstream CRM lookup for the counterparty fails on every one of them. With cardinality validation, `parties` with `count: 1, min: 2` → `TOO_FEW (ERROR)` → blocked at extraction boundary, routed to retry with "ensure both parties are identified" instruction.

## Forces

- **Empty arrays are the most common cardinality failure.** The model returns `line_items: []` when it cannot locate the relevant section of the document. This is indistinguishable from "a document with no items" based on type checking alone. Most extraction schemas have at least one field where an empty array means failure, not an empty document. Register `min: 1` for those fields.
- **Maximum bounds matter for hallucinated lists.** When the model has low confidence, it sometimes generates many plausible-sounding items. A `risk_factors` list with 15 items often indicates the model is padding. Register `max: 10` as a WARN to flag over-generated outputs for review without blocking them.
- **Cardinality combines with arithmetic.** F-92 checks `total = sum(line_items)`. If `line_items` is empty, F-92 sees `sum([]) = 0`, which matches a total of 0 (no arithmetic violation). Only cardinality validation catches the empty-array case. Run cardinality before F-92: if `line_items` is empty, skip the arithmetic check.
- **Null fields are F-70's job, not this validator's.** If `parties` is null because the field was not extracted at all, F-70 reports a required-field violation. This validator skips null fields explicitly. The two validators compose: F-70 first (required fields present), cardinality second (array fields correctly populated).
- **Register party minimums from your domain schema.** For bilateral contracts: min=2. For multi-party frameworks: min=3. For agreements-of-one: min=1. The minimum is not a generic default — it comes from the contract type. Register it per document class if your pipeline processes multiple contract types.
- **WARN for over-generation; ERROR for under-extraction.** Under-extraction (`parties: 1` when 2 are needed) is always wrong and should block. Over-generation (`risk_factors: 12` when max=10 expects a concise list) may or may not be wrong and warrants human review. Use ERROR for lower bounds on fields that require populated content; use WARN for upper bounds on fields that could legitimately vary.

## The move

**Register min/max item bounds per array field. Validate after F-70 presence checks. Block on lower-bound ERRORs; log upper-bound WARNs.**

```js
// --- Output array field cardinality validator ---
// Validates that array fields in model extraction outputs contain the right number of items.
// Fills the gap between F-70 (confirms field is a non-null array) and
// arithmetic invariants (F-92, requires items to be present to sum).
// ERROR: fails status → block output, trigger retry or review.
// WARN:  logs violation but does not fail status → proceed, flag for review.
// null/undefined fields: skipped — F-70 handles required-field presence.

class OutputArrayCardinalityValidator {
  constructor() {
    this._rules = new Map();  // fieldName → { min, max, severity }
  }

  // Register cardinality bounds for an array field.
  // opts.min: minimum item count (default 0)
  // opts.max: maximum item count (default Infinity)
  // opts.severity: 'ERROR' (default, blocks on violation) or 'WARN' (logs only)
  register(field, opts = {}) {
    this._rules.set(field, {
      min:      opts.min      ?? 0,
      max:      opts.max      ?? Infinity,
      severity: opts.severity ?? 'ERROR',
    });
    return this;
  }

  // Validate array field cardinality in an extraction output.
  // Returns { status: 'PASS'|'FAIL', violations: [{field, issue, count, min?, max?, severity}], errorCount, warnCount }
  validate(output) {
    const violations = [];

    for (const [field, rule] of this._rules) {
      const value = output[field];
      if (value === null || value === undefined) continue;  // F-70 handles presence

      if (!Array.isArray(value)) {
        violations.push({ field, issue: 'NOT_AN_ARRAY', actual: typeof value, severity: rule.severity });
        continue;
      }

      const count = value.length;
      if (count < rule.min) {
        violations.push({ field, issue: 'TOO_FEW', count, min: rule.min, severity: rule.severity });
      } else if (rule.max !== Infinity && count > rule.max) {
        violations.push({ field, issue: 'TOO_MANY', count, max: rule.max, severity: rule.severity });
      }
    }

    const errorCount = violations.filter(v => v.severity === 'ERROR').length;
    return {
      status:     errorCount > 0 ? 'FAIL' : 'PASS',
      violations,
      errorCount,
      warnCount:  violations.length - errorCount,
    };
  }
}

// --- Integration: after F-70 presence/type checks; before F-92 arithmetic ---

const CARDINALITY_VALIDATOR = new OutputArrayCardinalityValidator()
  .register('line_items',    { min: 1, max: 100, severity: 'ERROR' })
  .register('citations',     { min: 1, max: 20,  severity: 'ERROR' })
  .register('risk_factors',  { min: 0, max: 10,  severity: 'WARN'  })
  .register('parties',       { min: 2, max: 10,  severity: 'ERROR' })
  .register('payment_terms', { min: 1,            severity: 'ERROR' });

function validateExtraction(output) {
  // Step 1: F-70 presence/type checks (not shown)

  // Step 2: Array cardinality
  const cardResult = CARDINALITY_VALIDATOR.validate(output);
  if (cardResult.status === 'FAIL') {
    const retryHints = cardResult.violations
      .filter(v => v.severity === 'ERROR')
      .map(v => v.issue === 'TOO_FEW'
        ? v.field + ' requires at least ' + v.min + ' items (found ' + v.count + ')'
        : v.field + ' allows at most ' + v.max + ' items (found ' + v.count + ')')
      .join('; ');
    return { valid: false, retryHints };
  }

  // Step 3: F-92 arithmetic (only if arrays are populated)
  return { valid: true, output };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `validate()` timed over 100 000 iterations on a 5-field extraction output. 5 rules registered.

```
=== OutputArrayCardinalityValidator timing (100 000 iterations) ===

validate() — 5 rules, PASS (0 violations):            0.0009 ms
validate() — 5 rules, FAIL (3 ERRORs + 1 WARN):       0.0010 ms

=== Scenario A: valid output ===

{
  line_items: [{ amount: 1000 }], citations: ['src-1', 'src-2'],
  risk_factors: ['low credit'], parties: ['Alpha Corp', 'Beta LLC'],
  payment_terms: ['net 30']
}

validate():
{ status: 'PASS', violations: [], errorCount: 0, warnCount: 0 }

=== Scenario B: 3 ERRORs + 1 WARN ===

{
  line_items:    []               → TOO_FEW  count=0  min=1  (ERROR)
  citations:     [c0..c24]        → TOO_MANY count=25 max=20 (ERROR)
  risk_factors:  [r0..r11]        → TOO_MANY count=12 max=10 (WARN)
  parties:       ['Alpha Corp']   → TOO_FEW  count=1  min=2  (ERROR)
  payment_terms: null             → skipped (F-70 handles required-field null)
}

validate():
{
  status: 'FAIL',
  violations: [
    { field: 'line_items',   issue: 'TOO_FEW',  count: 0,  min: 1,  severity: 'ERROR' },
    { field: 'citations',    issue: 'TOO_MANY',  count: 25, max: 20, severity: 'ERROR' },
    { field: 'risk_factors', issue: 'TOO_MANY',  count: 12, max: 10, severity: 'WARN'  },
    { field: 'parties',      issue: 'TOO_FEW',  count: 1,  min: 2,  severity: 'ERROR' }
  ],
  errorCount: 3,
  warnCount:  1
}

retryHints:
  'line_items requires at least 1 items (found 0);
   citations allows at most 20 items (found 25);
   parties requires at least 2 items (found 1)'

=== Scenario C: bilateral contract with one party extracted ===

parties: ['Alpha Corp']   ← counterparty block on page 12 was missed

validate():
{
  status: 'FAIL',
  violations: [{ field: 'parties', issue: 'TOO_FEW', count: 1, min: 2, severity: 'ERROR' }],
  errorCount: 1,
  warnCount:  0
}

retryHint: 'parties requires at least 2 items (found 1)'
Retry instruction: 'Ensure both parties are identified — check the counterparty signature block.'

=== F-70 vs F-131 vs F-92 vs F-132 ===

              │ F-70 (structural)               │ F-131 (string patterns)        │ F-92 (arithmetic)             │ F-132 (array cardinality)
──────────────┼─────────────────────────────────┼────────────────────────────────┼───────────────────────────────┼──────────────────────────────
What it checks│ Required, type, enum, invariant  │ String format (regex)          │ Numeric totals and ratios     │ Array item count (min/max)
Array handling│ Confirms field is non-null array │ Not applicable to arrays       │ Uses array items for sums     │ Counts array items directly
Empty array   │ PASS (valid empty array)         │ Not applicable                 │ sum([]) = 0, no violation     │ FAIL if min ≥ 1
Too many items│ Not checked                      │ Not applicable                 │ Not checked                   │ FAIL/WARN if > max
Compose       │ First                            │ After F-70                     │ After F-132                   │ After F-70, before F-92
```

## See also

[F-70](f70-structured-output-validation.md) · [F-131](f131-output-field-string-pattern-validator.md) · [F-92](f92-agent-output-arithmetic-invariants.md) · [F-120](f120-output-field-mutual-exclusivity.md) · [F-103](f103-response-completeness-check.md) · [F-124](f124-assertion-coverage-audit.md)

## Go deeper

Keywords: `output array cardinality validation` · `extraction array item count` · `structured output array bounds` · `min max array field validation` · `extraction array length check` · `array field cardinality` · `output array count constraint` · `too few items extraction` · `array cardinality gate` · `extraction required item count`
