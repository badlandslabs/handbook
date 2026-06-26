# S-64 · Agent Output Schema Versioning

[S-04](s04-structured-output.md) covers how to define a schema and make the model return it. What happens when the schema needs to change? The agent returns `{summary, tags}`. Downstream code reads `.tags`. You need to add a `confidence` field and rename `tags` to `categories`. Without a versioning strategy, any change that breaks the existing shape breaks every downstream consumer silently — until their parse fails in production.

## Situation

A report-generation agent has been running in production for two months, returning `{summary: string, tags: string[]}`. The product team wants to add `confidence: number` and `sources_cited: number`. One new field is optional — safe to add. The other is required by the new UI — breaking for any consumer that doesn't handle it. Meanwhile, someone suggests renaming `tags` to `categories` for consistency. That rename breaks every caller reading `.tags`. Three changes, two are breaking. Without version discipline, this ships as a JSON patch that breaks at runtime.

## Forces

- **Only additive changes are safe.** Adding an optional field doesn't break readers that don't read it. Everything else — rename, type change, required new field, remove field, narrowed enum — is breaking for at least one existing consumer.
- **The model doesn't enforce the schema.** You asked for `{summary, tags}`. You get `{summary, tags}` most of the time. If you change the schema, the model produces the new shape — and old consumers receiving the new shape fail silently or throw.
- **A version field costs five tokens and saves debugging hours.** `"_v": 2` in the output lets any consumer know immediately which contract it received. Without it, the consumer has to infer the version from field presence — fragile and implicit.
- **Consumers must tolerate unknown fields.** A reader that throws on unexpected fields will break every time the producer adds one. Default-to-null for unknown fields is the correct posture; it makes additive changes safe at the receiver.
- **Contract tests in CI catch schema drift early.** The model can hallucinate a field, drop one, or change a type after a provider model update. A CI check that runs the agent against saved inputs and asserts schema shape catches this before it reaches users.

## The move

**Embed a `_v` field from day one. Make additive changes only. For breaking changes, add alongside the old field, migrate consumers, then remove. Test schema shape in CI.**

**The change taxonomy:**

| Change | Safe? | Why |
|---|---|---|
| Add optional field | Yes | Old readers ignore unknown fields |
| Add required field | **No** | Old readers don't handle the new field |
| Rename field | **No** | Old readers read the old name |
| Change field type | **No** | Old readers expect the old type |
| Remove field | **No** | Any reader that uses it breaks |
| Narrow enum | **No** | Old handlers for dropped values break |

**Schema version field in the output contract:**

```js
// System prompt (add to <output> section — S-36)
// "Always include \"_v\": 2 as the first field in your JSON response."

// v1 (no version field — implicit v1)
// { "summary": "...", "tags": ["a", "b"] }

// v2 (added _v, confidence, sources_cited — all additive)
// { "_v": 2, "summary": "...", "tags": ["a", "b"], "confidence": 0.91, "sources_cited": 3 }
```

**Consumer-side tolerance pattern:**

```js
function parseAgentOutput(raw) {
  const obj = typeof raw === 'string' ? JSON.parse(raw) : raw;
  return {
    _v:            obj._v           ?? 1,                         // default to v1 if absent
    summary:       obj.summary      ?? '',
    tags:          obj.tags         ?? obj.categories ?? [],      // handle if rename ships
    confidence:    obj.confidence   ?? null,                      // optional: null if absent
    sources_cited: obj.sources_cited ?? null,
  };
}
```

The `?? null` defaults mean new optional fields are safe to add without touching this function. The `obj.tags ?? obj.categories` line handles a rename by reading both names — remove when migration is complete.

**Migration playbook for breaking changes:**

```
Step 1: Add new field alongside old (additive — safe to ship)
        { tags: [...], categories: [...] }  // both present

Step 2: Update all consumers to read the new field, ignore the old

Step 3: In the next release, remove the old field from the schema
        { categories: [...] }  // tags gone

Step 4: Bump _v. Update contract test.
```

Never skip Step 2 before Step 3. The window where both fields exist is the migration window — it must be open long enough for all consumers to update.

**Schema contract test:**

```js
const REQUIRED_FIELDS = {
  1: ['summary', 'tags'],
  2: ['_v', 'summary', 'tags', 'confidence'],
};

function assertSchema(output, expectedVersion) {
  const required = REQUIRED_FIELDS[expectedVersion];
  if (!required) throw new Error('Unknown schema version: ' + expectedVersion);
  const missing = required.filter(k => !(k in output));
  if (missing.length) throw new Error('Schema v' + expectedVersion + ' missing: ' + missing.join(', '));
  if (output._v !== undefined && output._v !== expectedVersion) {
    throw new Error('Schema version mismatch: got _v=' + output._v + ', expected ' + expectedVersion);
  }
}

// In CI: run the agent against golden inputs, assert schema
test('agent output matches schema v2', async () => {
  const output = await agent.run(GOLDEN_INPUT);
  assertSchema(output, 2);
});
```

Run this test on every PR. It catches model drift (provider update changed output shape), prompt regression (edit accidentally dropped the `_v` instruction), and schema mismatches before they hit users.

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). Price: $15.00/M output.

```
=== Schema version field overhead ===

v1 output (no version):         34 tokens   { summary, tags }
v2 output (with _v + 2 fields): 51 tokens   { _v, summary, tags, confidence, sources_cited }
_v field overhead alone:         5 tokens

At 10k outputs/day:
  _v field cost: $22.50/month
  Value: catches schema mismatch before it hits users — a single production
  schema incident costs far more in engineering time.

=== Breaking vs safe change classification ===

✓ SAFE     ADD_OPTIONAL   add confidence: number (optional)
✗ BREAKING ADD_REQUIRED   add required field — breaks old readers
✗ BREAKING RENAME_FIELD   rename tags → categories — breaks .tags readers
✗ BREAKING CHANGE_TYPE    tags: string[] → tags: {id, label}[] — breaks consumers
✗ BREAKING REMOVE_FIELD   remove tags — breaks any reader using it
✗ BREAKING NARROW_ENUM    status: "ok"|"fail" → "ok" only — breaks "fail" handlers
```

## See also

[S-04](s04-structured-output.md) · [S-39](s39-output-parsing-robustness.md) · [F-22](../forward-deployed/f22-cicd-for-ai-pipelines.md) · [W-09](../workspace/w09-prompt-versioning.md) · [S-36](s36-system-prompt-architecture.md) · [F-07](../forward-deployed/f07-evaluation-driven-development.md)

## Go deeper

Keywords: `schema versioning` · `output schema` · `breaking change` · `additive schema` · `contract test` · `schema drift` · `backward compatibility` · `_v field` · `consumer tolerance` · `migration playbook`
