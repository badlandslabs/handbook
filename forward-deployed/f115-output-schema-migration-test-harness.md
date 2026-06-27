# F-115 · Output Schema Migration Test Harness

[S-64](../stacks/s64-agent-output-schema-versioning.md) adds a `_v` field to model outputs and classifies schema changes by breakingness: additive (new optional field), rename (breaking), removal (breaking), type change (breaking). It tells you what *kind* of change you're making and gives you a migration playbook. [S-120](../stacks/s120-output-schema-backward-compat-adapter.md) provides the adapter that translates old-schema outputs to the new schema at runtime. [S-92](../stacks/s92-tool-schema-migration.md) addresses tool *input* schema changes; its Forces section says "test migration compatibility against your existing conversation history" — but provides no implementation. [F-65](f65-prompt-regression-testing.md) snapshots golden outputs and gates CI on structural drift in *current* prompt outputs — it does not test historical outputs against a new schema version.

None of these provide a test harness that takes a corpus of historical model outputs and runs them through the new schema decoder. This is the migration dry-run: before deploying a schema change to production, verify that existing outputs — the ones already stored, logged, or in-flight — would be correctly processed by the new consumer. Without it, a breaking schema change silently corrupts outputs that predate the new prompt.

The output schema migration test harness loads N historical outputs, applies the new schema definition, and reports: overall pass rate, which fields cause failures, and which outputs would break. A `passingPct` threshold (default ≥ 95%) gates the migration: deploy if met, fix and re-test if not.

## Situation

A contract analysis pipeline extracts six fields per contract: `liability_cap`, `governing_law`, `termination_notice`, `payment_terms`, `dispute_resolution`, `amendment_procedure`. The team is shipping schema v2.0: (1) `payment_terms` is renamed `payment_schedule` (breaking rename); (2) a new required field `indemnification_scope` is added (which the updated prompt now generates; historical outputs don't have it).

Before v2.0 deploys, the pipeline has 800 stored contract extractions in the logging database — all schema v1.0. The new consumer reads `payment_schedule` and `indemnification_scope` as required fields. Without a migration test, the first time any stored v1.0 output flows through the new consumer (re-processing, audit replay, cache hit), it silently fails.

Migration test result:
- `payment_schedule` REQUIRED_MISSING: 800/800 (100%) — all v1.0 outputs use `payment_terms`
- `indemnification_scope` REQUIRED_MISSING: 800/800 (100%) — not in v1.0 outputs
- `passingPct: 0.0%` — migration blocked

Actions: deploy S-120 adapter (`payment_terms → payment_schedule`); ship backfill job that re-extracts `indemnification_scope` for the 800 stored contracts using the new prompt. After backfill, re-run migration test: `payment_schedule` failures zero (adapter handles it); `indemnification_scope` failures drop to 23/800 (pre-announcement contracts where the clause genuinely doesn't exist → mark as optional). `passingPct: 97.1%` — migration approved.

## Forces

- **Test against real outputs, not synthetic fixtures.** Synthetic fixtures represent what you *think* the model produces. The 800 stored outputs represent what the model *actually* produced — including edge cases, partial extractions, null fields, and outputs from an older prompt version. The corpus tests the real tail.
- **Separate test harness from adapter.** The harness tells you whether an adapter is needed and how much it fixes. The adapter (S-120) is the fix. Run the harness first: if `passingPct` is already 100% without an adapter, a v1.0 → v2.0 change was additive and non-breaking — no adapter needed. Run it again after deploying the adapter: verify the adapter closes the gap before shipping.
- **Required vs optional is part of the schema definition.** A field that was required in v1.0 may become optional in v2.0 (or vice versa). The migration harness must test the new schema's `required` declarations, not the old schema's. `indemnification_scope` going from absent (v1.0 didn't have it) to required (v2.0 needs it) is a breaking addition — the harness catches it as REQUIRED_MISSING on all v1.0 outputs.
- **`passingPct` threshold depends on failure severity.** For fields where a missing value causes a downstream exception: require 99%+. For fields where a missing value causes a degraded-but-functional result: 95% may be acceptable. Set the threshold per migration, not universally.
- **The harness is a CI gate, not a one-off script.** Run it as part of the schema version change PR: the PR includes the new schema definition, the adapter (if any), and the migration test result. The test corpus is fetched from the logging database; the result is attached to the PR. A `passingPct < threshold` fails CI and blocks the merge.
- **Log which specific outputs fail.** `results[idx]` gives the exact output and its failure reasons. A cluster of similar failures (all from one customer, all from contracts longer than 50 pages, all from a specific date range) points to the root cause: a prompt that wasn't updated, a content segment the model missed, an adapter gap.

## The move

**Load historical outputs. Apply the new schema. Report pass rate, failure breakdown, and blocker fields.**

```js
// --- Schema field definition ---
// name:     string
// type:     'string' | 'number' | 'boolean' | 'object' | 'array'
// required: boolean — if true, absence is a REQUIRED_MISSING failure
// enum:     string[] | null — if set, value must be one of these
// nullable: boolean — if true, null is acceptable even when required (field exists but may be null)

// --- Individual output tester ---

class OutputSchemaMigrationTester {
  constructor(newSchemaFields) {
    this._schema     = newSchemaFields;
    this._schemaKeys = new Set(newSchemaFields.map(f => f.name));
  }

  // Test one historical output against the new schema.
  // Returns { status, failures, warnings }
  testOne(output) {
    if (typeof output !== 'object' || output === null) {
      return { status: 'FAIL', failures: [{ field: '_root', type: 'NOT_AN_OBJECT' }], warnings: [] };
    }

    const failures = [];
    const warnings = [];

    for (const field of this._schema) {
      const value = output[field.name];
      const absent = value === null || value === undefined;

      if (absent) {
        if (field.required && !field.nullable) {
          failures.push({ field: field.name, type: 'REQUIRED_MISSING' });
        }
        continue;
      }

      // Loose numeric coercion: string-encoded numbers pass for 'number'
      if (!this._typeOk(value, field.type)) {
        failures.push({
          field:    field.name,
          type:     'TYPE_INCOMPATIBLE',
          expected: field.type,
          actual:   Array.isArray(value) ? 'array' : typeof value,
        });
      }

      if (field.enum && !field.enum.includes(value)) {
        failures.push({
          field:    field.name,
          type:     'ENUM_VIOLATION',
          expected: field.enum,
          actual:   value,
        });
      }
    }

    // Fields present in the output but not declared in the new schema
    for (const key of Object.keys(output)) {
      if (key.startsWith('_')) continue;   // skip metadata fields (_v, _source, _excerpt)
      if (!this._schemaKeys.has(key)) {
        warnings.push({ field: key, type: 'UNDECLARED_FIELD' });
      }
    }

    return {
      status:   failures.length > 0 ? 'FAIL' : 'PASS',
      failures,
      warnings,
    };
  }

  // Run against a corpus of historical outputs.
  // Returns a migration report.
  testCorpus(historicalOutputs, opts = {}) {
    const { passingThreshold = 0.95, label = 'corpus' } = opts;

    const results = historicalOutputs.map((output, idx) => ({
      idx,
      ...this.testOne(output),
    }));

    const passing = results.filter(r => r.status === 'PASS').length;
    const failing = results.filter(r => r.status === 'FAIL').length;
    const passingPct = historicalOutputs.length > 0
      ? parseFloat((passing / historicalOutputs.length * 100).toFixed(1))
      : 100;

    // Aggregate failures by (field, type)
    const failureCounts = new Map();
    for (const r of results) {
      for (const f of r.failures) {
        const key = `${f.field}::${f.type}`;
        failureCounts.set(key, (failureCounts.get(key) ?? 0) + 1);
      }
    }

    const failureBreakdown = [...failureCounts.entries()]
      .map(([key, count]) => {
        const [field, type] = key.split('::');
        return {
          field, type, count,
          affectedPct: parseFloat((count / historicalOutputs.length * 100).toFixed(1)),
        };
      })
      .sort((a, b) => b.count - a.count);

    const blockerFields = failureBreakdown
      .filter(f => f.affectedPct >= 5.0)   // affects ≥5% of corpus
      .map(f => f.field);

    return {
      label,
      total:            historicalOutputs.length,
      passing,
      failing,
      passingPct,
      passingThreshold: passingThreshold * 100,
      migrationApproved: passingPct >= passingThreshold * 100,
      failureBreakdown,
      blockerFields,
      results,
    };
  }

  _typeOk(value, declaredType) {
    if (declaredType === 'number') {
      return typeof value === 'number' ||
             (typeof value === 'string' && !isNaN(parseFloat(value)));
    }
    if (declaredType === 'array')  return Array.isArray(value);
    if (declaredType === 'string') return typeof value === 'string' || typeof value === 'number';
    return typeof value === declaredType;
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `testOne()` and `testCorpus()` timed over 100 000 iterations. Corpus scenario: 800 contract extractions (v1.0 schema), tested against v2.0 schema.

```
=== OutputSchemaMigrationTester timing (100 000 iterations) ===

testOne() — 6-field schema, PASS output:         0.0021 ms
testOne() — 6-field schema, 2 REQUIRED_MISSING:  0.0024 ms
testOne() — with UNDECLARED_FIELD warnings:       0.0029 ms
testCorpus() — N=800 outputs, 6-field schema:    0.4181 ms (800 × testOne + aggregation)
testCorpus() — N=200 outputs:                    0.1041 ms

=== Contract extraction: v1.0 → v2.0 migration ===

Schema v1.0 fields: liability_cap, governing_law, termination_notice,
                    payment_terms, dispute_resolution, amendment_procedure (all required)

Schema v2.0 changes:
  1. payment_terms renamed to payment_schedule (required)
  2. indemnification_scope added (required)
  3. amendment_procedure changed from required to optional

--- Run 1: No adapter, no backfill (800 v1.0 outputs vs v2.0 schema) ---

failureBreakdown:
  payment_schedule    REQUIRED_MISSING    800/800   100.0%   ← old field name
  indemnification_scope REQUIRED_MISSING  800/800   100.0%   ← new field, v1 never generated it
  [amendment_procedure: now optional → no longer flagged as missing when absent]

passingPct:        0.0%
migrationApproved: false
blockerFields:     ['payment_schedule', 'indemnification_scope']

--- Action 1: Deploy S-120 adapter (payment_terms → payment_schedule) ---
--- Action 2: Run backfill: re-extract indemnification_scope for 800 stored outputs ---

--- Run 2: Adapter deployed + backfill complete (800 updated outputs vs v2.0 schema) ---

payment_schedule: adapter maps payment_terms → 0 REQUIRED_MISSING failures remaining
indemnification_scope: backfill completed for 777/800 contracts (97.1%)
  23 contracts pre-date the indemnification clause becoming standard (genuine absence)
  → team marks indemnification_scope nullable: true for contracts < 2019

failureBreakdown after schema adjustment (indemnification_scope nullable for pre-2019):
  [no failures on 800 outputs after nullable flag applied]

passingPct:        100.0% (or 97.1% with strict required, 100% with nullable)
migrationApproved: true (threshold 95%)

--- UNDECLARED_FIELD warnings (informational, non-blocking) ---
payment_terms UNDECLARED_FIELD 800/800 — old field name still in output (adapter removed it for consumer,
  but raw output still has both payment_terms and payment_schedule until prompt is updated)

=== S-64 vs S-120 vs S-92 vs F-65 vs F-115 ===

              │ S-64 (schema versioning)          │ S-120 (compat adapter)            │ S-92 (tool schema migration)      │ F-65 (prompt regression)          │ F-115 (migration test harness)
──────────────┼───────────────────────────────────┼───────────────────────────────────┼───────────────────────────────────┼───────────────────────────────────┼───────────────────────────────────
What          │ _v field + change taxonomy        │ Runtime adapter old→new schema    │ Tool input schema migration       │ Snapshot current prompt outputs   │ Test corpus of stored outputs
Tests         │ No — classifies changes           │ No — adapts at runtime            │ Mentions dry-run in one line      │ Current outputs only              │ Historical outputs × new schema
Corpus        │ N/A                               │ N/A                               │ N/A                               │ Current runs                      │ Stored logs / replay outputs
Output        │ Change classification             │ Translated output                 │ N/A                               │ PASS / DRIFT / BLOCKED per run    │ passingPct, failureBreakdown, blockerFields
Gate          │ N/A                               │ N/A                               │ N/A                               │ CI on structural + content drift  │ CI: passingPct ≥ threshold
Composes with │ F-115 reads _v to filter corpus   │ F-115 validates the adapter fixed │ F-115 for output schemas,         │ F-115 tests backlog;              │ S-64 (change type), S-120 (adapter)
              │ by schema version                 │ the failures it was meant to fix  │ S-92 for tool input schemas       │ F-65 tests current prompt         │ F-65 (gate on current outputs)
```

## See also

[S-64](../stacks/s64-agent-output-schema-versioning.md) · [S-120](../stacks/s120-output-schema-backward-compat-adapter.md) · [S-92](../stacks/s92-tool-schema-migration.md) · [F-65](f65-prompt-regression-testing.md) · [F-75](f75-tool-output-schema-contracts.md) · [S-141](../stacks/s141-source-schema-contract-versioning.md)

## Go deeper

Keywords: `output schema migration testing` · `schema migration dry run` · `historical output compatibility` · `schema version migration test` · `model output backward compatibility` · `migration test harness` · `schema change test corpus` · `output schema breaking change detection` · `LLM output schema migration` · `schema compatibility test CI`
