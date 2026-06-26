# S-60 · Prompt Cache Invalidation

[S-08](s08-prompt-caching.md) covers the basic caching pattern — mark a static prefix with `cache_control`, pay $3.75/M to write it, read it back at $0.30/M. The entry stops there. What it doesn't cover: what makes the cache entry disappear, how much a surprise miss costs, and how to detect from the API response whether you got a hit or a miss. Those gaps bite in production.

## Situation

A support agent serves 1 000 calls/day against a 92-token system prompt. The cache hit rate is >99% during business hours — fast, cheap, the math works. Then a developer deploys a one-word tweak ("$500" → "$250"), or the on-call engineer upgrades the pinned model version to pick up a bug fix. The cache entry evicts. The next 1 000 calls each pay cache-write price. Nobody notices until the billing alert fires.

## Forces

- **A cache miss costs 25% more than no caching at all.** Cache creation is $3.75/M; base input is $3.00/M. A miss isn't neutral — it's actively more expensive than skipping the feature. The economics only work when hits outnumber misses by a wide margin.
- **The TTL is ~5 minutes.** Any gap in traffic longer than that — overnight, a deploy, a provider cold-start — resets the clock. Low-traffic products with periodic batch jobs pay creation price on every run.
- **Four triggers cause a miss.** Changing the cached content (even one token), changing the model version, changing the API version, or letting the TTL expire. Three of the four are operational decisions made outside the prompt itself.
- **The response tells you which path was taken.** `response.usage.cache_read_input_tokens > 0` = hit. `cache_creation_input_tokens > 0` and `cache_read_input_tokens == 0` = miss. If both are zero, that prefix was never marked for caching.
- **Retry-on-miss doesn't help.** The miss is the creation event — the next call will hit. Detecting a miss lets you log it and understand your effective hit rate; it doesn't change the call's cost.

## The move

**Pin model version and API version. Detect misses. Size your TTL exposure. Never change a cached prefix without budgeting the miss.**

**Invalidation triggers:**

| Trigger | Cache outcome |
|---|---|
| System prompt content changed (any token) | MISS + new entry created |
| Model version changed | MISS (different cache namespace) |
| API version changed | MISS (not shared across API versions) |
| TTL expired (~5 min idle) | MISS (entry evicted) |
| `cache_control` block removed | NOT CACHED on next call |
| Same content, same model, same API, <5 min | HIT |

**Miss detection:**

```js
function parseCacheStatus(usage) {
  if (usage.cache_read_input_tokens > 0) {
    return { status: 'HIT', tokens: usage.cache_read_input_tokens };
  }
  if (usage.cache_creation_input_tokens > 0) {
    return { status: 'MISS', tokens: usage.cache_creation_input_tokens };
  }
  return { status: 'NOT_CACHED', tokens: 0 };
}

const response = await client.messages.create({ /* ... */ });
const cache = parseCacheStatus(response.usage);

if (cache.status === 'MISS') {
  metrics.increment('prompt_cache.miss', { model, feature });
  // Expected at startup, after deploys, after TTL gaps — not a problem in isolation
  // Sustained misses (>1% of calls) = a bug: content changing per-call or TTL too short
}
```

**Protecting the cached prefix:**

```js
// Stable (cacheable): system identity, constraints, tools — never changes per-call
const SYSTEM_CACHED = {
  type: 'text',
  text: systemPromptText,
  cache_control: { type: 'ephemeral' },
};

// Dynamic (NOT cacheable): user context, retrieved docs, current turn
const userTurn = {
  role: 'user',
  content: [
    { type: 'text', text: `<context>${retrievedContext}</context>\n\n${userMessage}` },
    // No cache_control here — this changes every call
  ],
};
```

The canonical failure: accidentally placing `cache_control` on a block that contains per-call data (user ID, retrieved document, timestamp). Every call creates a new cache entry; you pay creation price forever and accumulate cache entries that are each used exactly once.

**Deciding what to cache:**

```
Always cache:  system prompt, static tool definitions, persona/constraints
Never cache:   retrieved context (changes per query), user session data, turn history
Sometimes:     long static documents (FAQ, product catalog) — cache if >1k tokens and used repeatedly
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, `gpt-tokenizer` (cl100k). System prompt: 6-sentence support agent definition. Pricing from Anthropic public docs (2026-06-26): base $3.00/M, cache write $3.75/M, cache read $0.30/M — verify at docs.anthropic.com/prompt-caching before relying on these for budget calculations.

```
=== Prompt cache invalidation: cost impact ===

System prompt v1: 92 tokens
System prompt v2 (one word changed): 92 tokens  ← full miss, new cache entry

Cost per 1k calls, 92-token system prompt:
  Cache hit  (TTL warm):  $0.0276/k
  Cache miss (creation):  $0.3450/k   ← 25% MORE than no-cache
  No caching (base):      $0.2760/k

Miss penalty vs hit:      12.5×
Miss vs no-cache:         +25% (cache creation surcharge)

1k calls/day, 1 miss/day (TTL expires once overnight):
  Daily with caching: $0.02795
  Daily no caching:   $0.27600
  Monthly savings:    $7.44   ← only if hit rate stays >99%

=== Hit/miss detection from response.usage ===

HIT:  status=HIT   cache_read=92  cache_creation=0
MISS: status=MISS  cache_read=0   cache_creation=92
```

The cost math only favors caching when cache_read_input_tokens outnumbers cache_creation_input_tokens by >15:1. At lower ratios, you pay a premium for failed cache entries. Track the ratio per deploy; alert if it drops below 10:1.

## See also

[S-08](s08-prompt-caching.md) · [S-36](s36-system-prompt-architecture.md) · [S-56](s56-preflight-token-check.md) · [F-29](../forward-deployed/f29-cost-attribution.md) · [F-26](../forward-deployed/f26-behavioral-drift-detection.md)

## Go deeper

Keywords: `prompt caching` · `cache invalidation` · `cache TTL` · `cache_creation_input_tokens` · `cache_read_input_tokens` · `cache miss penalty` · `cache hit rate` · `ephemeral cache` · `cache control`
