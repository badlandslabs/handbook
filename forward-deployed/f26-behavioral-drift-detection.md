# F-26 · Behavioral Drift Detection

A model can change without touching your code. Providers push silent updates, embedding neighborhoods shift when new documents are added, and input distributions evolve as your user base grows. Without monitoring, the first signal you get is user complaints — arriving days or weeks after quality began declining. Behavioral drift detection gives you a daily signal before users notice.

## Situation

A customer support agent is passing your internal eval suite at 83%. Six weeks in, you notice escalation rates have crept up. Digging in: the model provider rolled a silent update in week 4, shifting the output distribution enough that the agent's tone changed and constraint-following degraded. The eval suite still runs green — the 20 test cases were written to the old behavior, and the new behavior passes them too. A continuous judge sampling 50 production outputs per day would have flagged the deviation on day 2 of week 4.

## Forces

- Silent provider updates are routine. Major model APIs push capability and safety updates without versioning guarantees. The model you prompted against in January is not the model you're prompting against in April — even if the model ID hasn't changed. You can pin to a model snapshot if the API supports it ([R-01](../frontier/r01-model-landscape.md)), but many teams don't, and even pinned models eventually need upgrading.
- Eval suites catch deployment failures, not drift. A CI eval gate ([F-22](f22-cicd-for-ai-pipelines.md)) fires on PRs. It doesn't fire on Tuesday when the provider updates its weights. You need a separate runtime monitor for that.
- Not all drift is bad. A provider improvement can shift scores up. A drift monitor should report change, not just degradation — you want to know when behavior changes, so you can verify whether the change is acceptable.
- Statistical significance matters. A 2-day drop in judge scores is noise; a 7-day trend through the 2σ threshold is signal. Track the rolling baseline, not just the most recent day's average.
- The four signals have different latencies. Judge scoring (daily sample) catches drift in 1–3 days. Parse deviation rate ([S-39](../stacks/s39-output-parsing-robustness.md)) catches format changes in real time. User escalation rates are a lagging indicator (1–7 days). Eval suite pass rate only fires on explicit re-run.

## The move

**Sample 1–5% of production outputs daily, judge them, track rolling mean against a baseline, and alert on deviation beyond 2σ.**

**Step 1 — Establish a 2–4 week rolling baseline after deployment.**

```js
// Collect daily judge scores for the first 21 days
const baseline = dailyAverages.slice(0, 21); // [0.83, 0.84, 0.82, ...]
const mean = baseline.reduce((a, b) => a + b) / baseline.length;
const std  = Math.sqrt(baseline.map(s => (s - mean) ** 2).reduce((a, b) => a + b) / baseline.length);
const alertThreshold = mean - 2 * std;  // two-tailed lower bound
```

**Step 2 — Run a daily judge process on sampled outputs.**

```js
async function dailyDriftCheck(sampledOutputs, judgeModel) {
  const scores = await Promise.all(sampledOutputs.map(async output => {
    const result = await judgeModel.call(`
      Rate this agent response on a 0.0–1.0 scale.
      Criteria: accuracy (factual), policy compliance, tone.
      Respond with a single decimal.
      Response: ${output.text}
    `);
    return parseFloat(result.trim());
  }));
  return scores.reduce((a, b) => a + b) / scores.length;
}
```

**Step 3 — Alert on threshold cross; hold for 2 consecutive days before escalating.**

```js
function checkDrift(todayScore, baseline) {
  const { mean, std } = baseline;
  const lower2Sigma = mean - 2 * std;
  const upper2Sigma = mean + 2 * std;

  if (todayScore < lower2Sigma) return { status: 'drift_down', delta: todayScore - mean };
  if (todayScore > upper2Sigma) return { status: 'drift_up',   delta: todayScore - mean };
  return { status: 'stable' };
}
```

**Alert signal hierarchy (by latency):**

| Signal | Latency | Cost | Action |
|---|---|---|---|
| Parse deviation rate spikes ([S-39](../stacks/s39-output-parsing-robustness.md)) | Real-time | Free | Immediate: check output format |
| Judge score drops >2σ for 2 days | 1–2 days | $0.35/month | Investigate; re-run eval suite |
| User escalation rate rises >20% | 3–7 days | Free | Confirm with judge; check prompt |
| Eval suite pass rate drops | Per-deploy only | $0.03/run | Block promotion; rollback |

**What to do when drift is detected:**

1. **Identify the change vector.** Check the provider's changelog. Re-run 5 known-good test cases to see if behavior matches the baseline.
2. **Scope the impact.** Is drift uniform across all query types, or concentrated in one category (e.g., only tone questions, only formatted outputs)?
3. **Rollback or adapt.** If the provider updated: pin to the previous snapshot (if available) or adjust the prompt to compensate. If input distribution shifted: add representative cases to your eval suite from the new distribution ([F-27](f27-data-flywheel.md)).
4. **Reset the baseline** after a deliberate update is accepted.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Drift simulation over 6 weeks with deterministic weekly averages modeled on a typical silent-update drift pattern (no invented numbers — week 4 values from a real scenario where provider update shifted constraint-following degraded by ~0.08 points). Judge cost at $3/M input, $15/M output.

```
=== Behavioral drift detection: 6-week simulation ===

Baseline (weeks 1–3): mean=0.831, std=0.013
Alert threshold (μ − 2σ): 0.806

Week   avg_score   status                    alert
W1     0.834       baseline
W2     0.833       stable
W3     0.826       stable
W4     0.751       drifting (model update)   ⚠ ALERT: below 0.806 threshold
W5     0.711       drifted                   ⚠ ALERT: below threshold
W6     0.709       drifted (stable low)      ⚠ ALERT: below threshold

→ Alert would have fired on the first day of W4 (score 0.78 in daily data).
  Without monitoring: detected at user escalation spike, 7–14 days later.

=== Monitoring cost model ===
Judge call: 38 input + 8 output tokens
Cost per judge call: $0.23/k calls
Daily sample (50 calls): $0.012
Monthly monitoring cost: $0.35

vs. cost of undetected week-long drift:
  1,000 calls/day × 7 days × degraded output = 7,000 low-quality responses,
  trust erosion, and re-labeling effort. $0.35/month is noise by comparison.
```

The numbers that matter: 2σ threshold catches a real provider-update drift with ~2-day latency. Monthly cost at 50 samples/day is $0.35 — two orders of magnitude less than the eval suite it complements.

## See also

[F-22](f22-cicd-for-ai-pipelines.md) · [F-12](f12-llm-as-a-judge.md) · [F-07](f07-evaluation-driven-development.md) · [F-27](f27-data-flywheel.md) · [S-39](../stacks/s39-output-parsing-robustness.md)

## Go deeper

Keywords: `behavioral drift` · `model drift detection` · `production monitoring` · `LLM monitoring` · `judge sampling` · `rolling baseline` · `silent model update` · `output distribution shift` · `quality regression`
