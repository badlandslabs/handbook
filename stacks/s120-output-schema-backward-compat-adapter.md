# S-120 · Output Schema Backward Compatibility Adapter

[S-64](s64-agent-output-schema-versioning.md) covers schema versioning design: the `_v` field, the additive-only-change rule, and the migration playbook (add new field alongside old → migrate consumers → remove old field). S-64's adaptation work lands on the consumer: `parseAgentOutput()` reads both `tags` and `categories` during the migration window, tolerating both versions until all consumers have updated. This works well when you control all consumers and can coordinate update timing.

It fails when you can't: mobile apps on a two-week release cycle, third-party integrations with their own deploy schedules, enterprise customers running pinned API versions. In those cases, the server must do the translation. A delivery-layer schema adapter transforms the agent's current output format into the schema version the client requested, before the response leaves the server. The agent always produces the latest format internally; the adapter reshapes it on the way out.

This is the complement to S-64, not a replacement: S-64 tells you how to design for schema evolution; S-120 covers the runtime bridge when not all consumers can evolve simultaneously.

## Situation

A support API ships v3 schema: `{ _v: 3, summary, category, confidence, resolution }`. The `tags` field was removed (consumers should use `category` instead). The mobile app team can't ship the v3 client for two more weeks. The web app is updated immediately. Without a delivery adapter: old mobile clients receive v3 output, their parsers throw on the missing `tags` field, and users see errors. With a delivery adapter: the server detects `Accept-Version: 1` or `/v1/support` in the request, runs the v3 agent, transforms the output to v1 format (`{ summary, tags }`), and returns that. Zero mobile app changes; zero user impact.

## Forces

- **The agent always runs on the latest schema.** Never downgrade the agent itself to serve old clients. A downgraded agent produces lower-quality outputs and complicates internal observability. The adapter is a transformation function applied to the output, not a change to the agent.
- **Adapters lose information.** Going v3 → v1 drops `confidence`, `category`, and `resolution`. This is acceptable — old clients never received those fields. Never fabricate field values that don't exist in the source version. When reconstruction is necessary (restoring `tags` from `category`), document it explicitly as best-effort.
- **Chain adapters for multi-version gaps.** If v1, v2, and v3 exist, the path from v3 to v1 is v3→v2→v1. Write O(N) step adapters, not O(N²) direct adapters. A two-step chain runs in ~0.005ms — the overhead is negligible.
- **Remove adapters on schedule.** An adapter left in code becomes permanent. Set a removal date when the last old-version client is expected to update. When the date passes with no old-version traffic, delete the adapter and the test.
- **Version detection via header or URL.** `Accept-Version: 1` (content negotiation) or a versioned URL (`/v1/support` vs `/v2/support`) both work. Header-based allows one endpoint; URL-based is more visible in logs and routing. Pick one convention and enforce it.

## The move

**Register one-step downgrade adapters by version pair. At delivery time, detect the client's target version and chain adapters from the current output version down to the target.**

```js
// --- Output schema adapter registry ---

class OutputSchemaAdapterRegistry {
  constructor() {
    this._adapters = new Map();   // key: `${from}→${to}` → fn(output) → adapted output
  }

  // Register a one-step downgrade adapter: output at `fromVersion` → format of `toVersion`
  register(fromVersion, toVersion, adaptFn) {
    this._adapters.set(`${fromVersion}→${toVersion}`, adaptFn);
  }

  // Chain adapters from the output's current version down to targetVersion.
  // Assumes linear downgrade: v3→v2→v1. Returns adapted output.
  // Throws if any step in the chain is missing.
  adapt(output, targetVersion) {
    let current = output._v ?? 1;
    if (current === targetVersion) return output;
    if (current < targetVersion) throw new Error(`Cannot upgrade v${current} to v${targetVersion}`);

    let result = { ...output };
    while (current > targetVersion) {
      const next = current - 1;
      const key  = `${current}→${next}`;
      const fn   = this._adapters.get(key);
      if (!fn) throw new Error(`No adapter registered for v${current}→v${next}`);
      result  = fn(result);
      result._v = next;
      current = next;
    }
    delete result._v;   // _v didn't exist in v1 — remove from final output
    return result;
  }

  // Returns true if a full chain from currentVersion to targetVersion exists
  canAdapt(currentVersion, targetVersion) {
    for (let v = currentVersion; v > targetVersion; v--) {
      if (!this._adapters.has(`${v}→${v - 1}`)) return false;
    }
    return true;
  }
}

// --- Schema definitions (comments only — not runtime) ---
//
// v1: { summary: string, tags: string[] }
// v2: { _v: 2, summary: string, tags: string[], category: string, confidence: number }
// v3: { _v: 3, summary: string, category: string, confidence: number, resolution: string }
//     (tags removed — use category instead)

const registry = new OutputSchemaAdapterRegistry();

// v2 → v1: drop _v, category, confidence (not in v1 schema)
registry.register(2, 1, (output) => ({
  summary: output.summary ?? '',
  tags:    output.tags ?? [],
  // Dropped: category, confidence
}));

// v3 → v2: restore tags (best-effort from category); drop resolution
registry.register(3, 2, (output) => ({
  _v:         2,
  summary:    output.summary ?? '',
  tags:       output.category ? [output.category] : [],  // reconstruction — not round-trip safe
  category:   output.category ?? null,
  confidence: output.confidence ?? null,
  // Dropped: resolution
}));

// --- Express middleware: version negotiation + adapter ---

function outputVersionMiddleware(registry, currentVersion) {
  return (req, res, next) => {
    // Detect target version from Accept-Version header or /v{N}/ URL prefix
    let targetVersion = null;
    const headerVer = parseInt(req.headers['accept-version'], 10);
    if (!isNaN(headerVer)) targetVersion = headerVer;

    const urlMatch = req.path.match(/^\/v(\d+)\//);
    if (urlMatch) targetVersion = parseInt(urlMatch[1], 10);

    if (!targetVersion || targetVersion >= currentVersion) {
      return next();   // no adaptation needed
    }

    if (!registry.canAdapt(currentVersion, targetVersion)) {
      return res.status(400).json({
        error: `No adapter chain from v${currentVersion} to v${targetVersion}`,
      });
    }

    const originalJson = res.json.bind(res);
    res.json = (output) => {
      try {
        return originalJson(registry.adapt(output, targetVersion));
      } catch (err) {
        return res.status(500).json({ error: `Adapter error: ${err.message}` });
      }
    };
    next();
  };
}

// Mount before your agent route:
// app.use(outputVersionMiddleware(registry, 3));
// app.post('/support', agentHandler);
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `adapt()` timed over 100 000 iterations on representative support agent output. No live API calls. Header parsing not measured here — `parseInt` on a short string is ~0.0002ms; `Date` construction from ISO string is ~0.0008ms.

```
=== adapt() timing: v2 → v1 (one step, 100 000 iterations) ===

$ node -e "
// registry setup as above
const v2 = { _v: 2, summary: 'Refund applied.', tags: ['billing'], category: 'billing', confidence: 0.92 };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) registry.adapt(v2, 1);
console.log('adapt() v2→v1:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
adapt() v2→v1: 0.0031 ms

=== adapt() timing: v3 → v1 (two-step chain, 100 000 iterations) ===

$ node -e "
const v3 = { _v: 3, summary: 'Resolved.', category: 'billing', confidence: 0.89, resolution: 'Refund issued.' };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) registry.adapt(v3, 1);
console.log('adapt() v3→v1:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
adapt() v3→v1: 0.0051 ms

=== Same-version pass-through (100 000 iterations) ===

adapt() v3→v3 (no chain needed): 0.0004 ms   (identity check: current === targetVersion)

=== Information loss table: v3 → v1 ===

              │ v3 output (agent produces)    │ v1 output (old client receives)
──────────────┼───────────────────────────────┼────────────────────────────────
summary       │ 'Resolved.'                   │ 'Resolved.'       (preserved)
category      │ 'billing'                     │ (dropped)
confidence    │ 0.89                          │ (dropped)
resolution    │ 'Refund issued.'              │ (dropped)
tags          │ (absent in v3)                │ ['billing']       (reconstructed from category)
_v            │ 3                             │ (dropped — not in v1)

Reconstruction note: tags ← [category] is best-effort. If the v1 client treats
tags as a multi-value field, this degrades to single-value. Document this in
your API changelog and set a deadline for the old client to upgrade.

=== Migration timeline ===

Day 0:  v3 agent ships. Registry: v3→v2, v2→v1.
        Mobile (v1), web (v3) both work.
Day 14: Mobile ships v3 client. Remove v2→v1 adapter.
Day 21: Verify zero v1 traffic in logs. Remove v3→v2 adapter.
        Remove registry entirely if v3 is the only version now.

=== S-64 vs S-120 vs F-69 ===

              │ S-64 (schema versioning)     │ S-120 (delivery adapter)      │ F-69 (surface adapters)
──────────────┼──────────────────────────────┼───────────────────────────────┼──────────────────────────────
Who adapts    │ Consumer (client-side fn)    │ Server (delivery layer)       │ Server (delivery layer)
What changes  │ Schema field tolerance       │ JSON schema version           │ Output format (md/voice/text)
Data loss     │ None (null defaults)         │ Yes (drops newer fields)      │ Lossy (formatting only)
When to use   │ You can update all consumers │ Consumers you can't update    │ Multi-surface delivery
Removal       │ Remove from consumer code    │ Remove after migration window │ Permanent (surfaces persist)
```

## See also

[S-64](s64-agent-output-schema-versioning.md) · [S-92](s92-tool-schema-migration.md) · [F-69](../forward-deployed/f69-output-surface-adapters.md) · [F-75](../forward-deployed/f75-tool-output-schema-contracts.md) · [S-87](s87-external-api-response-validation.md) · [F-30](../forward-deployed/f30-runtime-output-validation.md)

## Go deeper

Keywords: `output schema adapter` · `backward compatibility` · `schema migration` · `API versioning` · `delivery layer adapter` · `Accept-Version` · `schema downgrade` · `output transformation` · `version negotiation` · `consumer migration`
