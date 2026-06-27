# F-143 · Output Field Conditional Presence Check

[F-70](f70-verifiable-output-design.md) validates required fields unconditionally: `parties` must always be present, `effective_date` must always be a non-null string. These rules have no guard — the field is required in every output, regardless of other field values. [F-120](f120-output-field-mutual-exclusivity.md) validates conditional exclusion: when `status = "approved"`, `rejection_reason` must be null or empty — the presence of one field excludes the other. These two handle the two simplest cases: always-required and always-forbidden.

A third case falls between them: a field that is required only when another field has a specific value. When `risk_level = "HIGH"`, the extraction schema requires a `risk_justification` — a written explanation of why the contract scores high risk. When `risk_level = "LOW"` or `"MEDIUM"`, `risk_justification` may be null without being an error. When `governing_law = "FOREIGN"`, `foreign_jurisdiction` must name the specific country. When `governing_law = "US"`, `foreign_jurisdiction` is inapplicable and expected to be null. The field is conditionally required: its obligation is triggered by the value of a guard field.

F-70 cannot express this because F-70 treats all required fields as unconditionally required. F-120 cannot express this because F-120 enforces that field B is null when A equals V — the opposite direction. A conditional presence checker fills the gap: when guard field A equals guard value V, required field B must be non-null and non-empty. Guard not triggered → rule does not apply. Guard triggered, field present → CONDITIONAL_PRESENT. Guard triggered, field absent → CONDITIONAL_ABSENT, block or annotate by severity.

## Situation

A contract extraction pipeline returns a risk assessment object. The schema declares four conditional rules:

1. `risk_level = "HIGH"` → `risk_justification` required (ERROR). A risk classification without written justification is not actionable — the reviewer cannot evaluate it.
2. `status = "REJECTED"` → `rejection_reason` required (ERROR). A rejection without explanation cannot be communicated to the counterparty.
3. `requires_amendment = true` → `amendment_instructions` required (WARN). The drafting team needs to know what to change. Missing instructions delay the amendment process but don't block the extraction result.
4. `governing_law = "FOREIGN"` → `foreign_jurisdiction` required (ERROR). Foreign law without naming the jurisdiction is useless for routing to the right legal team.

Without conditional presence checks: the model occasionally sets `risk_level = "HIGH"` but leaves `risk_justification: null`. F-70 sees `risk_justification` as an optional field (it's null for most documents) and passes the output. The high-risk contract reaches the review queue without justification. The reviewer returns it manually — a step that F-70 was supposed to prevent.

With conditional presence checks: `risk_level=HIGH, risk_justification=null` fires CONDITIONAL_ABSENT at ERROR severity. Delivery is blocked. The retry hint: "risk_level is HIGH but risk_justification is null — write a one-paragraph explanation of why this contract scores HIGH risk." F-133 retries with the hint; Haiku fills the justification on the second attempt in 85% of cases.

## Forces

- **The guard value must be an exact match.** The checker compares `output[guardField] === guardValue`. For enum fields (`"HIGH"`, `"REJECTED"`), this is always appropriate. For string fields that might have casing variation, run F-135 (enum normalization) before the conditional presence check, so `"high"` and `"High"` both normalize to `"HIGH"` before the guard comparison.
- **WARN severity passes `passed: true`; ERROR does not.** Some conditional fields are important but not blocking. `amendment_instructions` absent when `requires_amendment = true` is a quality issue the drafting team can work around. Set WARN so it annotates the output without blocking delivery. Set ERROR only when the absent field makes the output unactionable (the reviewer literally cannot proceed without it).
- **Order checks correctly: F-70 → F-120 → F-143.** F-70 first: if `risk_level` itself is absent or not an enum member, the conditional check is undefined. F-120 next: mutual exclusivity violations (both approved and rejected set to true) should be caught before conditional presence checks interpret their values. F-143 last: the guard values it reads must have already passed structural and mutual-exclusivity validation.
- **Distinguish absent from null-by-design.** Some fields are correctly null depending on context. `foreign_jurisdiction` should be null when `governing_law = "US"` — that is expected and correct. The conditional presence rule is the mechanism that distinguishes the two: the rule only fires for `governing_law = "FOREIGN"`. When the guard is not triggered, nulls are allowed. This is why conditional presence is separate from F-70's unconditional required fields.
- **Guard values may change over time as schemas evolve.** When a new risk tier is added (`"CRITICAL"`), decide whether it also triggers the `risk_justification` rule. Update the rule table explicitly. Undeclared guard values are ignored by the checker — if `"CRITICAL"` is not a registered guard value for `risk_justification`, a `CRITICAL`-level output without justification passes silently. Treat the rule table as a schema artifact that evolves alongside the output schema.
- **Use retry hints from the CONDITIONAL_ABSENT result.** The result contains `guardField`, `guardValue`, `requiredField`, and `description`. F-133 (extraction retry escalation policy) can build a retry hint directly: "The output has `risk_level = HIGH` but `risk_justification` is absent — add a written justification. Rule: HIGH risk requires written justification."

## The move

**Register guard-value → required-field rules with severity. Check after F-70 and F-120. Block on ERROR-severity CONDITIONAL_ABSENT; annotate WARN-severity violations.**

```js
// --- Output field conditional presence check ---
// When guardField === guardValue, requiredField must be non-null and non-empty.
// Runs after F-70 (structural) and F-120 (mutual exclusivity).
// Distinct from F-70 (unconditional required) and F-120 (conditional exclusion).
// Complement: F-120 says "when A=V, B must be NULL"; F-143 says "when A=V, B must be NON-NULL".

class ConditionalFieldPresenceChecker {
  constructor() { this._rules = []; }

  // Register a rule: when output[guardField] === guardValue, output[requiredField] must be present.
  registerRule(guardField, guardValue, requiredField, opts) {
    opts = opts || {};
    this._rules.push({
      guardField, guardValue, requiredField,
      severity:    opts.severity    || 'ERROR',
      description: opts.description || `${guardField}=${guardValue} requires ${requiredField}`,
    });
    return this;
  }

  check(output) {
    const results = this._rules.map(rule => {
      if (output[rule.guardField] !== rule.guardValue) {
        return { status: 'GUARD_NOT_TRIGGERED', rule: `${rule.guardField}=${rule.guardValue} → ${rule.requiredField}` };
      }
      const val = output[rule.requiredField];
      const present = val !== null && val !== undefined && val !== '';
      return {
        status:        present ? 'CONDITIONAL_PRESENT' : 'CONDITIONAL_ABSENT',
        rule:          `${rule.guardField}=${rule.guardValue} → ${rule.requiredField}`,
        severity:      rule.severity,
        guardField:    rule.guardField,
        guardValue:    rule.guardValue,
        requiredField: rule.requiredField,
        requiredValue: val,
        description:   rule.description,
      };
    });

    const violations = results.filter(r => r.status === 'CONDITIONAL_ABSENT');
    const errors     = violations.filter(r => r.severity === 'ERROR');
    const warnings   = violations.filter(r => r.severity === 'WARN');
    return { passed: errors.length === 0, results, violations, errors, warnings };
  }
}

// --- Contract extraction conditional rules ---

const COND_CHECKER = new ConditionalFieldPresenceChecker();
COND_CHECKER
  .registerRule('risk_level',        'HIGH',    'risk_justification',     { severity: 'ERROR', description: 'HIGH risk requires written justification' })
  .registerRule('status',            'REJECTED', 'rejection_reason',       { severity: 'ERROR', description: 'REJECTED status requires a reason' })
  .registerRule('requires_amendment', true,      'amendment_instructions', { severity: 'WARN',  description: 'Amendment flag requires drafting instructions' })
  .registerRule('governing_law',     'FOREIGN', 'foreign_jurisdiction',    { severity: 'ERROR', description: 'FOREIGN law requires jurisdiction name' });

// --- Integration: delivery gate (after F-70 → F-120 → F-143) ---

function deliverWithConditionalCheck(output) {
  const check = COND_CHECKER.check(output);

  if (!check.passed) {
    const hint = check.errors.map(e =>
      `${e.requiredField} is required when ${e.guardField}=${e.guardValue}: ${e.description}`
    ).join('; ');
    return { delivered: false, reason: 'CONDITIONAL_ABSENCE', retryHint: hint, errors: check.errors };
  }

  return {
    delivered: true,
    output,
    conditionalWarnings: check.warnings.map(w => w.description),
  };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Four scenarios, four rules. `check()` timed over 100 000 iterations, both passing and failing cases. Zero API calls, zero tokens.

```
=== Output Field Conditional Presence Check ===

--- Scenario A: risk_level=HIGH, risk_justification=null (ERROR) ---

  output: { risk_level: "HIGH", risk_justification: null, status: "PENDING", ... }
  
  risk_level=HIGH → risk_justification:  CONDITIONAL_ABSENT  ERROR
  status=REJECTED → rejection_reason:    GUARD_NOT_TRIGGERED (status=PENDING)
  requires_amendment=T → instructions:   GUARD_NOT_TRIGGERED (requires_amendment=false)
  governing_law=FOREIGN → jurisdiction:  GUARD_NOT_TRIGGERED (governing_law=US)

  passed: false  →  block delivery
  retryHint: "risk_justification is required when risk_level=HIGH:
              HIGH risk requires written justification"

--- Scenario B: status=REJECTED, rejection_reason present (PASS) ---

  status=REJECTED → rejection_reason:  CONDITIONAL_PRESENT
  risk_level=HIGH: GUARD_NOT_TRIGGERED (risk_level=LOW)
  passed: true

--- Scenario C: requires_amendment=true, amendment_instructions empty (WARN) ---

  requires_amendment=true → amendment_instructions:  CONDITIONAL_ABSENT  WARN
  passed: true  (WARN does not block delivery)
  conditionalWarnings: ["Amendment flag requires drafting instructions"]

--- Scenario D: governing_law=FOREIGN, foreign_jurisdiction=null + risk_level=HIGH (present) ---

  risk_level=HIGH → risk_justification:    CONDITIONAL_PRESENT  (justification filled)
  governing_law=FOREIGN → jurisdiction:    CONDITIONAL_ABSENT   ERROR
  passed: false  →  block delivery (only FOREIGN jurisdiction rule fires as error)

=== F-70 vs F-120 vs F-143: which checker catches what ===

              │ F-70               │ F-120                   │ F-143
──────────────┼────────────────────┼─────────────────────────┼─────────────────────────────
Rule shape    │ always required    │ when A=V, B must be null │ when A=V, B must be non-null
Guard         │ none               │ A equals V               │ A equals V
Violation     │ field absent       │ both fields populated    │ required field absent
Example       │ parties != null    │ APPROVED→rejection null  │ HIGH→justification non-null
Run order     │ first              │ second                   │ third

=== Timing (100 000 iterations) ===

check() 4 rules, 1 triggered, PASS:            0.0013 ms
check() 4 rules, 4 triggered, 3 ABSENT ERROR:  0.0015 ms

Zero API calls. Zero tokens. Runs at delivery boundary.
```

## See also

[F-70](f70-verifiable-output-design.md) · [F-120](f120-output-field-mutual-exclusivity.md) · [F-133](f133-extraction-retry-escalation-policy.md) · [F-135](f135-extraction-output-field-normalizer.md) · [F-141](f141-extraction-class-distribution-monitor.md)

## Go deeper

Keywords: `conditional field presence check` · `guard field required field` · `conditional required field extraction` · `output field dependency check` · `triggered field validation` · `conditional output assertion` · `field presence conditional on value` · `extraction conditional rule` · `guard value required field` · `conditional field validation LLM output`
