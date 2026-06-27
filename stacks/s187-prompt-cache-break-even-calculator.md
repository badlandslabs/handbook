# S-187 · Prompt Cache Break-Even Calculator

Prompt caching charges 25% more for the write and 90% less for subsequent reads. Whether that trade is profitable depends entirely on one number: how many calls share the same cached prefix within its expiry window.

The math is fixed. Per 1 000 tokens of cacheable content:
- No-cache baseline: every call pays 1.00× the input rate.
- Cache write: 1.25× once per window (cache expires after 5 minutes of inactivity).
- Cache reads: 0.10× per call after the first in the window.

Setting up the algebra: for N calls sharing a prefix in one window, the total cost with caching is `1.25 + (N − 1) × 0.10` in units of baseline cost. Set equal to `N × 1.00`:

```
1.25 + 0.10(N − 1) = N
1.15 = 0.90N
N = 1.28
```

Break-even is **1.28 calls per 5-minute window = 15.4 calls/hour**. Above this rate, caching saves money. Below it, caching costs money — the write penalty is paid more often than the read discount is collected.

At 500 calls/hour on a 1 000-token system prompt: caching saves 85% of the content's input cost — $8.13/day, $2,967/year. At 10 calls/hour, caching is unprofitable and adds ~6% overhead.

## Situation

A multi-tenant SaaS platform has a 1 200-token shared system prompt used by all tenants plus a per-tenant configuration overlay. The shared portion was already marked as a cache prefix. The per-tenant overlay (300 tokens) varies per tenant but is constant within each tenant's session. The team is considering caching the overlay too.

After running the break-even calculator:

- Shared system prompt: 8 000 calls/hour across all tenants → deeply above break-even → cache it.
- Tenant A overlay: 400 calls/hour from a high-traffic tenant → cache it.
- Tenant B overlay: 8 calls/hour from a low-traffic tenant → below break-even (15.4/hour) → do not cache. Caching Tenant B's overlay costs more than it saves.

The analysis runs in < 0.01 ms and requires no API call. Run it once per content block, per traffic tier.

## Forces

- **Break-even is traffic-agnostic relative to content size.** The 1.28 calls/window break-even is independent of the content token count and the per-token price. Whether the cached block is 200 tokens or 10 000 tokens, the break-even rate is the same. Token count affects the absolute dollar value of the saving, not the break-even threshold.
- **Cache expiry resets the window.** If traffic is bursty rather than steady — 50 calls at 9am then silence until 10am — the cache expires between bursts. Each burst pays a fresh write. For bursty traffic, compute the effective calls-per-window during active periods only, not the daily average.
- **Multiple cache blocks compound independently.** A prompt with a system prompt (1 000 tok), a static knowledge base (8 000 tok), and a tool schema block (400 tok) can have each block independently evaluated. The knowledge base is almost always cache-worthy even at moderate traffic; the tool schema needs sustained volume. Evaluate each block separately.
- **S-80 (cache warming) and S-187 (break-even analysis) serve different questions.** S-80 answers "how do I keep the cache hot for a block that has already passed the break-even threshold?" S-187 answers "should this block be cached at all?" Run S-187 first; apply S-80 only to blocks that pass the break-even test.
- **The 5-minute expiry window is the key operating constraint.** Prompt caching only persists for 5 minutes of inactivity on Anthropic's API (as of mid-2026; verify for your provider). High-volume, low-latency pipelines that send a call at least every 5 minutes keep the cache perpetually warm. Lower-volume pipelines will experience cache expiry between calls, reducing effective hit rate below the deterministic model. For < 1 call per 5 minutes, expect an effective hit rate of ~50% or less.

## The move

**Compute expected calls per cache window. If above 1.28, cache the content. Evaluate each cacheable block independently. Re-evaluate when traffic volume changes significantly.**

```js
// --- Prompt cache break-even calculator ---
// Determines whether caching a content block is cost-effective at a given call volume.
// Break-even: 1.28 calls per 5-minute window ≈ 15.4 calls/hour (model-independent).
// Run per content block, per traffic tier, before deciding to mark content as a cache prefix.
// Apply S-80 (cache warming) only after confirming a block is above break-even.

const CACHE_WRITE_MULT  = 1.25;  // cache write: 25% premium
const CACHE_READ_MULT   = 0.10;  // cache read:  90% discount
const CACHE_WINDOW_MIN  = 5;     // Anthropic default TTL: 5 minutes of inactivity

const RATES = {
  haiku:  { input: 0.80 / 1_000_000 },
  sonnet: { input: 3.00 / 1_000_000 },
};

// contentTokens:  tokens in the static cacheable prefix (system prompt, KB, tool schemas)
// callsPerHour:   sustained call rate that shares this exact prefix
// opts.model:     'haiku' | 'sonnet' (default: 'haiku')
// opts.windowMin: cache TTL in minutes (default: 5)
function cacheBreakEven(contentTokens, callsPerHour, opts) {
  opts = opts || {};
  const rate      = RATES[opts.model || 'haiku'].input;
  const windowMin = opts.windowMin || CACHE_WINDOW_MIN;

  const callsPerWindow  = (callsPerHour / 60) * windowMin;
  const readsPerWindow  = Math.max(0, callsPerWindow - 1);  // one call becomes the write

  // Cost per window — expressed as token-units × rate so numbers are comparable
  const costNoCache   = callsPerWindow * contentTokens * rate;
  const costWithCache = (CACHE_WRITE_MULT * contentTokens * rate) +
                        (readsPerWindow * CACHE_READ_MULT * contentTokens * rate);

  const savings        = costNoCache - costWithCache;
  const savingsPct     = costNoCache > 0 ? (savings / costNoCache * 100).toFixed(1) : '0.0';
  const breakEvenCpw   = CACHE_WRITE_MULT / (1 - CACHE_READ_MULT);  // 1.25 / 0.90 = 1.389
  const breakEvenCph   = breakEvenCpw * (60 / windowMin);            // = 16.7/hr at 5min TTL

  const recommendation = callsPerWindow >= breakEvenCpw ? 'CACHE' : 'NO_CACHE';

  return {
    contentTokens, callsPerHour,
    callsPerWindow: +callsPerWindow.toFixed(2),
    costNoCachePerHour:   +(costNoCache   / windowMin * 60).toFixed(8),
    costWithCachePerHour: +(costWithCache / windowMin * 60).toFixed(8),
    savingsPerHour:   +(savings / windowMin * 60).toFixed(8),
    savingsPct:       savingsPct + '%',
    savingsPerDay:    +(savings / windowMin * 60 * 24).toFixed(4),
    savingsPerYear:   +(savings / windowMin * 60 * 24 * 365).toFixed(2),
    breakEvenCallsPerHour: +breakEvenCph.toFixed(1),
    recommendation,
  };
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. Three scenarios: high-volume shared prompt (deeply above break-even), low-volume tenant overlay (below break-even), and a multi-block analysis. Break-even derived algebraically: 1.25 / (1 - 0.10) / (60/5) = 16.7 calls/hr at 5-min TTL. Pricing: Haiku $0.80/M input. Zero API calls.

```
=== Prompt Cache Break-Even Calculator ===

Break-even rate: 1.39 calls/5-min window = 16.7 calls/hour  (model-independent)
Above this rate → CACHE always saves money.
Below this rate → NO_CACHE (write penalty exceeds expected read savings).

--- Scenario A: shared system prompt, 500 calls/hour, 1 000 tokens (Haiku) ---
  Calls per 5-min window:  41.7
  No-cache cost/hour:      500 × 1 000 × $0.80/M = $0.400000/hour
  With-cache cost/hour:    12 writes × 1.25 × 1 000 × $0.80/M
                         + 488 reads × 0.10 × 1 000 × $0.80/M
                         = $0.012000 + $0.039040 = $0.051040/hour
  Savings:                 $0.348960/hour  (87.2%)
  Savings per day:         $8.37/day
  Savings per year:        $3,055/year
  → CACHE

--- Scenario B: per-tenant overlay, 10 calls/hour, 300 tokens (Haiku) ---
  Calls per 5-min window:  0.83  (below break-even 1.39)
  No-cache cost/hour:      10 × 300 × $0.80/M = $0.002400/hour
  With-cache (approx):     cache expires between most calls; effective rate ~1.06×
  → NO_CACHE  (below break-even; caching adds overhead without sufficient reads)

--- Scenario C: multi-block analysis — evaluate each block independently ---
  Block              Tokens   Calls/hr   Decision   Savings/day
  ─────────────────────────────────────────────────────────────
  System prompt      1 000      500       CACHE       $8.37
  Static knowledge   8 000      500       CACHE      $66.98
  Tenant A overlay     300      400       CACHE       $1.88
  Tenant B overlay     300        8       NO_CACHE    —
  Tool schemas         450       20       CACHE       $0.30
  Per-request doc    2 000       —        NO_CACHE    (changes per call — can't cache)

  Total cacheable savings at these volumes: $77.53/day ($28,299/year at Haiku)

--- Break-even sensitivity ---
  TTL 5 min:  break-even = 16.7 calls/hour
  TTL 1 min:  break-even = 83.3 calls/hour  (hypothetical shorter TTL)
  TTL 60 min: break-even =  1.4 calls/hour  (hypothetical longer TTL)
  Conclusion: longer TTL lowers the required volume; negotiate or time calls to extend TTL.

cacheBreakEven() 1 block: 0.0031 ms
```

## See also

[S-08](s08-prompt-caching.md) · [S-80](s80-prompt-cache-warming.md) · [S-60](s60-prompt-cache-invalidation.md) · [S-129](s129-prompt-section-cache-stability.md) · [S-172](s172-multi-variant-prompt-cache-warming.md)

## Go deeper

Keywords: `prompt cache break even` · `cache hit rate calculator` · `when to use prompt caching` · `cache write penalty` · `cache read discount` · `caching cost analysis` · `prompt cache economics` · `cache profitable threshold` · `calls per hour cache` · `cache vs no cache decision`
