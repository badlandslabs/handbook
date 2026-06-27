# S-162 · Tool Result Field Projector

[S-130](s130-structured-tool-result-compression.md) compresses tool results structurally — pruning null fields, sampling long arrays, truncating strings — without knowing which fields are semantically needed for the current query. [S-97](s97-tool-result-summarization.md) uses an LLM to summarize large tool results into a concise description, consuming tokens to save tokens. [S-84](s84-tool-return-value-design.md) governs what a tool should return at design time.

None of these exploit a simpler opportunity: when you know the query type being handled, you know exactly which fields from each tool result are needed — and can drop the rest before injection. A billing query against `get_customer` needs `customer_id`, `plan_tier`, and `account_status`. A risk query needs `risk_tier`, `jurisdiction`, and `kyc_status`. Neither needs billing history, usage logs, preferences, contacts, notes, integrations, or the 15 other fields a typical CRM response returns.

Tool result field projection applies a per-query-type whitelist at zero LLM cost. If the projector has a rule for the tool + query type, it keeps only the registered fields and drops the rest. If no rule is registered, it passes the result through unmodified. The caller keeps the same tool interface; the projection is invisible to both the model and the tool.

## Situation

A customer support agent handles two query types: `billing` (account status, plan, upcoming charges) and `risk` (KYC status, jurisdiction, risk tier). Both types call `get_customer`. The CRM returns a 25-field record: billing history, usage logs, preferences, contacts, notes, integrations, SSO configuration, and more. Most of these fields are irrelevant to the current query and are never read by the model.

Without projection: all 25 fields are injected into context on every call. At approximately 5 tokens per field, the tool result injects ~125 tokens beyond what the model needs. In a session with 4 tool calls across 6 turns, the injected context carries these unused fields for the lifetime of the conversation. At 10 000 sessions per day, the wasted input token volume is 4.2M tokens — $3.36/day at Haiku input pricing, purely from fields the model never touches.

With projection: the billing query sees 4 fields (105 unused tokens dropped); the risk query sees 5 fields (100 unused tokens dropped). The context is accurate and minimal from the first injection. At 10 000 sessions/day: 4.2M fewer input tokens, no LLM call required.

## Forces

- **Query type is already known before the tool call.** F-130 routes the model tier per turn. The router's output — or the intent classification that drives it — already encodes the query type. Pass that value to the projector; do not re-derive it.
- **Field projection is not the same as structural compression.** S-130 prunes nulls, samples arrays, and truncates strings — generic transformations that apply to any field. Field projection discards entire fields based on semantic relevance to the query. Both are useful; run projection first (discard irrelevant fields entirely), then structural compression on what remains.
- **No rule → passthrough, not failure.** Not every tool has projection rules registered, and not every query type is covered. When the projector has no matching rule, return the full result unmodified. Unknown query types should not break the pipeline.
- **Register rules from your domain, not from defaults.** Which fields a risk query needs is a business decision, not a framework decision. The projector is a registry; you fill it. Start by logging which fields the model actually uses in its responses (field lineage, F-110) and discard the rest.
- **`*` wildcard for tools with stable field needs.** If `get_order` always needs the same 3 fields regardless of query type, register against `*` rather than per-type. The projector checks the specific query type first, then falls back to the wildcard.
- **Token savings compound over context length.** Dropped fields are gone for the entire conversation, not just the turn they were dropped on. If `billing_history` is a 2-element array that would have been carried as 40 tokens for 6 turns, the savings are 240 tokens — not 40.

## The move

**Register per-query-type field whitelists. Project each tool result before injection. No LLM cost; no tool interface changes.**

```js
// --- Tool result field projector ---
// Keeps only registered fields from a tool result for the current query type.
// Saves input tokens at zero LLM cost when query type is known before tool calls.
// Composites with S-130 structural compression: run projection first, then compression.
// Register: (toolName, fields[], queryType?) → set a whitelist for a query type.
// Project:  (toolName, result, queryType?) → { projected, keptCount, droppedCount, droppedFields }
// No rule registered → passthrough (keptCount = all fields, droppedCount = 0).

class ToolResultProjector {
  constructor() {
    this._projections = new Map();  // 'toolName:queryType' → Set<fieldName>
  }

  // Register the fields to keep for toolName when handling queryType.
  // queryType defaults to '*' (wildcard — applies to all query types with no specific rule).
  register(toolName, fields, queryType) {
    queryType = queryType || '*';
    this._projections.set(toolName + ':' + queryType, new Set(fields));
    return this;
  }

  // Project a tool result to only the registered fields.
  // queryType: the current query type (e.g. 'billing', 'risk'). Defaults to '*'.
  // Checks specific queryType first; falls back to wildcard rule.
  // Returns { projected, keptCount, droppedCount, droppedFields }
  project(toolName, result, queryType) {
    queryType = queryType || '*';
    const specific = this._projections.get(toolName + ':' + queryType);
    const wildcard = this._projections.get(toolName + ':*');
    const fields   = specific != null ? specific : wildcard;

    if (!fields) {
      const all = Object.keys(result);
      return { projected: result, keptCount: all.length, droppedCount: 0, droppedFields: [] };
    }

    const projected     = {};
    const droppedFields = [];
    for (const k of Object.keys(result)) {
      if (fields.has(k)) projected[k] = result[k];
      else droppedFields.push(k);
    }
    const keptCount = Object.keys(projected).length;
    return { projected, keptCount, droppedCount: droppedFields.length, droppedFields };
  }
}

// --- Configuration: field whitelists per tool per query type ---

const PROJECTOR = new ToolResultProjector()
  .register('get_customer', ['customer_id', 'name', 'plan_tier', 'account_status'],
            'billing')
  .register('get_customer', ['customer_id', 'name', 'risk_tier', 'jurisdiction', 'kyc_status'],
            'risk')
  .register('get_order',    ['order_id', 'status', 'total', 'created_at'],
            '*');  // same fields for all query types on get_order

// --- Integration: project before injection into agent context ---

async function executeToolCall(toolName, toolArgs, queryType) {
  const rawResult = await dispatchTool(toolName, toolArgs);

  // Project to only the fields needed for this query type
  const { projected, keptCount, droppedCount } = PROJECTOR.project(toolName, rawResult, queryType);

  if (droppedCount > 0) {
    log({ tool: toolName, queryType, keptCount, droppedCount, tokensSaved: droppedCount * 5 });
  }

  return projected;  // inject this into agent context, not rawResult
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `project()` timed over 100 000 iterations on a 25-field CRM record. Two query types registered for `get_customer`; wildcard rule registered for `get_order`.

```
=== ToolResultProjector timing (100 000 iterations) ===
Input: 25-field CRM record from get_customer

project() billing (4 fields kept, 21 dropped):   0.0038 ms
project() risk    (5 fields kept, 20 dropped):   0.0036 ms
project() no rule (25 fields kept, passthrough): 0.0008 ms

=== Scenario A: billing query ===

PROJECTOR.project('get_customer', crmRecord, 'billing'):
{
  projected:    { customer_id: 'C-1001', name: 'Acme Corp', plan_tier: 'enterprise', account_status: 'active' },
  keptCount:    4,
  droppedCount: 21,
  droppedFields: ['risk_tier', 'jurisdiction', 'kyc_status', 'billing_history', 'usage_last_30d', ... +16 more]
}

=== Scenario B: risk query ===

PROJECTOR.project('get_customer', crmRecord, 'risk'):
{
  projected:    { customer_id: 'C-1001', name: 'Acme Corp', risk_tier: 'low', jurisdiction: 'US', kyc_status: 'verified' },
  keptCount:    5,
  droppedCount: 20
}

=== Token savings (approx 5 tok/field, Haiku $0.80/M input) ===

billing: 25 → 4 fields, saved ~105 tok/call
risk:    25 → 5 fields, saved ~100 tok/call

At 10 000 sessions/day × 4 tool calls/session:
  billing: ~4.2M tok/day saved → $3.36/day
  zero LLM cost to achieve this

=== Comparison: projection vs compression ===

                 │ S-130 (structural compression)    │ S-162 (field projection)
─────────────────┼───────────────────────────────────┼───────────────────────────────────
Query awareness  │ None — structural rules only       │ Yes — whitelist per query type
Fields dropped   │ Null fields, long strings (trunc.) │ Any non-whitelisted field entirely
Arrays           │ Sampled (first N + count)          │ Dropped if not whitelisted
LLM cost         │ Zero                               │ Zero
Config           │ Generic (nulls, thresholds)        │ Domain-specific (per tool/query)
Compose          │ After projection                   │ First — discard irrelevant fields
```

## See also

[S-130](s130-structured-tool-result-compression.md) · [S-97](s97-tool-result-summarization.md) · [S-84](s84-tool-return-value-design.md) · [F-130](../forward-deployed/f130-per-turn-model-router.md) · [F-110](../forward-deployed/f110-structured-output-field-lineage.md) · [S-153](s153-tool-result-novelty-filter.md)

## Go deeper

Keywords: `tool result field projection` · `per-query-type field whitelist` · `agent context token reduction` · `tool result field selection` · `query-aware result filtering` · `tool output field pruning` · `context injection optimization` · `tool result field whitelist` · `semantic field projection` · `agent tool result trimming`
