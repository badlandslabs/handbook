# S-161 · Entity Change Aggregator

[S-159](s159-live-field-change-notification-filter.md) decides, per field per entity, whether a value change warrants agent notification — it fires separately for each field that crosses its threshold. [S-144](s144-live-data-burst-event-coalescing.md) coalesces bursts of ticks for a single entity within a time window (40 ticks in 800ms → 1 call) using a debounce-plus-maxWait strategy. [S-104](s104-event-stream-agent-integration.md) maintains a per-entity circular event buffer and applies a significance filter before dispatching to the LLM.

None of these answer the question: when multiple fields change for the same entity in a single poll cycle, how do you produce one combined notification instead of N separate dispatches? S-159 fires once for `price` and again for `account_status` — both for AAPL, in the same tick. Without aggregation, that is two separate LLM calls for one entity. The agent sees two separate contexts, may produce inconsistent responses (one about the price move, one about the status change), and pays twice for the same entity update.

The entity change aggregator collects per-field change notifications within a poll cycle, groups them by entity, and flushes one compound notification per entity at the end of the cycle. The agent handles one context per entity per cycle, containing all changed fields and their before/after values, regardless of how many fields triggered.

## Situation

A financial monitoring agent watches 50 tickers across 30-second poll cycles. During a market open, AAPL experiences three simultaneous field changes on the same tick: `price` crosses the 2% threshold (THRESHOLD_CROSSED), `account_status` changes from `active` to `suspended` (ALWAYS_NOTIFY), and `bid` crosses the 2% threshold (THRESHOLD_CROSSED).

Without aggregation:
- S-159 fires 3 separate notifications for AAPL.
- 3 LLM dispatches, each with a narrow context about one field change.
- The agent writes "AAPL price moved" → "AAPL account suspended" → "AAPL bid moved" in three separate responses.
- No single response synthesizes the full picture: AAPL's account was suspended AND the price gapped, which suggests the suspension may be the cause of the price move.

With aggregation:
- All 3 notifications are collected during the poll cycle.
- `flush()` returns 1 entity notification: AAPL with 3 changed fields.
- 1 LLM dispatch with the full change context: `{ price: 189.52→196.43, account_status: active→suspended, bid: 189.40→196.20 }`.
- The agent synthesizes: "AAPL suspended at market open — price and bid both gapped +3.6% on the news."

LLM dispatch count: 3 → 1. The full picture is visible in one context.

## Forces

- **Aggregation happens after per-field filtering.** S-159 (or equivalent field-change logic) runs first and decides which fields are significant enough to notify. The aggregator only collects the approved notifications — it does not re-evaluate significance. The filtering and aggregation roles are separate; swapping their order would mean aggregating all field values (including unchanged ones) and then filtering, which wastes allocation on suppressed fields.
- **One flush per poll cycle.** The aggregator is not a persistent store — it holds state only for the duration of one poll cycle. Call `flush()` once at the end of each cycle and dispatch the results. Do not accumulate across cycles. If you accumulate across cycles, a second poll where no fields change still carries stale change records from the previous cycle.
- **Flush is destructive.** `flush()` clears all pending state. If the dispatch to the LLM fails after `flush()`, the change records are gone. For durable delivery requirements, record the notification before flushing, or use a dead-letter queue on dispatch failure.
- **Aggregation does not change the per-field decision — only the dispatch timing.** Whether `price` warrants notification is still decided by S-159's threshold. The aggregator does not introduce a second significance gate. The only thing it changes is: instead of dispatching immediately on each field's notification, all notifications for an entity are batched to the end of the cycle.
- **Entity with many changed fields should not be further coalesced.** S-144 coalesces a burst of ticks (time-based). The aggregator coalesces multiple field changes within one tick (field-based). These address different problems and compose cleanly: S-144 reduces tick count before S-159 evaluates, then S-159 evaluates significance, then the aggregator batches the survivors.
- **The compound notification context is richer than any individual field.** The agent can reason about the relationship between multiple field changes when they appear together. `price: +3.6%` alone is a price alert. `price: +3.6%, account_status: suspended` together suggest a causally linked event. Do not split what happened to one entity across multiple calls.

## The move

**Within each poll cycle, collect all per-field change notifications. At the end of the cycle, flush one compound notification per entity and dispatch each to the agent.**

```js
// --- Entity change aggregator ---
// Collects per-field change notifications (from S-159 or equivalent) within one poll cycle.
// Groups changes by entity. flush() returns one compound notification per entity.
// Call flush() exactly once per poll cycle, after all field checks are complete.

class EntityChangeAggregator {
  constructor() {
    this._pending = new Map();  // entityId → [{field, from, to, reason}]
  }

  // Register a per-field change notification for an entity.
  // Call when S-159.check() returns notify: true.
  // reason: the S-159 reason (THRESHOLD_CROSSED, ALWAYS_NOTIFY, VALUE_CHANGED)
  add(entityId, field, from, to, reason = 'VALUE_CHANGED') {
    if (!this._pending.has(entityId)) this._pending.set(entityId, []);
    this._pending.get(entityId).push({ field, from, to, reason });
    return this;
  }

  // Number of entities with pending changes (not yet dispatched).
  pendingCount() { return this._pending.size; }

  // Flush: return one notification per entity with all changed fields.
  // Clears all pending state. Call exactly once per poll cycle.
  // Returns [{entityId, changeCount, changedFields: [{field, from, to, reason}]}]
  flush() {
    const notifications = [];
    for (const [entityId, changes] of this._pending) {
      notifications.push({
        entityId,
        changeCount:   changes.length,
        changedFields: changes,
      });
    }
    this._pending.clear();
    return notifications;
  }
}

// --- Integration: S-159 filter → aggregator → single dispatch per entity ---

const CHANGE_FILTER  = new LiveFieldChangeNotificationFilter()  // S-159
  .configureField('price',          { numericThreshold: 0.02 })
  .configureField('account_status', { always: true })
  .configureField('bid',            { numericThreshold: 0.02 })
  .configureField('trading_halt',   { always: true });

async function onPollCycle(polledData) {
  // polledData: Map<entityId, {field: value, ...}>
  const aggregator = new EntityChangeAggregator();

  for (const [entityId, fields] of polledData) {
    for (const [field, newValue] of Object.entries(fields)) {
      const result = CHANGE_FILTER.check(entityId, field, newValue);
      if (result.notify) {
        aggregator.add(entityId, field, result.from, result.to, result.reason);
      }
    }
  }

  const notifications = aggregator.flush();

  // One LLM dispatch per entity, not per field
  for (const notification of notifications) {
    await dispatchToAgent(notification);
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `add()` timed over 100 000 iterations (first change per entity). `flush()` timed over 100 000 iterations with 5 entities and 6 total changes.

```
=== EntityChangeAggregator timing (100 000 iterations) ===

add() — first change for entity:                0.0004 ms
flush() — 5 entities, 6 total changes:          0.0009 ms

=== Scenario A: 3 fields changed for AAPL in one poll tick ===

add('AAPL', 'price', 189.52, 196.43, 'THRESHOLD_CROSSED')
add('AAPL', 'account_status', 'active', 'suspended', 'ALWAYS_NOTIFY')
add('AAPL', 'bid', 189.40, 196.20, 'THRESHOLD_CROSSED')

pendingCount: 1   ← one entity with pending changes

flush():
[{
  entityId:      'AAPL',
  changeCount:   3,
  changedFields: [
    { field: 'price',          from: 189.52, to: 196.43, reason: 'THRESHOLD_CROSSED' },
    { field: 'account_status', from: 'active', to: 'suspended', reason: 'ALWAYS_NOTIFY' },
    { field: 'bid',            from: 189.40, to: 196.20, reason: 'THRESHOLD_CROSSED' }
  ]
}]

pendingCount after flush: 0

LLM dispatches: 1 (vs 3 without aggregator).
Context: full picture of AAPL's tick — price gapped and account suspended together.

=== Scenario B: 3 entities, each with 1 field change ===

AAPL: price THRESHOLD_CROSSED
MSFT: price THRESHOLD_CROSSED
GOOG: trading_halt VALUE_CHANGED
AMZN: price unchanged at +0.3% — S-159 WITHIN_THRESHOLD, not added

flush() → 3 notifications (one per entity).
LLM dispatches: 3 (same count as without aggregator, but each dispatch has entity context)

=== S-144 vs S-159 vs S-161 ===

              │ S-144 (burst coalescing)         │ S-159 (per-field filter)         │ S-161 (change aggregator)
──────────────┼──────────────────────────────────┼──────────────────────────────────┼──────────────────────────────
Scope         │ Many ticks, one entity, one field│ One tick, one entity, one field  │ One tick, one entity, all fields
Input         │ Stream of ticks                  │ (entityId, field, value)         │ S-159 notify: true results
Output        │ One coalesced value              │ notify: bool + reason            │ One compound notification/entity
Reduces       │ Tick count → LLM call count      │ Tick significance → dispatches   │ Per-field dispatches → per-entity
Compose       │ Before S-159                     │ After S-144                      │ After S-159
```

## See also

[S-159](s159-live-field-change-notification-filter.md) · [S-144](s144-live-data-burst-event-coalescing.md) · [S-104](s104-event-stream-agent-integration.md) · [S-136](s136-adaptive-per-entity-poll-rate.md) · [F-98](../forward-deployed/f98-live-source-fan-out.md) · [S-42](s42-event-driven-agents.md)

## Go deeper

Keywords: `entity change aggregator` · `per-entity change notification batching` · `field change grouping` · `compound entity notification` · `poll cycle change aggregation` · `multi-field entity notification` · `live data field change batching` · `entity change batch dispatch` · `grouped field change notification` · `poll cycle notification aggregation`
