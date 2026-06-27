# F-150 · Extraction Mutual Field Completeness Check

[F-70](f70-verifiable-output-design.md) registers fields that must always be present in every extraction — unconditional required fields. [F-147](f147-extraction-field-co-presence-assertion.md) registers unidirectional co-presence rules: when field A is non-null (any value), field B must also be non-null. Both patterns address single-field or directed-pair constraints.

Neither handles groups of fields that co-occur in the same document clause. A contract term clause contains `effective_date`, `expiry_date`, and `term_length_days` in the same sentence. If the model extracts `effective_date` it found the term clause — and if it found the term clause, `expiry_date` and `term_length_days` should be there too. An extraction that returns `effective_date = "2026-01-01"` and `expiry_date = null` is not missing data — it is inconsistent: the model found the clause but extracted it incompletely.

The mutual field completeness check registers groups of fields with an all-or-nothing constraint: if ANY field in the group is non-null, ALL fields in the group must be non-null. It is symmetric — unlike F-147, direction does not matter. The three statuses: `ALL_ABSENT` (no fields in the group are set — not a violation, the clause may not exist in this document), `ALL_PRESENT` (all fields set — pass), `INCOMPLETE_GROUP` (some set, some missing — violation). The `INCOMPLETE_GROUP` result includes a targeted retry hint that names both the present fields and the missing ones, explaining why their co-occurrence is expected.

## Situation

A contract extraction pipeline processes agreements that may or may not contain a term clause, a payment clause, and a parties section. All three sections are optional — some contracts are open-ended, some are handshake agreements without payment terms. But when a section exists, all its fields must be found together.

Scenario B: the term clause is present in the document ("This Agreement commences January 1, 2026 and runs for a term of three (3) years"). The model extracts `effective_date = "2026-01-01"` but returns `expiry_date = null` and `term_length_days = null`. F-70 does not fire — these fields are not unconditionally required. F-147 does not fire — there is no directed pair rule covering this. The mutual completeness check fires: `INCOMPLETE_GROUP` on the `term` group. Retry hint: "effective_date extracted but expiry_date, term_length_days missing — these fields co-occur in the term clause; if one is findable, all should be findable."

Scenario C: all three groups are absent — no term clause, no payment terms, no parties section. All statuses are `ALL_ABSENT`. Passed — `ALL_ABSENT` is never a violation. The completeness check does not force any field to exist; it only enforces consistency when fields do exist.

Scenario D: parties list is set but party_roles is null — a WARN-severity `INCOMPLETE_GROUP`. Delivery is not blocked (passed=true), but the anomaly is logged for human review.

## Forces

- **ALL_ABSENT is not a violation.** The mutual completeness constraint does not make fields required. A contract with no term clause correctly produces `ALL_ABSENT` for the term group. Only register a field as unconditionally required (F-70) if it must appear in every extraction. The mutual constraint fires only when the model found the clause but extracted it incompletely.
- **Severity follows field importance, not group membership.** Not every incomplete group is an error. The term and payment groups are ERROR-severity: incomplete extraction of those clauses is a substantive failure that blocks downstream processing. The parties group may be WARN-severity — the list is useful without roles, though not ideal. Register severity per group based on how downstream systems consume each group's fields.
- **F-147 vs F-150: direction matters.** F-147 is unidirectional: when `payment_terms` is set, `currency` must be set. `currency` can be absent when `payment_terms` is absent — the trigger only fires one way. F-150 is symmetric: when any of `{effective_date, expiry_date, term_length_days}` is set, all must be set. If `expiry_date` is set, `effective_date` is also required — the constraint fires from any member, not just a designated trigger.
- **Chain position: after F-147, before F-145 (completeness score).** F-147 checks unidirectional triggers; F-150 checks symmetric groups. Run both before computing the per-extraction completeness score (F-145) — completeness scoring should count incomplete-group failures as missing fields, not as present ones.
- **Register groups based on document structure, not semantic similarity.** Fields belong in the same group because they co-occur in the same clause — not because they are conceptually related. `effective_date` and `jurisdiction` are both contract metadata but may come from different sections. Put them in the same group only if finding one reliably means the other is in the same passage.

## The move

**Register groups of mutually required fields. When any field in the group is non-null, all must be non-null. Return ALL_ABSENT / ALL_PRESENT / INCOMPLETE_GROUP per group.**

```js
// --- Extraction mutual field completeness check ---
// Symmetric all-or-nothing constraint: if any field in the group is non-null,
// all fields in the group must be non-null.
// Distinct from F-70 (unconditional required) and F-147 (unidirectional: when A, then B).
// Chain: F-70 → F-147 → F-150 → F-145 (completeness score) → F-146.

function isPresent(val) {
  return val !== null && val !== undefined && val !== '' &&
         !(Array.isArray(val) && val.length === 0);
}

class MutualFieldCompletenessChecker {
  constructor() { this._groups = []; }

  registerGroup(groupName, fields, opts) {
    opts = opts || {};
    this._groups.push({
      groupName,
      fields,
      severity:    opts.severity    || 'ERROR',
      description: opts.description || `Group "${groupName}": all-or-nothing`,
    });
    return this;
  }

  check(output) {
    const results = this._groups.map(group => {
      const presentFields = group.fields.filter(f => isPresent(output[f]));
      const missingFields = group.fields.filter(f => !isPresent(output[f]));

      if (presentFields.length === 0) {
        return { status: 'ALL_ABSENT', group: group.groupName };
      }
      if (missingFields.length === 0) {
        return { status: 'ALL_PRESENT', group: group.groupName, presentFields };
      }

      return {
        status:        'INCOMPLETE_GROUP',
        group:         group.groupName,
        severity:      group.severity,
        presentFields,
        missingFields,
        retryHint:     `Group "${group.groupName}": [${presentFields.join(', ')}] extracted ` +
                       `but [${missingFields.join(', ')}] missing — these fields co-occur in ` +
                       `the same clause; if one is findable, all should be findable`,
      };
    });

    const violations = results.filter(r => r.status === 'INCOMPLETE_GROUP');
    const errors     = violations.filter(r => r.severity === 'ERROR');
    const warnings   = violations.filter(r => r.severity === 'WARN');
    return { passed: errors.length === 0, results, violations, errors, warnings };
  }
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Three registered groups; four scenarios covering ALL_PRESENT, INCOMPLETE_GROUP (ERROR), ALL_ABSENT, and INCOMPLETE_GROUP (WARN). Timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Extraction Mutual Field Completeness Check ===

--- Scenario A: All groups complete ---
  ALL_PRESENT        group="term"
  ALL_PRESENT        group="payment"
  ALL_PRESENT        group="parties_detail"
  passed: true

--- Scenario B: term group incomplete — effective_date set but expiry_date/term_length missing ---
  INCOMPLETE_GROUP   group="term"  ERROR
    retryHint: "Group "term": [effective_date] extracted but [expiry_date, term_length_days]
                missing — these fields co-occur in the same clause; if one is findable,
                all should be findable"
  ALL_PRESENT        group="payment"
  ALL_ABSENT         group="parties_detail"
  passed: false  errors: 1

--- Scenario C: All groups ALL_ABSENT — not a violation ---
  ALL_ABSENT         group="term"
  ALL_ABSENT         group="payment"
  ALL_ABSENT         group="parties_detail"
  passed: true  (ALL_ABSENT is never a violation — group is optional as a whole)

--- Scenario D: term/payment complete; parties_detail INCOMPLETE (WARN) ---
  ALL_PRESENT        group="term"
  ALL_PRESENT        group="payment"
  INCOMPLETE_GROUP   group="parties_detail"  WARN
    retryHint: "Group "parties_detail": [parties] extracted but [party_roles] missing —
                these fields co-occur in the same clause; if one is findable, all should
                be findable"
  passed: true  (WARN only — delivery not blocked)

=== Mutual completeness triad ===
F-70:   unconditional required     field ALWAYS required, no condition
F-147:  unidirectional co-presence  when A set (any value) → B must be set (A→B only)
F-150:  symmetric mutual            when ANY of {A,B,C} set → ALL of {A,B,C} must be set

=== Timing (1 000 000 iterations) ===
check() 3 groups, all ALL_PRESENT/ALL_ABSENT:  0.0014 ms
check() 3 groups, 1 INCOMPLETE_GROUP ERROR:    0.0023 ms
Zero API calls. Zero tokens. Runs at delivery boundary.
```

## See also

[F-70](f70-verifiable-output-design.md) · [F-147](f147-extraction-field-co-presence-assertion.md) · [F-145](f145-extraction-output-completeness-score.md) · [F-143](f143-output-field-conditional-presence-check.md) · [F-131](f131-extraction-output-field-pattern-validation.md)

## Go deeper

Keywords: `extraction mutual field completeness` · `all-or-nothing field group` · `symmetric co-presence check` · `extraction clause completeness` · `field group validation extraction` · `incomplete extraction detection` · `co-occurring field validation` · `extraction completeness check LLM` · `mutual field presence assertion` · `extraction group completeness`
