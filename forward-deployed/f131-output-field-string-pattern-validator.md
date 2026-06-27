# F-131 · Output Field String Pattern Validator

[F-70](f70-structured-output-validation.md) validates that required fields are present, that field types match the schema (string, number, boolean), that enum fields contain only permitted values, and that structural invariants hold (e.g., `action_required` is true whenever `description` is populated). [F-99](f99-numeric-unit-consistency-check.md) normalizes numeric field formats — converting `$2.5M` to `2500000` and detecting mixed currency formats — to enforce unit consistency in numeric data. [F-92](f92-agent-output-arithmetic-invariants.md) checks that numeric fields satisfy arithmetic invariants like `total = subtotal + tax`.

None of these validate the string format of an extracted field against a domain-specific pattern. F-70 confirms that `clause_id` is a non-null string; it does not confirm that `clause_id` matches the pattern `CL-{digits}`. A model that returns `{ clause_id: "Section 4" }` passes F-70 (the field is present and a string) but is wrong — downstream systems that route by `clause_id` will fail to find a match. The format is wrong, not the type.

String pattern validation fills the gap between type-checking and free-form string acceptance. For each field that has a defined format, register the expected pattern. On each extraction, validate non-null fields against their patterns. ERRORs block the output; WARNs are logged but do not block. Null and empty fields are skipped — F-70 handles presence checking.

## Situation

A contract extraction pipeline produces structured outputs consumed by a downstream routing system. The router uses `clause_id` to look up the clause in a reference database, `contract_date` to feed a date parser, `counterparty_id` to query the CRM, and `email` to send a notification.

Four months into production, the routing system logs begin showing lookup failures on `clause_id`. Investigation reveals: the extraction model, when a clause is ambiguous, sometimes returns the section heading instead of the registry ID — `"Section 4"` instead of `"CL-042"`. F-70 did not catch this because both are non-null strings.

Adding pattern validation for `clause_id: /^CL-\d+$/` would have flagged this at extraction time rather than at routing time:

- `clause_id: "Section 4"` → FAIL (`CL-{digits}` expected)
- `contract_date: "2024/06/15"` → FAIL (`YYYY-MM-DD` expected, slash not dash)
- `email: "missing-at-sign"` → WARN (not valid email — logged, not blocked)

After adding the validator, the failure class "wrong format, right type" is caught at the extraction boundary rather than propagating silently to downstream systems.

## Forces

- **Start with ERROR for fields that break downstream routing.** If `clause_id` has the wrong format, every downstream lookup fails. Make this an ERROR so extraction is blocked and a retry (or human review) is triggered. Reserve WARN for fields that are nice-to-have in the right format but degrade gracefully when malformed.
- **Skip null fields explicitly.** F-70's job is to enforce field presence. If `clause_id` is null, the right error is "required field missing" (F-70), not "format mismatch." The pattern validator skips nulls so the two validators compose cleanly without double-firing.
- **Patterns must match your model's actual output conventions.** If the model returns dates as `Jun 15, 2024` on some inputs, a strict `YYYY-MM-DD` pattern will fire frequently — not because the model is wrong, but because the pattern is wrong. Run the validator on a representative sample of production outputs before enabling ERROR severity. Use WARN to gather data first.
- **Write the description, not just the pattern.** The `description` field — `CL-{digits}`, `YYYY-MM-DD`, `valid email` — is what appears in the violation log. A violation log entry showing `expected: /^CL-\d+$/` is only readable to engineers. `expected: 'CL-{digits}'` is readable to the team that reviews extraction failures.
- **Patterns cover format, not semantics.** `/^\d{4}-\d{2}-\d{2}$/` verifies date format; it does not verify that `2024-02-30` is a real date. `/^CL-\d+$/` verifies the registry ID format; it does not verify that `CL-042` exists in the database. F-102 (cross-field reference integrity) handles the existence check. Stack both where needed.
- **ERRORs and WARNs serve different audiences.** ERRORs trigger the retry loop or escalation queue — an automated action. WARNs go to the monitoring dashboard — a human looks at them weekly to assess whether to promote WARNs to ERRORs. Keep the two severity levels because they have different costs: every ERROR that fires triggers a retry; you cannot afford to ERROR on patterns that fire 20% of the time.

## The move

**Register one pattern per field with a severity and a human-readable description. On each extraction, validate non-null fields. Block on ERRORs; log WARNs.**

```js
// --- Output field string pattern validator ---
// Validates non-null string fields in model extraction outputs against registered regex patterns.
// Fills the gap between F-70 (type/enum/presence) and free-form string acceptance.
// ERROR: fails status → block output, trigger retry or review.
// WARN:  logs violation but does not fail status → proceed, flag for monitoring.
// null/undefined/empty: skipped — F-70 handles field presence.

class OutputFieldPatternValidator {
  constructor() {
    this._rules = new Map();  // fieldName → { pattern: RegExp, description: string, severity: string }
  }

  // Register a format rule for a field.
  // pattern: RegExp to test against String(value).
  // opts.description: human-readable expected format (shown in violation log).
  // opts.severity: 'ERROR' (default, blocks) or 'WARN' (logs, does not block).
  register(field, pattern, opts = {}) {
    this._rules.set(field, {
      pattern,
      description: opts.description ?? pattern.toString(),
      severity:    opts.severity    ?? 'ERROR',
    });
    return this;
  }

  // Validate non-null string fields in an extraction output.
  // Returns { status: 'PASS'|'FAIL', violations: [{field, value, expected, severity}], errorCount, warnCount }
  validate(output) {
    const violations = [];

    for (const [field, rule] of this._rules) {
      const value = output[field];
      // Skip null/undefined/empty — F-70 handles presence
      if (value === null || value === undefined || value === '') continue;

      if (!rule.pattern.test(String(value))) {
        violations.push({
          field,
          value,
          expected: rule.description,
          severity: rule.severity,
        });
      }
    }

    const errorCount = violations.filter(v => v.severity === 'ERROR').length;
    const warnCount  = violations.length - errorCount;

    return {
      status:     errorCount > 0 ? 'FAIL' : 'PASS',
      violations,
      errorCount,
      warnCount,
    };
  }
}

// --- Integration: run after F-70 presence/type checks; before routing output downstream ---

const PATTERN_VALIDATOR = new OutputFieldPatternValidator()
  .register('clause_id',       /^CL-\d+$/,             { description: 'CL-{digits}',          severity: 'ERROR' })
  .register('contract_date',   /^\d{4}-\d{2}-\d{2}$/,  { description: 'YYYY-MM-DD',           severity: 'ERROR' })
  .register('counterparty_id', /^CP-[A-Z0-9]+$/,       { description: 'CP-{alphanumeric}',    severity: 'ERROR' })
  .register('email',           /^[^\s@]+@[^\s@]+\.[^\s@]+$/, { description: 'valid email',   severity: 'WARN'  })
  .register('risk_score',      /^\d+(\.\d+)?$/,          { description: 'numeric string',      severity: 'ERROR' });

function validateExtraction(output) {
  // Step 1: F-70 presence/type checks (not shown here)

  // Step 2: String pattern validation
  const patternResult = PATTERN_VALIDATOR.validate(output);
  if (patternResult.status === 'FAIL') {
    log({ event: 'extraction_pattern_fail', violations: patternResult.violations });
    return { valid: false, errors: patternResult.violations.filter(v => v.severity === 'ERROR') };
  }
  if (patternResult.warnCount > 0) {
    log({ event: 'extraction_pattern_warn', violations: patternResult.violations });
  }

  // Step 3: Route to downstream systems
  return { valid: true, output };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `validate()` timed over 100 000 iterations on a 6-field extraction output. 5 pattern rules registered.

```
=== OutputFieldPatternValidator timing (100 000 iterations) ===

validate() — 6 fields, PASS (0 violations):        0.0019 ms
validate() — 6 fields, FAIL (2 ERRORs + 1 WARN):   0.0018 ms

=== Scenario A: valid output ===

{
  clause_id: 'CL-042', contract_date: '2024-06-15',
  counterparty_id: 'CP-ACME01', email: 'legal@acme.com', risk_score: '7.5'
}

validate():
{ status: 'PASS', violations: [], errorCount: 0, warnCount: 0 }

=== Scenario B: 2 ERRORs + 1 WARN ===

{
  clause_id: 'Section 4',       ← wrong format (model returned heading, not registry ID)
  contract_date: '2024/06/15',  ← wrong separator (slash instead of dash)
  counterparty_id: 'CP-ACME01', ← valid
  email: 'missing-at-sign',     ← malformed email (WARN — does not block)
  risk_score: '7.5'             ← valid
}

validate():
{
  status: 'FAIL',
  violations: [
    { field: 'clause_id',     value: 'Section 4',      expected: 'CL-{digits}',   severity: 'ERROR' },
    { field: 'contract_date', value: '2024/06/15',      expected: 'YYYY-MM-DD',    severity: 'ERROR' },
    { field: 'email',         value: 'missing-at-sign', expected: 'valid email',   severity: 'WARN'  }
  ],
  errorCount: 2,
  warnCount:  1
}

Action: block output, log violations, trigger retry.
→ Retry prompt includes: 'clause_id must be in CL-{digits} format (e.g. CL-042).
  contract_date must be YYYY-MM-DD (e.g. 2024-06-15).'

=== Scenario C: null fields skipped ===

{ clause_id: null, contract_date: '2024-06-15', counterparty_id: 'CP-ACME01', email: null, risk_score: '7.5' }

validate():
{ status: 'PASS', violations: [], errorCount: 0, warnCount: 0 }

Note: null clause_id is correct behavior — F-70 handles required-field errors.
Pattern validator does not double-fire on nulls.

=== F-70 vs F-99 vs F-92 vs F-131 ===

              │ F-70 (structural)              │ F-99 (unit consistency)       │ F-92 (arithmetic)           │ F-131 (string patterns)
──────────────┼────────────────────────────────┼───────────────────────────────┼─────────────────────────────┼──────────────────────────────
What it checks│ Required, type, enum, invariant│ Currency/pct/date unit mixing │ total = sum(parts)          │ String format against regex
Null handling │ Flags null required fields      │ Skips null                    │ Skips null                  │ Skips null (F-70's job)
Catches       │ Wrong type, missing, bad enum  │ Mixed $M vs $B in same output │ Math errors in numeric fields│ Wrong format, right type
Misses        │ String format violations        │ String pattern violations     │ String fields entirely       │ Semantic value correctness
Compose       │ First (hard gate)               │ After F-70                    │ After F-70                  │ After F-70
```

## See also

[F-70](f70-structured-output-validation.md) · [F-99](f99-numeric-unit-consistency-check.md) · [F-92](f92-agent-output-arithmetic-invariants.md) · [F-102](f102-cross-field-reference-integrity.md) · [F-120](f120-output-field-mutual-exclusivity.md) · [F-124](f124-assertion-coverage-audit.md)

## Go deeper

Keywords: `output field string pattern validation` · `extraction field format validator` · `regex field validation` · `structured output format check` · `LLM output field format` · `field string format constraint` · `extraction output regex gate` · `field pattern registry` · `output format enforcement` · `structured extraction string pattern check`
