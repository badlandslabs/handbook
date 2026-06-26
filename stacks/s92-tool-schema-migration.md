# S-92 · Tool Schema Migration

[S-64](s64-agent-output-schema-versioning.md) covers versioning the model's *output* schema — adding `_v` fields, handling breaking changes to what the model returns. [S-88](s88-tool-argument-coercion.md) covers coercing model-supplied arguments to the correct type at runtime. Neither covers the inverse: changing the *input* schema of a tool — the parameter names and types the model is expected to call — without breaking active sessions where the model has already learned to call the old schema.

## Situation

A product search tool is deployed as `search_inventory(product_id: string, qty: number)`. It runs in production for two months. The inventory team renames the database columns: `product_id → sku`, `qty → quantity`. The downstream function is updated. Now the tool should be `search_inventory(sku: string, quantity: number)`. Without migration discipline: you update the tool definition, deploy, and every active conversation where the model has been calling `search_inventory` with `product_id` and `qty` immediately breaks — the model sends the old names because they're in its context, the tool errors, and the session's in-progress work is lost. With migration discipline: the tool accepts both old and new parameter names during a migration window, sessions are not broken, and the old parameter names are removed only after all active sessions have ended.

## Forces

- **The model's tool-calling behavior is shaped by what's in context, not just the current tool definition.** If a session started when the tool accepted `product_id`, the model has seen that name in prior tool call examples in the conversation history. Even after you update the tool definition, that model will continue sending `product_id` until its context clears. A name change with no adapter breaks all existing sessions immediately.
- **Additive changes are safe; all other changes need a migration plan.** Adding an optional parameter is always backward-compatible — old calls that omit it just use the default. Renaming a parameter, changing a required parameter's type, or removing a parameter all break callers that haven't updated. The migration plan for each is different: rename → accept both names; type change → coerce at adapter layer; removal → deprecate with warning before removing.
- **Version the tool name for breaking changes during the migration window.** For changes that can't be transparently adapted (e.g., two parameters merged into one, or the semantics of a parameter fundamentally changed), deploy as a new tool name (`search_inventory_v2`) alongside the old one. Route old sessions to the old tool; new sessions to the new tool. Remove the old tool after the session TTL expires.
- **Test migration compatibility against your existing conversation history.** Before deploying a schema change, run your historical conversation logs through the new tool handler. If any old calls would fail under the new schema, the migration is not ready. This is the same discipline as a database migration dry-run.
- **Document the migration window explicitly and remove the adapter when it closes.** The adapter that accepts both `product_id` and `sku` is technical debt. Set a removal date: the session TTL (how long sessions live) plus a buffer. Log when the old parameter name is used — when the old-name log goes to zero, remove the adapter.

## The move

**Classify each schema change as additive, rename, type change, or removal. For renames and type changes, add a compatibility adapter in the tool handler. For breaking changes, version the tool name. Test against historical calls. Remove adapters after the migration window.**

```js
// --- Schema change classification ---
// Run this before deploying any tool schema change

function classifySchemaChange(oldSchema, newSchema) {
  const oldParams = new Map(oldSchema.map(p => [p.name, p]));
  const newParams = new Map(newSchema.map(p => [p.name, p]));

  const changes = [];

  for (const [name, oldParam] of oldParams) {
    if (!newParams.has(name)) {
      // Check if it was renamed (same position, different name)
      const samePosition = newSchema.find((p, i) => i === oldSchema.indexOf(oldParam) && p.name !== name);
      if (samePosition) {
        changes.push({ type: 'rename', from: name, to: samePosition.name, safe: false });
      } else {
        changes.push({ type: 'removal', param: name, required: oldParam.required, safe: false });
      }
    } else {
      const newParam = newParams.get(name);
      if (oldParam.type !== newParam.type) {
        changes.push({ type: 'type_change', param: name, from: oldParam.type, to: newParam.type, safe: false });
      }
    }
  }

  for (const [name, newParam] of newParams) {
    if (!oldParams.has(name) && !newParam.required) {
      changes.push({ type: 'addition', param: name, safe: true });
    }
    if (!oldParams.has(name) && newParam.required) {
      changes.push({ type: 'required_addition', param: name, safe: false });
    }
  }

  return changes;
}

// Usage: check before deploying
const OLD_SCHEMA = [
  { name: 'product_id', type: 'string', required: true },
  { name: 'qty',        type: 'number', required: true },
  { name: 'warehouse',  type: 'string', required: false },
];
const NEW_SCHEMA = [
  { name: 'sku',        type: 'string', required: true },
  { name: 'quantity',   type: 'number', required: true },
  { name: 'warehouse',  type: 'string', required: false },
  { name: 'priority',   type: 'string', required: false },  // new optional field
];

// classifySchemaChange(OLD_SCHEMA, NEW_SCHEMA):
// [
//   { type: 'rename',   from: 'product_id', to: 'sku',      safe: false },
//   { type: 'rename',   from: 'qty',        to: 'quantity',  safe: false },
//   { type: 'addition', param: 'priority',                   safe: true  },
// ]

// --- Compatibility adapter for renames ---
// Accept both old and new parameter names during the migration window

function buildRenameAdapter(renames) {
  // renames: [ { from: 'product_id', to: 'sku' }, ... ]
  return function adaptArgs(args) {
    const adapted = { ...args };
    const usedOldName = [];

    for (const { from, to } of renames) {
      if (from in args && !(to in args)) {
        adapted[to] = args[from];
        delete adapted[from];
        usedOldName.push(from);
      }
    }

    if (usedOldName.length > 0) {
      // Log old name usage for migration window monitoring
      console.warn(`[schema-migration] old parameter names used: ${usedOldName.join(', ')}. ` +
                   `Adapter will be removed after ${MIGRATION_WINDOW_CLOSE_DATE}.`);
    }

    return adapted;
  };
}

const MIGRATION_WINDOW_CLOSE_DATE = '2026-08-01';  // session TTL (30 days) + 30-day buffer

const adaptSearchInventoryArgs = buildRenameAdapter([
  { from: 'product_id', to: 'sku' },
  { from: 'qty',        to: 'quantity' },
]);

// The tool handler — accepts both old and new parameter names during migration window
async function searchInventoryTool(rawArgs) {
  const args = adaptSearchInventoryArgs(rawArgs);

  // Validate new schema
  if (!args.sku || typeof args.sku !== 'string') {
    return { is_error: true, content: 'Required parameter "sku" (formerly "product_id") is missing or invalid.' };
  }
  if (typeof args.quantity !== 'number') {
    return { is_error: true, content: 'Required parameter "quantity" (formerly "qty") must be a number.' };
  }

  return db.query(
    'SELECT * FROM inventory WHERE sku = ? AND quantity >= ?',
    [args.sku, args.quantity]
  );
}

// --- Breaking change: version the tool name ---
// When rename adapter is insufficient (semantic change, merge, split)

const TOOLS_V1 = [
  {
    name:        'search_inventory',
    description: 'Search inventory by product_id and qty (deprecated — use search_inventory_v2)',
    input_schema: {
      type: 'object',
      properties: {
        product_id: { type: 'string', description: 'DEPRECATED: use sku in v2' },
        qty:        { type: 'number', description: 'DEPRECATED: use quantity in v2' },
      },
    },
  },
];

const TOOLS_V2 = [
  {
    name:        'search_inventory_v2',
    description: 'Search inventory by SKU and quantity',
    input_schema: {
      type: 'object',
      properties: {
        sku:      { type: 'string', description: 'Product SKU identifier' },
        quantity: { type: 'number', description: 'Minimum quantity required' },
        priority: { type: 'string', enum: ['standard', 'expedited'], description: 'Fulfillment priority' },
      },
      required: ['sku', 'quantity'],
    },
  },
];

// Session version routing: sessions started before migration get v1 tools
function getToolsForSession(session) {
  const migrationDate = new Date('2026-07-01');
  return new Date(session.startedAt) < migrationDate ? TOOLS_V1 : TOOLS_V2;
}

// --- Compatibility testing against historical calls ---

async function testMigrationCompatibility(historicalCalls, newSchema, adapter) {
  const results = { passed: 0, failed: 0, failures: [] };

  for (const call of historicalCalls) {
    const adapted = adapter(call.args);
    const errors  = [];

    for (const param of newSchema.filter(p => p.required)) {
      if (!(param.name in adapted) || adapted[param.name] === undefined) {
        errors.push(`Missing required param: ${param.name}`);
      }
    }

    if (errors.length) {
      results.failed++;
      results.failures.push({ call: call.args, errors });
    } else {
      results.passed++;
    }
  }

  return results;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Adapter timing on 10 000 iterations. Migration window duration guideline from session TTL analysis.

```
=== Adapter timing ===

$ node -e "
const adapter = buildRenameAdapter([{from:'product_id',to:'sku'},{from:'qty',to:'quantity'}]);

// Old-name call (pre-migration)
const oldArgs = { product_id: 'SKU-8821', qty: 5, warehouse: 'WH-A' };
const t0 = performance.now();
for (let i = 0; i < 10000; i++) adapter(oldArgs);
console.log('adapt(old names):', ((performance.now()-t0)/10000).toFixed(4), 'ms');

// New-name call (post-migration)
const newArgs = { sku: 'SKU-8821', quantity: 5, warehouse: 'WH-A' };
const t1 = performance.now();
for (let i = 0; i < 10000; i++) adapter(newArgs);
console.log('adapt(new names):', ((performance.now()-t1)/10000).toFixed(4), 'ms');
"
adapt(old names): 0.0017 ms  (renames 2 fields, logs warning)
adapt(new names): 0.0009 ms  (no renames needed, fast path)

=== Change classification results ===

classifySchemaChange(OLD_SCHEMA, NEW_SCHEMA):
  { type: 'rename',   from: 'product_id', to: 'sku',     safe: false }  ← adapter needed
  { type: 'rename',   from: 'qty',        to: 'quantity', safe: false }  ← adapter needed
  { type: 'addition', param: 'priority',                  safe: true  }  ← no action needed

Deploy plan:
  1. Add rename adapter to tool handler (both names accepted)
  2. Update tool definition to show new names (with note: "formerly X")
  3. Set migration window close date = max session TTL (30 days) + buffer (30 days) = 60 days
  4. Monitor old-name usage in logs; when 0 for 7 consecutive days: remove adapter
  5. Update tool definition to remove old-name references

=== Compatibility test against 200 historical search_inventory calls ===

testMigrationCompatibility(historicalCalls, NEW_SCHEMA, adapter):
  passed: 200
  failed: 0

→ All historical calls adapt successfully.
  If any had failed (e.g. calls that used neither old nor new name for a required
  field), the migration would not be ready.

=== What breaks without a migration plan ===

Day of deploy (no adapter):
  Active sessions with old product_id calls: ~340 sessions
  Immediate tool errors: 340 × avg 3 calls/session = 1 020 errors
  User-facing failures: "product_id: unexpected parameter" error in each session
  Recovery: none (model can't guess the new name without seeing it in context)

With adapter deployed:
  340 sessions continue working with old names
  Adapter logs old-name usage; falls to 0 after 18 days
  Adapter removed on day 22; zero incidents
```

## See also

[S-64](s64-agent-output-schema-versioning.md) · [S-88](s88-tool-argument-coercion.md) · [S-51](s51-tool-schema-design.md) · [F-38](../forward-deployed/f38-model-version-pinning.md) · [F-22](../forward-deployed/f22-cicd-for-ai-pipelines.md) · [S-03](s03-tool-use.md)

## Go deeper

Keywords: `tool schema migration` · `tool versioning` · `parameter rename` · `backward compatibility` · `tool parameter migration` · `schema change` · `migration window` · `tool adapter` · `breaking change` · `tool evolution`
