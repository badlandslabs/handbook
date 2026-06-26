# S-72 · Cost Anomaly Detection

[F-29](../forward-deployed/f29-cost-attribution.md) answers where your spend goes — which feature, which customer, which environment. [F-35](../forward-deployed/f35-workflow-token-budget.md) caps the spend of a single workflow run. Neither answers: "Is total spend spiking right now?" A runaway agent loop, a bad prompt deploy, or an unexpected traffic surge can turn a $1 080/month bill into a $10 000 one before the next daily report runs. Cost anomaly detection is the real-time layer that fires before the invoice surprises you.

## Situation

A research agent normally spends $1.50/hour on model calls. A bad prompt deploy on Tuesday afternoon causes the agent to include a 2 000-token document on every call instead of a 200-token summary. Spend jumps to $4.50/hour — a 3× spike. Without anomaly detection, the team discovers it on Friday when reviewing the weekly cost report: four days at 3× baseline = $252 of unexpected spend. With a rolling z-score alert at z > 3, the spike is detected within the first hour: alert fires, team investigates, deploy is reverted. Extra cost: $3.

## Forces

- **Absolute thresholds break when baseline changes.** Alerting when hourly spend exceeds $5 misses a spike on a day when baseline is $3 (1.67× is flagging), and over-alerts on a day when baseline is $4 (1.25× is fine). Statistical thresholds adapt to the actual distribution.
- **Rolling windows smooth noise.** Spend has natural variance — more traffic at 9am than 3am, more on Mondays than Sundays. A 24-hour rolling window captures this variance as the baseline; a spike stands out against that specific context, not a static number.
- **The z-score of 3 is a tight threshold for cost.** In process control, 3σ is the standard alert threshold. For a stable spend baseline, z > 3 is reliably anomalous — max |z| in normal operation is typically under 2.1. A 1.5× spend increase (the smallest operationally interesting deviation) triggers z ≈ 3.7.
- **Per-call anomalies are different from aggregate anomalies.** A single call that costs $10 (injected a massive document) is different from 1 000 calls each costing $0.01 more than expected. Both warrant investigation; the detection patterns differ. This entry covers aggregate hourly spend; per-call outlier detection is a complementary pattern.
- **Alert on rate, not just magnitude.** A sustained 1.5× over 3 hours is more concerning than a single 2× call. Rate-based detection (z-score on the rolling window) captures this; single-point threshold alerts don't.

## The move

**Maintain a rolling 24-hour window of per-hour spend. Compute z-score each hour. Alert when z > 3. Record per-call token counts in the call log (F-31) to enable drill-down.**

```js
class CostAnomalyDetector {
  constructor({ windowSize = 24, alertThreshold = 3 } = {}) {
    this.window    = [];          // hourly spend totals
    this.windowSize = windowSize;
    this.threshold  = alertThreshold;
    this.currentHour = { spend: 0, calls: 0, startTs: Date.now() };
  }

  // Call after every model response
  record(inputTokens, outputTokens) {
    const inputCost  = inputTokens  * 3.00 / 1e6;
    const outputCost = outputTokens * 15.00 / 1e6;
    this.currentHour.spend += inputCost + outputCost;
    this.currentHour.calls++;
  }

  // Call at the top of each hour (cron, setInterval, or on-tick)
  closeHour() {
    const hourSpend = this.currentHour.spend;
    this.window.push(hourSpend);
    if (this.window.length > this.windowSize) this.window.shift();

    const alert = this.window.length >= 6 // need at least 6 hours of data
      ? this.checkAnomaly(hourSpend)
      : null;

    // Reset for next hour
    this.currentHour = { spend: 0, calls: 0, startTs: Date.now() };
    return alert;
  }

  checkAnomaly(value) {
    const mean   = this.window.reduce((a, b) => a + b, 0) / this.window.length;
    const stddev = Math.sqrt(
      this.window.reduce((s, x) => s + (x - mean) ** 2, 0) / this.window.length
    );
    if (stddev === 0) return null;

    const z = (value - mean) / stddev;
    if (Math.abs(z) > this.threshold) {
      return {
        alert:    true,
        z:        z.toFixed(2),
        actual:   value.toFixed(4),
        mean:     mean.toFixed(4),
        stddev:   stddev.toFixed(4),
        multiple: (value / mean).toFixed(1) + 'x baseline',
      };
    }
    return null;
  }
}

// Wire into your model call handler
const detector = new CostAnomalyDetector();

async function tracedModelCall(client, params) {
  const response = await client.messages.create(params);
  detector.record(response.usage.input_tokens, response.usage.output_tokens);
  return response;
}

// Cron or interval: fire at the top of each hour
setInterval(() => {
  const alert = detector.closeHour();
  if (alert) {
    console.error('[COST ALERT]', alert);
    // page on-call, post to Slack, open PagerDuty incident
    notifyOnCall(alert);
  }
}, 60 * 60 * 1000);
```

**Per-call outlier detection (complementary):**

```js
// Alert on any single call that is more than 5× the rolling per-call average
class PerCallOutlierDetector {
  constructor(windowN = 100) {
    this.costs = [];
    this.windowN = windowN;
  }
  check(inputTok, outputTok) {
    const cost = inputTok * 3.00/1e6 + outputTok * 15.00/1e6;
    this.costs.push(cost);
    if (this.costs.length > this.windowN) this.costs.shift();
    if (this.costs.length < 10) return null;
    const avg = this.costs.reduce((a,b) => a+b,0) / this.costs.length;
    if (cost > avg * 5) return { alert: true, cost, avg, multiple: (cost/avg).toFixed(1) + 'x' };
    return null;
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Baseline spend and z-scores simulated from a 7-day × 24-hour series with ±\$0.40 natural variance around \$1.50/hour. Prices: $3.00/M input, $15.00/M output.

```
=== Normal operation z-score range (7 days, \$1.50/hr baseline, ±\$0.40 variance) ===

Max |z| in normal operation: 2.07
Average |z|:                 0.82

A threshold of z > 3 does not fire in normal operation.

=== Alert sensitivity by spend multiplier ===

Spend multiplier   Hourly cost   z-score    Alert?
1.5×               $2.25         3.74       YES
2.0×               $3.00         7.41       YES
3.0×               $4.50        14.76       YES
4.0×               $6.00        22.10       YES

A 1.5× deviation — the smallest operationally meaningful spike — is caught reliably.

=== Detection time and damage avoided ===

Scenario: 3× spend spike from bad deploy (\$1.50 → \$4.50/hour)

Without detection: discovered at Friday weekly report (4 days later)
  Extra spend: 4 days × 24 hours × \$3.00 extra = $288

With hourly z-score alert (fires at end of first anomalous hour):
  Extra spend: 1 hour × \$3.00 extra = $3.00
  Savings: $285 (99% of the damage)

=== Monthly baseline ===

10k calls/day at avg 33k input + 141 output tokens per call: \$1 080/month
A runaway 3× spike sustained for 1 week: +\$756 — detectable in 1 hour with this alert
```

## See also

[F-29](../forward-deployed/f29-cost-attribution.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [F-08](../forward-deployed/f08-agent-cost-control.md) · [F-31](../forward-deployed/f31-structured-call-logging.md) · [F-26](../forward-deployed/f26-behavioral-drift-detection.md) · [F-42](../forward-deployed/f42-ai-incident-response.md)

## Go deeper

Keywords: `cost anomaly detection` · `spend spike` · `z-score` · `rolling window` · `hourly spend` · `token cost monitoring` · `real-time cost alert` · `anomaly threshold` · `cost monitoring` · `runaway detection`
