# S-53 · Confidence Calibration

A model that is wrong 30% of the time is useful if you know which 30%. A model that is wrong 5% of the time is dangerous if you can't tell which 5%. Confidence calibration is the practice of reading the model's own uncertainty signals — logprobs, sampling variance, explicit verbalization — and routing based on them. The goal is not to make the model more accurate; it's to route low-confidence outputs to a human or a clarification request before they become errors.

## Situation

An agent classifies customer support tickets by urgency and routes them to queues. It's accurate 87% of the time overall. The remaining 13% are tickets where the input is ambiguous: requests that could be billing or technical, tickets written in unusual phrasing, multi-issue requests. These 13% are concentrated in a detectable signal: when the model is uncertain, its top-token logprob is below −0.70 (probability under 50%). Adding a routing step that sends logprob < −0.70 tickets to a human review queue reduces the error rate on auto-routed tickets to 3% at the cost of flagging 18% for manual review — a trade-off worth making.

## Forces

- The model cannot reliably self-report uncertainty in long prose. A model asked "are you confident?" will often say yes regardless. Structured signals (logprobs, sampling variance) are more reliable than open-ended self-reports.
- Logprobs are the highest-signal and cheapest confidence indicator. For short, structured outputs — classification labels, yes/no decisions, single-value extractions — the logprob of the top token is a direct probabilistic calibration signal. It costs nothing extra; it just requires enabling `logprobs: true` in the API call.
- Sampling variance (self-consistency at N > 1) works for tasks where logprobs aren't available or useful. Generate N responses at temperature 1.0; if ≥4/5 agree, confidence is high. If 3/5 agree, confidence is borderline. This is 5× more expensive than a single call.
- Explicit verbalization is the cheapest fallback when neither logprobs nor multi-sampling are viable. Asking the model to append `CONFIDENCE: [high|medium|low]` costs 11 tokens per output and gives a usable signal for routing, though it relies on instruction-following quality.
- Calibration is task-specific. A model that is well-calibrated on factual lookups may be poorly calibrated on subjective judgments. Verify calibration on your specific task, not on benchmarks. The right threshold for "escalate" depends on your task's error cost vs. escalation cost.
- Confidence routing is not a replacement for evals. It catches individual uncertain outputs at runtime. It doesn't tell you about systemic prompt failures. Both are needed.

## The move

**Pick the confidence signal that fits your output type: logprobs for single-token outputs, sampling variance for short classifications, verbalization for free-text. Set routing thresholds based on your error/escalation cost trade-off.**

**Signal 1 — Logprobs (single-token or short structured output):**

```js
const response = await client.messages.create({
  model: 'claude-sonnet-4-6',
  // OpenAI: add logprobs: true, top_logprobs: 5
  // Anthropic: check API version — logprobs are available on select endpoints
  messages: [{ role: 'user', content: 'Classify: billing, technical, or general? Reply with one word.' }],
});

const topLogprob = response.logprobs?.content[0]?.logprob ?? null;
const confidence = topLogprob !== null ? Math.exp(topLogprob) : null;

function routeByLogprob(confidence) {
  if (confidence === null)  return 'verbalized_fallback';
  if (confidence > 0.90)    return 'proceed';
  if (confidence > 0.60)    return 'proceed_and_log';
  return 'human_review';
}
```

**Signal 2 — Sampling variance (N=5 at T=1.0):**

```js
async function confidenceByVoting(prompt, model, N = 5) {
  const responses = await Promise.all(
    Array.from({ length: N }, () =>
      client.messages.create({ model, temperature: 1.0, messages: [{ role: 'user', content: prompt }] })
        .then(r => r.content[0].text.trim().toLowerCase())
    )
  );
  const counts  = {};
  responses.forEach(r => { counts[r] = (counts[r] || 0) + 1; });
  const topAnswer = Object.entries(counts).sort((a, b) => b[1] - a[1])[0];
  return { answer: topAnswer[0], confidence: topAnswer[1] / N, votes: counts };
}

const result = await confidenceByVoting('Is this ticket urgent? Answer yes or no.', 'claude-haiku-4-5-20251001');
// { answer: 'yes', confidence: 0.8, votes: { yes: 4, no: 1 } }
```

**Signal 3 — Explicit verbalization (fallback):**

```
Add to your prompt:
"After your answer, add on a new line: CONFIDENCE: [high|medium|low]
  high   = you are certain based on clear evidence in the input
  medium = the input is somewhat ambiguous
  low    = insufficient information; answer is a best guess"
```

```js
function parseVerbalized(output) {
  const match = output.match(/CONFIDENCE:\s*(high|medium|low)/i);
  return match ? match[1].toLowerCase() : 'unknown';
}
// Route: high → proceed; medium → proceed + log; low → escalate
```

**Routing decision table:**

| Signal | Threshold | Action |
|---|---|---|
| Logprob > 0.90 | p > 90% | Proceed directly |
| Logprob 0.60–0.90 | p 60–90% | Proceed + flag for periodic review |
| Logprob < 0.60 | p < 60% | Human review queue |
| Sampling 5/5 or 4/5 agree | ≥80% | Proceed with majority answer |
| Sampling 3/5 agree | 60% | Request clarification or escalate |
| Verbalized "high" | — | Proceed |
| Verbalized "medium" | — | Proceed + log |
| Verbalized "low" | — | Escalate immediately |

**Setting thresholds.** The right threshold depends on: (1) what a wrong answer costs (support queue misroute = low; medical triage = high); (2) what escalation costs (human review time). Measure your error rate at each threshold on a sample of labeled production outputs before choosing.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Logprob signal modeled using exact `exp(logprob)` math for three realistic classification outputs. Sampling variance using deterministic agreement ratios (not model calls — the voting logic is deterministic given fixed samples). Verbalization overhead measured by tokenizing the added instruction. Calibration percentages (high→90%, medium→70%, low→45%) are directional estimates from published LLM calibration research; verify on your own task distribution.

```
=== Signal 1: Logprobs (classification example) ===

Output                  logprob   prob    action
"billing" (clear)       −0.04     96.1%   route directly
"technical" (mixed)     −0.82     44.0%   escalate to human
"billing" (ambiguous)   −1.31     27.0%   escalate to human

=== Signal 2: Sampling variance (N=5 at T=1.0) ===

Question                              Agreement   Confidence   Action
"What is 2+2?"                        5/5         100%         use "4" directly
"Is this review positive?"            4/5          80%         use "yes" directly
"Should we escalate this ticket?"     3/5          60%         flag; request clarification

Cost: single call $0.099/k  |  N=5: $0.495/k  |  5× overhead for binary decisions

=== Signal 3: Explicit verbalization ===
Prompt overhead:   +11 tokens per output
high  → observed accuracy ~90%  (well-calibrated for factual tasks)
medium → ~70%  (correct to flag these)
low   → ~45%   (near-chance — always escalate)
```

The cost/benefit of each signal: logprobs are zero overhead for the right task; sampling variance is 5× but no prompt change needed; verbalization is 11 tokens and works anywhere. Use them in that order of preference.

## See also

[S-24](s24-self-consistency.md) · [F-09](../forward-deployed/f09-human-in-the-loop.md) · [S-06](s06-model-routing.md) · [F-12](../forward-deployed/f12-llm-as-a-judge.md) · [F-26](../forward-deployed/f26-behavioral-drift-detection.md)

## Go deeper

Keywords: `confidence calibration` · `logprobs` · `uncertainty estimation` · `sampling variance` · `self-consistency` · `confidence routing` · `model uncertainty` · `escalation routing` · `abstention` · `selective prediction`
