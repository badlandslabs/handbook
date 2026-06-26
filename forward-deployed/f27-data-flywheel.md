# F-27 · Data Flywheel

The best training and eval data comes from real users doing real things. Production outputs are the only source that can't be hand-crafted or synthetically approximated — they capture the distribution of actual requests, the edge cases your specs didn't anticipate, and the failure modes that matter because they're happening. The data flywheel is the practice of turning production traffic into a continuously improving eval suite and, eventually, training data.

## Situation

You ship with 20 hand-crafted eval cases. Six weeks in, your pass rate is 87%. The problem: those 20 cases were written before you knew what users would actually ask. Real traffic includes billing disputes, account merge requests, and edge cases that nobody wrote a test for — and a non-trivial fraction of those are getting bad responses right now. You're measuring quality on the distribution you imagined, not the distribution you have. The flywheel closes that gap: sample real outputs, judge them, promote the failures and golden examples to your eval suite, iterate.

## Forces

- Eval suites written before launch test an imagined distribution. They're necessary but not sufficient. Real traffic always produces unexpected inputs; handcrafted evals miss them. A suite that only tests anticipated inputs gives false confidence.
- Labeling at scale is expensive; sampling is not. You can't judge every output. But 1–5% sampling, judged automatically with an LLM judge ([F-12](f12-llm-as-a-judge.md)), is cheap enough to run daily. A week of sampling costs less than a single hour of human labeling.
- Promotion thresholds matter more than volume. Not every sampled output goes into the eval suite. High-confidence fails (judge score < 0.60) become regression tests. High-confidence wins (score > 0.90) become golden examples for few-shot selection ([S-44](../stacks/s44-few-shot-example-selection.md)). The middle band is noise — discard it.
- Synthetic evals (F-17) bootstrap the flywheel; real data matures it. Use synthetic eval generation ([F-17](f17-synthetic-eval-generation.md)) to cover the known distribution at launch. As production traffic accumulates, real cases replace or supplement synthetic ones for the distribution they cover. The two are complementary, not competing.
- The flywheel compounds but slowly. Quality improvements from eval suite expansion take weeks, not days. Don't expect a 10-point jump week-over-week; expect 2–5 percentage points of consistent drift upward as the suite becomes more representative.
- Fine-tuning is the next stage of the flywheel, not the first. Once you have 500–1,000 labeled production examples (a few months at low traffic, weeks at high), you have a real fine-tuning dataset. Before that point, eval suite improvement is the right use of the data.

## The move

**Log production calls, sample 2–5% daily, judge them, promote to evals by score threshold, re-run suite weekly.**

**Step 1 — Log production calls in a structured format.**

```js
function logProductionCall(call) {
  productionLog.append({
    id:        call.id,
    timestamp: call.timestamp,
    input:     call.prompt,           // user message
    output:    call.response,         // agent response
    metadata:  call.metadata,         // query type, user segment, etc.
    // judge fields populated later:
    score:     null,
    label:     null,
    promoted:  false,
  });
}
```

Store everything. Storage cost is negligible (~$0.01/GB); you can't retroactively judge what you didn't log.

**Step 2 — Sample and judge daily.**

```js
async function dailyFlywheelRun(log, judge, { sampleRate = 0.02, lookbackDays = 1 } = {}) {
  const recent    = log.filter(c => c.age < lookbackDays && !c.promoted);
  const sample    = recent.filter((_, i) => (i % Math.round(1 / sampleRate)) === 0);
  const judgments = await Promise.all(sample.map(c => judge.score(c.input, c.output)));

  judgments.forEach((j, i) => {
    sample[i].score = j.score;
    sample[i].label = j.rationale;
  });

  return sample;
}
```

**Step 3 — Promote by score threshold.**

```js
function promoteToEvalSuite(judgedSample, evalSuite) {
  for (const call of judgedSample) {
    if (call.score < 0.60) {
      evalSuite.addFailCase({ input: call.input, badOutput: call.output, rationale: call.label });
      call.promoted = true;
    } else if (call.score > 0.90) {
      evalSuite.addGoldenExample({ input: call.input, output: call.output });
      call.promoted = true;
    }
    // 0.60–0.90 band: discard — too noisy for training signal
  }
}
```

**Flywheel stages:**

| Stage | Trigger | Action |
|---|---|---|
| Bootstrap | Pre-launch | Generate synthetic evals ([F-17](f17-synthetic-eval-generation.md)) |
| Accumulate | Week 1+ | Log all; sample + judge 2–5% daily |
| Promote | Ongoing | Score <0.60 → fail case; score >0.90 → golden |
| Iterate | Weekly | Re-run suite; update prompt if pass rate drops |
| Fine-tune | ~500 labeled examples | Train a specialized model or adapter ([R-03](../frontier/r03-fine-tuning-vs-prompting.md)) |

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Cost model: $3/M input, $15/M output. Sample judging at 10 calls/week; eval suite at ~35 cases avg. Quality improvement directional (15pp over 4 weeks at 75 calls/day); escalation cost savings at $2.50/escalation are order-of-magnitude, not exact.

```
=== Data flywheel: 4-week production improvement ===

Judge call: 25 input + 12 output tokens
Cost per judge call: $0.255/k

Week   eval_cases   judged/wk   pass_rate   flywheel_cost/wk
W1     20           10          72%         $0.0026
W2     25           10          78%         $0.0026
W3     30           11          83%         $0.0028
W4     36           11          87%         $0.0028

Total 4-week flywheel cost: $0.0107
Suite growth: 20 → 36 cases (all grounded in real production patterns)
Pass rate: 72% → 87% (+15pp)

=== What each promoted case cost ===
Judge to label one case:  $0.000255
Promote 16 new cases:     $0.0041

=== ROI (directional) ===
Production volume:     ~75 calls/day
Failures avoided:      ~11/day at +15pp pass rate
Escalation cost saved: $28.13/day (at $2.50/escalation)
Flywheel running cost: $0.0004/day
```

The 4-week flywheel cost $0.01. The quality improvement it produced — if you count avoided escalations at any reasonable cost per escalation — pays back the entire cost within the first day. The constraint is not cost; it's discipline: you have to actually build the logging, sampling, and promotion pipeline, and run it consistently.

## See also

[F-17](f17-synthetic-eval-generation.md) · [F-12](f12-llm-as-a-judge.md) · [F-07](f07-evaluation-driven-development.md) · [F-26](f26-behavioral-drift-detection.md) · [S-44](../stacks/s44-few-shot-example-selection.md) · [R-03](../frontier/r03-fine-tuning-vs-prompting.md)

## Go deeper

Keywords: `data flywheel` · `production feedback loop` · `eval suite growth` · `production sampling` · `LLM-as-judge` · `labeled data` · `fine-tuning data collection` · `quality improvement loop` · `online learning`
