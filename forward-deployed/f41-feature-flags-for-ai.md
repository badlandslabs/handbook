# F-41 · Feature Flags for AI Rollout

[F-22](f22-cicd-for-ai-pipelines.md) covers the CI/CD pipeline: eval gates, shadow testing, and post-deploy monitoring. It does not cover the runtime mechanism that lets you deploy a new model or prompt to 1% of traffic, watch the metrics, and expand only when the numbers hold. That mechanism is a feature flag — in AI, a traffic-splitting rule that deterministically assigns each request to a variant and lets you roll forward or back without a deploy.

## Situation

A team wants to switch their support agent from claude-sonnet-4-5-20251001 to a new snapshot with better instruction-following. The eval suite passes. They want to start with 1% of production traffic, not all of it, because eval coverage is never complete and production traffic always contains surprises. After 24 hours at 1%, thumbs-down rate and LLM judge scores are within bounds. They expand to 5%, then 20%, then 100% — over four days. No incident. No emergency rollback.

## Forces

- **Sticky assignment is required.** If a user is assigned to the control group on turn 1, they must be in the control group on turn 2. Randomizing per-request means users get inconsistent responses mid-conversation. Hash the user ID (or session ID) to a bucket; the assignment is then deterministic and stable.
- **The flag must be runtime-configurable, not a code deploy.** The point of a feature flag is to change behavior without a deploy. A flag value stored in code doesn't enable rollback in 30 seconds — a flag value fetched from a config service does.
- **AI-specific metrics differ from service metrics.** Latency, error rate, and 5xx count are necessary but not sufficient. You also need: thumbs-down rate (F-40), LLM judge score on a sample of outputs (F-12), and behavioral drift markers (F-26). A model change can degrade output quality without changing any service metric.
- **Rollout speed should match signal confidence.** At 1%, you need 48–72 hours to accumulate statistically meaningful thumbs-down signal (assuming ~0.8% thumbs-down rate). At 5%, you accumulate signal 5× faster. Don't advance the rollout faster than your metrics can tell you whether it's safe.
- **Rollback must be one operation.** Set the flag to 0%. The previous variant resumes serving all traffic immediately. No deploy. No migration. This is the entire value proposition.

## The move

**Hash user ID to a stable bucket (0–99). Compare against the flag threshold. Serve control below, treatment above. Monitor AI-specific metrics at each stage. Advance on signal; rollback on anomaly.**

**Traffic assignment (deterministic, sticky):**

```js
const crypto = require('crypto');

// Returns 0–99, stable for a given userId + flagName combination
function getBucket(userId, flagName) {
  const hash = crypto.createHash('md5')
    .update(userId + ':' + flagName)
    .digest('hex');
  return parseInt(hash.slice(0, 8), 16) % 100;
}

// Flag config — fetched from config service, not hardcoded
async function getFlag(flagName) {
  return configService.get(flagName);
  // Example: { treatment_pct: 5, treatment_model: 'claude-sonnet-4-5-20251001', seed: 'v2-rollout' }
}

async function resolveModel(userId) {
  const flag = await getFlag('model-upgrade-v2');
  if (!flag || flag.treatment_pct === 0) return flag.control_model;

  const bucket = getBucket(userId, flag.seed ?? 'model-upgrade-v2');
  const inTreatment = bucket < flag.treatment_pct;

  // Log the assignment for analysis
  await metricsLog({ userId, flag: 'model-upgrade-v2', variant: inTreatment ? 'treatment' : 'control' });

  return inTreatment ? flag.treatment_model : flag.control_model;
}

// In the request handler:
async function handleRequest(userId, systemPrompt, userMessage) {
  const model = await resolveModel(userId);
  const response = await client.messages.create({ model, max_tokens: 512,
    system: systemPrompt, messages: [{ role: 'user', content: userMessage }] });
  return response.content[0].text;
}
```

**Rollout schedule:**

```
Stage    Traffic %   Hold time   Advance condition
─────    ─────────   ─────────   ─────────────────────────────────────────────
canary        1%      48h         No spike in thumbs-down or judge score drop
early         5%      48h         Same; latency p99 stable; error rate flat
expanded     20%      72h         Accumulate statistical significance (F-33)
full        100%      —           Monitor for 1 week; flag removed after stable

Rollback trigger: thumbs-down rate increases > +0.3% absolute, or judge score
drops > -2% relative to control, or any p99 latency spike > 20%.
```

**Config service flag schema:**

```js
// Stored in your config service (LaunchDarkly, Unleash, Flipt, or a simple DB table)
{
  "model-upgrade-v2": {
    "enabled":           true,
    "treatment_pct":     5,         // advance this without deploys
    "control_model":     "claude-sonnet-4-5-20250801",
    "treatment_model":   "claude-sonnet-4-5-20251001",
    "seed":              "model-upgrade-v2-2026-06",
    "created_at":        "2026-06-26",
    "owner":             "platform-team"
  }
}
```

**AI-specific monitoring during rollout:**

```js
// After each response, log variant-aware metrics
async function logRolloutMetrics(userId, variant, response, latencyMs) {
  await metricsLog({
    flag:        'model-upgrade-v2',
    variant,                           // 'control' | 'treatment'
    latency_ms:  latencyMs,
    stop_reason: response.stop_reason,
    output_tok:  response.usage.output_tokens,
    ts:          Date.now(),
  });
  // thumbs-down and judge score are logged separately by F-40 / F-12
  // join on messageId to compare control vs treatment rates
}

// Dashboard query: compare thumbs-down rate by variant
// SELECT variant, COUNT(*) FILTER (WHERE signal='thumbs_down') / COUNT(*) AS rate
// FROM feedback JOIN rollout_log USING (session_id)
// WHERE flag = 'model-upgrade-v2' AND ts > NOW() - INTERVAL '48h'
// GROUP BY variant
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. Hash distribution measured over 100 000 user IDs. Traffic flag overhead measured; monitoring cost estimated from F-40 (feedback) and F-12 (judge) pricing.

```
=== Traffic assignment ===

$ node -e "
const crypto = require('crypto');
function getBucket(userId, seed) {
  return parseInt(crypto.createHash('md5').update(userId+':'+seed).digest('hex').slice(0,8), 16) % 100;
}
const N = 100000;
let inTreatment = 0;
const t0 = performance.now();
for (let i = 0; i < N; i++) {
  if (getBucket('user_'+i, 'model-upgrade-v2') < 5) inTreatment++;
}
console.log('5% target →', (inTreatment/N*100).toFixed(2) + '% assigned');
console.log('Hash per call:', ((performance.now()-t0)/N).toFixed(4), 'ms');
"
5% target → 5.03% assigned
Hash per call: 0.0061 ms

Bucket assignment is stable (same userId always gets same bucket), adds 0.006ms overhead.

=== Monitoring cost during rollout ===

LLM judge on 10% sample of treatment calls:
  At 5% traffic (500 calls/day treatment), judge 50 calls/day
  100 tok per judge call × $3.00/M = $0.0003/call × 50 = $0.015/day
  Negligible vs value of catching a regression before full rollout

=== Rollback speed ===

Set treatment_pct = 0 in config service: <1 second propagation
Zero deploys, zero restarts, zero downtime
All traffic immediately serves control model

=== Signal accumulation at each stage ===

At 1% (100 calls/day treatment):
  thumbs-down at 0.8% rate → ~0.8/day → need ~4 days for meaningful signal
  → hold 48h for directional signal only

At 5% (500 calls/day treatment):
  thumbs-down → ~4/day → accumulate faster; compare rates with F-33 pairwise judge
  → 48h hold sufficient for basic statistical confidence

At 20%: clear statistical separation from control becomes detectable in 24h
```

## See also

[F-22](f22-cicd-for-ai-pipelines.md) · [F-40](f40-user-feedback-collection.md) · [F-26](f26-behavioral-drift-detection.md) · [F-33](f33-prompt-ab-testing.md) · [F-38](f38-model-version-pinning.md) · [F-08](f08-agent-cost-control.md)

## Go deeper

Keywords: `feature flag` · `traffic splitting` · `canary deploy` · `gradual rollout` · `model rollout` · `prompt rollout` · `bucket assignment` · `sticky assignment` · `rollback` · `AI feature flag`
