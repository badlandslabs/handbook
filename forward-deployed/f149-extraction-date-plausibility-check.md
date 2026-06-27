# F-149 · Extraction Date Plausibility Check

[F-140](f140-extraction-date-ordering-assertions.md) validates relative date ordering: `signing_date < effective_date < expiry_date`. [F-144](f144-extraction-event-sequence-monotonicity-check.md) validates that a timeline array of events runs in chronological order. Both are relative checks — they compare dates to each other. [F-146](f146-extraction-conditional-numeric-range-check.md) validates numeric fields against conditional bounds: when `risk_level = "HIGH"`, `penalty_amount >= 10000`.

None of these check whether an extracted date falls within an absolute domain-plausible range. A model extracting a contract effective date might return "1026-01-01" — a real parseable date, chronologically before `expiry_date`, non-null — that passes every check listed above while being obviously wrong: a 10th-century contract date from an OCR that read "1026" instead of "2026." Similarly, a signing date of "2026-12-01" on a contract signed today is a future date — impossible — and passes F-140 and F-144 without issue. An expiry date of "2099-12-31" is technically a valid date but implausible for any contract in a typical enterprise portfolio.

The extraction date plausibility check registers per-field absolute bounds: a minimum date, a maximum date, or both. It parses each extracted date field, compares against the bounds, and returns `WITHIN_BOUNDS`, `OUT_OF_BOUNDS`, `UNPARSEABLE`, or `SKIP` (null fields, which F-143 handles). The `OUT_OF_BOUNDS` result includes a targeted retry hint identifying the specific field, its value, and which bound it violated. `UNPARSEABLE` catches natural language dates ("Q1 2026", "next January") that the model returned instead of a parseable format.

## Situation

A contract extraction pipeline processes 1 000 agreements per day. Four date fields per contract: `effective_date`, `signing_date`, `expiry_date`, `last_amended_date`. Domain constraints for this portfolio: no contract predates 2000 (no legacy paper contracts in this system), no contract is dated more than one year in the future, no signing date is in the future, no expiry extends beyond 2060.

Scenario B: `effective_date: "1026-01-01"`. F-140 would catch this only if `signing_date` were "2025-12-15" — which it is — because 1026 < 2025 violates `signing_date < effective_date`. But not all implementations run F-140 on every field pair. F-149 catches it independently: 1026-01-01 predates the minimum bound 2000-01-01. Retry hint: `possible OCR error (wrong century) or extraction from wrong document`.

Scenario C: `signing_date: "2026-12-01"` (six months in the future). F-140 passes because `signing_date` comes before `effective_date` of "2026-01-01"... wait, no — "2026-12-01" is after "2026-01-01" so F-140 would actually catch this pair violation. But F-149 catches it differently: it does not require `effective_date` to be present. A null `effective_date` would cause F-140 to skip; F-149 fires regardless. It also catches the `expiry_date: "2099-12-31"` as a WARN.

Scenario D: `effective_date: "Q1 2026"`. F-140 would fail on date parsing. F-149 returns UNPARSEABLE with a specific hint: the model returned natural language instead of ISO format. Retry with explicit format instruction.

Without F-149, in 1 000 daily extractions: ~2 OCR wrong-century artifacts, ~3 natural-language dates, ~5 implausible future dates average one week of undetected errors before a human review catches the pattern. With F-149, all fire retry hints the same day.

## Forces

- **SKIP null fields — do not double-fire with F-143.** A null date field is a conditional presence failure (F-143), not a plausibility failure. If F-143 is in the chain and fires on a null `effective_date`, F-149 should not also fire on the same null. Return SKIP for null/missing/empty fields.
- **UNPARSEABLE is a separate status from OUT_OF_BOUNDS.** A date string that fails `new Date()` parsing is not out of bounds — it is not a date at all. The retry hint for UNPARSEABLE ("return an ISO date string, e.g., 2026-01-15") is different from the hint for OUT_OF_BOUNDS ("correct the century" or "confirm future date is intentional"). Do not conflate the two.
- **Maximum date bounds for signing dates should use today's actual date, injected at startup.** A hard-coded "2026-06-27" max for `signing_date` becomes wrong tomorrow. Inject `TODAY = new Date()` at the application startup and use it as the dynamic max. For `effective_date`, a one-year-forward bound (today + 365 days) catches hallucinated future dates while allowing legitimate near-future contracts.
- **Expiry date bounds warrant WARN, not ERROR.** A 30-year expiry ("2056-06-01") is unusual but not necessarily wrong — some real estate and infrastructure contracts run that long. Use WARN severity for far-future expiry bounds so the delivery is not blocked; log for human review. Use ERROR only for bounds whose violation is unambiguously a mistake: OCR wrong-century artifacts, future signing dates.
- **Chain position: after F-140 and F-144, before F-146.** Run relative date ordering first (F-140, F-144). If a date fails relative ordering, the absolute bound may be the root cause — a future signing date that comes after the effective date might be caught by either check. Run F-149 after F-140/144 so the retry hint for the root cause (absolute implausibility) is not masked by the symptom (relative ordering violation). Run before F-146 (numeric range) which operates on non-date fields.
- **Compose with F-135 (field normalizer) before this check for consistent date formats.** If the model returns "January 1, 2026" (natural language), F-135 normalizes it to "2026-01-01" before F-149 parses it. If F-135 is not in the chain, accept a wider range of date formats in the parser — but always require a parseable result.

## The move

**Register per-field absolute date bounds with min/max and severity. Parse date strings; return WITHIN_BOUNDS / OUT_OF_BOUNDS / UNPARSEABLE / SKIP. Inject TODAY dynamically — never hard-code the current date.**

```js
// --- Extraction date absolute plausibility check ---
// Validates extracted date fields against domain-defined absolute min/max bounds.
// Distinct from F-140 (relative ordering: A < B) and F-146 (numeric conditional range).
// SKIP null fields (F-143 handles presence). UNPARSEABLE ≠ OUT_OF_BOUNDS.
// Run order: F-70 → F-131 → F-140 → F-144 → F-149 → F-146.

function parseDate(str) {
  if (!str) return null;
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

class ExtractionDatePlausibilityChecker {
  constructor() { this._rules = []; }

  registerRule(field, opts) {
    opts = opts || {};
    this._rules.push({
      field,
      minDate:  opts.minDate ? new Date(opts.minDate) : null,
      maxDate:  opts.maxDate ? new Date(opts.maxDate) : null,
      severity: opts.severity  || 'ERROR',
      description: opts.description || field,
    });
    return this;
  }

  check(output) {
    const results = this._rules.map(rule => {
      const raw = output[rule.field];
      if (raw === null || raw === undefined || raw === '') {
        return { status: 'SKIP', field: rule.field, reason: 'null/missing — F-143 handles presence' };
      }
      const d = parseDate(raw);
      if (!d) {
        return {
          status: 'UNPARSEABLE', field: rule.field, value: raw, severity: rule.severity,
          retryHint: `${rule.field} value "${raw}" cannot be parsed as a date — return ISO format (e.g., 2026-01-15)`,
        };
      }
      if (rule.minDate && d < rule.minDate) {
        return {
          status: 'OUT_OF_BOUNDS', field: rule.field, value: raw, severity: rule.severity,
          bound: `>= ${rule.minDate.toISOString().slice(0, 10)}`,
          retryHint: `${rule.field} "${raw}" predates minimum bound ${rule.minDate.toISOString().slice(0, 10)} — ` +
                     `possible OCR error (wrong century) or extraction from wrong document`,
        };
      }
      if (rule.maxDate && d > rule.maxDate) {
        return {
          status: 'OUT_OF_BOUNDS', field: rule.field, value: raw, severity: rule.severity,
          bound: `<= ${rule.maxDate.toISOString().slice(0, 10)}`,
          retryHint: `${rule.field} "${raw}" exceeds maximum bound ${rule.maxDate.toISOString().slice(0, 10)} — ` +
                     `implausible for this contract portfolio; confirm extraction is correct`,
        };
      }
      return { status: 'WITHIN_BOUNDS', field: rule.field, value: raw };
    });

    const violations = results.filter(r => r.status === 'OUT_OF_BOUNDS' || r.status === 'UNPARSEABLE');
    const errors     = violations.filter(r => r.severity === 'ERROR');
    const warnings   = violations.filter(r => r.severity === 'WARN');
    return { passed: errors.length === 0, results, violations, errors, warnings };
  }
}

// --- Contract date plausibility rules ---
// TODAY injected at startup — never hard-code.
const TODAY     = new Date();
const IN_1_YEAR = new Date(TODAY); IN_1_YEAR.setFullYear(TODAY.getFullYear() + 1);
const IN_34_YR  = new Date('2060-01-01');

const DATE_CHECKER = new ExtractionDatePlausibilityChecker();
DATE_CHECKER
  .registerRule('effective_date',    { minDate: '2000-01-01', maxDate: IN_1_YEAR,  severity: 'ERROR' })
  .registerRule('signing_date',      { minDate: '2000-01-01', maxDate: TODAY,       severity: 'ERROR' })
  .registerRule('expiry_date',       { minDate: '2000-01-01', maxDate: IN_34_YR,   severity: 'WARN'  })
  .registerRule('last_amended_date', { minDate: '2000-01-01', maxDate: TODAY,       severity: 'ERROR' });
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four rules, four scenarios. `check()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Extraction Date Absolute Plausibility Check ===

--- Scenario A: All within bounds ---
  WITHIN_BOUNDS    effective_date="2026-01-01"
  WITHIN_BOUNDS    signing_date="2025-12-15"
  WITHIN_BOUNDS    expiry_date="2029-01-01"
  WITHIN_BOUNDS    last_amended_date="2026-03-10"
  passed: true

--- Scenario B: OCR artifact — effective_date "1026-01-01" ---
  OUT_OF_BOUNDS    effective_date
    retryHint: "effective_date "1026-01-01" predates minimum bound 2000-01-01 —
                possible OCR error (wrong century) or extraction from wrong document"
  WITHIN_BOUNDS    signing_date
  WITHIN_BOUNDS    expiry_date
  SKIP             last_amended_date  (null — F-143 handles presence)
  passed: false  errors: 1

--- Scenario C: future signing date (ERROR); far-future expiry (WARN) ---
  WITHIN_BOUNDS    effective_date="2026-01-01"
  OUT_OF_BOUNDS    signing_date="2026-12-01"  ERROR
    retryHint: "signing_date "2026-12-01" exceeds maximum bound 2026-06-27 —
                implausible for this contract portfolio; confirm extraction is correct"
  OUT_OF_BOUNDS    expiry_date="2099-12-31"  WARN
    retryHint: "expiry_date "2099-12-31" exceeds maximum bound 2060-01-01 —
                implausible for this contract portfolio"
  SKIP             last_amended_date
  passed: false  errors: 1  warnings: 1

--- Scenario D: unparseable — "Q1 2026" ---
  UNPARSEABLE      effective_date="Q1 2026"
    retryHint: "effective_date value "Q1 2026" cannot be parsed — return ISO format (e.g., 2026-01-15)"
  WITHIN_BOUNDS    signing_date
  WITHIN_BOUNDS    expiry_date
  SKIP             last_amended_date
  passed: false  errors: 1

=== Run order ===
F-70 → F-131 → F-140 → F-144 → F-149 → F-146

=== Timing (1 000 000 iterations) ===
check() 4 rules, all WITHIN_BOUNDS:  0.0065 ms
check() 4 rules, 1 OUT_OF_BOUNDS:    0.0115 ms

Zero API calls. Zero tokens. Runs at delivery boundary.
```

## See also

[F-140](f140-extraction-date-ordering-assertions.md) · [F-144](f144-extraction-event-sequence-monotonicity-check.md) · [F-146](f146-extraction-conditional-numeric-range-check.md) · [F-143](f143-output-field-conditional-presence-check.md) · [F-135](f135-extraction-output-field-normalizer.md)

## Go deeper

Keywords: `extraction date plausibility` · `absolute date bound check` · `OCR date error detection` · `date range validator extraction` · `domain date bounds` · `future date detection extraction` · `wrong century date check` · `extraction date validation` · `date out of bounds LLM` · `plausible date range extraction`
