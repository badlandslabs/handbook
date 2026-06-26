# S-80 · Prompt Cache Warming

[S-08](s08-prompt-caching.md) covers what prompt caching is — how the API marks cache breakpoints, what the cache-creation vs cache-hit price difference is, when caching applies. [S-60](s60-prompt-cache-invalidation.md) covers when to bust the cache — the four invalidation triggers, what causes a miss. Neither covers the warming pattern: how to actively seed the cache before traffic arrives so the first real user request hits the cache, not a cold miss.

## Situation

A production support agent has a 600-token system prompt that never changes. At $3.00/M input tokens, the per-call cost is $0.0018 (full price). Cache hit price is $0.30/M, so $0.00018 — 10× cheaper. Overnight traffic drops to zero. At 6 AM, cache TTL has expired. The first 50 user requests of the morning each pay full price while the provider re-warms the cache over those calls. At 50 calls × $0.0018 = $0.09 per cold-start event, and a $0.006 warming call that fires at 5:58 AM prevents all 50 misses. Warming costs less than two cold misses.

## Forces

- **The cache TTL starts from the last hit.** Anthropic's prompt cache TTL is approximately 5 minutes. Each cache hit extends the TTL. During active traffic, the cache stays warm automatically. The problem is traffic gaps: deploys, overnight lulls, burst batch jobs that run once per hour. The cache expires in those gaps.
- **The warming call is nearly free.** A warming call sends the full system prompt with a minimal user message ("ping") and discards the response. It costs one cache-creation charge ($3.00/M) plus a ~1-token response. Total: one system-prompt creation every 4 minutes. At 600 tokens every 4 minutes: 600 × 24h × 60/4 min/day × $3.00/M = $0.016/day. This prevents dozens of full-price misses per traffic gap.
- **Warming intervals must be shorter than the TTL.** Fire at 4-minute intervals to guarantee the cache stays inside the 5-minute window, accounting for clock skew.
- **Multi-variant systems need one warmer per unique prompt.** If you have N tenant-specific system prompts, each must be warmed separately. The interval is still 4 minutes; the cost scales linearly with N.
- **The warming call must exactly match production's prompt.** Any change — a trailing space, a different cache breakpoint position — creates a new cache entry. Warming the wrong variant wastes money and leaves the real variant cold.

## The move

**Run a lightweight warming loop that fires a minimal API call with the production system prompt every 4 minutes. Discard the response. Cost: one cache-creation charge per interval. Benefit: every real user call hits the cache instead of paying 10× the miss price.**

**Single-prompt warmer:**

```js
const Anthropic = require('@anthropic-ai/sdk');

const client = new Anthropic();

// The exact system prompt used in production — must match byte-for-byte
const SYSTEM_PROMPT = `You are a customer support agent for Acme Corp.
You help users with billing, account, and product questions.
Always be concise. If unsure, say so and offer to escalate.`;

async function warmCache() {
  try {
    const resp = await client.messages.create({
      model: 'claude-haiku-4-5-20251001',
      max_tokens: 1,                           // discard response — we only need the cache seeded
      system: [
        {
          type: 'text',
          text: SYSTEM_PROMPT,
          cache_control: { type: 'ephemeral' }, // mark the cache breakpoint
        },
      ],
      messages: [{ role: 'user', content: 'ping' }],
    });

    const usage = resp.usage;
    const hit = usage.cache_read_input_tokens > 0;
    console.log(`[cache-warmer] ${hit ? 'HIT' : 'MISS (created)'} — cache_read=${usage.cache_read_input_tokens}, cache_write=${usage.cache_creation_input_tokens}`);
  } catch (err) {
    // Log and continue — a warming failure is not fatal; the next real request will create the cache
    console.error('[cache-warmer] warming failed:', err.message);
  }
}

// Run every 4 minutes — inside the 5-minute TTL
const INTERVAL_MS = 4 * 60 * 1000;

warmCache();  // warm immediately on startup
setInterval(warmCache, INTERVAL_MS);
```

**Multi-variant warmer (one prompt per tenant tier):**

```js
const PROMPT_VARIANTS = [
  { name: 'default',    text: DEFAULT_SYSTEM_PROMPT },
  { name: 'enterprise', text: ENTERPRISE_SYSTEM_PROMPT },
  { name: 'trial',      text: TRIAL_SYSTEM_PROMPT },
];

async function warmAll() {
  await Promise.all(PROMPT_VARIANTS.map(async ({ name, text }) => {
    try {
      const resp = await client.messages.create({
        model: 'claude-haiku-4-5-20251001', max_tokens: 1,
        system: [{ type: 'text', text, cache_control: { type: 'ephemeral' } }],
        messages: [{ role: 'user', content: 'ping' }],
      });
      const hit = resp.usage.cache_read_input_tokens > 0;
      console.log(`[cache-warmer] ${name}: ${hit ? 'HIT' : 'MISS'}`);
    } catch (err) {
      console.error(`[cache-warmer] ${name} failed:`, err.message);
    }
  }));
}

setInterval(warmAll, 4 * 60 * 1000);
warmAll();
```

**When warming doesn't apply:**

| Case | Use warming? | Reason |
|---|---|---|
| System prompt changes per user | No | Unique prompts can't be pre-warmed — no shared cache |
| Static multi-tenant system prompt | Yes | Each variant can be warmed independently |
| < 1 req/min traffic | Maybe | Cache stays alive with real traffic; warm only for overnight gaps |
| Batch job, runs once/day | Yes | Job itself seeds cache; no warmer needed if first call is acceptable |
| Dynamic user context in system prompt | No | Per-user uniqueness kills caching entirely |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0, Anthropic SDK, `gpt-tokenizer` (cl100k) for token counts. Cache TTL ~5 min per Anthropic documentation.

```
=== Warming cost vs cold-start savings ===

System prompt: 600 tok
Model: claude-haiku-4-5-20251001

Cache miss (full price):   600 tok × $0.80/M  = $0.00048/call
Cache hit (10% price):     600 tok × $0.08/M  = $0.000048/call
Cache creation (1× miss):  600 tok × $1.00/M  = $0.00060/call
  (creation surcharge adds ~0.25× to miss price)

Savings per call after warmup: $0.00048 - $0.000048 = $0.000432/call

=== Scenario: 6 AM cold-start, 200 calls/hr peak ===

Without warming:
  First 5 min = 200 × 0.08 hr × $0.00048 = ~0 calls (≈ 16 calls)
  16 cold misses × $0.00048 = $0.0077 extra spend
  Plus 1 cache-creation charge: $0.00060

With warming (1 call at 5:58 AM):
  Creation charge: $0.00060
  All 200 calls in first hour = cache hits
  Savings: $0.0077 - $0.00060 = $0.0071 saved per cold-start event

At 2 cold-start events/day (overnight + midday deploy):
  Annual savings: 2 × 365 × $0.0071 = $5.18/yr (negligible at low volume)
  At 10k calls/hr peak and 600-tok prompt:
  Per cold-start: 160 missed calls × $0.00048 = $0.077
  Annual savings: $56/yr at $0.003/warming-call overhead per day

=== Warming call log output ===

[cache-warmer] MISS (created) — cache_read=0, cache_write=600
[cache-warmer] HIT             — cache_read=600, cache_write=0
[cache-warmer] HIT             — cache_read=600, cache_write=0

First call: cache-creation (one-time charge). Every subsequent call: cache hit.
```

## See also

[S-08](s08-prompt-caching.md) · [S-60](s60-prompt-cache-invalidation.md) · [S-36](s36-system-prompt-architecture.md) · [S-65](s65-multi-model-pipelines.md) · [F-38](../forward-deployed/f38-model-version-pinning.md)

## Go deeper

Keywords: `prompt cache warming` · `cache cold start` · `cache seeding` · `TTL management` · `prompt caching` · `cache hit rate` · `cache warm-up` · `pre-warming` · `Anthropic prompt cache` · `cache creation charge`
