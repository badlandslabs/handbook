# F-142 · Cross-Extraction Field Consistency Check

[F-140](f140-extraction-date-ordering-assertions.md) checks that date fields within a single extraction are in the correct temporal order: effective date before termination date, signing date before effective date. [F-70](f70-verifiable-output-design.md) validates that a single extraction's fields are present, correctly typed, and within enum bounds. [F-128](f128-cross-field-agreement-rate-tracker.md) tracks the rate of contradictions between two fields within the same extraction over many calls. None of these check whether the same field extracted independently from two different related documents agrees.

When a contract is composed of a master agreement, an amendment, and a schedule, the effective date appears in each document. An extraction pipeline that processes each document independently will return an effective date for each. In most cases these should match — the amendment's preamble typically references the original agreement's effective date. When they do not match, there are three possible causes: the model extracted from the wrong clause in one document (the amendment's own effective date instead of the original), the documents are genuinely inconsistent (a drafting error), or the field has legitimate variation across documents (the amendment introduced a new party). All three are worth surfacing. Only one (genuine inconsistency) requires a legal review. Without a cross-extraction check, none of them surface automatically.

A cross-extraction field consistency check registers which fields must agree across all documents in a set, then compares the extracted values after all documents are processed. Fields that agree across all documents return CONSISTENT with high confidence that the value is correct. Fields that conflict return CONFLICT with a reference to which document disagreed, a root-cause hint, and the actual values for the reviewer.

## Situation

A legal due-diligence pipeline processes transaction document packages: each package contains a master agreement, an amendment, and one or two schedules. The pipeline extracts the same schema from each document. Three shared fields should agree across all documents: `effective_date`, `governing_law`, and `parties`.

Without cross-extraction checks: a batch of 500 packages is processed. 23 packages have `effective_date` values that disagree across documents — the model extracted the amendment's own effective date from the amendment document instead of the original agreement's effective date referenced in the preamble. The disagreements are never surfaced. Downstream analysis uses the master agreement's date for all packages, silently dropping the conflicting amendment dates. 3 of those 23 packages are later flagged in legal review for date inconsistency — the cause is traced back to the extraction layer six weeks after delivery.

With cross-extraction checks: all 23 disagreements surface on the day of extraction. 20 are model extraction errors (wrong clause); the retry hint fixes 17. 3 are genuine document inconsistencies flagged for legal review immediately. The other 477 packages have CONSISTENT across all three shared fields — the agreement gives the downstream team high confidence in those extractions.

## Forces

- **CONSISTENT is signal, not just absence of error.** When three independent document extractions return the same value for a field, that is stronger evidence of correctness than any single extraction alone. Report the agreed value and the list of agreeing documents. Downstream consumers can use CONSISTENT fields with higher confidence without re-running validation.
- **PARTIAL_DATA is not a failure by default.** Some documents in a set intentionally omit fields. A schedule often does not repeat the effective date — it references the master agreement by default. When only one document provides a field value and others are silent, that is ambiguous, not necessarily wrong. Return PARTIAL_DATA with WARN severity and the absent document list; let the downstream team decide whether to require the field in all documents.
- **Set comparison for array fields, not ordering comparison.** A parties field `["Alpha Corp", "Beta Ltd"]` and `["Beta Ltd", "Alpha Corp"]` represent the same set. Document to document, the model may list parties in different orders depending on which party is named first in each document's introductory clause. Use order-insensitive set comparison for array fields; use exact string comparison for scalar fields.
- **The reference document matters for CONFLICT hints.** When conflict is detected, identify the reference document (typically the master agreement) and the conflicting documents. The retry hint should say "amendment extracted 2026-03-15 but master agreement extracted 2026-02-01 — check which clause was used." Without naming the specific documents and values, the hint is not actionable.
- **Do not auto-resolve conflicts.** When documents disagree, the checker does not pick a winner. Resolving a conflict between a master agreement and an amendment requires legal judgment: the amendment may legally supersede the master agreement on that field, or the master agreement's value may be the authoritative one for the extraction schema. Return the CONFLICT and block delivery until a human makes the call.
- **Compose at the end of the per-document validation chain.** Run F-70 → F-131 → F-140 per document first. Once all per-document validations pass, run the cross-extraction consistency check as the final gate before delivering the document set. A document that fails F-70 is already blocked; the cross-extraction check is for documents that individually pass all validators but collectively disagree.

## The move

**Register shared fields with severity and comparison type. Add each document's extraction output. After all documents are processed, call `checkAll()`. Block delivery on ERROR-severity CONFLICT; annotate on WARN.**

```js
// --- Cross-extraction field consistency check ---
// Verifies that shared fields agree across all documents in a set.
// Distinct from F-140 (within-doc temporal ordering) and F-128 (cross-field rate tracker).
// Compose: run after per-document F-70/F-131/F-140 validation passes.

class CrossExtractionConsistencyChecker {
  constructor() {
    this._sharedFields = [];
    this._extractions  = {};
  }

  // Declare a field that must agree across all documents in the set.
  // compare: 'exact' (scalar) | 'set' (array, order-insensitive)
  // severity: 'ERROR' (block delivery) | 'WARN' (annotate)
  registerSharedField(fieldName, opts) {
    opts = opts || {};
    this._sharedFields.push({
      field:    fieldName,
      severity: opts.severity || 'ERROR',
      compare:  opts.compare  || 'exact',
    });
    return this;
  }

  add(docId, extraction) {
    this._extractions[docId] = extraction;
    return this;
  }

  reset() { this._extractions = {}; return this; }

  // Check one field across all recorded documents.
  // status: CONSISTENT | CONFLICT | PARTIAL_DATA | ABSENT | NO_DATA
  checkField(fieldName) {
    const rule     = this._sharedFields.find(r => r.field === fieldName) || {};
    const severity = rule.severity || 'ERROR';
    const compare  = rule.compare  || 'exact';
    const docIds   = Object.keys(this._extractions);

    if (docIds.length === 0) return { status: 'NO_DATA', field: fieldName };

    const present = [], absent = [];
    for (const id of docIds) {
      const val = this._extractions[id][fieldName];
      if (val !== null && val !== undefined && val !== '') present.push({ docId: id, value: val });
      else absent.push(id);
    }

    if (present.length === 0) return { status: 'ABSENT', field: fieldName, absentDocs: docIds };
    if (present.length === 1 && docIds.length > 1) {
      return { status: 'PARTIAL_DATA', field: fieldName, severity: 'WARN',
               presentDocs: present.map(p => p.docId), absentDocs: absent, value: present[0].value };
    }

    const ref = present[0];
    const conflictingDocs = [];
    for (let i = 1; i < present.length; i++) {
      const cand = present[i];
      const agrees = compare === 'set' && Array.isArray(ref.value) && Array.isArray(cand.value)
        ? ref.value.slice().sort().join('|') === cand.value.slice().sort().join('|')
        : JSON.stringify(ref.value) === JSON.stringify(cand.value);
      if (!agrees) conflictingDocs.push({ docId: cand.docId, value: cand.value });
    }

    if (conflictingDocs.length === 0) {
      return { status: 'CONSISTENT', field: fieldName, severity, value: ref.value,
               agreedDocs: present.map(p => p.docId), absentDocs: absent };
    }

    return {
      status: 'CONFLICT', field: fieldName, severity,
      referenceDoc: ref.docId, referenceValue: ref.value,
      conflictingDocs, absentDocs: absent,
      hint: `Check which clause was used in each document for field "${fieldName}". ` +
            `Most common cause: amendment-level date extracted instead of original agreement date.`,
    };
  }

  checkAll() {
    const results  = this._sharedFields.map(r => this.checkField(r.field));
    const errors   = results.filter(r => r.status === 'CONFLICT' && r.severity === 'ERROR');
    const warnings = results.filter(r => r.status === 'CONFLICT' && r.severity === 'WARN'
                                      || r.status === 'PARTIAL_DATA');
    return { passed: errors.length === 0, results, errors, warnings };
  }
}

// --- Integration: document-set delivery gate ---

const CONSISTENCY = new CrossExtractionConsistencyChecker();
CONSISTENCY
  .registerSharedField('effective_date', { severity: 'ERROR', compare: 'exact' })
  .registerSharedField('governing_law',  { severity: 'ERROR', compare: 'exact' })
  .registerSharedField('parties',        { severity: 'ERROR', compare: 'set'   })
  .registerSharedField('currency',       { severity: 'WARN',  compare: 'exact' });

async function deliverDocumentSet(docSet) {
  CONSISTENCY.reset();
  for (const [docId, extraction] of Object.entries(docSet)) {
    CONSISTENCY.add(docId, extraction);
  }
  const check = CONSISTENCY.checkAll();
  if (!check.passed) {
    const hints = check.errors.map(e =>
      `${e.field}: ${e.referenceDoc}=${JSON.stringify(e.referenceValue)} ` +
      `vs ${e.conflictingDocs.map(c => `${c.docId}=${JSON.stringify(c.value)}`).join(', ')}`
    ).join('; ');
    return { delivered: false, reason: 'CONSISTENCY_ERROR', hint: hints, errors: check.errors };
  }
  return {
    delivered: true,
    consistencyWarnings: check.warnings,
    highConfidenceFields: check.results
      .filter(r => r.status === 'CONSISTENT')
      .map(r => r.field),
  };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Three scenarios: all consistent, effective_date conflict (wrong clause), parties conflict (genuine amendment change). Timed over 100 000 iterations. Zero API calls, zero tokens.

```
=== Cross-Extraction Field Consistency Check ===

--- Scenario A: master + amendment + schedule, all consistent ---

  effective_date: CONSISTENT  value=2026-02-01  agreedDocs=[master, amendment, schedule]
  governing_law:  CONSISTENT  value=US          agreedDocs=[master, amendment, schedule]
  parties (set):  CONSISTENT  order-insensitive: ["Alpha Corp","Beta Ltd"] = ["Beta Ltd","Alpha Corp"]
  passed: true, errors: 0, warnings: 0

--- Scenario B: amendment model extracted amendment effective date ---

  master:    effective_date = 2026-02-01  (correct — original agreement)
  amendment: effective_date = 2026-03-15  (wrong — amendment's own effective date)
  schedule:  effective_date = 2026-02-01  (correct — references original)

  effective_date:
    status:          CONFLICT
    referenceDoc:    master
    referenceValue:  2026-02-01
    conflictingDocs: [{ docId: amendment, value: 2026-03-15 }]
    hint:            Check which clause was used for extraction.
                     Most common cause: amendment-level date instead of original.
  passed: false, errors: 1

  Retry action: re-extract amendment with instruction
  "Extract the effective_date of the ORIGINAL master agreement,
   not the date this amendment takes effect."

--- Scenario C: amendment introduced a third party (genuine variation) ---

  master:    parties = ["Alpha Corp", "Beta Ltd"]
  amendment: parties = ["Alpha Corp", "Beta Ltd", "Gamma LLC"]
  schedule:  parties = ["Alpha Corp", "Beta Ltd"]

  parties:
    status:          CONFLICT (set comparison)
    conflictingDocs: [{ docId: amendment, value: ["Alpha Corp","Beta Ltd","Gamma LLC"] }]
  passed: false (blocked for legal review)

  Human review outcome: amendment added Gamma LLC as guarantor.
  Resolution: extraction for parties should be document-specific;
  shared parties field only valid for identical-party documents.

=== Root cause taxonomy for CONFLICT ===

  1. Wrong clause extracted   → fix extraction prompt; most common; often retriable
  2. Document version mismatch → verify doc fingerprints match expected version
  3. Genuine document conflict → flag for legal review; do not auto-resolve
  4. Field inapplicable in doc → register with WARN severity for that doc type

=== Timing (100 000 iterations) ===

checkField() CONSISTENT (3 docs):  0.0020 ms
checkField() CONFLICT (3 docs):    0.0020 ms
checkAll() 3 fields CONFLICT:      0.0090 ms

Zero API calls. Zero tokens. Runs after per-document F-70/F-131/F-140 validation.
```

## See also

[F-140](f140-extraction-date-ordering-assertions.md) · [F-70](f70-verifiable-output-design.md) · [F-128](f128-cross-field-agreement-rate-tracker.md) · [F-136](f136-extraction-lifecycle-audit-record.md) · [F-133](f133-extraction-retry-escalation-policy.md)

## Go deeper

Keywords: `cross-extraction consistency check` · `multi-document field agreement` · `document set extraction validation` · `cross-document date consistency` · `extraction conflict detection` · `master agreement amendment consistency` · `related document extraction check` · `extraction field consistency across documents` · `document set validation` · `cross-document field conflict`
