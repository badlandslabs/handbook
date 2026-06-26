# F-45 · AI Response Latency SLOs

[S-35](../stacks/s35-latency-budget.md) covers how to decompose the latency budget of a single AI request — where the milliseconds go, which components to optimize, how to structure parallel calls. That's design-time analysis. This entry covers the runtime operational layer: setting latency targets, measuring them from production data, and alerting before users notice degradation.

## Situation

A support AI endpoint had a P95 of 1 800ms at launch. Eight weeks later it's 2 700ms. No alert fired because the service returned 200s throughout — the quality of the response isn't what's slow, the time-to-first-token is. Customers started leaving negative reviews about "slow responses." The team discovered the regression by reading reviews, not dashboards. An SLO monitor would have fired within one hour of the P95 crossing 2 000ms.

## Forces

- **P50 is misleading for AI systems.** Median latency often looks fine while the tail is broken. A model call that includes a vector search, a slow tool, or a long output will push P95 to 3× the median. Alert on P95, not average.
- **Static thresholds ("alert if any call > 5s") miss sustained degradation.** If P95 creeps from 1 800ms to 2 700ms over three weeks, no single call crosses a 5s threshold. A percentile-based monitor catches the trend.
- **Error budget framing converts an abstract metric into a decision.** An SLO of "95% of requests under 2 000ms" means 5% of requests are the error budget. If 8% are over 2 000ms, the budget is 60% burned. That number drives action — it's not a graph to admire, it's a countdown.
- **Rolling window percentile is accurate enough and cheap to compute.** For windows under 500 samples, a sorted-array percentile is 0.07ms — negligible overhead and exact. Approximations like t-digest are not needed at this scale.
- **Set SLOs per endpoint, not per system.** A document upload endpoint has a different latency profile than a real-time chat endpoint. Mixing them blurs both signals.

## The move

**Record latency on every model call. Compute P50 and P95 from a rolling window every minute. Alert when P95 exceeds the target. Track error budget burn rate — alert when >50% burned before the end of the period.**

**Latency SLO monitor:**

```js
class LatencySLO {
  constructor({ name, target_p50_ms, target_p95_ms, windowSize = 200, budgetPct = 5 }) {
    this.name       = name;
    this.targets    = { p50: target_p50_ms, p95: target_p95_ms };
    this.window     = [];
    this.windowSize = windowSize;
    this.budgetPct  = budgetPct;     // % of requests allowed to exceed target_p95_ms
  }

  record(latencyMs) {
    this.window.push(latencyMs);
    if (this.window.length > this.windowSize) this.window.shift();
  }

  check() {
    if (this.window.length < 20) return null;   // not enough data yet

    const sorted = [...this.window].sort((a, b) => a - b);
    const p50 = sorted[Math.floor(sorted.length * 0.50)];
    const p95 = sorted[Math.floor(sorted.length * 0.95)];
    const violations = this.window.filter(l => l > this.targets.p95).length;
    const violationPct = violations / this.window.length * 100;
    const budgetBurnPct = violationPct / this.budgetPct * 100;

    return {
      name:          this.name,
      p50,  p95,
      p50_ok:        p50 <= this.targets.p50,
      p95_ok:        p95 <= this.targets.p95,
      violationPct:  +violationPct.toFixed(1),
      budgetBurnPct: +budgetBurnPct.toFixed(0),  // >100 = SLO already breached this window
      samples:       this.window.length,
    };
  }
}

// One SLO per endpoint
const slos = {
  chat:     new LatencySLO({ name: 'chat',     target_p50_ms: 800,  target_p95_ms: 2000 }),
  analysis: new LatencySLO({ name: 'analysis', target_p50_ms: 3000, target_p95_ms: 8000 }),
};
```

**Wire into request handlers:**

```js
async function handleChatRequest(req, res) {
  const t0 = Date.now();
  try {
    const response = await client.messages.create({
      model: 'claude-haiku-4-5-20251001', max_tokens: 512,
      messages: [{ role: 'user', content: req.body.message }],
    });
    const latency = Date.now() - t0;
    slos.chat.record(latency);
    return res.json({ text: response.content[0].text, latencyMs: latency });
  } catch (err) {
    slos.chat.record(Date.now() - t0);  // record latency even on error
    throw err;
  }
}
```

**Periodic SLO check (every minute):**

```js
function checkAllSLOs() {
  for (const slo of Object.values(slos)) {
    const status = slo.check();
    if (!status) continue;

    // Log all SLO statuses for dashboards
    console.log('[slo]', JSON.stringify(status));

    // Alert conditions
    if (!status.p95_ok) {
      notifyOnCall({
        severity: 'high',
        title:    `SLO BREACH: ${slo.name} P95 = ${status.p95}ms (target: ${slo.targets.p95}ms)`,
        body:     status,
      });
    } else if (status.budgetBurnPct > 50) {
      notifyOnCall({
        severity: 'warn',
        title:    `SLO WARNING: ${slo.name} error budget ${status.budgetBurnPct}% burned`,
        body:     status,
      });
    }
  }
}

setInterval(checkAllSLOs, 60_000);
```

**SLO targets by call type (starting points; tune to your p95 baseline + 20% headroom):**

| Endpoint type | P50 target | P95 target | Error budget |
|---|---|---|---|
| Real-time chat | 800ms | 2 000ms | 5% |
| Document analysis | 3 000ms | 8 000ms | 5% |
| Background summarization | 10 000ms | 30 000ms | 10% |
| Batch classification | 2 000ms | 6 000ms | 10% |

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Latency window: 200 samples. Distribution simulated with 5% outliers at 2 000–3 500ms to model realistic AI call tails. SLO check measured with `performance.now()`.

```
=== SLO check performance (200-sample window) ===

$ node -e "
const window = Array.from({length: 200}, (_, i) =>
  i < 10 ? 2000 + i * 150 : 400 + Math.floor(Math.random() * 1200)
);
const N = 1000000; const t0 = performance.now();
for (let i = 0; i < N; i++) {
  const s = [...window].sort((a,b)=>a-b);
  const p50 = s[Math.floor(s.length*0.50)];
  const p95 = s[Math.floor(s.length*0.95)];
  const viol = window.filter(l=>l>2000).length;
}
console.log('Full SLO check per call:', ((performance.now()-t0)/N).toFixed(4), 'ms');
"
Full SLO check per call: 0.0718 ms

Overhead: 0.07ms per check, called once per minute — effectively zero.

=== Example 200-sample window ===

Percentile   Latency
P50          1 008ms
P90          1 536ms
P95          2 000ms   ← at SLO target (2 000ms)
P99          3 200ms

Requests over 2 000ms target: 9/200 = 4.5%
Error budget (5% target):     10/200 requests
Budget burned:                 9/10 = 90%
Action:                        alert at 50% budget burn (5/10), page at breach (>10/10)

=== Detection time ===

Scenario: P95 degrades from 1 800ms → 2 700ms over 3 hours (slow rollout of bad deploy)

Minute 60:  10 calls have exceeded 2 000ms in the 200-sample window (5%) → budget at 100% → alert fires
vs.         reviewer checks the latency graph on Thursday → 3-hour degradation undetected

With SLO monitor: fires within 1 hour of regression crossing target.
Without: detected on the next dashboard review cycle.
```

## See also

[S-35](../stacks/s35-latency-budget.md) · [S-72](../stacks/s72-cost-anomaly-detection.md) · [F-42](f42-ai-incident-response.md) · [F-26](f26-behavioral-drift-detection.md) · [F-31](f31-structured-call-logging.md) · [S-69](../stacks/s69-streaming-cancellation.md)

## Go deeper

Keywords: `latency SLO` · `P95 latency` · `error budget` · `latency percentile` · `rolling window` · `SLO breach` · `latency monitoring` · `AI response time` · `production AI observability` · `TTFT`
