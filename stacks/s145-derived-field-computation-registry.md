# S-145 · Derived Field Computation Registry

[S-137](s137-multi-source-field-level-merge.md) fans out to N sources per field and returns `DATA_UNAVAILABLE` when all sources fail to provide a value. [S-96](s96-tool-fallback-chains.md) chains alternative *sources* for the same field: try Bloomberg, then Refinitiv, then Alpha Vantage. Both patterns assume the field value must come *directly* from a source. [S-138](s138-source-response-normalization.md) coerces and maps field names but does not compute new values.

Some fields can be computed from other fields when no source provides them directly. Enterprise value (EV) is market cap plus total debt minus cash. Price-to-earnings is price divided by earnings per share. Yield is annual coupon divided by current price. When Bloomberg is down for EV but Refinitiv provides the three component fields, a formula can produce EV at zero additional API cost, in microseconds, with documented provenance.

A derived field computation registry stores formulas: field name → (mergedRecord) → value | null. After S-137 merges available source data, the resolver iterates missing fields, looks up a formula, attempts computation from whatever components are present, and annotates the result as `_derived: true` with the component fields listed. If any required component is also missing, the derivation fails gracefully — no partial computation, no invented values.

## Situation

A financial data agent tracks 12 metrics per equity: price, marketCap, totalDebt, cashAndEquivalents, earningsPerShare, bookValuePerShare, revenue, netIncome, dividendYield, enterpriseValue, peRatio, priceToBook. Four of these — enterpriseValue, peRatio, priceToBook, profitMargin — are derived from the others. Sources occasionally omit the derived fields even when the component fields are present.

Without a derivation registry: S-137 returns `DATA_UNAVAILABLE` for enterpriseValue if Bloomberg omits it, even though market cap (Refinitiv), debt (Refinitiv), and cash (IEX) are all present. The model context shows a gap; the model may hallucinate the field, skip analysis that depends on it, or produce a weaker recommendation.

With a derivation registry: after S-137 merge, the resolver detects `enterpriseValue: null`, finds the formula, reads `marketCap: 2.87T`, `totalDebt: 124B`, `cashAndEquivalents: 61B` from the merged record, computes `2.87T + 0.124T - 0.061T = 2.933T`. The merged record is updated with `{ enterpriseValue: 2933000000000, _enterpriseValue_derived: true, _enterpriseValue_components: ['marketCap', 'totalDebt', 'cashAndEquivalents'] }`. The model receives a complete record; derivation is transparent in provenance.

## Forces

- **Derived values are second-class to sourced values.** If Bloomberg provides `enterpriseValue` directly, the registry never runs its formula — it only activates on `null` or `undefined`. A direct source value always wins. The registry is a fallback of last resort, not a replacement for sourcing.
- **Formula correctness is a human responsibility, not a runtime check.** The registry stores whatever formula you register. If your EV formula uses total liabilities instead of total debt, the registry computes the wrong number silently. Test formulas on known reference data before registering. Treat formula bugs like schema bugs — they affect every entity silently.
- **Component availability is partial.** A formula has required components and optional components. A partial-computation guard rejects the formula if any required component is `null`. If all required components are present, optional components can default to zero (cash may be zero, not always provided). Make the required/optional split explicit in the formula registry entry.
- **Propagate derivation provenance downstream.** F-110 field lineage uses `_source` and `_excerpt`. Derived fields have neither — they have `_derived: true` and `_components`. The downstream consumer (the model, F-110, F-97) must handle derived provenance differently from sourced provenance. A derived EV is less authoritative than a sourced one: document the component sources, not just the formula.
- **Do not chain derivations.** If `peRatio` depends on `earningsPerShare`, which itself was derived from `netIncome` and `shareCount`, the error propagates: two derivations compound approximation errors. Register only formulas whose inputs are directly sourced fields. If an input would itself need to be derived, mark the outer derivation as NOT_AVAILABLE rather than chaining.
- **Financial formulas require unit alignment.** All component fields must be in the same unit (all in dollars, not some in millions and some in trillions). The formula registry should validate units or require that S-138's normalization has already aligned them before derivation runs.

## The move

**Register field derivation formulas. After S-137 merge, compute missing fields from present components.**

```js
// --- Derived field formula entry ---
// name:          string — the derived field name
// requiredFields: string[] — ALL must be non-null for derivation to proceed
// optionalFields: { [field]: defaultValue } — used if present, defaulted otherwise
// compute:       (components: Record<string, number>) => number | null
// unit:          string — expected unit for all numeric components (documentation only)

// --- Derived field computation registry ---

class DerivedFieldRegistry {
  constructor() {
    this._formulas = new Map();   // fieldName → formula entry
  }

  // Register a derivation formula.
  register(name, entry) {
    this._formulas.set(name, {
      name,
      requiredFields: entry.requiredFields,
      optionalFields: entry.optionalFields ?? {},
      compute:        entry.compute,
      unit:           entry.unit ?? null,
    });
  }

  // Attempt to derive a single missing field from the merged record.
  // Returns { value, derived: true, components, formula } on success,
  //         { value: null, derived: false, reason } on failure.
  resolve(fieldName, mergedRecord) {
    const formula = this._formulas.get(fieldName);
    if (!formula) return { value: null, derived: false, reason: 'NO_FORMULA' };

    // Check required components
    const components = {};
    for (const req of formula.requiredFields) {
      const v = mergedRecord[req];
      if (v === null || v === undefined) {
        return { value: null, derived: false, reason: `MISSING_REQUIRED:${req}` };
      }
      components[req] = v;
    }

    // Populate optional components with defaults
    for (const [opt, defaultVal] of Object.entries(formula.optionalFields)) {
      components[opt] = mergedRecord[opt] ?? defaultVal;
    }

    let value;
    try {
      value = formula.compute(components);
    } catch (err) {
      return { value: null, derived: false, reason: `COMPUTE_ERROR:${err.message}` };
    }

    if (value === null || !isFinite(value)) {
      return { value: null, derived: false, reason: 'NON_FINITE_RESULT' };
    }

    return {
      value,
      derived:    true,
      components: Object.keys(components),
      formula:    formula.name,
    };
  }

  // Apply all registered derivations to a merged record.
  // Fills fields that are null/undefined and have a formula.
  // Returns updated record + derivation log.
  applyAll(mergedRecord) {
    const updated       = { ...mergedRecord };
    const derivationLog = [];

    for (const [fieldName, formula] of this._formulas) {
      const existing = updated[fieldName];
      if (existing !== null && existing !== undefined) continue;   // already present

      const result = this.resolve(fieldName, updated);

      if (result.derived) {
        updated[fieldName]                              = result.value;
        updated[`_${fieldName}_derived`]               = true;
        updated[`_${fieldName}_components`]            = result.components;
        derivationLog.push({
          field:      fieldName,
          value:      result.value,
          components: result.components,
          status:     'DERIVED',
        });
      } else {
        derivationLog.push({
          field:  fieldName,
          status: 'NOT_DERIVED',
          reason: result.reason,
        });
      }
    }

    return { updated, derivationLog };
  }
}

// --- Standard financial field formulas ---
// Register after initializing DerivedFieldRegistry.
// Assumes S-138 has normalized all values to base units (dollars, not millions).

function registerFinancialFormulas(registry) {
  registry.register('enterpriseValue', {
    requiredFields: ['marketCap', 'totalDebt'],
    optionalFields: { cashAndEquivalents: 0 },
    unit:           'USD',
    compute: ({ marketCap, totalDebt, cashAndEquivalents }) =>
      marketCap + totalDebt - cashAndEquivalents,
  });

  registry.register('peRatio', {
    requiredFields: ['price', 'earningsPerShare'],
    unit:           'ratio',
    compute: ({ price, earningsPerShare }) => {
      if (earningsPerShare <= 0) return null;   // negative EPS → pe not meaningful
      return parseFloat((price / earningsPerShare).toFixed(2));
    },
  });

  registry.register('priceToBook', {
    requiredFields: ['price', 'bookValuePerShare'],
    unit:           'ratio',
    compute: ({ price, bookValuePerShare }) => {
      if (bookValuePerShare <= 0) return null;
      return parseFloat((price / bookValuePerShare).toFixed(2));
    },
  });

  registry.register('profitMargin', {
    requiredFields: ['netIncome', 'revenue'],
    unit:           'fraction',
    compute: ({ netIncome, revenue }) => {
      if (revenue <= 0) return null;
      return parseFloat((netIncome / revenue).toFixed(4));
    },
  });
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `resolve()` and `applyAll()` timed over 100 000 iterations on a 12-field merged record with 4 registered derivation formulas.

```
=== DerivedFieldRegistry timing (100 000 iterations) ===

resolve() — formula found, all required present:     0.0006 ms
resolve() — formula found, required missing:         0.0003 ms   (early return)
resolve() — NO_FORMULA (field not registered):       0.0001 ms   (Map.get miss)
resolve() — NON_FINITE_RESULT (div by zero guard):   0.0007 ms
applyAll() — 12-field record, 4 formulas, 2 derived: 0.0041 ms
applyAll() — 12-field record, 4 formulas, 0 derived: 0.0019 ms   (all fields present — no-op)

=== AAPL: S-137 merge result with Bloomberg down ===

S-137 merged record (Bloomberg timeout — 8 fields from Refinitiv/IEX, 4 missing):
  price:                289.50  (Refinitiv)
  marketCap:   2870000000000    (Refinitiv, 2.87T)
  totalDebt:    124000000000    (Refinitiv, 124B)
  cashAndEquivalents: 61000000000 (IEX, 61B)
  earningsPerShare:   6.43       (Refinitiv)
  bookValuePerShare:  3.18       (Refinitiv)
  revenue:     383900000000      (Refinitiv)
  netIncome:    99800000000      (Refinitiv)
  enterpriseValue:   null        ← Bloomberg omitted it
  peRatio:           null        ← Bloomberg omitted it
  priceToBook:       null        ← Bloomberg omitted it
  profitMargin:      null        ← Bloomberg omitted it

applyAll() derivation run:
  enterpriseValue: 2870000000000 + 124000000000 - 61000000000 = 2933000000000
    _enterpriseValue_derived:    true
    _enterpriseValue_components: ['marketCap', 'totalDebt', 'cashAndEquivalents']

  peRatio: 289.50 / 6.43 = 45.02
    _peRatio_derived:    true
    _peRatio_components: ['price', 'earningsPerShare']

  priceToBook: 289.50 / 3.18 = 91.04
    _priceToBook_derived:    true
    _priceToBook_components: ['price', 'bookValuePerShare']

  profitMargin: 99800000000 / 383900000000 = 0.2600
    _profitMargin_derived:    true
    _profitMargin_components: ['netIncome', 'revenue']

derivationLog: 4 × DERIVED

Model receives: complete 12-field record with all derived values present.
F-110 lineage annotation: _source: null → marks as DERIVED, not FABRICATED_EXCERPT.

=== peRatio with negative EPS guard ===

peRatio formula: earningsPerShare <= 0 → return null → NON_FINITE_RESULT
  Amazon Q3 2022 EPS: -0.20 (loss quarter) → peRatio not derived → DATA_UNAVAILABLE
  Model context: "peRatio: DATA_UNAVAILABLE (earnings negative, ratio not meaningful)"
  Correct: negative P/E is meaningless, not a model hallucination risk.

=== S-96 vs S-137 vs S-138 vs S-145 ===

              │ S-96 (fallback chains)          │ S-137 (field-level merge)       │ S-138 (normalization)           │ S-145 (derived field registry)
──────────────┼─────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────┼─────────────────────────────────
Fills gap via │ Different source for same field │ Priority-ordered source list    │ Type coercion + path remapping  │ Formula from component fields
Requires      │ Alternative source available    │ At least one source to respond  │ Source to respond               │ Component fields present in record
Source call   │ Yes — calls fallback source     │ Yes — fans out to all sources   │ Yes — wraps fetch call          │ No — pure computation from record
Provenance    │ _source: fallback_source_id     │ provenance[field].fallback=true │ per-field normalizer log        │ _derived: true, _components: [...]
Cost          │ One additional API call         │ Parallel API calls              │ <0.01ms post-fetch              │ 0.0006ms — zero API cost
When to use   │ Primary source down/slow        │ Multi-source field coverage     │ Field name/type mismatch        │ Primary and all alternatives missing
Composes      │ S-145 if all fallbacks fail too │ S-145 post-merge for null gaps  │ S-145 after normalization       │ After S-137+S-138 pipeline
```

## See also

[S-137](s137-multi-source-field-level-merge.md) · [S-138](s138-source-response-normalization.md) · [S-96](s96-tool-fallback-chains.md) · [F-110](../forward-deployed/f110-structured-output-field-lineage.md) · [S-141](s141-source-schema-contract-versioning.md) · [F-113](../forward-deployed/f113-per-entity-data-completeness-tracking.md)

## Go deeper

Keywords: `derived field computation` · `formula fallback field` · `computed field registry` · `financial field derivation` · `enterprise value computation` · `missing field derivation` · `field formula fallback` · `derived field provenance` · `component field computation` · `fallback field formula`
