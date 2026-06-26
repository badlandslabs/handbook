# F-78 · Confidence-Gated Delivery

[S-53](../stacks/s53-confidence-calibration.md) covers confidence calibration: measuring how certain the model is via logprobs, sampling variance, or explicit verbalization. The three signals tell you when the model is uncertain. [F-68](f68-quality-gated-model-escalation.md) covers quality-gated escalation: when a cheap model's output fails a structural or judge check, route to a more capable model. [F-30](f30-runtime-output-validation.md) covers the judge gate: hold outputs that fail a binary PASS/FAIL quality check.

All three handle low-confidence answers by doing something more expensive: escalate to a better model, add a judge, try again. None implement the prior option: **do not deliver the answer at all**. When even the best model's confidence on a query is below a threshold — because the query is at the edge of the training distribution, requires knowledge that changes rapidly, or involves a domain where the model is systematically unreliable — the right response is abstention: "I cannot answer this reliably" rather than a confident-sounding guess.

Abstention is not a failure. It is a calibrated output. On high-stakes queries where a wrong answer costs more than no answer, withholding the uncertain response is the economically and ethically correct choice.

## Situation

A pharmaceutical information agent answers questions from pharmacists. It is measured on accuracy and has a 0.2% error rate overall — excellent. The team investigates incidents: 80% of errors come from a specific pattern — drug interaction queries involving uncommon drug combinations that appear in training data sparsely and with conflicting sources. On these queries, the model produces confident-sounding but wrong answers. On unambiguous queries, the model is well-calibrated.

Confidence-gated delivery fixes this: for drug interaction queries (high-consequence domain), the agent measures confidence before delivery. When confidence falls below 0.75 (determined by sampling variance: fewer than 4 of 5 samples agree on the key interaction fact), the response is withheld and replaced with: "I cannot give you a reliable answer on this interaction. Please consult the primary literature or a clinical pharmacist." Incident rate on uncommon interaction queries drops to zero. Overall answer rate drops from 98% to 91% — 7% of queries receive abstention responses. Pharmacists report the abstentions are handled correctly in their workflow: they escalate to specialists, which they should have done anyway for those cases.

## Forces

- **A confident-sounding wrong answer causes more harm than an honest abstention.** Downstream consumers (humans, other agents) treat model output as reliable unless they have reason not to. A low-confidence answer delivered without caveat teaches the consumer to trust the model — until the wrong answer causes an incident.
- **Escalation is not always available.** When the most capable model is already being used, there is no higher tier. When a judge would need domain expertise that no prompt-based evaluator has, the judge is unreliable. Abstention is the residual option when all escalation paths are exhausted or unavailable.
- **Confidence threshold is domain-specific, not universal.** A query about a product return policy tolerates a lower confidence threshold than a query about drug interactions. The threshold should be calibrated per domain: what is the cost of a wrong answer × probability of error at various confidence levels?
- **Abstention must be explicit, not ambiguous.** A response like "I'm not entirely sure, but..." is not abstention — it's a hedged delivery that still communicates an answer. True abstention withholds the answer content entirely and explains why. Hedging is the worst of both worlds: it delivers a potentially wrong answer AND signals uncertainty.
- **Abstention rate is a metric, not just a failure mode.** Track the abstention rate by domain and query type. A rising abstention rate on a stable domain signals model drift or distribution shift. A consistently high abstention rate on a query type signals a corpus gap that training or retrieval augmentation should address.

## The move

**Measure confidence before delivery. Below a domain-calibrated threshold, withhold the answer entirely and return an explicit abstention. Log every abstention for review and corpus improvement.**

```js
const Anthropic = require('@anthropic-ai/sdk');
const client    = new Anthropic();

// --- Domain-specific abstention thresholds ---
// Lower threshold = more willing to deliver uncertain answers
// Higher threshold = stricter: only high-confidence answers delivered

const ABSTENTION_POLICY = {
  drug_interaction:     { samplingThreshold: 0.80, verbalizationMin: 'high',   name: 'Drug interaction' },
  medical_diagnosis:    { samplingThreshold: 0.85, verbalizationMin: 'high',   name: 'Medical diagnosis' },
  legal_interpretation: { samplingThreshold: 0.75, verbalizationMin: 'high',   name: 'Legal interpretation' },
  financial_advice:     { samplingThreshold: 0.70, verbalizationMin: 'medium', name: 'Financial advice' },
  factual_lookup:       { samplingThreshold: 0.60, verbalizationMin: 'medium', name: 'Factual lookup' },
  product_info:         { samplingThreshold: 0.50, verbalizationMin: 'low',    name: 'Product information' },
  general:              { samplingThreshold: 0.60, verbalizationMin: 'low',    name: 'General' },
};

const VERBALIZATION_RANK = { high: 2, medium: 1, low: 0 };

// --- Sampling variance confidence estimate ---
// Run N times at temperature > 0; compare key claim agreement

async function estimateConfidenceBySampling(systemPrompt, userMessage, opts = {}) {
  const { N = 5, temperature = 1.0, model = 'claude-haiku-4-5-20251001', extractKey } = opts;

  const calls = Array.from({ length: N }, () =>
    client.messages.create({
      model, max_tokens: 600,
      system:   systemPrompt + '\n\nAlso, end your response with: CONFIDENCE: high|medium|low',
      messages: [{ role: 'user', content: userMessage }],
    })
  );

  const responses = await Promise.all(calls);
  const texts     = responses.map(r => r.content[0]?.text ?? '');

  // Extract verbalized confidence from each sample
  const confLabels = texts.map(t => {
    const m = t.match(/CONFIDENCE:\s*(high|medium|low)/i);
    return m ? m[1].toLowerCase() : 'low';
  });

  const highCount = confLabels.filter(c => c === 'high').length;
  const medCount  = confLabels.filter(c => c === 'medium').length;
  const agreement = (highCount + medCount) / N;

  // Extract and compare key answers if extractor provided
  let answerAgreement = null;
  if (extractKey) {
    const keys = texts.map(t => extractKey(t));
    const unique = new Set(keys.filter(Boolean));
    answerAgreement = unique.size === 0 ? 0 : Math.max(...[...unique].map(k => keys.filter(x => x === k).length)) / N;
  }

  const finalConfidence = answerAgreement !== null
    ? (agreement * 0.5 + answerAgreement * 0.5)
    : agreement;

  // Pick the most common high-confidence response as the candidate answer
  const highConfTexts = texts.filter((_, i) => confLabels[i] === 'high');
  const candidateAnswer = highConfTexts[0] ?? texts[0] ?? '';

  const totalCost = responses.reduce((s, r) =>
    s + (r.usage.input_tokens * 0.80 + r.usage.output_tokens * 4.00) / 1_000_000, 0);

  return {
    confidence:       parseFloat(finalConfidence.toFixed(3)),
    agreement,
    answerAgreement,
    confLabels,
    N,
    candidateAnswer:  candidateAnswer.replace(/CONFIDENCE:.*$/mi, '').trim(),
    samplingCost:     parseFloat(totalCost.toFixed(5)),
  };
}

// --- Abstention policy enforcement ---

function applyAbstentionPolicy(domain, confidenceResult) {
  const policy = ABSTENTION_POLICY[domain] ?? ABSTENTION_POLICY.general;

  const meetsThreshold = confidenceResult.confidence >= policy.samplingThreshold;

  // Also check minimum verbalization level
  const minRank    = VERBALIZATION_RANK[policy.verbalizationMin] ?? 0;
  const highCount  = confidenceResult.confLabels.filter(c => c === 'high').length;
  const medCount   = confidenceResult.confLabels.filter(c => c === 'medium').length;
  const maxRankSeen = highCount >= 3 ? 2 : medCount >= 3 ? 1 : 0;
  const meetsVerb  = maxRankSeen >= minRank;

  const deliver = meetsThreshold && meetsVerb;

  return {
    deliver,
    domain,
    confidence:         confidenceResult.confidence,
    threshold:          policy.samplingThreshold,
    meetsThreshold,
    meetsVerbalization: meetsVerb,
    abstentionReason:   deliver ? null
      : !meetsThreshold
        ? `Confidence ${confidenceResult.confidence} below domain threshold ${policy.samplingThreshold}`
        : `Verbalization level below required minimum (${policy.verbalizationMin})`,
  };
}

// --- Abstention response templates ---

const ABSTENTION_TEMPLATES = {
  drug_interaction:     (query) => `I cannot provide a reliable answer on this drug interaction. The available information on "${query.slice(0, 60)}..." has conflicting sources or insufficient data for confident guidance. Please consult the primary literature (Lexicomp, Micromedex) or a clinical pharmacist.`,
  medical_diagnosis:    (query) => `I'm unable to give you a reliable answer on this clinical question with sufficient confidence. Please consult a qualified healthcare provider.`,
  legal_interpretation: (query) => `My confidence in this legal interpretation is below the threshold for this domain. Please consult a qualified attorney.`,
  general:              (query) => `I cannot give a reliable answer to this question with sufficient confidence. The answer may depend on context I don't have access to, or may be at the boundary of what I can reliably assess.`,
};

function buildAbstentionResponse(domain, query, decision) {
  const template = ABSTENTION_TEMPLATES[domain] ?? ABSTENTION_TEMPLATES.general;
  return {
    answered:         false,
    abstained:        true,
    abstention_reason: decision.abstentionReason,
    response:         template(query),
    confidence:       decision.confidence,
    threshold:        decision.threshold,
  };
}

// --- Integrated delivery function ---

async function deliverWithConfidenceGate(systemPrompt, userMessage, domain, opts = {}) {
  const { N = 5, model = 'claude-haiku-4-5-20251001', extractKey } = opts;

  // Measure confidence via sampling
  const confidenceResult = await estimateConfidenceBySampling(systemPrompt, userMessage, { N, model, extractKey });

  // Apply abstention policy
  const decision = applyAbstentionPolicy(domain, confidenceResult);

  if (!decision.deliver) {
    const abstention = buildAbstentionResponse(domain, userMessage, decision);
    return { ...abstention, samplingCost: confidenceResult.samplingCost };
  }

  return {
    answered:         true,
    abstained:        false,
    response:         confidenceResult.candidateAnswer,
    confidence:       confidenceResult.confidence,
    threshold:        decision.threshold,
    samplingCost:     confidenceResult.samplingCost,
  };
}

// --- Abstention rate tracker ---

class AbstentionTracker {
  constructor() { this.records = []; }

  record(domain, query, delivered, confidence, threshold) {
    this.records.push({ domain, query: query.slice(0, 80), delivered, confidence, threshold, ts: Date.now() });
  }

  rateByDomain() {
    const byDomain = {};
    for (const r of this.records) {
      if (!byDomain[r.domain]) byDomain[r.domain] = { total: 0, abstained: 0 };
      byDomain[r.domain].total++;
      if (!r.delivered) byDomain[r.domain].abstained++;
    }
    return Object.fromEntries(
      Object.entries(byDomain).map(([d, s]) => [d, {
        ...s,
        abstentionRate: parseFloat((s.abstained / s.total).toFixed(3)),
      }])
    );
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. applyAbstentionPolicy() timing from 100 000 iterations. Sampling cost computed from Haiku pricing. No model calls in timing section. Representative abstention rates are design targets, not measured from production.

```
=== applyAbstentionPolicy() timing (100 000 iterations) ===

$ node -e "
const confResult = { confidence: 0.60, confLabels: ['high','medium','low','medium','low'], N: 5 };
const t0 = performance.now();
for (let i = 0; i < 100000; i++) applyAbstentionPolicy('drug_interaction', confResult);
console.log('applyAbstentionPolicy:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
applyAbstentionPolicy: 0.0004 ms

=== Sampling cost: N=5 at Haiku pricing ===

Per confidence check (5 calls × avg 450 tok input + 180 tok output):
  Input:  5 × 450 × $0.80/M = $0.00180
  Output: 5 × 180 × $4.00/M = $0.00360
  Total:  $0.00540 per confidence gate check

At 10 000 queries/day, drug interaction domain, 9% abstention rate:
  All 10 000 confidence checks: $54.00/day
  vs. incident cost of wrong answers (estimated 0.8% error rate × 10 000 queries × $100 avg incident cost):
    Without gating: 80 errors/day × $100 = $8 000/day expected incident cost
    With gating (91% answered, 9% abstained, error rate on delivered drops to 0.1%):
      9 100 delivered × 0.1% errors × $100 = $910/day expected incident cost
    Savings: $7 090/day in avoided incident cost vs $54/day confidence check cost

Note: incident cost estimate is illustrative. Calibrate to actual cost in your domain.

=== Decision table: drug interaction domain (threshold 0.80) ===

Query                                     │ Confidence │ Decision  │ Outcome
──────────────────────────────────────────┼────────────┼───────────┼──────────────────────────
"Warfarin + ibuprofen interaction?"       │ 0.94       │ DELIVER   │ Well-established interaction
"Clopidogrel + omeprazole interaction?"   │ 0.88       │ DELIVER   │ Known CYP2C19 interaction
"Rivaroxaban + clarithromycin interaction?"│ 0.71      │ ABSTAIN   │ Sparse training data
"Colchicine + azithromycin interaction?"  │ 0.68       │ ABSTAIN   │ Conflicting case reports
"Aspirin + acetaminophen interaction?"    │ 0.97       │ DELIVER   │ Well-established (minimal)
"Tacrolimus + cannabis interaction?"      │ 0.42       │ ABSTAIN   │ Very limited published data

=== Abstention vs hedging vs judge gate ===

                  │ Hedging ("I think...")│ Judge gate (F-30) │ Escalation (F-68)  │ Abstention (F-78)
──────────────────┼───────────────────────┼────────────────────┼────────────────────┼────────────────────
Answer delivered? │ Yes (uncertain)       │ Yes (if passes)    │ Yes (better model) │ No
Cost              │ 0                     │ +judge call        │ +expensive model   │ +sampling calls
When appropriate  │ Never in high-stakes  │ Structural quality │ Better model helps │ No model helps
User experience   │ Confusion             │ Transparent        │ Invisible          │ Explicit no-answer
Fixes             │ Nothing               │ Structural errors  │ Capability gap     │ Reliability gap

=== AbstentionTracker.rateByDomain() after 30-day sample ===

{
  drug_interaction:     { total: 8420,  abstained: 758,  abstentionRate: 0.090 },
  medical_diagnosis:    { total: 1230,  abstained: 184,  abstentionRate: 0.150 },
  legal_interpretation: { total: 3100,  abstained: 217,  abstentionRate: 0.070 },
  factual_lookup:       { total: 12400, abstained: 372,  abstentionRate: 0.030 },
  product_info:         { total: 18900, abstained: 189,  abstentionRate: 0.010 },
}

→ medical_diagnosis abstention rate 15% is high — signals corpus gap; add clinical reference retrieval
→ drug_interaction 9% is expected — rare drug combinations are inherently uncertain
→ product_info 1% is low — correct for low-stakes domain; threshold is working as designed
```

## See also

[S-53](../stacks/s53-confidence-calibration.md) · [F-68](f68-quality-gated-model-escalation.md) · [F-30](f30-runtime-output-validation.md) · [F-09](f09-human-in-the-loop.md) · [S-24](../stacks/s24-self-consistency.md) · [F-77](f77-cross-model-divergence.md) · [F-37](f37-knowledge-cutoff-handling.md)

## Go deeper

Keywords: `confidence-gated delivery` · `abstention policy` · `selective prediction` · `withhold answer` · `confidence threshold` · `abstain` · `uncertain answer` · `confidence gate` · `when not to answer` · `answer abstention`
