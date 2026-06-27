# F-147 · Extraction Field Co-Presence Assertion

[F-70](f70-verifiable-output-design.md) makes fields unconditionally required or optional: `governing_law` is either always required or never required across all extractions. [F-120](f120-output-field-mutual-exclusivity.md) handles conditional exclusion: when `status = "APPROVED"`, `rejection_reason` must be null. [F-143](f143-output-field-conditional-presence-check.md) handles conditional presence triggered by a specific value: when `risk_level = "HIGH"`, `risk_justification` must be non-null. F-143 fires only for the exact guard value — it does not fire when `risk_level = "LOW"` or `"MEDIUM"`.

A fourth shape falls between F-70 and F-143: when field A is present (any non-null value), field B must also be present — regardless of which value A has. When `governing_law` is set (to any jurisdiction), `jurisdiction` must also be set — the obligation is triggered by A being populated, not by A equaling a specific value. When `payment_terms` is set (to NET_30, NET_60, or NET_90), `currency` must also be set — the required pairing exists for every value of `payment_terms`, not just one. When `risk_level` is set (any tier), `risk_justification` must accompany it — the justification obligation applies across all risk tiers, not only HIGH.

F-143 cannot cover these cases without registering one rule per possible value of the trigger field. A contract schema with 12 risk tiers would need 12 F-143 rules to enforce the same co-presence invariant that F-147 covers with one. More importantly, the semantic is different: F-143 says "this specific condition creates a special obligation"; F-147 says "these two fields always travel together."

## Situation

A contract extraction pipeline produces structured output with co-presence invariants not captured by existing validators. Four rules govern the current schema:

1. `governing_law` present (any jurisdiction) → `jurisdiction` must be present (ERROR): a contract can be governed by any law, but law without a jurisdiction is incomplete and will fail the downstream compliance classifier.
2. `risk_level` present (HIGH, MEDIUM, or LOW) → `risk_justification` must be present (ERROR): every assigned risk tier requires a rationale. F-143 with `guardValue = "HIGH"` would miss LOW and MEDIUM contracts.
3. `payment_terms` present (any schedule) → `currency` must be present (ERROR): every payment schedule is meaningless without a currency.
4. `amendment_count` present (any non-zero count) → `last_amended_date` should be present (WARN): amendment count without a date is incomplete but not blocking — flag for human review.

Without F-147, Scenario B illustrates the gap: `risk_level = "LOW"`, `risk_justification = null`. F-143 rules registered for `guardValue = "HIGH"` do not fire. F-70's optional/required spec does not fire. The incomplete extraction passes validation, enters the risk model, and produces unexamined LOW-tier classifications without rationale.

## Forces

- **F-143 vs F-147: the trigger is value vs presence.** F-143 fires when `output[guardField] === guardValue` — an exact value comparison. F-147 fires when `isPresent(output[triggerField])` — any non-null, non-empty value. Use F-143 when the obligation depends on *which* value A has (HIGH risk is riskier than LOW; the obligation differs). Use F-147 when the obligation exists for *any* value of A (all risk tiers require rationale equally).
- **TRIGGER_ABSENT is not a violation.** If `governing_law` is null, the `jurisdiction` requirement does not fire — there is nothing to pair. `passed: true` when all trigger fields are null, even if all dependent fields are also null. F-70 handles unconditional required fields; F-147 only fires when the trigger is present.
- **Empty arrays are absent.** A field holding `[]` is not considered present. This matches F-145's completeness score definition and F-70's required field check. A `risk_justifications: []` does not satisfy the co-presence check any more than `null` does.
- **Compose with F-143 when both value-specific and presence-triggered rules coexist.** For `risk_level`: F-147 enforces that `risk_justification` is present for any risk tier. F-143 with `guardValue = "HIGH"` enforces that a HIGH-risk contract additionally has a `penalty_amount`. The two rules target different dependent fields and do not conflict — run both.
- **Run after F-70 in the validation chain.** F-70 runs first and fails on structurally invalid output. F-147 runs on structurally valid output to check semantic co-presence invariants. The canonical chain: F-70 → F-99 → F-131 → F-120 → F-143 → F-147 → F-146. F-147 is placed between F-143 and F-146 because co-presence (is the field present?) should be confirmed before range checking (is its value in range?).
- **WARN severity for co-presence rules that indicate incompleteness but not error.** Amendment count without a date is unusual but not invalid — the amendment may be recent and undated in the source. Annotate the output and log for trend analysis using F-141. If the WARN co-presence rate on a field exceeds 20% of extractions, the field is likely unreliably extracted and the schema or prompt needs attention.

## The move

**Register trigger-field → dependent-field co-presence rules with severity. Fire on any non-null value of the trigger field. Return CO_ABSENT with a retry hint.**

```js
// --- Extraction field co-presence assertion ---
// When output[triggerField] is non-null (any value), output[dependentField] must also be non-null.
// Distinct from F-143: F-143 fires on a specific guardValue; F-147 fires on any non-null triggerField.
// Distinct from F-70: F-70 is unconditional; F-147 fires only when the trigger field is present.
// Chain: F-70 → F-99 → F-131 → F-120 → F-143 → F-147 → F-146.

function isPresent(val) {
  return val !== null && val !== undefined && val !== '' &&
         !(Array.isArray(val) && val.length === 0);
}

class FieldCoPresenceChecker {
  constructor() { this._rules = []; }

  registerRule(triggerField, dependentField, opts) {
    opts = opts || {};
    this._rules.push({
      triggerField, dependentField,
      severity:    opts.severity    || 'ERROR',
      description: opts.description ||
        `when ${triggerField} is present, ${dependentField} must also be present`,
    });
    return this;
  }

  check(output) {
    const results = this._rules.map(rule => {
      if (!isPresent(output[rule.triggerField])) {
        return { status: 'TRIGGER_ABSENT', rule: rule.description };
      }
      const depPresent = isPresent(output[rule.dependentField]);
      return {
        status:         depPresent ? 'CO_PRESENT' : 'CO_ABSENT',
        rule:           rule.description,
        severity:       rule.severity,
        triggerField:   rule.triggerField,
        triggerValue:   output[rule.triggerField],
        dependentField: rule.dependentField,
        retryHint:      depPresent ? null :
          `${rule.dependentField} is required when ${rule.triggerField} is set (currently: ${JSON.stringify(output[rule.triggerField])})`,
      };
    });

    const violations = results.filter(r => r.status === 'CO_ABSENT');
    const errors     = violations.filter(r => r.severity === 'ERROR');
    const warnings   = violations.filter(r => r.severity === 'WARN');
    return { passed: errors.length === 0, results, violations, errors, warnings };
  }
}

// --- Contract extraction co-presence rules ---
const COPRESENCE = new FieldCoPresenceChecker();
COPRESENCE
  .registerRule('governing_law',   'jurisdiction',       { severity: 'ERROR', description: 'when governing_law is set, jurisdiction must also be set' })
  .registerRule('risk_level',      'risk_justification', { severity: 'ERROR', description: 'when risk_level is set (any tier), risk_justification must be provided' })
  .registerRule('payment_terms',   'currency',           { severity: 'ERROR', description: 'when payment_terms is set, currency must be specified' })
  .registerRule('amendment_count', 'last_amended_date',  { severity: 'WARN',  description: 'when amendment_count is set, last_amended_date should be present' });
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four rules, four scenarios. `check()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Extraction Field Co-Presence Assertion ===

--- Scenario A: governing_law=US, jurisdiction=null ---
  CO_ABSENT  ERROR  when governing_law is set, jurisdiction must also be set
  retryHint: "jurisdiction is required when governing_law is set (currently: "US")"
  CO_PRESENT  ERROR  when risk_level is set (any tier), risk_justification must be provided
  CO_PRESENT  ERROR  when payment_terms is set, currency must be specified
  passed: false  errors: 1  warnings: 0

--- Scenario B: risk_level=LOW, risk_justification=null ---
  (F-143 with guardValue=HIGH would skip LOW; F-147 fires for ANY non-null risk_level)
  CO_PRESENT  ERROR  when governing_law is set, jurisdiction must also be set
  CO_ABSENT  ERROR  when risk_level is set (any tier), risk_justification must be provided
  retryHint: "risk_justification is required when risk_level is set (currently: "LOW")"
  passed: false  errors: 1  warnings: 0

--- Scenario C: All triggers set and all dependents present ---
  CO_PRESENT  when governing_law is set, jurisdiction must also be set
  CO_PRESENT  when risk_level is set (any tier), risk_justification must be provided
  CO_PRESENT  when payment_terms is set, currency must be specified
  CO_PRESENT  when amendment_count is set, last_amended_date should be present
  passed: true

--- Scenario D: No triggers set (all null) — passed=true ---
  all rules: TRIGGER_ABSENT  passed: true

=== F-143 vs F-147 ===
F-143: trigger = specific value  (guardField === guardValue)
       e.g., when risk_level === "HIGH" → risk_justification required
       Does NOT fire for risk_level = "LOW" or "MEDIUM"
F-147: trigger = any non-null    (isPresent(triggerField))
       e.g., when risk_level is set (any tier) → risk_justification required
       Fires for risk_level = "HIGH", "MEDIUM", "LOW", any value

=== Timing (1 000 000 iterations) ===
check() 4 rules, 1 CO_ABSENT ERROR:  0.0014 ms
check() 4 rules, 4 CO_PRESENT:       0.0008 ms

Zero API calls. Zero tokens. Runs at delivery boundary.
```

## See also

[F-70](f70-verifiable-output-design.md) · [F-143](f143-output-field-conditional-presence-check.md) · [F-120](f120-output-field-mutual-exclusivity.md) · [F-146](f146-extraction-conditional-numeric-range-check.md) · [F-133](f133-extraction-retry-escalation-policy.md)

## Go deeper

Keywords: `field co-presence assertion` · `extraction field pairing` · `conditional presence any value` · `when field A set field B required` · `extraction co-occurrence constraint` · `field dependency presence check` · `output field co-presence` · `extraction paired field validation` · `field presence dependency` · `co-present field requirement`
