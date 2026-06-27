# S-172 · Multi-Variant Prompt Cache Warming Planner

[S-08](s08-prompt-caching.md) explains caching mechanics: mark a static prefix, pay a one-time cache-write premium (1.25× full price on Anthropic), read it cheaply (0.1× full price) on every subsequent call within the TTL window. [S-80](s80-prompt-cache-warming.md) covers the warming pattern for a single system prompt: fire a minimal warming call before the TTL expires so the first real user sees a cache hit, not a cold miss.

Neither addresses the problem that arises when you have multiple prompt variants. A SaaS platform with 10 tenant configurations, a multi-locale product with 6 language prompts, a tiered service with different system prompts per subscription level — each variant has its own cache entry, its own TTL, and its own call volume. The warming economics differ per variant. An enterprise tenant handling 4 800 calls per day amortizes a warming call across 17 hits per TTL period. A trial tenant at 8 calls per day has 0.03 calls per TTL period — the warming call costs 46× more than the one hit it might serve.

The break-even point is the call volume below which a warming call costs more than the cache hits it enables. Warm variants above that threshold; let the rest pay full price on cold calls. For Sonnet with an 800-token prompt: break-even is 400 calls per day. High-traffic tenants comfortably above this threshold should always be warmed. Low-traffic tenants should never be warmed — warming them wastes money.

## Situation

A contract extraction SaaS runs 12 tenant configurations, each with a 800-token system prompt variant (different industry glossaries, different output fields per plan). All 12 prompts are structurally static. The team warms all 12 on a 5-minute cron.

Without selective warming: warming overhead is 12 variants × 288 TTL periods/day × $0.003/warming call = $10.37/day. The 8 low-traffic tenants (starter and trial tiers, 8–320 calls/day) generate fewer cache hits than the warming calls that seed them. Warming those 8 wastes money.

With selective warming: only the 4 tenants above 400 calls/day are warmed. Their cache hits save $16.30/day net (after warming cost). The 8 skipped tenants pay full price on cold calls — but at 8–320 calls/day, those cold calls are rare and the warming overhead would exceed the savings. The cron runs for 4 tenants instead of 12: simpler, cheaper, and the savings are real.

## Forces

- **The break-even is volume-per-TTL, not volume-per-day.** The TTL is typically 5 minutes (Anthropic). A tenant with 400 calls/day has 400 / 288 = 1.39 calls per TTL period — just above the break-even of 1.39 for an 800-token Sonnet prompt. A tenant with 399 calls/day falls just below. The daily number is a derived convenience; the fundamental unit is calls-per-TTL.
- **Prompt token count shifts the break-even.** The break-even formula is: `warmingCost / savingsPerHit`. For an 800-token prompt at Sonnet pricing: `(800 × $3.75/M) / (800 × $2.70/M) = $0.003 / $0.00216 = 1.39 calls/TTL`. For a 2000-token prompt: the numerator and denominator both scale by 2.5×, so the break-even stays at 1.39 calls/TTL — the token count cancels out. Break-even is determined by the ratio of write-price to (full-price minus read-price), not by prompt length. At Anthropic Sonnet pricing, that ratio is always 1.39 calls/TTL, regardless of prompt size.
- **The break-even ratio is pricing-tier-specific.** Haiku ($0.80/$0.08/$1.00 per M full/read/write): break-even = ($1.00/M × T) / (($0.80 - $0.08)/M × T) = 1.00/0.72 = 1.39 calls/TTL. Same ratio at Haiku pricing. The 1.39 break-even is universal across Anthropic model tiers because the pricing ratios are held constant. Check provider pricing before assuming this — other providers may differ.
- **Cache TTL resets on each cache hit, not on each warming call.** A warming call seeds the cache for one TTL period. If any real traffic hits the cache in that period, the TTL does not extend. The next warming call must fire before the TTL expires. At 5-minute TTL: 288 warming calls per variant per day, whether the variant gets 1 call or 5000.
- **Warm at start of TTL period, not at end.** The warming call should fire at the beginning of each TTL window, not at the end. If you fire at minute 4:58 of a 5-minute TTL, real traffic in the next 2 seconds still hits the old cache entry and misses on the new one. Fire at minute 0:00 (or 0:30 as a buffer) so the full period benefits from the warm cache.
- **Don't warm variants that are structurally dynamic.** A prompt variant that changes per session (user-injected data in the system prompt, per-request context) does not benefit from warming — the write-only cost is paid without reuse. Warm only variants that are truly static for the TTL window. Detect dynamic variants with S-60's invalidation trigger checks before adding them to the warming plan.

## The move

**Compute break-even calls per TTL period. Warm variants above the threshold; skip the rest. Re-evaluate quarterly as call volumes shift.**

```js
// --- Multi-variant prompt cache warming planner ---
// Identifies which prompt variants are worth warming vs. letting run uncached.
// Break-even formula: warmingCost / savingsPerHit
// At Anthropic Sonnet pricing: 1.39 calls/TTL, regardless of prompt token count.
// Distinct from S-80 (single-prompt warming) and S-60 (invalidation triggers).

class PromptCacheWarmingPlanner {
  constructor(opts) {
    opts = opts || {};
    this._promptTokens         = opts.promptTokens;       // static prefix token count
    this._cacheTtlMinutes      = opts.cacheTtlMinutes || 5;
    this._fullPricePerMillion  = opts.fullPricePerMillion  || 3.00;  // Sonnet
    this._cacheReadPerMillion  = opts.cacheReadPerMillion  || 0.30;
    this._cacheWritePerMillion = opts.cacheWritePerMillion || 3.75;
    this._variants = [];
  }

  registerVariant(variantId, callsPerDay) {
    this._variants.push({ variantId, callsPerDay });
    return this;
  }

  // Cost of one warming call (pays cache-write price).
  _warmingCostUsd() {
    return this._promptTokens / 1e6 * this._cacheWritePerMillion;
  }

  // Savings per hit vs. full-price uncached call.
  _savingsPerHitUsd() {
    return this._promptTokens / 1e6 * (this._fullPricePerMillion - this._cacheReadPerMillion);
  }

  // Minimum calls per TTL period to break even. At Anthropic pricing: ~1.39.
  breakEvenCallsPerTtl() {
    return this._warmingCostUsd() / this._savingsPerHitUsd();
  }

  analyze(variantId) {
    const v = this._variants.find(v => v.variantId === variantId);
    const callsPerTtl    = v.callsPerDay / (24 * 60 / this._cacheTtlMinutes);
    const shouldWarm     = callsPerTtl >= this.breakEvenCallsPerTtl();
    const periodsPerDay  = 24 * 60 / this._cacheTtlMinutes;

    // Net savings per day = (hits per period − 1) × savingsPerHit − 0 (warming cost is break-even offset)
    // More precisely: period net = (callsPerTtl − 1) × savingsPerHit − warmingCost
    const netPerPeriod = shouldWarm
      ? Math.max(0, (callsPerTtl - 1) * this._savingsPerHitUsd() - this._warmingCostUsd())
      : 0;

    return {
      variantId,
      callsPerDay: v.callsPerDay,
      callsPerTtl: parseFloat(callsPerTtl.toFixed(3)),
      recommendation: shouldWarm ? 'WARM' : 'SKIP',
      dailyNetSavingsUsd: parseFloat((netPerPeriod * periodsPerDay).toFixed(4)),
    };
  }

  planAll() {
    const results = this._variants.map(v => this.analyze(v.variantId))
      .sort((a, b) => b.callsPerDay - a.callsPerDay);
    const warm = results.filter(r => r.recommendation === 'WARM');
    const skip = results.filter(r => r.recommendation === 'SKIP');
    return {
      warm,
      skip,
      totalDailyNetSavingsUsd: parseFloat(warm.reduce((s, r) => s + r.dailyNetSavingsUsd, 0).toFixed(4)),
    };
  }
}

// --- Warming cron integration ---

const PLAN = new PromptCacheWarmingPlanner({
  promptTokens: 800, cacheTtlMinutes: 5,
  fullPricePerMillion: 3.00, cacheReadPerMillion: 0.30, cacheWritePerMillion: 3.75,
});

// Register all tenant variants at startup; re-planAll() weekly.
PLAN.registerVariant('enterprise_a', 4800);
PLAN.registerVariant('enterprise_b', 3200);
PLAN.registerVariant('business_a',   1400);
PLAN.registerVariant('business_b',    900);
PLAN.registerVariant('starter_a',     320);  // below break-even
// ...

// Cron: every 4 minutes (fires before 5-min TTL expires)
async function warmingCron(variantRegistry) {
  const plan = PLAN.planAll();
  for (const v of plan.warm) {
    // Fire a minimal 1-token call with the variant's system prompt to seed the cache.
    await callApi({ system: variantRegistry[v.variantId], messages: [{ role: 'user', content: '.' }],
                    max_tokens: 1 });
  }
  // plan.skip variants: do nothing; cold misses are cheaper than warming them
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 12-tenant scenario, 800-token system prompt, Sonnet pricing. Break-even derived analytically; daily savings computed over 288 TTL periods/day.

```
Config: 800-tok system prompt, Sonnet ($3.00/$0.30/$3.75 full/read/write per M)

Break-even: 1.389 calls per 5-min TTL  =  400 calls/day

Variant           Calls/day  Calls/TTL   Rec   Daily net savings
──────────────────────────────────────────────────────────────────
enterprise_a          4800    16.667    WARM          $8.88/day
enterprise_b          3200    11.111    WARM          $5.43/day
business_a            1400     4.861    WARM          $1.54/day
business_b             900     3.125    WARM          $0.46/day

  ─── SKIP threshold (1.389 calls/TTL = 400 calls/day) ───

starter_a              320     1.111    SKIP              $0
starter_b              280     0.972    SKIP              $0
starter_c              210     0.729    SKIP              $0
starter_d              150     0.521    SKIP              $0
trial_a                 45     0.156    SKIP              $0
trial_b                 30     0.104    SKIP              $0
trial_c                 18     0.063    SKIP              $0
trial_d                  8     0.028    SKIP              $0

WARM: 4 / 12 tenants
Total daily net savings: $16.30/day

Flat-warm (all 12): warming overhead $10.37/day,
  8 SKIP variants return negative net savings.
Smart-warm (top 4): cron runs 4 variants instead of 12.

Break-even ratio is pricing-dependent, not token-count-dependent.
At Anthropic's write/read/full pricing ratio: always 1.39 calls/TTL.

=== Timing (100 000 iterations) ===

analyze() per variant:  0.0036 ms
planAll() 12 variants:  0.0436 ms
```

## See also

[S-80](s80-prompt-cache-warming.md) · [S-08](s08-prompt-caching.md) · [S-60](s60-prompt-cache-invalidation.md) · [S-73](s73-multi-tenant-ai-isolation.md) · [F-71](../forward-deployed/f71-cost-driven-prompt-design.md)

## Go deeper

Keywords: `prompt cache warming planner` · `multi-tenant cache warming` · `cache hit rate by variant` · `prompt variant cache economics` · `break-even cache warming` · `per-tenant prompt cache` · `cache warming threshold` · `variant cache warming strategy` · `multi-variant cache slot` · `cache warming cron`
