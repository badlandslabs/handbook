# F-153 · Extraction Temporal Arithmetic Check

[F-140](f140-extraction-date-ordering-assertions.md) verifies that one date precedes another: `effective_date < expiry_date`. It does not check whether the interval between them is consistent with a duration field. A contract extracted with `effective_date = "2026-01-01"`, `term_length_days = 365`, and `expiry_date = "2030-01-01"` passes F-140 (the ordering is correct), fails nothing in F-149 (both dates are in plausible bounds), and passes F-131 (all values are correctly formatted). Yet the data is internally inconsistent: a 365-day term starting January 1, 2026 should end January 1, 2027, not January 1, 2030.

This inconsistency arises most commonly when the model extracts dates and durations from different clauses of the same document. A contract renewal clause might reference a "one-year renewal term" while the original expiry date appears in the main term clause from a prior amendment. The model finds both and reports them as if they describe the same period. The result is a triad where start + duration ≠ end.

The temporal arithmetic check registers triads of `(startField, durationField, endField)` with a tolerance window. It computes `computedEnd = parseDate(start) + durationDays` and compares it to the extracted `end`. Discrepancies within the tolerance (default 7 days) pass as CONSISTENT — they capture normal rounding from "three years" expressed as calendar years vs. 1095 days vs. 1096 days in a leap-year span. Discrepancies in the warn zone (8–60 days) produce INCONSISTENT WARN: plausible for schedule slippage, worth investigating but not blocking. Discrepancies above 60 days produce INCONSISTENT ERROR: the dates almost certainly came from different clauses.

## Situation

A contract extraction pipeline registers one primary triad (`effective_date + term_length_days → expiry_date`, 7-day tolerance) and one secondary triad (`signing_date + notice_period_days → earliest_termination_date`, 1-day tolerance).

Scenario B: three-year contract, `effective_date = "2026-01-01"`, `term_length_days = 1095`, `expiry_date = "2029-01-05"`. Computed end: 2028-12-31 (1095 days from 2026-01-01 spans the 2028 leap year). Actual: 2029-01-05. Discrepancy: 5 days. CONSISTENT — within the 7-day tolerance. Leap-year arithmetic, not an error.

Scenario C: same 3-year contract, but `expiry_date = "2029-02-01"`. Discrepancy: 32 days. INCONSISTENT WARN — above the 7-day tolerance but within 60 days. Plausible: the renewal clause may have extended the term by one month. Log and flag for review; delivery not blocked.

Scenario D: `effective_date = "2026-01-01"`, `term_length_days = 365`, `expiry_date = "2030-01-01"`. Computed end: 2027-01-01. Actual: 2030-01-01. Discrepancy: 1096 days. INCONSISTENT ERROR — the 1-year term and the 4-year span are irreconcilable. The model extracted the expiry date from a different clause (likely an extension or amendment) than the term length.

## Forces

- **Skip if any field in the triad is null.** A null `term_length_days` means the duration was not found in the document. The triad cannot be checked, and this is not a failure — the field might be absent by design (open-ended agreements). Return SKIP and do not double-fire with F-143 (conditional presence). Only check the triad when all three fields are present.
- **Unparseable dates are SKIP, not FAIL.** If `effective_date = "Q1 2026"` does not parse, skip the triad and let F-149 (date plausibility) handle the format error. Avoid double-flagging the same root cause with two different checks.
- **The tolerance window absorbs leap-year and month-end arithmetic.** A "3-year term" expressed as 1095 days from January 1, 2026 ends on December 31, 2028 (because 2028 is a leap year). If the contract's expiry date is stated as January 1, 2029 (the natural "3 years later" in calendar terms), the discrepancy is 1 day. A 7-day tolerance accommodates all standard calendar-to-day-count rounding.
- **Set WARN severity for the secondary range (7–60 days) rather than alerting immediately.** A 32-day discrepancy may reflect a legitimate amendment that extended the term by one month. It is worth investigating but should not block extraction delivery. Only use ERROR severity for discrepancies that are clearly cross-clause artifacts (> 60 days, often > 365 days).
- **Chain position: after F-140 and F-149, before F-146.** Run F-140 first (simple ordering check). If F-140 fires (`effective_date ≥ expiry_date`), the temporal arithmetic check cannot run meaningfully — the start is after the end. Run F-149 before F-153 to ensure date fields are parseable; F-153 degrades to SKIP on unparseable fields, but F-149 will have already flagged them with better retry hints.

## The move

**Register triads of (startField, durationField, endField). Compute startDate + durationDays → check vs. actual endDate within tolerance. CONSISTENT / INCONSISTENT WARN / INCONSISTENT ERROR / SKIP.**

```js
// --- Extraction temporal arithmetic check ---
// Verifies: startDate + durationDays ≈ endDate (within toleranceDays).
// Distinct from F-140 (ordering only), F-92 (numeric sum decomposition),
// F-149 (absolute date bounds on individual fields).
// Chain: F-140 → F-149 → F-153 → F-146.

function parseDate(str) {
  if (!str) return null;
  const d = new Date(str);
  return isNaN(d.getTime()) ? null : d;
}

function addDays(date, days) {
  return new Date(date.getTime() + days * 86_400_000);
}

class ExtractionTemporalArithmeticChecker {
  constructor() { this._triads = []; }

  registerTriad(startField, durationField, endField, opts) {
    opts = opts || {};
    this._triads.push({
      startField, durationField, endField,
      toleranceDays:     opts.toleranceDays     || 7,
      warnToleranceDays: opts.warnToleranceDays || 60,
      severity:          opts.severity           || 'ERROR',
      description:       opts.description        || `${startField} + ${durationField} ≈ ${endField}`,
    });
    return this;
  }

  check(output) {
    const results = this._triads.map(triad => {
      const rawStart = output[triad.startField];
      const rawDur   = output[triad.durationField];
      const rawEnd   = output[triad.endField];

      if (!rawStart || rawDur == null || !rawEnd) {
        return { status: 'SKIP', triad: triad.description };
      }
      const startDate = parseDate(rawStart);
      const endDate   = parseDate(rawEnd);
      const dur       = Number(rawDur);
      if (!startDate || !endDate || isNaN(dur) || dur <= 0) {
        return { status: 'SKIP', triad: triad.description, reason: 'unparseable field — F-149 handles' };
      }

      const computedEnd = addDays(startDate, dur);
      const discDays = Math.abs(Math.round((endDate - computedEnd) / 86_400_000));

      if (discDays <= triad.toleranceDays) {
        return { status: 'CONSISTENT', triad: triad.description, discrepancyDays: discDays };
      }
      const severity = discDays <= triad.warnToleranceDays ? 'WARN' : triad.severity;
      return {
        status:        'INCONSISTENT',
        triad:         triad.description,
        severity,
        discrepancyDays: discDays,
        computedEnd:   computedEnd.toISOString().slice(0, 10),
        actualEnd:     rawEnd,
        retryHint:     `${triad.description}: ${rawStart} + ${dur} days = ` +
                       `${computedEnd.toISOString().slice(0, 10)}, ` +
                       `but ${triad.endField} = ${rawEnd} (${discDays}-day discrepancy). ` +
                       (discDays > 365
                         ? 'Large discrepancy — dates likely extracted from different clauses.'
                         : 'Small discrepancy — possible rounding or schedule adjustment.'),
      };
    });
    const violations = results.filter(r => r.status === 'INCONSISTENT');
    const errors     = violations.filter(r => r.severity === 'ERROR');
    return { passed: errors.length === 0, results, violations,
             errors, warnings: violations.filter(r => r.severity === 'WARN') };
  }
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Two registered triads (effective_date + term_length_days → expiry_date; signing_date + notice_period_days → earliest_termination_date). Four scenarios. `check()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Extraction Temporal Arithmetic Check ===

--- Scenario A: exact match ---
  CONSISTENT  effective_date + term_length_days ≈ expiry_date     discrepancy=0 days
  CONSISTENT  signing_date + notice_period_days ≈ earliest_termination_date  discrepancy=0 days
  passed: true

--- Scenario B: 5-day discrepancy (leap year — within 7-day tolerance) ---
  effective_date=2026-01-01, term_length_days=1095, expiry_date=2029-01-05
  computed end: 2028-12-31  (1095 days spans the 2028 leap year)
  actual end:   2029-01-05  discrepancy: 5 days
  CONSISTENT — within 7-day tolerance
  passed: true

--- Scenario C: 32-day discrepancy (WARN — above 7-day tolerance, within 60-day zone) ---
  effective_date=2026-01-01, term_length_days=1095, expiry_date=2029-02-01
  INCONSISTENT  WARN  discrepancy=32 days
    retryHint: "effective_date + term_length_days ≈ expiry_date: 2026-01-01 + 1095 days =
                2028-12-31, but expiry_date = 2029-02-01 (32-day discrepancy).
                Small discrepancy — possible rounding or schedule adjustment."
  passed: true  (WARN — delivery not blocked; flag for review)

--- Scenario D: 1096-day discrepancy (ERROR — dates from different clauses) ---
  effective_date=2026-01-01, term_length_days=365, expiry_date=2030-01-01
  INCONSISTENT  ERROR  discrepancy=1096 days
    retryHint: "effective_date + term_length_days ≈ expiry_date: 2026-01-01 + 365 days =
                2027-01-01, but expiry_date = 2030-01-01 (1096-day discrepancy).
                Large discrepancy — dates likely extracted from different clauses."
  Scenario D passes F-140 (2026-01-01 < 2030-01-01 — ordering correct)
  and F-149 (both dates in plausible bounds). Only F-153 catches the inconsistency.
  passed: false  errors: 1

=== Timing (1 000 000 iterations, 2 triads) ===
check() 2 triads, CONSISTENT:     0.0035 ms
check() 2 triads, 1 INCONSISTENT: 0.0097 ms
Zero API calls. Zero tokens. Runs at delivery boundary.
```

## See also

[F-140](f140-extraction-date-ordering-assertions.md) · [F-149](f149-extraction-date-plausibility-check.md) · [F-92](f92-extraction-arithmetic-invariant-check.md) · [F-70](f70-verifiable-output-design.md) · [F-150](f150-extraction-mutual-field-completeness-check.md)

## Go deeper

Keywords: `extraction temporal arithmetic` · `date duration consistency check` · `start plus duration equals end` · `extraction date triad` · `temporal arithmetic extraction` · `contract date duration check` · `date arithmetic extraction validation` · `start date end date duration consistency` · `extraction cross-field date arithmetic` · `term length date verification`
