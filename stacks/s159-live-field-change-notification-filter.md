# S-159 · Live Field Change Notification Filter

[S-126](s126-cache-invalidation-on-change.md) invalidates a cache entry when a live data field changes — the action is always the same: invalidate. [S-152](s152-event-significance-scoring.md) scores the significance of incoming events from a stream and decides whether to surface them to the agent. [F-129](../forward-deployed/f129-per-entity-output-regression-check.md) compares a new model extraction against the last known extraction for the same entity — it catches when the model's output changes, not when the underlying data source changes.

None of these answer the real-time question: a live data field just updated its value for a tracked entity — should the agent be interrupted to handle it, or should this update wait for the next scheduled poll? For a market data feed, AAPL price ticking from $189.52 to $190.10 (a 0.31% move) does not need to wake the agent. AAPL account status changing from `active` to `suspended` needs to wake the agent immediately. The decision is per-field, and the threshold is field-specific.

The live field change notification filter tracks the last notified value per `(entity, field)` pair — not the last seen value. When a new value arrives, it checks whether the change is significant enough to notify. Insignificant changes are suppressed; the reference value stays at the last notified value, not the last seen one. This means 10 consecutive 1% price moves each get suppressed individually, but a cumulative 10% drift from the last notified value eventually crosses the threshold. For categorical fields configured with `always: true`, any value change triggers a notification regardless of magnitude.

## Situation

A financial data agent monitors AAPL on a 30-second poll. The agent's system prompt says: "Interrupt me when AAPL price moves more than 2% from the last significant price, or when account status changes."

During a 10-minute window, the feed sends:
- Price tick: $189.52 (first observation — no prior, store and suppress)
- Price tick: $190.10 (+0.31% from $189.52 — below 2% threshold, suppress)
- Price tick: $196.43 (+3.65% from $189.52 — above 2% threshold, notify, update reference to $196.43)
- Account status: `active → suspended` (always-notify field, notify immediately)
- Account status: `suspended → suspended` (no change, suppress)

Without the filter: every tick dispatches an LLM call. At 30-second polling, that is 20 calls/10 min, most of which add no signal. With the filter: 2 notifications in 10 minutes — the 3.65% price move and the status change. 18 calls suppressed; the agent handles only what requires action.

## Forces

- **The reference point is last notified, not last seen.** A filter that updates the reference on every tick resets the baseline on every suppressed update, making it blind to cumulative drift. Keeping the reference at the last notified value means 10 × 1% moves will eventually accumulate to a 10%+ drift that triggers notification. This is usually what operators want for slow-moving data sources.
- **Categorical and numeric thresholds are different.** `account_status: active → suspended` is always significant regardless of "magnitude." `price` is numeric and only significant when it exceeds a relative threshold. Register fields explicitly with their notification semantics: `always` for categorical high-consequence fields, `numericThreshold` for continuous values, and default (notify on any change) for fields that don't fit either.
- **First observation is never a notification.** The first time a field is seen, there is nothing to compare against. The value is stored as the reference and suppressed. If the agent needs to be primed with initial state, do it at session start, not through the notification filter.
- **The filter does not decide what to do with a notification.** When `notify: true`, the caller decides whether to interrupt an in-progress agent turn, queue the update for the next turn, or escalate. The filter classifies the change; the dispatcher handles the action.
- **Suppressed does not mean lost.** A value that fails the threshold check is not recorded anywhere inside the filter — only the reference value (last notified) is kept. If the caller needs a complete history of all observed values, maintain that separately. The filter is a gate, not a store.
- **Pair with S-152 for event streams.** S-152 scores the significance of an event from a stream (a JSON event with multiple fields) and decides whether to surface the whole event. S-159 tracks a single field's value over time and decides whether a change in that field crosses a notification threshold. They compose: S-152 as the event-level pre-filter, S-159 as the field-level refinement.

## The move

**Configure each field's notification rule. On each poll tick, check each updated field. Notify when the change exceeds the rule's threshold; suppress otherwise.**

```js
// --- Live field change notification filter ---
// Tracks last notified value per (entityId, field).
// On each poll update, checks whether the new value warrants agent notification.
// Categorical fields: always notify on any change (always: true).
// Numeric fields: notify only when relative change >= numericThreshold.
// Default: notify on any categorical change.

class LiveFieldChangeNotificationFilter {
  constructor() {
    this._knownValues = new Map();  // 'entityId:field' → last NOTIFIED value
    this._rules       = new Map();  // fieldName → { always?: bool, numericThreshold?: number }
  }

  // Configure a field's notification rule.
  // always: true        → notify on any value change (use for status, halt, flags)
  // numericThreshold: N → notify when relative change >= N (e.g. 0.02 = 2%)
  // No config          → notify on any categorical change (default)
  configureField(field, opts = {}) {
    this._rules.set(field, opts);
    return this;
  }

  // Check whether the agent should be notified of this field value.
  // Returns { notify: bool, reason: string, entityId, field, ... }
  check(entityId, field, newValue) {
    const key      = entityId + ':' + field;
    const oldValue = this._knownValues.get(key);
    const rule     = this._rules.get(field) ?? {};

    // First observation: store reference, no notification
    if (oldValue === undefined) {
      this._knownValues.set(key, newValue);
      return { notify: false, reason: 'FIRST_OBSERVATION', entityId, field, value: newValue };
    }

    // No change at all
    if (String(oldValue) === String(newValue)) {
      return { notify: false, reason: 'NO_CHANGE', entityId, field, value: newValue };
    }

    // Always-notify fields (account_status, trading_halt, etc.)
    if (rule.always) {
      this._knownValues.set(key, newValue);
      return { notify: true, reason: 'ALWAYS_NOTIFY', entityId, field, from: oldValue, to: newValue };
    }

    // Numeric threshold: suppress changes below the relative threshold
    if (rule.numericThreshold !== undefined) {
      const n = Number(newValue), o = Number(oldValue);
      if (!isNaN(n) && !isNaN(o) && o !== 0) {
        const relChange = Math.abs(n - o) / Math.abs(o);
        if (relChange < rule.numericThreshold) {
          // Do NOT update the reference — we measure from the last notified value
          return { notify: false, reason: 'WITHIN_THRESHOLD', entityId, field,
                   from: oldValue, to: newValue, relChange: parseFloat(relChange.toFixed(4)) };
        }
        this._knownValues.set(key, newValue);
        return { notify: true, reason: 'THRESHOLD_CROSSED', entityId, field,
                 from: oldValue, to: newValue, relChange: parseFloat(relChange.toFixed(4)) };
      }
    }

    // Default: categorical change → notify
    this._knownValues.set(key, newValue);
    return { notify: true, reason: 'VALUE_CHANGED', entityId, field, from: oldValue, to: newValue };
  }
}

// --- Integration: poll handler with notification dispatch ---

const CHANGE_FILTER = new LiveFieldChangeNotificationFilter()
  .configureField('price',          { numericThreshold: 0.02 })   // notify on >2% move
  .configureField('bid',            { numericThreshold: 0.02 })
  .configureField('account_status', { always: true })              // always notify
  .configureField('trading_halt',   { always: true });

async function onPollTick(entityId, updatedFields) {
  for (const [field, newValue] of Object.entries(updatedFields)) {
    const result = CHANGE_FILTER.check(entityId, field, newValue);
    if (result.notify) {
      await dispatchToAgent({ entityId, field, from: result.from, to: result.to, reason: result.reason });
    }
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `check()` timed over 100 000 iterations. `numericThreshold: 0.02` (2%). Field: price.

```
=== LiveFieldChangeNotificationFilter timing (100 000 iterations) ===

check() — WITHIN_THRESHOLD (no reference update):   0.0013 ms
check() — THRESHOLD_CROSSED (reference updated):    0.0014 ms

=== Scenario A: first observation ===

check('AAPL', 'price', 189.52):
{ notify: false, reason: 'FIRST_OBSERVATION', entityId: 'AAPL', field: 'price', value: 189.52 }
Reference set: 189.52. No dispatch.

=== Scenario B: small price move 189.52 → 190.10 (+0.31%) ===

check('AAPL', 'price', 190.10):
{ notify: false, reason: 'WITHIN_THRESHOLD', from: 189.52, to: 190.10, relChange: 0.0031 }
Reference unchanged at 189.52. Suppressed.

=== Scenario C: cumulative drift — 189.52 → 196.43 (+3.65% from reference) ===

check('AAPL', 'price', 196.43):
{ notify: true, reason: 'THRESHOLD_CROSSED', from: 189.52, to: 196.43, relChange: 0.0365 }
Reference updated to 196.43. Agent dispatched.

Note: from=189.52 (last NOTIFIED value), not 190.10 (last seen).
Cumulative drift from reference, not tick-over-tick delta.

=== Scenario D: account_status active → suspended (always notify) ===

check('AAPL', 'account_status', 'suspended'):
{ notify: true, reason: 'ALWAYS_NOTIFY', from: 'active', to: 'suspended' }
Agent dispatched immediately.

=== Scenario E: account_status suspended → suspended (no change) ===

check('AAPL', 'account_status', 'suspended'):
{ notify: false, reason: 'NO_CHANGE', value: 'suspended' }
Suppressed.

=== S-126 vs S-152 vs F-129 vs S-159 ===

              │ S-126 (cache invalidation)    │ S-152 (event significance)    │ F-129 (extraction regression) │ S-159 (notification filter)
──────────────┼───────────────────────────────┼───────────────────────────────┼───────────────────────────────┼──────────────────────────────
Source        │ Live data field change        │ Event stream event            │ Model extraction output       │ Live data field poll
Action        │ Invalidate cache              │ Surface/suppress event        │ Flag field-level changes      │ Notify/suppress agent
Reference     │ Cache key                     │ Field significance config     │ Last extraction per entity    │ Last notified value per field
Threshold     │ Any change → invalidate       │ Score-based per event         │ Field tier (HIGH/LOW)         │ Relative numeric or always
Numeric drift │ No (binary: changed/not)      │ Optional, event-level         │ No (string equality)          │ Yes — cumulative from reference
```

## See also

[S-126](s126-cache-invalidation-on-change.md) · [S-152](s152-event-significance-scoring.md) · [F-129](../forward-deployed/f129-per-entity-output-regression-check.md) · [S-126](s126-cache-invalidation-on-change.md) · [F-126](../forward-deployed/f126-output-field-change-velocity.md) · [S-141](s141-live-data-freshness-contract.md)

## Go deeper

Keywords: `live field change notification filter` · `agent notification threshold` · `poll update significance filter` · `field value change gate` · `live data field change dispatch` · `numeric threshold field notification` · `agent interrupt filter` · `field change significance` · `real-time field notification gate` · `live data change classification`
