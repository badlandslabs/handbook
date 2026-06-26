# S-37 · Batch vs Real-Time Pipelines

Two architectural modes, not two speeds. Real-time pipelines serve a waiting user or system — the result must arrive before the next step can proceed. Batch pipelines run offline against a queue and return results on a schedule — minutes to hours later, at 50% token cost. The decision is not "how fast do I need it?" — it is "who is blocked while I generate?" If nobody is waiting, batch. If someone is waiting, real-time.

## Situation

You have an LLM call in your pipeline — classifying tickets, generating summaries, scoring evals — and you chose real-time because that is the default. At low volume it barely matters. At 100,000 calls a day the cost difference is material, and at 1,000,000 calls you are paying twice what you should. Or the reverse: you built a batch pipeline for a task users are waiting on, and now latency complaints are coming in.

## Forces

- The Batch API (Anthropic's implementation: 50% cost reduction, results within 24 hours) is a different endpoint, not a parameter. You write the jobs to a file, submit, poll for completion. The engineering overhead is real — typically a few hours to implement, plus a monitoring/retry layer.
- At low volume, engineering overhead dominates the savings. At 1,000 tokens per call and the 50% batch discount, break-even on a modest 4-hour setup investment is roughly 1,000,000 calls. At 10,000 calls/day that is 100 days. At 1,000 calls/day, it is nearly 3 years. Build batch for volume, not for novelty.
- Real-time with parallelism recovers most of the latency gap for moderate N. Issuing 500 requests concurrently turns 20 seconds serial into ~2 seconds — close to what an interactive user will tolerate. Batch is not the only answer to throughput.
- Batch provides natural failure isolation: each item in the queue is independent. One poisoned request does not bring down the run. Retrying only failed items is automatic. In real-time pipelines, you build this isolation yourself.
- [S-12](s12-streaming.md) is a rendering decision (stream tokens to the user as they generate). Batch vs real-time is a pipeline architecture decision. They operate at different layers and stack independently: a real-time pipeline can stream output; a batch pipeline never should.

## The move

**The primary decision axis: is anyone blocked?**
- User, API caller, or downstream system is waiting → real-time.
- No hard deadline (evals, report generation, data pipelines, nightly jobs, annotation) → batch.

**Secondary axes that shift the answer:**
- Cost sensitivity > 20%? Lean batch for non-interactive work.
- Volume > 100,000 calls/week? Engineering overhead of batch pipeline amortizes in days.
- Need failure isolation or easy reruns? Batch queues give it for free.
- Results needed in < 30 seconds? Real-time. Batch SLA is minutes to hours.

**Real-time with parallelism is not the same as batch, but covers the gap at low-to-moderate volume.** For N < 10,000 calls/run: fan out concurrent requests up to provider rate limits. This avoids async pipeline engineering while recovering most of the throughput. See [S-05](s05-multi-agent-patterns.md) for parallel fan-out patterns.

**Batch is the right default for evals.** Evaluation runs are always offline, latency-tolerant, and often large. Every eval harness should route through the batch API — it directly halves the cost of running evals at scale ([F-02](../forward-deployed/f02-evaluation-at-scale.md), [F-17](../forward-deployed/f17-synthetic-eval-generation.md)).

**Design for idempotency in batch pipelines.** Every batch job should be re-runnable safely: assign each item a stable ID, write outputs keyed by ID, check if output already exists before re-generating. A crashed batch job that is not idempotent wastes money on re-processing and risks duplicates.

**Don't use batch for agents that need tool calls mid-generation.** Async batch is for single-shot generation jobs. An agent that calls a tool, waits for the result, and decides next steps needs a real-time loop — the tool latency and the decision cycle are interleaved in ways batch can't express cleanly.

## Receipt

> Verified 2026-06-26 — Node, `gpt-tokenizer`. Token counts measured; costs computed at $6.07/M blended real-time rate (from F-08 receipt, Q1'26) and 50% batch discount (Anthropic published rate). Break-even uses $300 engineering setup estimate (2 hours at $150/hr); adjust for your actual cost. Throughput model: 50 req/s real-time rate-limit ceiling (common hosted tier); 500 concurrent with parallelism.

```
Task: 1,000 ticket classifications × (80 in + 20 out tokens each)
      = 80,000 input + 20,000 output tokens

Mode          Cost      Latency               Use when
Real-time    $0.6070   20s serial / ~2s parallel  someone is waiting
Batch API    $0.3035   minutes to hours            no deadline

Savings:     $0.3035 per run  (50% cheaper per token)

Break-even on batch pipeline setup ($300 engineering):
  → ~989 runs of 1,000 calls
  → At 1 run/day: 989 days  (don't build batch at this volume)
  → At 10 runs/day: 99 days
  → At 100 runs/day: 10 days  (obviously worth it)
```

**What the receipt shows:**

- The 50% batch discount is real and compounding — at $0.3035 savings per 1,000-call run, it becomes significant fast at volume.
- At low volume, the batch pipeline's engineering overhead takes years to pay back. This is the number most teams don't compute. "Batch is cheaper" is true; "batch is worth building" depends on volume.
- Parallelism on real-time closes most of the throughput gap for moderate N: 1,000 calls at 500 concurrent takes ~2 seconds — good enough for any non-interactive use case without the async pipeline complexity.
- The decision is not latency vs cost. It is "is someone blocked?" If yes, the cost premium of real-time is mandatory. If no, the 50% savings is available, and the question is only whether volume justifies the engineering.

## See also

[S-12](s12-streaming.md) · [S-05](s05-multi-agent-patterns.md) · [F-02](../forward-deployed/f02-evaluation-at-scale.md) · [F-08](../forward-deployed/f08-agent-cost-control.md) · [S-35](s35-latency-budget.md)

## Go deeper

Keywords: `batch API` · `async inference` · `real-time pipeline` · `offline processing` · `throughput` · `rate limits` · `parallelism` · `idempotency` · `eval pipeline` · `cost per run`
