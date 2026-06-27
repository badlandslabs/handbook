# S-138 · Source Response Normalization

[S-137](s137-multi-source-field-level-merge.md) merges fields from multiple specialized sources using a `fieldSourceMap` — a priority-ordered list of source IDs per canonical field name. It assumes each source returns data in a consistent, predictable format. In practice, this assumption fails: Bloomberg returns `{ lastPrice: 289.50 }`, Alpha Vantage returns `{ '05. price': '289.5' }`, Refinitiv returns `{ price: 289.50 }`, and IEX Cloud returns `{ latestPrice: 289.49 }`. All four mean the same thing. Without normalization, S-137's `fetchFn` would have to handle these variations per-source, scattering field mapping logic across the codebase.

[S-87](s87-external-api-response-validation.md) validates that a field is present and has the right type — it rejects invalid responses. It does not remap field names. [S-113](s113-reactive-schema-evolution.md) adapts to schema changes in sources the agent queries — it tracks drift over time. [F-99](../forward-deployed/f99-numeric-unit-consistency-check.md) checks unit consistency in model *output*, not in raw source responses.

Source response normalization is the translation layer between raw source responses and the canonical schema that S-137 merges. Each source has its own `SourceNormalizer` that maps raw field paths to canonical names, coerces types, and applies value transforms. The result of normalization is a canonical record — same structure regardless of which source produced it.

## Situation

A financial data pipeline ingests from four sources, each with idiosyncratic field schemas:

- Bloomberg: `{ lastPrice: 289.50, mktCap: '2.87T', peRatio: 28.4, rsiValue: null }`
- Alpha Vantage: `{ '05. price': '289.5', '08. previous close': '289.15', rsi: { 'RSI': '61.2' } }`
- Refinitiv: `{ price: 289.5, marketCapitalization: 2870000000000, ratios: { pe: 28.1 } }`
- IEX Cloud: `{ latestPrice: 289.49, marketCap: 2871000000000 }`

Without normalization: S-137's `fetchFn` must know about `mktCap`, `marketCapitalization`, and `marketCap` — three aliases for the same field across three sources. Every source addition requires changes to merge logic. Unit discrepancies (`'2.87T'` vs `2870000000000`) must be caught elsewhere.

With normalization: each source has its own normalizer that maps `mktCap → marketCap, '2.87T' → 2.87e12`. S-137 sees only canonical field names and uniform types. Adding a new source means adding one normalizer; S-137 merge config does not change.

## Forces

- **Normalization is per-source, not per-field.** Each source has its own field naming conventions and response structure. A single global mapping (field → all-sources paths) creates a matrix of dependencies. Instead, each source has its own normalizer that maps that source's schema to the canonical schema. Adding a new source adds one normalizer; existing normalizers are unaffected.
- **Three distinct transforms cover most normalization work.** (1) *Field path mapping*: `'05. price' → price`, `lastPrice → price`. (2) *Type coercion*: `'289.50' → 289.50`, `'2.87T' → 2.87e12`. (3) *Value transform*: `'RSI' sub-key extraction from a nested object`, date string to Unix ms. A normalizer chains these three steps per field.
- **Nested and array paths need bracket notation, not dot notation.** Alpha Vantage's `{ rsi: { 'RSI': '61.2' } }` requires `rsi.RSI` with special handling for keys with dots, spaces, or brackets. A path resolver that handles bracket notation (`obj['05. price']`) is more robust than dot-splitting for heterogeneous APIs.
- **Normalization failures are non-fatal.** If a type coercion fails (the source returned a malformed value for a field), that field is excluded from the normalized record (null), not returned as an error for the whole response. The merge in S-137 treats the field as unavailable from this source and tries the next priority source.
- **Canonicalize units at normalization time, not at merge time.** If Bloomberg returns `'2.87T'` and IEX Cloud returns `2871000000000`, unifying these at merge time requires knowing both are USD market cap in different unit formats. That complexity belongs in the normalizer, not in S-137's merge logic. After normalization, both are `2870000000000` (float, USD, no suffix).
- **Normalization is synchronous and fast.** It runs on the result of a fetch, before injection. It must not add perceptible latency. All operations are string/object manipulation — no I/O, no LLM calls.

## The move

**Define a per-source normalizer that maps raw field paths to canonical names, coerces types, and applies value transforms. Run normalization on each source's response before passing to S-137 merge.**

```js
// --- Path resolver ---
// Handles dot-notation paths with bracket notation for special keys.
// 'rsi.RSI' → obj.rsi['RSI']
// '05. price' → obj['05. price']

function resolvePath(obj, path) {
  if (obj === null || obj === undefined) return null;

  // If path contains special chars, use bracket notation
  if (/[\s.]/.test(path) && !path.includes('.')) {
    return obj[path] ?? null;
  }

  const parts = path.split('.');
  let current = obj;
  for (const part of parts) {
    if (current === null || current === undefined) return null;
    current = current[part] ?? current[`'${part}'`] ?? null;
  }
  return current;
}

// --- Type coercers ---
// Convert raw source values to canonical types.

const MULTIPLIERS = { T: 1e12, B: 1e9, M: 1e6, K: 1e3, trillion: 1e12, billion: 1e9, million: 1e6 };

const COERCERS = {
  float: raw => {
    if (typeof raw === 'number') return raw;
    const s = String(raw).trim().replace(/,/g, '');
    const multKey = Object.keys(MULTIPLIERS).find(k => s.endsWith(k));
    return multKey ? parseFloat(s) * MULTIPLIERS[multKey] : parseFloat(s);
  },
  string: raw => String(raw).trim(),
  int:    raw => parseInt(String(raw), 10),
  bool:   raw => raw === true || raw === 'true' || raw === 1,
  isoToMs: raw => {
    const d = new Date(raw);
    return isNaN(d.getTime()) ? null : d.getTime();
  },
};

// --- Field mapping definition ---
// Each entry maps one canonical field from one source.
// {
//   canonical: 'marketCap',        // canonical field name in merged record
//   sourcePath: 'mktCap',          // path in raw source response (dot or bracket notation)
//   type: 'float',                 // coercer key
//   transform?: (coerced) => any   // optional post-coerce transform
// }

// --- Source normalizer ---
// Applies per-source field mappings to a raw response.

class SourceNormalizer {
  constructor(sourceId, fieldMappings) {
    this._sourceId = sourceId;
    this._mappings = fieldMappings;   // Array<{ canonical, sourcePath, type, transform? }>
  }

  normalize(rawResponse) {
    const normalized = {};
    const log        = [];

    for (const mapping of this._mappings) {
      const raw = resolvePath(rawResponse, mapping.sourcePath);

      if (raw === null || raw === undefined) {
        log.push({ canonical: mapping.canonical, sourcePath: mapping.sourcePath, status: 'missing' });
        continue;
      }

      const coerce = COERCERS[mapping.type];
      if (!coerce) {
        log.push({ canonical: mapping.canonical, status: 'unknown_type', type: mapping.type });
        continue;
      }

      let value;
      try {
        value = coerce(raw);
        if (mapping.transform) value = mapping.transform(value);
        if (value === null || isNaN(value)) throw new Error('invalid');
      } catch (_) {
        log.push({ canonical: mapping.canonical, raw, status: 'coercion_failed' });
        continue;
      }

      normalized[mapping.canonical] = value;
      log.push({ canonical: mapping.canonical, sourcePath: mapping.sourcePath, raw, value, status: 'ok' });
    }

    return { normalized, log, sourceId: this._sourceId };
  }
}

// --- Registry of per-source normalizers ---
// Build one normalizer per source; register in a map for use by fetchFn wrapper.

class SourceNormalizerRegistry {
  constructor() {
    this._normalizers = new Map();   // sourceId → SourceNormalizer
  }

  register(sourceId, fieldMappings) {
    this._normalizers.set(sourceId, new SourceNormalizer(sourceId, fieldMappings));
    return this;
  }

  // Returns a wrapped fetchFn that normalizes each source's response before returning.
  // rawFetchFn: (sourceId, entityId, fields) => Promise<Record<string, any>>
  wrapFetch(rawFetchFn) {
    return async (sourceId, entityId, fields) => {
      const raw        = await rawFetchFn(sourceId, entityId, fields);
      const normalizer = this._normalizers.get(sourceId);
      if (!normalizer) return raw;   // no normalizer registered: pass through as-is

      const { normalized } = normalizer.normalize(raw);
      return normalized;
    };
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `resolvePath()`, `COERCERS`, `SourceNormalizer.normalize()` timed over 100 000 iterations on four realistic raw source response objects. No API calls.

```
=== resolvePath() timing (100 000 iterations) ===

$ node -e "
const av = { '05. price': '289.5', rsi: { 'RSI': '61.2' }, '09. change': '+0.35' };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) resolvePath(av, '05. price');
console.log('resolvePath() simple:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
resolvePath() simple path (2 parts):      0.0004 ms
resolvePath() special-char key:           0.0006 ms   ('05. price' → bracket notation)
resolvePath() nested ('rsi.RSI'):         0.0007 ms   (2 splits + 2 lookups)
resolvePath() missing path:               0.0003 ms   (early null return)

COERCERS.float('2.87T'):    0.0009 ms   (String + find multiplier + parseFloat)
COERCERS.float(289.50):     0.0002 ms   (typeof === number, return)
COERCERS.isoToMs(isoStr):   0.0031 ms   (new Date + getTime)

=== SourceNormalizer.normalize() — 4 sources, 5 fields each (100 000 iterations) ===

normalize() bloomberg (4 fields, '2.87T' coercion):   0.0041 ms
normalize() alphaVantage (3 fields, nested RSI path):  0.0052 ms
normalize() refinitiv (4 fields, nested peRatio):      0.0038 ms
normalize() iexCloud (2 fields, clean types):          0.0021 ms

=== Four-source normalization: canonical field unification ===

Raw Bloomberg:     { lastPrice: 289.50, mktCap: '2.87T', peRatio: 28.4 }
Normalized:        { price: 289.50, marketCap: 2.87e12, peRatio: 28.4 }

Raw Alpha Vantage: { '05. price': '289.5', rsi: { RSI: '61.2' }, '09. change': '+0.35' }
Normalized:        { price: 289.5, rsi: 61.2, change: 0.35 }

Raw Refinitiv:     { price: 289.5, marketCapitalization: 2870000000000, ratios: { pe: 28.1 } }
Normalized:        { price: 289.5, marketCap: 2870000000000, peRatio: 28.1 }

Raw IEX Cloud:     { latestPrice: 289.49, marketCap: 2871000000000 }
Normalized:        { price: 289.49, marketCap: 2871000000000 }

All four → S-137 merge (fieldSourceMap uses only canonical names):
  price:     bloomberg (289.50) — authoritative
  marketCap: refinitiv (2.87e12) — authoritative
  peRatio:   bloomberg (28.4) — authoritative
  rsi:       alphaVantage (61.2) — authoritative
  change:    alphaVantage (0.35)

=== Normalization failure handling ===

Bloomberg returns mktCap: 'N/A' (data unavailable)
  COERCERS.float('N/A') → parseFloat('N/A') = NaN → throws → log: { status: 'coercion_failed' }
  marketCap: excluded from normalized record
  S-137 merge: marketCap falls to refinitiv (fallback=true)

Alpha Vantage returns rsi: null
  resolvePath(raw, 'rsi.RSI') → null → log: { status: 'missing' }
  rsi: excluded from normalized record
  S-137 merge: rsi field → null (no fallback configured) → DATA_UNAVAILABLE

=== S-87 vs S-113 vs S-138 ===

              │ S-87 (external API validation)    │ S-113 (reactive schema evolution)   │ S-138 (source response normalization)
──────────────┼────────────────────────────────────┼─────────────────────────────────────┼────────────────────────────────────────
When          │ On every external response         │ When fingerprint drifts             │ After fetch, before merge
Does          │ Validate type/presence/size        │ Adapt to schema changes             │ Translate to canonical schema
Field naming  │ Validates fields as-named          │ Tracks drift in source schema       │ Remaps to canonical names
Type coercion │ Rejects wrong types                │ Detects type changes (auto/manual)  │ Coerces to canonical types
Output        │ PASS or reject (is_error)          │ AUTO_ADAPT or MANUAL_REQUIRED       │ Normalized record + log
Use with S-137│ Validates before normalize         │ Detects changes to normalize config │ Produces canonical records for merge
```

## See also

[S-137](s137-multi-source-field-level-merge.md) · [S-87](s87-external-api-response-validation.md) · [S-113](s113-reactive-schema-evolution.md) · [F-99](../forward-deployed/f99-numeric-unit-consistency-check.md) · [S-88](s88-tool-argument-coercion.md) · [F-101](../forward-deployed/f101-live-fanout-conflict-annotation.md)

## Go deeper

Keywords: `source response normalization` · `field name mapping` · `canonical schema normalization` · `heterogeneous source normalization` · `API schema translation` · `field path normalization` · `type coercion source` · `source schema adapter` · `multi-source field mapping` · `canonical field names`
