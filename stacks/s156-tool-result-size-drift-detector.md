# S-156 · Tool Result Size Drift Detector

[S-97](s97-tool-result-summarization.md) summarizes tool results that arrive too long: a `get_orders` call that returns 5 000 characters is compressed before it enters the prompt. [S-130](s130-structured-tool-result-compression.md) compresses structured results by eliding fields the agent does not need. [F-95](../forward-deployed/f95-tool-invocation-cost-attribution.md) attributes cost per tool call over time, surfacing which tools consume the most tokens. [F-87](../forward-deployed/f87-tool-call-argument-audit-log.md) logs every tool call for audit.

None of these detect the underlying cause: the tool result itself is growing. S-97 summarizes the overage but does not ask why it occurred. F-95 tracks cost but does not distinguish between a tool being called more often and a tool's results getting larger on each call. When an API silently adds fields to its response payload — pagination metadata, embedded analytics, deprecation notices, expanded relationship objects — the results grow incrementally with no single call that looks broken. Over 30 days, `get_customer` goes from 280 characters to 560 characters per call. Every session now carries an extra ~70 tokens of context overhead per customer tool call. At 10 000 sessions/day with three customer lookups each, that is an extra 2.1 million tokens per day — $6.30/day at Sonnet pricing, invisible without this detector.

A tool result size drift detector maintains a rolling window of result sizes (in characters) per tool name. After each tool call, it checks whether the current result is a spike (significantly above the rolling average) or whether the window itself shows a trend (second-half average significantly above first-half average). SPIKE catches a single bad call (an API that embeds a raw document blob on certain entities). DRIFT catches gradual payload bloat across many calls.

## Situation

A support agent calls three tools per session: `get_customer`, `get_orders`, and `get_contract`. Two months ago an external orders API provider updated their response schema to include per-item cost breakdowns, tax codes, and delivery sub-statuses. No webhook or email was sent. The `get_orders` result went from an average of 300 characters to an average of 620 characters.

No single call looks wrong. F-87's audit log shows the tool returning results. S-97's summarization threshold (default 2 000 characters) was never reached. F-95's cost attribution shows the sessions are getting more expensive, but the cause is attributed to "more tool calls per session" by the analyst looking at the chart.

The drift detector fires DRIFT after 20 calls: first-half average 299 characters, second-half average 602 characters, driftRatio 2.01. An alert reaches the prompt engineering team. Investigation: the API expanded its response format. Fix: register S-130 field elision rules to drop the new fields not needed by the agent.

## Forces

- **Two failure modes require two checks.** A spike is a single-call event: one call returns 10× the normal size because of an entity-specific anomaly (a customer with 50 nested accounts, a contract with an embedded PDF). A drift is a trend: the average grows across many calls because the API added fields. A spike check (current vs rolling average) catches the first; a trend check (first-half average vs second-half average) catches the second. Run both on every call.
- **The window must be large enough to smooth noise but small enough to detect recent changes.** At `windowSize: 20`, a trend that emerges over 10 calls is detectable. At `windowSize: 5`, a single large call dominates the average and produces false drift alerts. At `windowSize: 100`, a trend that started 50 calls ago has already inflated the first-half average and reduces sensitivity. 20 is a reasonable default for daily-traffic tools; increase it for high-volume tools where individual-call variance is high.
- **Size is a proxy for tokens, not a direct measure.** `Math.ceil(chars / 4)` is close enough for alerting. If you need an exact token count, run the result through the tokenizer at alert time — not on every call (expensive). Use chars for the rolling window; convert to tokens only when logging the alert.
- **The DRIFT threshold (1.5×) is a warning, not a stop.** When DRIFT fires, the agent continues functioning. The correct response is investigation: check the API's changelog, compare a current response to an archived one from 30 days ago, and decide whether to update S-130 elision rules. Do not automatically block tool calls on DRIFT — the larger result may be legitimately required.
- **Tool-level aggregation can miss entity-level spikes.** `get_customer` may be stable at 280 characters for 99% of entities but consistently return 4 000 characters for enterprise customers with many nested accounts. Rolling the window per tool name will not detect this. If entity-level segmentation matters, key the window by `toolName + entityType` — but that multiplies the number of windows to maintain.
- **Use stats() for dashboards, check() in the call path.** `stats()` returns P50/P95/min/max across the window and belongs in a monitoring dashboard. `check()` is designed for the call path — it records and checks in one call, returning the alert status for immediate action.

## The move

**After each tool call, pass the result size to `check()`. On SPIKE, log and investigate the entity causing the anomaly. On DRIFT, log and audit the API's recent changelog.**

```js
// --- Tool result size drift detector ---
// Maintains a rolling window of result sizes per tool name.
// SPIKE: current call > spikeRatio × rolling average (single anomalous call).
// DRIFT: second-half window average > driftThreshold × first-half average (payload growth trend).

class ToolResultSizeDriftDetector {
  constructor(opts = {}) {
    this._windowSize     = opts.windowSize     ?? 20;    // calls per window
    this._spikeRatio     = opts.spikeRatio     ?? 2.0;   // alert if current > 2× avg
    this._driftThreshold = opts.driftThreshold ?? 1.5;   // alert if 2nd-half avg > 1.5× 1st-half
    this._history        = new Map();  // toolName → number[] (chars per call)
  }

  // Record result size for a tool call (without checking).
  record(toolName, resultChars) {
    if (!this._history.has(toolName)) this._history.set(toolName, []);
    const arr = this._history.get(toolName);
    arr.push(resultChars);
    if (arr.length > this._windowSize) arr.shift();
  }

  // Record and check. Returns status: 'INSUFFICIENT_DATA' | 'SPIKE' | 'DRIFT' | 'NORMAL'
  check(toolName, resultChars) {
    this.record(toolName, resultChars);
    const arr = this._history.get(toolName);
    if (arr.length < 3) return { status: 'INSUFFICIENT_DATA', samples: arr.length };

    // Spike: current vs rolling average (excluding current call)
    const prior      = arr.slice(0, -1);
    const avg        = prior.reduce((s, v) => s + v, 0) / prior.length;
    const spikeRatio = avg > 0 ? resultChars / avg : 1;

    if (spikeRatio >= this._spikeRatio) {
      return {
        status:          'SPIKE',
        toolName,
        currentChars:    resultChars,
        rollingAvgChars: Math.round(avg),
        spikeRatio:      parseFloat(spikeRatio.toFixed(2)),
        samples:         arr.length,
      };
    }

    // Drift: first-half average vs second-half average
    if (arr.length >= 10) {
      const mid       = Math.floor(arr.length / 2);
      const firstAvg  = arr.slice(0, mid).reduce((s, v) => s + v, 0) / mid;
      const secondAvg = arr.slice(mid).reduce((s, v) => s + v, 0) / (arr.length - mid);
      const driftRatio = firstAvg > 0 ? secondAvg / firstAvg : 1;
      if (driftRatio >= this._driftThreshold) {
        return {
          status:             'DRIFT',
          toolName,
          firstHalfAvgChars:  Math.round(firstAvg),
          secondHalfAvgChars: Math.round(secondAvg),
          driftRatio:         parseFloat(driftRatio.toFixed(2)),
          samples:            arr.length,
        };
      }
    }

    return { status: 'NORMAL', toolName, currentChars: resultChars,
             rollingAvgChars: Math.round(avg), samples: arr.length };
  }

  // Distribution stats for monitoring dashboards. Not in the call path.
  stats(toolName) {
    const arr = this._history.get(toolName);
    if (!arr || arr.length < 1) return null;
    const sorted = arr.slice().sort((a, b) => a - b);
    const avg    = arr.reduce((s, v) => s + v, 0) / arr.length;
    return {
      toolName,
      samples: arr.length,
      avg:     Math.round(avg),
      p50:     sorted[Math.floor(arr.length * 0.50)],
      p95:     sorted[Math.min(Math.floor(arr.length * 0.95), arr.length - 1)],
      min:     sorted[0],
      max:     sorted[arr.length - 1],
    };
  }
}

// --- Integration: wrap tool dispatch, check result size on return ---

const SIZE_DETECTOR = new ToolResultSizeDriftDetector({
  windowSize:     20,
  spikeRatio:     2.0,
  driftThreshold: 1.5,
});

async function callToolWithSizeCheck(toolName, args, executor) {
  const result     = await executor(toolName, args);
  const resultText = typeof result === 'string' ? result : JSON.stringify(result);
  const status     = SIZE_DETECTOR.check(toolName, resultText.length);

  if (status.status === 'SPIKE') {
    log({
      event:           'tool_result_size_spike',
      tool:            toolName,
      currentChars:    status.currentChars,
      rollingAvgChars: status.rollingAvgChars,
      spikeRatio:      status.spikeRatio,
      approxTokens:    Math.ceil(status.currentChars / 4),
    });
  } else if (status.status === 'DRIFT') {
    log({
      event:              'tool_result_size_drift',
      tool:               toolName,
      firstHalfAvgChars:  status.firstHalfAvgChars,
      secondHalfAvgChars: status.secondHalfAvgChars,
      driftRatio:         status.driftRatio,
      tokenDeltaPerCall:  Math.ceil((status.secondHalfAvgChars - status.firstHalfAvgChars) / 4),
    });
  }

  return result;
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `record()` and `check()` timed over 100 000 iterations. Window size 20. Three tool scenarios: stable, gradual drift, and single spike.

```
=== ToolResultSizeDriftDetector timing (100 000 iterations, windowSize=20) ===

record()            0.0003 ms
check() 20 samples  0.0010 ms

=== Scenario A: get_customer — stable at ~280 chars ===

20 calls: 275–285 chars (normal variance)

check('get_customer', 283):
{
  status:          'NORMAL',
  toolName:        'get_customer',
  currentChars:    283,
  rollingAvgChars: 280,
  samples:         20
}

=== Scenario B: get_orders — gradual drift 300 → 620 chars ===

First 10 calls: 290–308 chars  (API response before expansion)
Next 10 calls:  580–625 chars  (API added per-item tax codes and sub-statuses)

check('get_orders', 620):
{
  status:             'DRIFT',
  toolName:           'get_orders',
  firstHalfAvgChars:  299,
  secondHalfAvgChars: 602,
  driftRatio:         2.01,
  samples:            20
}

stats('get_orders'): { avg: 451, p50: 580, p95: 620, min: 290, max: 620 }

Cost impact of undetected drift:
  Before: 300 chars / 4 =  75 tokens per get_orders call
  After:  620 chars / 4 = 155 tokens per get_orders call
  Delta:  +80 tokens/call × 10 000 sessions/day × 3 calls/session
  = +2.4M tokens/day × $3.00/M Sonnet = +$7.20/day invisible cost creep

=== Scenario C: get_contract — single spike (PDF blob in response) ===

19 calls: 400–440 chars (normal, text-only summaries)
Call 20:  4 200 chars (API embedded raw PDF content for enterprise entity)

check('get_contract', 4200):
{
  status:          'SPIKE',
  toolName:        'get_contract',
  currentChars:    4200,
  rollingAvgChars: 419,
  spikeRatio:      10.03,
  samples:         20
}

approxTokens: ceil(4200 / 4) = 1050 tokens for this one call.
Action: log entity ID that triggered spike; add S-130 elision rule to exclude raw_content field.

=== S-97 vs S-130 vs F-95 vs S-156 ===

              │ S-97 (summarization)        │ S-130 (compression)         │ F-95 (cost attribution)     │ S-156 (size drift)
──────────────┼─────────────────────────────┼─────────────────────────────┼─────────────────────────────┼──────────────────────────────
When          │ Result arrives, > threshold │ Result arrives, structured  │ Periodic cost reporting     │ Every call, rolling window
Action        │ Compress before inject      │ Elide unused fields         │ Report tool cost share      │ Detect size trends and spikes
What it fixes │ Single large result         │ Fields agent doesn't need   │ Cost visibility             │ Silent growth in API payloads
Misses        │ Cause of large result       │ Doesn't detect trends       │ Can't isolate size growth   │ Doesn't summarize or compress
Compose       │ After: S-156 fires, S-97 acts on SPIKE │               │                             │ Fires → triggers S-97 / S-130
```

## See also

[S-97](s97-tool-result-summarization.md) · [S-130](s130-structured-tool-result-compression.md) · [F-95](../forward-deployed/f95-tool-invocation-cost-attribution.md) · [F-87](../forward-deployed/f87-tool-call-argument-audit-log.md) · [S-124](s124-api-response-change-rate-monitor.md) · [S-155](s155-tool-call-argument-size-cap.md)

## Go deeper

Keywords: `tool result size drift` · `API payload bloat detection` · `tool result size monitoring` · `LLM tool call overhead tracking` · `API response size growth` · `tool result spike detection` · `rolling window result size` · `tool payload drift alert` · `API schema expansion detection` · `agent tool cost drift`
