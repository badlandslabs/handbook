# F-124 · Assertion Coverage Audit

[F-70](f70-structured-output-validation.md) validates structured output against a static schema — type checks, value ranges, required fields. [F-92](f92-structured-output-schema-drift.md) checks arithmetic invariants. [F-121](f121-output-field-value-anomaly-detection.md) catches statistically implausible numeric values. [F-122](f122-output-context-consistency-assertions.md) registers domain-specific relational constraints that require the full context to evaluate.

Teams add these one at a time, in response to specific bugs. Six months into production, a 12-field extraction schema may have F-70 covering all 12 fields structurally, F-121 covering 4 numeric fields, and F-122 covering 5 relational fields. The remaining 3 fields — `jurisdiction`, `governing_law_clause_id`, `contract_language` — have zero domain-specific validation beyond F-70's type check.

Nobody planned this. Nobody left it on purpose. It happened incrementally. The gap is invisible until a model hallucinates a jurisdiction the platform does not support, and the hallucination routes the contract to the wrong legal review queue, and two days later a case manager finds the wrong law applied to a cross-border agreement.

An assertion coverage audit scans the registered schema fields and cross-references them against all registered assertion layers. For each field, it reports whether it has structural coverage only (F-70) or also has business-logic coverage (F-92, F-121, F-122). Fields with structural coverage only and a HIGH consequence tier are surfaced as gaps — the ones most likely to produce silent failures when the model makes an error the type checker will not catch.

## Situation

A contract extraction agent has a 12-field output schema. Three assertion layers have been registered incrementally over six months:

- **F-70 structural**: covers all 12 fields (type, required presence, value ranges).
- **F-121 anomaly**: covers 4 numeric fields (`termination_fee`, `confidence`, `page_count`, `notice_period_days`).
- **F-122 context**: covers 5 relational fields (`recommended_action`, `cited_clauses`, `risk_level`, `rationale`, `assigned_reviewer`).

Coverage audit result:

```
totalFields:         12
fullyCovered:         9   (structural + business logic)
structuralOnly:       3   (F-70 only — no domain check)
businessCoveragePct: 75%
highGapCount:         2
```

Gaps:
- `jurisdiction` (HIGH) — structural only. The model can output `jurisdiction: "Utopia"`. F-70 passes (type: string, non-empty). No assertion checks whether the value is in the platform's `supported_jurisdictions` list.
- `governing_law_clause_id` (HIGH) — structural only. The model can fabricate a clause ID that references a section that does not exist in the provided document. F-57 checks citation IDs in prose, but this field is not registered in that check.
- `contract_language` (LOW) — structural only. Low consequence; acceptable to leave.

Action: register one F-122 assertion covering both HIGH gaps:

```js
.register({
  name:     'jurisdiction_is_supported',
  severity: 'critical',
  test: (out, ctx) => ctx.supported_jurisdictions.includes(out.jurisdiction),
})
.register({
  name:     'governing_law_clause_exists',
  severity: 'error',
  test: (out, ctx) => ctx.document_sections.includes(out.governing_law_clause_id),
})
```

After registering these, re-audit: `highGapCount: 0`. The two HIGH gaps are closed.

## Forces

- **The structural layer is a floor, not coverage.** F-70 proves that `jurisdiction` is a non-empty string. It says nothing about whether that string is a valid jurisdiction the platform can route to. Every field that matters has a structural check; the question is which fields also have a constraint on their value's domain meaning.
- **Tier determines priority.** Not every uncovered field is a gap worth fixing. `contract_language: 'English'` being structurally-only is acceptable — a wrong value causes no downstream harm. `jurisdiction: 'Utopia'` routing a contract to a non-existent legal queue is a hard failure. The `tier` (HIGH/MEDIUM/LOW) is set by consequence: how bad is a wrong value for this field in production?
- **The audit runs at startup, not per-output.** This is a development and deployment tool, not a per-call runtime check. Run the audit when the schema changes, when a new assertion layer is added, and as part of CI (fail the deploy if `highGapCount > 0`). It does not run in the call path.
- **`registerAssertion` maps existing registries, not new assertions.** The auditor does not create assertions. It mirrors what you have registered in F-70, F-92, F-121, and F-122 — the assertions you have already written. The audit's job is to reveal which schema fields none of those assertions mention.
- **Two layers are enough to distinguish.** Structural (F-70) vs business-logic (everything else) is the right split for most teams. A field in the structural layer only needs a domain-specific check added. A field missing from both layers needs both — but that is a sign of a schema field added after the initial validation pass.
- **The audit produces work, not answers.** When `jurisdiction` surfaces as a HIGH gap, the next step is: what would a correct value look like? What source of truth exists? That is a product question, not a technical one. The audit's value is surfacing it before a production incident does.

## The move

**Mirror your schema fields into the auditor. Mirror your existing assertions by which fields they cover. Run `audit()` at startup and in CI. Address `highGapCount > 0` before deploying schema changes.**

```js
// --- Assertion coverage auditor ---
// Tracks two coverage layers per schema field:
//   'structural' = F-70 type/range/presence (blanket, all fields)
//   'business'   = F-92/F-121/F-122 domain-specific assertions
// Run at startup and in CI. Not in the call path.

class AssertionCoverageAuditor {
  constructor() {
    this._fields     = [];   // [{name, type, tier: 'HIGH'|'MEDIUM'|'LOW'}]
    this._assertions = [];   // [{name, layer: 'structural'|'business', coveredFields: string[]}]
  }

  // Register a schema field.
  // tier: 'HIGH' (blocking if uncovered) | 'MEDIUM' (warning) | 'LOW' (acceptable gap)
  registerField(name, type, tier = 'LOW') {
    this._fields.push({ name, type, tier });
    return this;
  }

  // Register an assertion layer's field coverage.
  // layer: 'structural' (F-70) | 'business' (F-92, F-121, F-122, or any other domain check)
  // coveredFields: which schema fields this assertion touches
  registerAssertion(name, layer, coveredFields = []) {
    this._assertions.push({ name, layer, coveredFields });
    return this;
  }

  // Audit coverage. Run at startup and in CI — not in the call path.
  // Returns { totalFields, fullyCovered, structuralOnly, uncovered,
  //           businessCoveragePct, gapsByTier, highGapCount }
  audit() {
    const structural = new Set();
    const business   = new Set();
    for (const a of this._assertions) {
      const target = a.layer === 'structural' ? structural : business;
      for (const f of a.coveredFields) target.add(f);
    }
    const gaps  = [];
    const stats = { fullyCovered: 0, structuralOnly: 0, uncovered: 0 };
    for (const f of this._fields) {
      const hasS = structural.has(f.name);
      const hasB = business.has(f.name);
      if   (hasS && hasB)  { stats.fullyCovered++;  }
      else if (hasS)       { stats.structuralOnly++; gaps.push({ name: f.name, tier: f.tier, layer: 'structural_only' }); }
      else                 { stats.uncovered++;      gaps.push({ name: f.name, tier: f.tier, layer: 'uncovered' }); }
    }
    const byTier = { HIGH: [], MEDIUM: [], LOW: [] };
    for (const g of gaps) byTier[g.tier].push(g);
    return {
      totalFields:         this._fields.length,
      fullyCovered:        stats.fullyCovered,
      structuralOnly:      stats.structuralOnly,
      uncovered:           stats.uncovered,
      businessCoveragePct: parseFloat((business.size / this._fields.length * 100).toFixed(1)),
      gapsByTier:          byTier,
      highGapCount:        byTier.HIGH.length,
    };
  }
}

// --- Integration: register schema + existing assertions, audit at startup ---

const CONTRACT_COVERAGE = new AssertionCoverageAuditor()
  // Schema fields
  .registerField('recommended_action',      'string', 'HIGH')
  .registerField('cited_clauses',           'array',  'HIGH')
  .registerField('risk_level',              'string', 'HIGH')
  .registerField('rationale',               'string', 'HIGH')
  .registerField('assigned_reviewer',       'string', 'MEDIUM')
  .registerField('termination_fee',         'number', 'HIGH')
  .registerField('confidence',              'number', 'MEDIUM')
  .registerField('page_count',              'number', 'LOW')
  .registerField('jurisdiction',            'string', 'HIGH')
  .registerField('governing_law_clause_id', 'string', 'HIGH')
  .registerField('notice_period_days',      'number', 'MEDIUM')
  .registerField('contract_language',       'string', 'LOW')
  // Mirror existing assertion coverage
  .registerAssertion('f70_structural', 'structural', [
    'recommended_action', 'cited_clauses', 'risk_level', 'rationale',
    'assigned_reviewer', 'termination_fee', 'confidence', 'page_count',
    'jurisdiction', 'governing_law_clause_id', 'notice_period_days', 'contract_language',
  ])
  .registerAssertion('f121_anomaly', 'business',
    ['termination_fee', 'confidence', 'page_count', 'notice_period_days'])
  .registerAssertion('f122_context', 'business',
    ['recommended_action', 'cited_clauses', 'risk_level', 'rationale', 'assigned_reviewer']);

// --- CI gate: fail deploy if HIGH gaps remain unaddressed ---
function assertNoCriticalGaps(auditor) {
  const result = auditor.audit();
  if (result.highGapCount > 0) {
    const gaps = result.gapsByTier.HIGH.map(g => `${g.name} (${g.layer})`).join(', ');
    throw new Error(
      `AssertionCoverageAuditor: ${result.highGapCount} HIGH-consequence field(s) have no business-logic assertion: ${gaps}. ` +
      `Register a domain check (F-70 type/range does not count) or reclassify the field tier.`
    );
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `audit()`, `registerField()`, `registerAssertion()` timed over 100 000 iterations. Schema: 12-field contract extraction agent. Assertion layers: F-70 structural (all 12), F-121 anomaly (4 numeric), F-122 context (5 relational).

```
=== AssertionCoverageAuditor timing (100 000 iterations) ===

registerField():                0.0003 ms
registerAssertion():            0.0006 ms
audit() — 12 fields, 3 layers:  0.0044 ms

=== 12-field contract extraction schema ===

Fields registered: 12
Assertion layers:
  f70_structural  → structural   → covers 12 fields (all, type/range checks)
  f121_anomaly    → business     → covers 4  fields (termination_fee, confidence, page_count, notice_period_days)
  f122_context    → business     → covers 5  fields (recommended_action, cited_clauses, risk_level, rationale, assigned_reviewer)

=== Audit result (baseline — 3 assertion layers) ===

{
  totalFields:          12,
  fullyCovered:          9,    ← structural + business logic
  structuralOnly:        3,    ← F-70 only — no domain check
  uncovered:             0,
  businessCoveragePct:  75.0,
  gapsByTier: {
    HIGH:   [ { name: 'jurisdiction',            layer: 'structural_only' },
              { name: 'governing_law_clause_id', layer: 'structural_only' } ],
    MEDIUM: [],
    LOW:    [ { name: 'contract_language',       layer: 'structural_only' } ]
  },
  highGapCount: 2
}

CI gate: assertNoCriticalGaps() → throws:
  "2 HIGH-consequence field(s) have no business-logic assertion:
   jurisdiction (structural_only), governing_law_clause_id (structural_only)"

Action: register two F-122 assertions:

  .register({ name: 'jurisdiction_is_supported', severity: 'critical',
    test: (out, ctx) => ctx.supported_jurisdictions.includes(out.jurisdiction) })
  .register({ name: 'governing_law_clause_exists', severity: 'error',
    test: (out, ctx) => ctx.document_sections.includes(out.governing_law_clause_id) })

Mirror in coverage auditor:

  CONTRACT_COVERAGE.registerAssertion('f122_jurisdiction_check', 'business',
    ['jurisdiction', 'governing_law_clause_id']);

=== Audit result (after adding jurisdiction assertions) ===

{
  totalFields:          12,
  fullyCovered:         11,
  structuralOnly:        1,   ← contract_language (LOW tier — acceptable)
  uncovered:             0,
  businessCoveragePct:  91.7,
  gapsByTier: {
    HIGH:   [],
    MEDIUM: [],
    LOW:    [ { name: 'contract_language', layer: 'structural_only' } ]
  },
  highGapCount: 0
}

CI gate: assertNoCriticalGaps() → passes.

=== What each assertion type catches (and misses per field) ===

Field                     │ F-70 (structural)  │ F-121 (anomaly)     │ F-122 (relational)  │ Gap
──────────────────────────┼────────────────────┼─────────────────────┼─────────────────────┼─────────────────
jurisdiction              │ type:string ✓       │ not numeric         │ ← MISSING            │ HIGH gap
governing_law_clause_id   │ type:string ✓       │ not numeric         │ ← MISSING            │ HIGH gap
termination_fee           │ type:number ✓       │ z-score ≥3.0 ✓     │ N/A                  │ CLOSED
recommended_action        │ type:string ✓       │ not numeric         │ ∈ available_actions ✓│ CLOSED
contract_language         │ type:string ✓       │ not numeric         │ no rule registered   │ LOW gap (ok)
```

## See also

[F-70](f70-structured-output-validation.md) · [F-92](f92-structured-output-schema-drift.md) · [F-121](f121-output-field-value-anomaly-detection.md) · [F-122](f122-output-context-consistency-assertions.md) · [F-64](f64-prompt-template-testing.md) · [F-83](f83-agent-capability-testing.md)

## Go deeper

Keywords: `assertion coverage audit` · `output schema assertion gap` · `LLM validation coverage` · `structured output assertion registry` · `uncovered output field detection` · `output validation completeness` · `schema field assertion map` · `assertion coverage CI gate` · `output assertion gap detection` · `structured output validation coverage`
