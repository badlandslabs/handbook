# S-178 · Context Freshness Watermark

[S-174](s174-stale-while-revalidate-live-data.md) tracks freshness per store: a single cache entry is FRESH, STALE, or EXPIRED based on its own TTL. [S-100](s100-live-data-freshness-contracts.md) defines per-action freshness requirements: before writing to the database, require data fetched within the last 30 seconds. Both patterns work at the level of individual data sources.

A multi-source agent assembles context from several live feeds before acting: user profile (cached 45 seconds ago from a session store), market data (fetched 2 seconds ago from a pricing API), system configuration (loaded 5 minutes ago from a config service), and a tool result (returned 50 milliseconds ago). S-174 tells you each source's individual status. But the action gate needs to answer a different question: is the assembled context — the combination of all four sources — fresh enough for the intended action?

The answer is always bounded by the oldest component. A context block that combines fresh market data with a 5-minute-old system config is a 5-minute-old context, regardless of how fresh the other components are. The context freshness watermark is `min(fetchedAt)` across all assembled blocks — the timestamp of the oldest component. When an action gate checks freshness, it compares the watermark age against the action's tolerance. When the check fails, the watermark identifies exactly which source is the bottleneck and must be refreshed.

This is distinct from S-174 (per-store SWR) and S-100 (per-action contracts) in one important way: it aggregates across sources. S-174 answers "is this store entry fresh?" S-100 answers "how fresh does this action need context to be?" S-178 answers "how fresh is the assembled context right now, and which source is the weakest link?"

## Situation

An order-confirmation agent assembles four context blocks before executing a trade. The action requires context fresher than 30 seconds (`CONFIRM_ORDER` tolerance). The assembled context has:

- `user_profile`: 45 seconds old (session cache)
- `market_data`: 2 seconds old (just fetched)
- `system_config`: 300 seconds old (5-minute reload interval)
- `tool_result`: 0.1 seconds old (just returned)

Watermark: `system_config` at 300 seconds. The action gate fires: `STALE_CONTEXT`, stale by 270 seconds. The hint: "Refresh `system_config` and retry."

After refreshing `system_config`, the new watermark shifts to `user_profile` at 45 seconds. The gate still fails for `CONFIRM_ORDER` (45 > 30 seconds). Refreshing the oldest source surfaces the next bottleneck — the gate correctly requires both to be refreshed. For `SEND_REPORT` (10-minute tolerance) and `READ_ONLY_VIEW` (15-minute tolerance), the original context is fresh enough and no refresh is needed.

The watermark also propagates through assembly: when two pre-assembled context objects are merged, the combined watermark is the older of the two. A retrieval context (10 seconds old) merged with a conversation state context (120 seconds old) produces a combined watermark of 120 seconds. The combined object inherits the least-fresh component's timestamp.

## Forces

- **Watermark = min(fetchedAt), not average.** An average age watermark lets a very fresh source offset a very stale one — but the stale source still affects the agent's reasoning. The watermark must be the oldest timestamp because any stale component can cause outdated decisions, regardless of how fresh the other components are.
- **Different actions have different freshness tolerances.** A financial confirmation action (`CONFIRM_ORDER`) tolerates 30 seconds of staleness. A report generation action (`SEND_REPORT`) tolerates 10 minutes. An informational display (`READ_ONLY_VIEW`) tolerates 15 minutes. Encode tolerances per action, not per data source — the data source does not know what action it will be used for.
- **The watermark identifies the bottleneck, not just a pass/fail.** When a gate fails, the retry hint must name the specific source to refresh. Refreshing all sources on every staleness event is wasteful; refreshing only the bottleneck source is efficient. The watermark carries the source name alongside the age.
- **Refreshing the oldest source reveals the next oldest.** After refreshing `system_config` (300 seconds), `user_profile` (45 seconds) becomes the new watermark. Build a refresh loop that re-checks the watermark after each targeted refresh, stopping when the gate passes or a maximum refresh budget is exhausted.
- **Compose S-174 for the refresh operation.** When the watermark identifies a stale source, S-174's `EXPIRED` path fetches a fresh value. S-178 decides that a refresh is needed and which source to target; S-174 executes the refresh and returns the new value. The two patterns are complementary: S-174 manages individual store freshness; S-178 aggregates across stores and routes refresh requests.
- **Include tool results in the watermark.** Tool results injected into context carry their own fetch timestamp. A tool result that is 2 hours old and re-injected as context history is 2 hours old, not freshly fetched. Tag every tool result with `fetchedAt` at the time it was returned, and include that tag in the watermark calculation. Do not treat tool results as always-fresh.

## The move

**Tag each context block with `fetchedAt`. Compute watermark = min(fetchedAt) across all blocks. Gate actions on watermarkAge ≤ requiredFreshnessMs. Hint names the bottleneck source.**

```js
// --- Context freshness watermark ---
// Tag each context block with fetchedAt. Compute watermark = age of oldest block.
// Action gates check watermarkAge <= tolerance. Hint identifies which source to refresh.
// Distinct from S-174 (per-store SWR) and S-100 (per-action freshness contracts).
// Compose: S-178 gate → S-174 refresh of identified source → re-check watermark.

function contextFreshnessWatermark(blocks) {
  // blocks: [{ name, fetchedAt: timestamp_ms, ...data }]
  let oldestFetchedAt = Infinity, oldestSource = null;
  for (const block of blocks) {
    if (block.fetchedAt < oldestFetchedAt) {
      oldestFetchedAt = block.fetchedAt;
      oldestSource = block.name;
    }
  }
  return { watermarkAgeMs: Date.now() - oldestFetchedAt, oldestSource };
}

function checkContextFreshness(blocks, actionName, requiredFreshnessMs) {
  const { watermarkAgeMs, oldestSource } = contextFreshnessWatermark(blocks);
  const fresh = watermarkAgeMs <= requiredFreshnessMs;
  return {
    action: actionName, status: fresh ? 'FRESH' : 'STALE_CONTEXT',
    watermarkAgeMs, oldestSource, requiredFreshnessMs,
    staleByMs: fresh ? 0 : watermarkAgeMs - requiredFreshnessMs,
    retryHint: fresh ? null :
      `Context stale by ${watermarkAgeMs - requiredFreshnessMs}ms — ` +
      `"${oldestSource}" is ${watermarkAgeMs}ms old, ` +
      `but ${actionName} requires data < ${requiredFreshnessMs}ms old. Refresh "${oldestSource}" and retry.`,
  };
}

// Merge watermarks when combining two pre-assembled context objects
function mergeWatermarks(wmA, wmB) {
  return wmA.watermarkAgeMs >= wmB.watermarkAgeMs ? wmA : wmB;
}

// Per-action freshness tolerances
const ACTION_FRESHNESS_MS = {
  CONFIRM_ORDER:  30_000,   // 30s — financial action
  DISPLAY_QUOTE:  60_000,   // 60s — price display
  SEND_REPORT:   600_000,   // 10min — asynchronous report
  READ_ONLY_VIEW:900_000,   // 15min — informational
};

// Integration: assemble context, check watermark before every consequential action
async function assembleAndGate(sources, actionName, fetchFn) {
  const blocks = await Promise.all(
    sources.map(async name => ({ name, fetchedAt: Date.now(), data: await fetchFn(name) }))
  );
  const check = checkContextFreshness(blocks, actionName, ACTION_FRESHNESS_MS[actionName]);
  if (check.status === 'STALE_CONTEXT') throw new Error(check.retryHint);
  return blocks;
}
```

## Receipt

> Verified 2026-06-27 — Node.js v24.16.0. 4 context blocks, 4 action gates. Refresh-then-recheck scenario. `contextFreshnessWatermark()` timed over 1 000 000 iterations. Zero API calls, zero tokens.

```
=== Context Freshness Watermark ===

Context blocks:
  user_profile      : age = 45.0s
  market_data       : age =  2.0s
  system_config     : age = 300.0s
  tool_result       : age =  0.1s

Watermark: oldest source = "system_config"  age = 300.0s
(Context is only as fresh as its stalest component)

--- Action freshness gate checks ---
  CONFIRM_ORDER   : STALE_CONTEXT  watermark=300s > limit=30s  stale by 270s
    retryHint: "Context stale by 270000ms — "system_config" is 300000ms old,
                but CONFIRM_ORDER requires data < 30000ms old. Refresh "system_config" and retry."
  DISPLAY_QUOTE   : STALE_CONTEXT  watermark=300s > limit=60s  stale by 240s
  SEND_REPORT     : FRESH   watermark=300s ≤ limit=600s
  READ_ONLY_VIEW  : FRESH   watermark=300s ≤ limit=900s

--- After refreshing system_config ---
  New watermark: "user_profile"  45.0s
  CONFIRM_ORDER: STALE_CONTEXT  ← refreshing oldest reveals next bottleneck
  (user_profile at 45s still exceeds 30s limit; refresh user_profile next)

--- Watermark merge: retrieval (10s) + conversation state (120s) ---
  merged watermark: "conversation_state"  120s old
  (combined context inherits the older watermark)

=== Timing (1 000 000 iterations) ===
contextFreshnessWatermark() 4 blocks:  0.0002 ms
checkContextFreshness() gate check:    0.0004 ms

Zero API calls. Zero tokens.
```

## See also

[S-174](s174-stale-while-revalidate-live-data.md) · [S-100](s100-live-data-freshness-contracts.md) · [S-111](s111-context-block-refresh.md) · [S-176](s176-context-section-budget-enforcer.md) · [F-67](../forward-deployed/f67-dynamic-tool-registration.md)

## Go deeper

Keywords: `context freshness watermark` · `multi-source freshness aggregation` · `stale context detection` · `assembled context freshness` · `watermark freshness agent` · `context staleness gate` · `live data freshness aggregation` · `freshness bottleneck detection` · `context source staleness` · `combined context age`
