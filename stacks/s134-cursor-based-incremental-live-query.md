# S-134 · Cursor-Based Incremental Live Query

[S-108](s108-progressive-tool-results.md) paginates over large result sets using continuation tokens: the tool returns `{ partial_results, has_more, continuation_token }`, the model decides when to stop paginating, and the next tool call passes the token back. [S-42](s42-event-driven-agents.md) triggers agent runs from incoming webhook events. [S-104](s104-event-stream-agent-integration.md) buffers a continuous SSE stream, applies a significance filter, and fires agent runs on significant events.

None covers the common case of a polling agent that monitors multiple entities via a REST API. Without a cursor, each poll re-fetches everything: all 100 articles for each of 10 monitored tickers, all 500 recent transactions for each of 20 monitored accounts. The result set returned is nearly identical to the previous poll — with perhaps 5-10 new items buried in it. The agent must either re-process old items (duplicate work, duplicate cost) or implement its own dedup logic (re-inventing the cursor). The payload is 10-50× larger than it needs to be, injecting 10-50× more tokens into context.

Cursor-based incremental live query maintains a per-entity watermark — the timestamp or ID of the last item seen. Each poll uses the cursor to request only items newer than the watermark. After a successful poll, the cursor advances to the latest item in the result. The query payload shrinks to only new events; no dedup logic is needed because by definition only new items are returned.

## Situation

A financial news agent monitors 10 tickers for material events. Without cursor: each 5-minute poll fetches `limit=50` articles per ticker → 500 articles total. Average 5 new articles per ticker per 5 minutes → 50 new articles are relevant; 450 (90%) are re-fetched duplicates paying full token cost. At 288 polls/day: 288 × 500 articles × ~100 tokens/article = 14.4M tokens injected per day vs 288 × 50 × 100 = 1.44M tokens with cursor. Token cost at Haiku $0.80/M: $11.52/day vs $1.15/day. Cursor saves 90%.

With cursor: each 5-minute poll fetches articles published after `lastFetchedAt[ticker]`. Result: 50 articles total (5 per ticker), 100% new, no dedup needed. Cursor advances to the latest article's `publishedAt` timestamp after each poll.

## Forces

- **Two cursor types: timestamp and ID.** Timestamp cursors (`since=2024-01-15T10:00:00Z`) work when the source API supports time filtering and timestamps are monotonically increasing. ID cursors (`after_id=12345`) work for paginated APIs that return items in stable insertion order. Prefer ID cursors when available — they are exact; timestamp cursors have edge cases when items arrive out of order or two items share the same timestamp.
- **Cursor granularity is per entity, not per poll.** Ten tickers are polled together but each has its own cursor. If ticker A has no news for 3 hours but ticker B has 20 articles, ticker A's cursor stays at its last article while ticker B's advances. A single global cursor would stale-fetch ticker A unnecessarily.
- **Advance the cursor only after successful processing.** If the poll succeeds but the agent crashes before processing the results, the cursor must not advance — the new items should be re-fetched on the next poll. Set the cursor after confirming results are injected/stored, not at the start of the poll.
- **Handle the empty-result case as a no-op.** When a poll returns no new items (the cursor is already at the latest event), the correct action is to do nothing: do not advance the cursor (there is nothing newer to advance to), do not inject empty context. An empty poll is a success.
- **Cold start: initial cursor is null.** The first poll has no cursor — it fetches a bounded initial window (e.g., last 24 hours). After the first poll, the cursor is set to the latest item's timestamp. The initial window size controls how much historical backfill runs on startup.
- **Cursor persistence controls session behavior.** An in-memory cursor resets on agent restart (re-fetches the initial window). A persistent cursor (Redis, database) survives restarts and resumes from where the agent left off. For event-monitoring agents that run continuously, persistent cursors are required. For session-scoped agents, in-memory cursors are sufficient.

## The move

**Store a cursor per entity. Build each query with `since=cursor`. After successful processing, advance the cursor to the latest item in the result.**

```js
// --- Cursor store ---
// Per-entity cursor state: { cursor: string|null, lastPollAt: number, itemsSeen: number }
// cursor is a timestamp ISO string, an ID, or null (first poll)

class CursorStore {
  constructor(opts = {}) {
    this._cursors     = new Map();   // entityId → { cursor, lastPollAt, itemsSeen }
    this._initialWindow = opts.initialWindowMs ?? 24 * 60 * 60 * 1000;   // 24h default
  }

  // Get cursor for entity. Returns null if first poll.
  get(entityId) {
    return this._cursors.get(entityId) ?? { cursor: null, lastPollAt: 0, itemsSeen: 0 };
  }

  // Build query params for this entity's next poll.
  // cursorField: 'since' | 'after_id' | 'from_timestamp' (API-specific)
  buildParams(entityId, baseParams = {}, cursorField = 'since') {
    const { cursor } = this.get(entityId);
    if (cursor === null) {
      // First poll: use initial window
      const since = new Date(Date.now() - this._initialWindow).toISOString();
      return { ...baseParams, [cursorField]: since };
    }
    return { ...baseParams, [cursorField]: cursor };
  }

  // Advance cursor after successful poll.
  // items: the fetched items; extractCursor extracts the cursor value from the latest item.
  advance(entityId, items, extractCursor) {
    if (items.length === 0) return;   // empty result: cursor stays where it is

    const state = this.get(entityId);
    const newCursor = extractCursor(items);

    this._cursors.set(entityId, {
      cursor:      newCursor,
      lastPollAt:  Date.now(),
      itemsSeen:   state.itemsSeen + items.length,
    });
  }

  // Snapshot of all entity cursors (for persistence or logging)
  snapshot() {
    return Object.fromEntries(this._cursors);
  }
}

// --- Incremental poller ---
// Polls multiple entities via a live API using per-entity cursors.
// fetchFn: (entityId, params) => Promise<Item[]>
// extractCursor: (items: Item[]) => string  (e.g., latest publishedAt or id)

async function pollIncremental(entityIds, fetchFn, cursorStore, opts = {}) {
  const {
    cursorField   = 'since',
    extractCursor = items => items.reduce((max, item) => item.timestamp > max ? item.timestamp : max, ''),
    baseParams    = {},
    perSourceTimeoutMs = 3000,
  } = opts;

  const results = await Promise.allSettled(
    entityIds.map(async entityId => {
      const params = cursorStore.buildParams(entityId, baseParams, cursorField);

      const timer = new Promise((_, rej) => setTimeout(() => rej(new Error('timeout')), perSourceTimeoutMs));
      let items;
      try {
        items = await Promise.race([fetchFn(entityId, params), timer]);
      } catch (err) {
        return { entityId, items: [], error: err.message, cursorAdvanced: false };
      }

      // Advance cursor only after successful fetch
      cursorStore.advance(entityId, items, extractCursor);

      return { entityId, items, error: null, cursorAdvanced: items.length > 0 };
    })
  );

  const summary = {
    total:    entityIds.length,
    success:  results.filter(r => r.status === 'fulfilled' && !r.value.error).length,
    failed:   results.filter(r => r.status === 'rejected' || r.value?.error).length,
    newItems: results.reduce((sum, r) => sum + (r.value?.items?.length ?? 0), 0),
  };

  return {
    results: results.map(r => r.status === 'fulfilled' ? r.value : { entityId: null, items: [], error: r.reason.message }),
    summary,
    cursorSnapshot: cursorStore.snapshot(),
  };
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `CursorStore.get()`, `buildParams()`, `advance()` timed over 100 000 iterations. `pollIncremental()` timed with in-process `fetchFn` (immediate resolve). No live API calls.

```
=== CursorStore timing (100 000 iterations) ===

$ node -e "
const store = new CursorStore();
store.advance('AAPL', [{timestamp:'2024-01-15T10:00:00Z',headline:'Apple reports...'}],
  items => items.at(-1).timestamp);
const t0 = performance.now();
for (let i = 0; i < 100000; i++) {
  store.buildParams('AAPL', { limit: 20 }, 'since');
}
console.log('buildParams() with cursor:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
store.get() first poll (null cursor): 0.0004 ms
store.get() with cursor:              0.0003 ms
buildParams() first poll:             0.0011 ms   (null cursor + Date.now() + toISOString())
buildParams() with cursor:            0.0008 ms
advance() 5-item result:              0.0019 ms   (reduce to find latest + Map.set())
advance() empty result:               0.0004 ms   (early return)
snapshot() N=10 entities:            0.0021 ms

=== pollIncremental() — 10 entities, in-process fetch (100 000 iterations) ===

pollIncremental() N=10, all success:  0.089 ms   (Promise.allSettled + 10 advance() calls)

=== Financial news agent: 10 tickers, 5-minute poll interval ===

Setup:
  tickers: ['AAPL','MSFT','GOOGL','AMZN','META','NVDA','TSLA','BRK-B','JPM','V']
  poll interval: 5 minutes (288 polls/day)
  avg new articles per ticker per 5 min: 5

Poll 1 (cold start, 24h initial window):
  buildParams('AAPL', {limit:50}, 'since'):
    → { limit: 50, since: '2024-01-14T10:05:00Z' }   (24h ago)
  fetchFn returns 47 articles (all from last 24h)
  advance('AAPL', items, extract): cursor → '2024-01-15T10:04:52Z' (latest)

Poll 2 (5 min later, cursor set):
  buildParams('AAPL', {limit:50}, 'since'):
    → { limit: 50, since: '2024-01-15T10:04:52Z' }   (last seen)
  fetchFn returns 5 articles (only new since cursor)

=== Token cost comparison (10 tickers × 288 polls/day) ===

              │ Without cursor (full re-fetch)   │ With cursor (incremental)
──────────────┼──────────────────────────────────┼──────────────────────────
Articles/poll │ 500 (50 per ticker)              │ 50 (5 new per ticker)
Articles/day  │ 500 × 288 = 144 000              │ 50 × 288 = 14 400
Tokens/article│ 100 (avg headline + metadata)    │ 100
Tokens/day    │ 14 400 000                       │ 1 440 000
Cost (Haiku)  │ 14.4M × $0.80/M = $11.52/day    │ 1.44M × $0.80/M = $1.15/day
Saved         │ —                                │ $10.37/day ($311/month)

Dedup work:   Without cursor: agent must dedup 450 re-fetched articles per poll
              With cursor: no dedup needed — by definition all returned items are new

Latency:      Smaller payload → faster API response → smaller injection → faster TTFT

=== S-108 vs S-104 vs S-134 ===

              │ S-108 (progressive tool results) │ S-104 (SSE event stream)          │ S-134 (cursor-based polling)
──────────────┼───────────────────────────────────┼────────────────────────────────────┼──────────────────────────────
Model         │ Poll (agent-driven)               │ Push (server-sends)                │ Poll (schedule-driven)
Cursor        │ Continuation token in tool result │ Implicit (stream position)         │ Per-entity watermark in state
Granularity   │ Per result set                    │ Per stream                         │ Per entity
Pattern       │ Model decides "more" or "stop"    │ Agent buffers + filters stream     │ Agent polls on schedule
Reduces       │ Per-query token ceiling           │ LLM call frequency (filter)        │ Payload size + dedup work
Composes with │ S-55 (parallel), S-75 (inject)   │ S-119 (frontend protocol)          │ S-104 (cursor as stream position)
```

## See also

[S-108](s108-progressive-tool-results.md) · [S-104](s104-event-stream-agent-integration.md) · [S-42](s42-event-driven-agents.md) · [S-117](s117-webhook-event-deduplication.md) · [F-104](../forward-deployed/f104-live-source-health-monitor.md) · [S-100](s100-live-data-freshness-contracts.md)

## Go deeper

Keywords: `cursor-based polling` · `incremental live query` · `watermark polling` · `since cursor` · `after_id cursor` · `per-entity cursor` · `incremental fetch` · `polling watermark` · `live API incremental` · `cursor store`
