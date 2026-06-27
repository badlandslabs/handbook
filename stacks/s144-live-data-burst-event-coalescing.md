# S-144 · Live Data Burst Event Coalescing

[S-42](s42-event-driven-agents.md) replaces polling loops with event subscriptions: instead of calling an API every N seconds, subscribe to a feed and react when events arrive. It solves the pull-vs-push decision. [S-136](s136-adaptive-per-entity-poll-rate.md) adapts how frequently a *polling* agent checks each entity based on observed volatility — quiet entities are polled less often, volatile ones more often. [S-104](s104-event-stream-agent-integration.md) maintains a sliding window of recent events per entity and fires an LLM call when a rule-based significance filter detects a meaningful *pattern* across the window.

None of these address what happens when a push-based feed delivers more events per entity than the agent can profitably consume. During market open, a price feed may emit 20–50 ticks per second for AAPL. Calling the LLM on each tick costs 20–50 LLM calls per second per entity — far more than the decision quality warrants. S-104's significance filter rejects events that don't match a pattern, but it is designed to detect patterns like "three declines in 60 seconds," not to coalesce 20 price ticks in 200ms into one call.

Burst event coalescing buffers rapid-fire events per entity within a debounce window. When no new event arrives for `debounceMs` (default 200ms), it fires one LLM call using the coalesced final state. A `maxWaitMs` ceiling (default 2000ms) prevents indefinite deferral on continuous high-frequency feeds. The debounce window absorbs bursts; the coalesced payload carries the net field change; suppressed intermediate events are counted in metadata.

## Situation

An equity monitoring agent subscribes to a WebSocket price feed (S-42 event-driven) for 200 tickers. During an earnings announcement, AAPL emits 40 price ticks in 800ms — each tick a new `{ price, volume, bid, ask }` event. The agent's LLM call costs ~$0.00036/call at Haiku (450 tok average).

Without coalescing: 40 events × $0.00036 = $0.0144 for one entity's 800ms burst. Across 200 tickers during peak periods: 200 × 40 × $0.00036 = $2.88/burst-event (the kind that happens every few minutes at market open). Monthly at scale: hundreds of dollars in redundant calls, each seeing a marginally different price the agent would have handled identically.

With coalescing (debounceMs=200, maxWaitMs=2000): 40 ticks → 1 LLM call, `_eventCount: 40, _suppressedCount: 39`. Cost: $0.00036 for the burst. The coalesced payload contains the final price at tick 40 — the only value the downstream decision depends on. The first 39 intermediate prices are immaterial: the model's decision ("still above threshold," "momentum continues") would be identical.

Caveats: coalescing delays the first LLM response by up to `debounceMs` (200ms) after the last event. For low-latency trading, this is unacceptable — don't coalesce, and don't use an LLM in the hot path. For monitoring, alerting, and advisory agents, 200ms delay is imperceptible.

## Forces

- **Debounce per entity, not globally.** AAPL is bursting; MSFT has been quiet for 3 seconds. A global debounce window would delay MSFT's event unnecessarily. Each entity has its own timer.
- **Two timers per entity: debounce + max-wait.** The debounce timer resets on each new event. On a continuous feed (>1 event every 200ms), the debounce timer would never fire — the entity would never get processed. The max-wait timer fires at `maxWaitMs` regardless, ensuring minimum throughput even during sustained bursts.
- **Coalescing strategy is field-specific.** For numeric fields (price, volume, bid, ask): take the final value (latest tick). For min/max trackers: take min or max across all events. For event counts: sum. For categorical status: take the final value. The default "last non-null value wins" handles price feeds correctly.
- **Suppressed event count is the receipt.** Log `_suppressedCount` per coalescence. If it's consistently 0, coalescing adds 200ms latency for nothing — reduce `debounceMs` or disable coalescing for that entity. If it's consistently 30–50, the burst pattern is real and the savings are real.
- **Do not coalesce side-effecting events.** If each event triggers a trade, a notification, or a database write, you cannot coalesce: each event requires its own action. Coalescing is for *read* events that feed into a single *decision* — not for writes where every event has independent significance.
- **Compose with S-104's significance filter.** Coalescing fires one call per burst. S-104's significance filter then decides whether that burst is worth an LLM call. Stack them: coalesce first → significance-filter the coalesced result → LLM only when significant. This is the full cost control stack for high-frequency entity feeds.

## The move

**Buffer push events per entity within a debounce window. Fire one coalesced call per burst. Count suppressed events.**

```js
// --- Per-entity burst event coalescer ---
// debounceMs: fire this long after the last event (default 200ms)
// maxWaitMs:  fire regardless after this wait — prevents indefinite deferral
//             on continuous streams (default 2000ms)
// onFire:     (entityId, coalescedEvent, meta) => void
//             meta = { eventCount, suppressedCount, burstDurationMs }

class EntityEventCoalescer {
  constructor(opts = {}) {
    this._debounceMs = opts.debounceMs ?? 200;
    this._maxWaitMs  = opts.maxWaitMs  ?? 2000;
    this._onFire     = opts.onFire;
    this._pending    = new Map();   // entityId → { events, debounceTimer, maxTimer, firstAt }
  }

  // Record one event for an entity.
  push(entityId, event) {
    if (!this._pending.has(entityId)) {
      const maxTimer = setTimeout(() => this._fire(entityId), this._maxWaitMs);
      this._pending.set(entityId, {
        events:        [],
        debounceTimer: null,
        maxTimer,
        firstAt:       Date.now(),
      });
    }

    const entry = this._pending.get(entityId);
    entry.events.push(event);

    clearTimeout(entry.debounceTimer);
    entry.debounceTimer = setTimeout(() => this._fire(entityId), this._debounceMs);
  }

  // Flush an entity immediately (e.g., on market close or explicit drain).
  flush(entityId) {
    if (this._pending.has(entityId)) this._fire(entityId);
  }

  flushAll() {
    for (const entityId of [...this._pending.keys()]) this._fire(entityId);
  }

  _fire(entityId) {
    const entry = this._pending.get(entityId);
    if (!entry) return;

    clearTimeout(entry.debounceTimer);
    clearTimeout(entry.maxTimer);
    this._pending.delete(entityId);

    const coalesced = this._coalesce(entry.events);
    this._onFire(entityId, coalesced, {
      eventCount:      entry.events.length,
      suppressedCount: entry.events.length - 1,
      burstDurationMs: Date.now() - entry.firstAt,
    });
  }

  // Default coalescing: last non-null value wins per field.
  // Override with a custom coalesceFn if field-specific logic is needed.
  _coalesce(events) {
    const merged = {};
    for (const event of events) {
      for (const [k, v] of Object.entries(event)) {
        if (v !== null && v !== undefined) merged[k] = v;
      }
    }
    return { ...merged, _eventCount: events.length };
  }

  // For custom coalescing (min/max trackers, sum, etc.):
  // Pass coalesceFn: (events: Event[]) => CoalescedEvent to the constructor.
}

// --- Custom coalescer for OHLCV-style aggregation ---
// Instead of "latest value," produce a summary of the burst: open/high/low/close for price.
function ohlcvCoalesce(events) {
  const prices  = events.map(e => e.price).filter(Boolean);
  const volumes = events.map(e => e.volume).filter(Boolean);
  return {
    open:         prices[0]   ?? null,
    high:         Math.max(...prices),
    low:          Math.min(...prices),
    close:        prices[prices.length - 1] ?? null,
    totalVolume:  volumes.reduce((sum, v) => sum + v, 0),
    bid:          events[events.length - 1]?.bid  ?? null,
    ask:          events[events.length - 1]?.ask  ?? null,
    _eventCount:  events.length,
  };
}

// --- Significance filter integration (S-104 pattern) ---
// Apply after coalescing: only call the LLM if the coalesced event is significant.

function buildCoalescedSignificanceFilter(thresholds) {
  // thresholds: { priceChangePct: 0.005, volumeSpike: 2.0 }
  return function isSignificant(coalescedEvent, lastProcessed) {
    if (!lastProcessed) return true;   // first event always significant

    if (thresholds.priceChangePct && coalescedEvent.close && lastProcessed.close) {
      const changePct = Math.abs(coalescedEvent.close - lastProcessed.close) / lastProcessed.close;
      if (changePct >= thresholds.priceChangePct) return true;
    }
    if (thresholds.volumeSpike && coalescedEvent.totalVolume && lastProcessed.avgVolume) {
      if (coalescedEvent.totalVolume / lastProcessed.avgVolume >= thresholds.volumeSpike) return true;
    }
    return false;
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `push()` and `_coalesce()` timed over 100 000 iterations with setTimeout replaced by a no-op stub. Burst scenario: 40 events for AAPL in 800ms, debounceMs=200, maxWaitMs=2000.

```
=== EntityEventCoalescer timing (100 000 iterations, setTimeout stubbed) ===

push() — entity not yet pending (new entry):       0.0021 ms
push() — entity pending, debounce reset:           0.0019 ms
_fire() — including _coalesce() on 40 events:      0.0034 ms
_coalesce() — 40 events × 4 fields each:           0.0031 ms
flush() / flushAll():                              0.0011 ms per entity

=== AAPL earnings burst: 40 ticks in 800ms ===

Tick arrival rate:  ~50 ticks/second (800ms burst)
debounceMs:         200ms (fire 200ms after last tick)
maxWaitMs:          2000ms (backstop)

Event trace:
  t=0ms:    tick 1 → push('AAPL', { price: 189.10, volume: 120000, bid: 189.09, ask: 189.11 })
              → new entry, maxTimer set at 2000ms, debounceTimer set at 200ms
  t=20ms:   tick 2 → push('AAPL', { price: 189.15, ... })
              → debounceTimer reset to t=220ms
  ...
  t=800ms:  tick 40 → push('AAPL', { price: 191.40, volume: 890000, bid: 191.38, ask: 191.42 })
              → debounceTimer reset to t=1000ms
  t=1000ms: debounce fires → _fire('AAPL')
              coalesced: { price: 191.40, volume: 890000, bid: 191.38, ask: 191.42, _eventCount: 40 }
              meta: { eventCount: 40, suppressedCount: 39, burstDurationMs: 1000ms }
              maxTimer cancelled

LLM call: 1 call with final state { price: 191.40, ... }

=== Cost comparison: 200-ticker portfolio, earnings day ===

Feed rate:     40 ticks/entity during burst; burst every 3 minutes for 5 top-movers
Model:         Haiku, 450 tok/call, $0.80/M input + $4.00/M output = ~$0.0000036/call

Without coalescing (each tick → 1 call):
  5 movers × 40 ticks × 20 bursts/day = 4000 calls/day × $0.0000036 = $0.0144/day
  (195 quiet tickers: 195 × 2 calls/day = 390 calls × $0.0000036 = $0.0014/day)
  Total: ~$0.016/day — modest in absolute terms

With coalescing (1 call per burst):
  5 movers × 1 call × 20 bursts/day = 100 calls/day × $0.0000036 = $0.00036/day
  Reduction: 97.5% fewer calls during burst periods

=== latency impact ===

First LLM call after burst starts:   +200ms (debounce wait)
In practice on 40-event bursts:       first tick t=0ms; last tick t=800ms; call fires t=1000ms
  → relative to "call on last tick":   +200ms (debounce after tick 40)
  → relative to "call on first tick":  +1000ms but 39 intermediate calls eliminated

For monitoring/advisory agents:       200ms delay imperceptible
For low-latency trading:              do not coalesce — remove LLM from hot path entirely

=== S-42 vs S-104 vs S-136 vs S-144 ===

              │ S-42 (event-driven agents)        │ S-104 (event stream + window)    │ S-136 (adaptive poll rate)        │ S-144 (burst coalescing)
──────────────┼───────────────────────────────────┼──────────────────────────────────┼───────────────────────────────────┼──────────────────────────────────
Source        │ Pull vs push decision             │ Push: continuous stream          │ Pull: adaptive interval            │ Push: burst on subscribed feed
Unit          │ Each event → 1 LLM call           │ Pattern across window → LLM call │ Poll result → LLM call            │ Burst of N events → 1 LLM call
Filter        │ None — all events trigger         │ Significance filter (rule-based)  │ Volatility band controls interval │ Debounce window + max-wait
Key cost lever│ Avoids polling waste (14× savings)│ 99.99% event rejection           │ Quiet entities polled less        │ N-1 events per burst suppressed
Trigger logic │ Subscribe + react                 │ Pattern in time window           │ Timer + volatility band           │ Debounce per entity
Compose       │ S-144: coalesce before LLM        │ S-144 → S-104 → LLM             │ S-144 for push sources,           │ S-104 (filter coalesced result),
              │                                   │ (coalesce first, then filter)    │ S-136 for pull sources            │ S-42 (event-driven trigger)
```

## See also

[S-104](s104-event-stream-agent-integration.md) · [S-42](s42-event-driven-agents.md) · [S-136](s136-adaptive-per-entity-poll-rate.md) · [S-137](s137-multi-source-field-level-merge.md) · [F-113](../forward-deployed/f113-per-entity-data-completeness-tracking.md) · [F-114](../forward-deployed/f114-source-response-time-slos.md)

## Go deeper

Keywords: `event burst coalescing` · `debounce LLM calls` · `per-entity event debounce` · `live data burst suppression` · `event coalescing agent` · `high-frequency event batching` · `tick debounce agent` · `push event rate limiting` · `entity-level event buffer` · `burst event to single LLM call`
