# S-43 · Tool Result Caching

Prompt caching ([S-08](s08-prompt-caching.md)) caches what goes into the model. Tool result caching caches what comes back from your tools. In a multi-turn agent session, the same tool is often called multiple times with the same arguments. Without caching, you pay for each call in tokens, latency, and downstream API cost.

## Situation

A support agent handles an 8-turn conversation about a billing issue. The agent calls `get_account(user_id="usr_123")` on turn 1 to understand the account, again on turn 4 when the billing question changes, again on turn 6 for a clarification. The record hasn't changed. The agent paid three external DB lookups and injected 150 tokens it already had. Caching the first result and returning it on subsequent calls with the same key costs nothing and cuts per-call DB requests by 75%.

## Forces

- An agent loop is not stateful by default — each tool call executes independently. The agent doesn't "remember" it already fetched a record unless you build that memory. Caching is the explicit mechanism.
- Cache correctness depends on TTL design. Reference data (user records, product catalog) is stable enough for a 5-minute TTL within a session. Market prices need near-zero TTL. Side-effecting tools (send email, write file, charge card) must never be cached — they are not idempotent.
- Token savings are real but secondary to latency savings. At 120ms per external tool call, calling the same tool four times adds 360ms of unnecessary latency to a conversation. For real-time interactions ([S-35](s35-latency-budget.md)), this compounds.
- Cache scope matters. Session cache (in-memory, per conversation) is safe and simple. Cross-session cache (Redis, shared) needs careful TTL and invalidation. A record cached at session start is correct for that session; shared across sessions it may be stale.
- The cache key must be deterministic: `{tool_name}:{canonical_json(args)}`. Canonicalize JSON (sorted keys) or the same logical call with different arg ordering misses the cache.
- Caching and prompt caching are complementary, not alternatives. S-08 caches the static part of the prompt (system prompt, tool schemas). Tool result caching caches the dynamic part (tool outputs). Both are in play in a well-optimized agent.

## The move

**Cache tool results by `tool_name:args` key within a session. Never cache side-effecting tools.**

```js
class ToolCache {
  constructor() { this.store = new Map(); }

  key(name, args) {
    return `${name}:${JSON.stringify(Object.keys(args).sort().reduce((o, k) => (o[k]=args[k], o), {}))}`;
  }

  get(name, args)        { return this.store.get(this.key(name, args)); }
  set(name, args, result){ this.store.set(this.key(name, args), result); }
}

const SIDE_EFFECTS = new Set(['send_email', 'write_file', 'charge_card', 'post_message']);

async function callTool(name, args, cache) {
  if (SIDE_EFFECTS.has(name)) return await tools[name](args);  // never cache
  const cached = cache.get(name, args);
  if (cached !== undefined) return cached;
  const result = await tools[name](args);
  cache.set(name, args, result);
  return result;
}
```

**TTL by data class:**

| Tool type | Example | TTL |
|---|---|---|
| User/account data | `get_account`, `get_profile` | 5 min (session scope) |
| Config/catalog | `get_product`, `get_plan` | 30 min |
| Environmental | `get_weather`, `get_time` | 1–10 min |
| Real-time | `get_price`, `get_inventory` | 1–5 sec or no cache |
| Side-effect | `send_email`, `write_file` | Never cache |

**For long-running or cross-session agents:** use a shared cache (Redis) with explicit TTL. Set TTL conservatively — a stale cache answer that's acted on is worse than a fresh lookup. Add a per-tool cache-bypass flag for when freshness is critical.

**Instrument cache hit rate.** A hit rate under 20% means either your TTL is too short or the tool isn't called repeatedly enough to benefit. A hit rate over 90% with a long TTL means you may be serving stale data — check if staleness is acceptable.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. 8-turn support session; tool result is a 50-token JSON user record; called 4× in one session on the same user_id; 120ms external DB latency per call modeled from typical cloud DB read latency.

```
=== Tool result caching: 8-turn support session ===
Tool: get_account(user_id="usr_123") → 50-token JSON record
Calls without caching: 4  (same user_id each time)
Calls with caching:    1  (3 cache hits at 0ms / 0 tokens)

Per-session:
  Uncached — tokens: 236  latency: 480ms  DB calls: 4
  Cached   — tokens:  59  latency: 120ms  DB calls: 1
  Savings:   75% token reduction  75% latency reduction

At 1,000 sessions/day:
  Uncached: $42.98/month
  Cached:   $10.74/month
  Monthly savings: $32.23

Cache key examples (canonical JSON):
  get_account:{"user_id":"usr_123"}     TTL=5min   ← safe to cache
  get_price:{"symbol":"AAPL"}           TTL=1s     ← near-real-time, short TTL
  send_email:{"to":"alice@..."}         NO-CACHE   ← side-effect, never cache
```

The savings numbers are modest per-session but compound at scale. The latency reduction is the sharper argument: 360ms of unnecessary DB round-trips per session at 1,000 sessions/day is 360 seconds of pure wait time removed per day.

## See also

[S-08](s08-prompt-caching.md) · [S-03](s03-tool-use.md) · [S-35](s35-latency-budget.md) · [F-08](../forward-deployed/f08-agent-cost-control.md) · [S-09](s09-memory-systems.md)

## Go deeper

Keywords: `tool result cache` · `memoization` · `agent caching` · `TTL` · `idempotent tools` · `side-effect tools` · `session cache` · `Redis` · `cache key design`
