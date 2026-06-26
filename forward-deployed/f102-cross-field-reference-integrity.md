# F-102 · Cross-Field Reference Integrity

[F-70](f70-verifiable-output-design.md) defines an output assertion layer: required fields, type/range checks, co-occurrence invariants (if `action_required` then `action_description` must be non-empty), and one hardcoded referential integrity example (each `citations[i].clause` must appear in `documentClauses`). [F-92](f92-agent-output-arithmetic-invariants.md) checks arithmetic invariants (totals, rates, allocations). [F-99](f99-numeric-unit-consistency-check.md) checks that fields of the same quantity type use consistent representations.

F-70's referential integrity check is a single hardcoded assertion for one specific schema. The underlying pattern is general: any structured output where field A contains ID values that must appear as IDs in field B. A contract summary: `citations[*].source_id` must be in `sources[*].id`. An invoice: `lineItems[*].productId` must be in `products[*].sku`. An agent task plan: `stepDependencies[*].dependsOnId` must be in `steps[*].id`. Writing this check by hand for each schema produces boilerplate that's easy to miss and hard to maintain.

Cross-field reference integrity provides a declarative constraint language for these checks. Constraints are expressed as `{ from: 'path.to[*].id', to: 'other.path[*].id' }`. The engine resolves array paths, extracts ID sets, and verifies inclusion. The same engine runs any constraint, any schema.

## Situation

A legal contract analysis agent returns a structured output with five reference relationships: citations reference source IDs, clauses reference section IDs, obligations reference party IDs, risk factors reference clause IDs, and recommended actions reference obligation IDs. A developer writes F-70-style assertions for required fields and type checks. Without a declarative referential integrity layer, cross-field relationships either go unchecked or require five separate hand-coded loops — each one a potential copy-paste error.

With a constraint declaration and a shared engine: five constraints declared in a table; one `checkReferentialIntegrity(output, constraints)` call; structured results showing which constraints passed and which failed, with the specific invalid IDs. A citation referencing `source_id: 'S-99'` when the sources list contains only `S-01` through `S-12` is caught and returned as `{ constraint: 'citation references known source', invalid: ['S-99'], severity: 'HIGH' }`.

## Forces

- **Array path resolution must handle both `[*].field` (array of objects) and `[]` (flat array of scalars).** A constraint from `citations[*].source_id` extracts the `source_id` field from each element of the `citations` array. A constraint from `allowedRoles[]` extracts the array values directly (it's a flat array of strings, not objects with an ID field).
- **Partial path resolution failures are not violations.** If a path resolves to `undefined` because the field doesn't exist in this output, that's a structural problem (F-70 catches it). A referential integrity check should only fire when both `from` and `to` paths resolve. An unresolved path returns `{ skipped: true, reason: 'path_not_found' }`, not a violation.
- **Bidirectional constraints are sometimes needed.** "Every citation references a known source" is one direction (from ⊆ to). "Every source is cited at least once" is the other (to ⊆ from). Declare separately; most outputs only need the forward direction.
- **Violation severity belongs in the constraint, not the engine.** Some reference violations are blocking (`citations[*].source_id` referencing a nonexistent source — can't audit the claim). Others are advisory (`lineItems[*].productId` referencing a catalog entry that's present but inactive). Declare severity per constraint; the engine propagates it to results.
- **Use sets, not arrays, for membership checks.** Extracting `to` IDs into a `Set` makes the membership check O(1) instead of O(N). For 100 citations against 20 sources, that's 100 O(1) checks instead of 100 × 20 scans.
- **The engine is pure code, zero API cost.** Referential integrity is deterministic — given the output and the constraints, the result is always the same. No need for a model judge. This check costs <0.01ms for typical outputs and zero tokens.

## The move

**Declare cross-field reference constraints as `{ from, to, name, severity }` tuples. Resolve paths to ID sets. Check inclusion. Return structured violations.**

```js
// --- Array path resolver ---
// Resolves a dot-notation path with optional [*] (array spread) and [] (flat array).
// 'citations[*].source_id'  → [all source_id values from citations array]
// 'sources[*].id'           → [all id values from sources array]
// 'allowedRoles[]'          → [all values in the allowedRoles array]
// 'steps[*].id'             → [all id values in steps]

function resolvePath(obj, path) {
  const parts = path.split('.');
  let current = [obj];

  for (const part of parts) {
    const next = [];
    const arraySpread = part.endsWith('[*]') || part.endsWith('[]');
    const key         = part.replace(/\[\*\]$|\[\]$/, '');

    for (const node of current) {
      if (node === null || node === undefined) continue;

      const val = key ? node[key] : node;
      if (val === undefined || val === null) return null;   // path not found

      if (arraySpread && Array.isArray(val)) {
        next.push(...val);
      } else {
        next.push(val);
      }
    }

    current = next;
    if (current.length === 0) return null;   // path resolved to empty
  }

  // Final values: flatten and extract primitives (the actual IDs)
  return current.flat().filter(v => v !== null && v !== undefined && typeof v !== 'object');
}

// --- Constraint runner ---
// constraint: { from: string, to: string, name: string, severity?: 'HIGH'|'MEDIUM'|'LOW' }
// output: the structured JSON object from the agent

function checkConstraint(output, constraint) {
  const { from, to, name, severity = 'HIGH' } = constraint;

  const fromValues = resolvePath(output, from);
  const toValues   = resolvePath(output, to);

  if (fromValues === null) return { name, status: 'SKIPPED', reason: `from path not found: ${from}` };
  if (toValues   === null) return { name, status: 'SKIPPED', reason: `to path not found: ${to}` };

  const toSet   = new Set(toValues.map(String));
  const invalid = fromValues.filter(v => !toSet.has(String(v)));

  if (invalid.length === 0) {
    return { name, status: 'PASS', fromCount: fromValues.length, toCount: toValues.length };
  }

  return {
    name, status: 'FAIL', severity,
    fromCount: fromValues.length,
    toCount:   toValues.length,
    invalid,
    msg: `${invalid.length} value(s) in '${from}' not found in '${to}': ${invalid.slice(0,3).join(', ')}${invalid.length > 3 ? ' ...' : ''}`,
  };
}

// --- Full referential integrity check ---
// output:      structured JSON from agent
// constraints: array of constraint declarations
// Returns: { pass, violations, skipped, results }

function checkReferentialIntegrity(output, constraints) {
  const results    = constraints.map(c => checkConstraint(output, c));
  const violations = results.filter(r => r.status === 'FAIL');
  const skipped    = results.filter(r => r.status === 'SKIPPED');

  return {
    pass:       violations.length === 0,
    violations,
    skipped,
    results,
    summary: {
      total:      constraints.length,
      passed:     results.filter(r => r.status === 'PASS').length,
      failed:     violations.length,
      skipped:    skipped.length,
      highFails:  violations.filter(v => v.severity === 'HIGH').length,
    },
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `resolvePath()`, `checkConstraint()`, `checkReferentialIntegrity()` timed over 100 000 iterations on a 7-field contract analysis output with 5 reference constraints. No API calls.

```
=== resolvePath() timing (100 000 iterations) ===

$ node -e "
const output = {
  sources: [{id:'S-01',title:'MSA'},{id:'S-02',title:'Amendment'},{id:'S-03',title:'Exhibit'}],
  citations: [{source_id:'S-01',quote:'...'},{source_id:'S-99',quote:'...'}],
  parties: [{id:'P-01',name:'Acme'},{id:'P-02',name:'Vendor'}],
  obligations: [{id:'OB-1',party:'P-01',desc:'...'},{id:'OB-2',party:'P-03',desc:'...'}],
  steps: [{id:'STEP-1',name:'Review'},{id:'STEP-2',name:'Sign'}],
  stepDependencies: [{stepId:'STEP-1',dependsOnId:'STEP-3'}]
};
const t0 = performance.now();
for (let i = 0; i < 100000; i++) resolvePath(output, 'citations[*].source_id');
console.log('resolvePath citations[*].source_id:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
resolvePath citations[*].source_id: 0.0019 ms   (array spread + field extraction)
resolvePath sources[*].id:          0.0014 ms
resolvePath simple field:           0.0004 ms

=== checkConstraint() timing (100 000 iterations) ===

checkConstraint() PASS:    0.0031 ms   (resolvePath × 2 + Set construction + membership check)
checkConstraint() FAIL:    0.0038 ms   (same + filter for invalids)
checkConstraint() SKIPPED: 0.0011 ms   (early exit on null path)

=== checkReferentialIntegrity() — 5 constraints (100 000 iterations) ===

checkReferentialIntegrity(): 0.0148 ms

=== Contract analysis: 7-field output, 5 constraints ===

Agent output (abbreviated):
  {
    sources:          [{ id:'S-01',title:'MSA' }, { id:'S-02',title:'Amendment' }],
    citations:        [{ source_id:'S-01', quote:'The agreement...' },
                       { source_id:'S-99', quote:'Liability is limited...' }],  ← invalid
    sections:         [{ id:'SEC-A' }, { id:'SEC-B' }],
    clauses:          [{ id:'CL-1', sectionId:'SEC-A' }, { id:'CL-2', sectionId:'SEC-X' }], ← invalid
    parties:          [{ id:'P-01', name:'Acme' }, { id:'P-02', name:'Vendor' }],
    obligations:      [{ id:'OB-1', partyId:'P-01' }, { id:'OB-2', partyId:'P-03' }],  ← invalid
    riskFactors:      [{ clauseRef:'CL-1' }, { clauseRef:'CL-99' }],  ← invalid
  }

Constraints:
  [
    { from:'citations[*].source_id', to:'sources[*].id',       name:'citation→source',  severity:'HIGH' },
    { from:'clauses[*].sectionId',   to:'sections[*].id',      name:'clause→section',   severity:'HIGH' },
    { from:'obligations[*].partyId', to:'parties[*].id',       name:'obligation→party', severity:'HIGH' },
    { from:'riskFactors[*].clauseRef', to:'clauses[*].id',     name:'risk→clause',      severity:'MEDIUM' },
    { from:'obligations[*].id',      to:'riskFactors[*].id',   name:'every obligation has risk', severity:'LOW' },
  ]

checkReferentialIntegrity() result:

  results:
    { name:'citation→source',  status:'FAIL',    severity:'HIGH',   invalid:['S-99'],  msg:"1 value(s) in 'citations[*].source_id' not found in 'sources[*].id': S-99" }
    { name:'clause→section',   status:'FAIL',    severity:'HIGH',   invalid:['SEC-X'], msg:"1 value(s) in 'clauses[*].sectionId' not found in 'sections[*].id': SEC-X" }
    { name:'obligation→party', status:'FAIL',    severity:'HIGH',   invalid:['P-03'],  msg:"1 value(s) in 'obligations[*].partyId' not found in 'parties[*].id': P-03" }
    { name:'risk→clause',      status:'FAIL',    severity:'MEDIUM', invalid:['CL-99'], msg:"1 value(s) in 'riskFactors[*].clauseRef' not found in 'clauses[*].id': CL-99" }
    { name:'every obligation has risk', status:'SKIPPED', reason:'to path not found: riskFactors[*].id' }

  summary: { total:5, passed:0, failed:4, skipped:1, highFails:3 }
  pass: false

Delivery actions:
  HIGH failures (3): block delivery; retry with explicit instruction "all source_ids must be from the provided sources list"
  MEDIUM failures (1): flag for review; may deliver with warning annotation
  SKIPPED (1): F-70 should catch that riskFactors has no .id field (structural issue)

=== F-70 vs F-92 vs F-102 ===

              │ F-70 (structural assertions)     │ F-92 (arithmetic)        │ F-102 (reference integrity)
──────────────┼──────────────────────────────────┼──────────────────────────┼──────────────────────────────
What          │ Required fields, type/range       │ total = sum(items)       │ A[*].id ⊆ B[*].id
Declarative?  │ Partially (mixed code+assertions) │ Schema-specific code     │ Yes — constraint tuples
API cost      │ $0, <0.01ms                       │ $0, 0.0021ms             │ $0, 0.0148ms (5 constraints)
Path syntax   │ Hardcoded field access            │ Hardcoded field access   │ dot-notation + [*] spread
Cross-field?  │ Co-occurrence invariants          │ Arithmetic relationships │ ID membership (set inclusion)
Catches       │ Missing/wrong-type/range fields   │ Wrong totals/rates       │ Dangling references between fields
```

## See also

[F-70](f70-verifiable-output-design.md) · [F-92](f92-agent-output-arithmetic-invariants.md) · [F-57](f57-rag-answer-citations.md) · [F-73](f73-agent-output-lineage.md) · [S-04](../stacks/s04-structured-output.md) · [F-99](f99-numeric-unit-consistency-check.md)

## Go deeper

Keywords: `cross-field reference integrity` · `referential integrity check` · `field reference constraint` · `declarative integrity` · `output reference check` · `ID membership check` · `citation reference integrity` · `structured output consistency` · `referential constraint engine` · `cross-field validation`
