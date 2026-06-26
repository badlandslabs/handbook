# R-08 · Inference-Time Compute Scaling

The lever that mattered most in 2024–2026 wasn't a bigger model — it was spending *more compute per query* on the model you already had. Self-consistency, reflection, planning, extended thinking — all are the same move under different names: pay at query time, not training time, for a better answer.

## Forces

- Pretraining scaling is hitting diminishing returns; the next quality-per-dollar has to come from somewhere else
- Inference tricks ship this afternoon — no retrain, no GPU cluster, just code in the agent loop
- Every extra sample, pass, or plan step is a fresh bill, and easy queries waste that money fast
- Long-horizon agent work compounds errors: a 95%-per-step accuracy rate over 20 steps gives a 36% end-to-end success rate — and 20 steps is a short agent run
- The form of compute has to match the query: k samples help discrete answers, refinement helps open-ended drafts, planning helps multi-step goals

## The move

**Route first, then spend.** Pair with [S-06](../stacks/s06-model-routing.md): easy queries get a single greedy call; hard queries earn the extra compute. Never blanket-apply k=9.

**Read vote entropy as a "should I spend more?" signal.** When all k samples agree (entropy=0), stop. When they disagree (entropy>0), that's the cue to spend more or escalate to a stronger model. This is what CATTS (arXiv 2602.12276) operationalizes: invoke the verifier only when vote-derived uncertainty exceeds a threshold.

**Pick the form to match the failure mode:**
- Sampling + majority vote ([S-24](../stacks/s24-self-consistency.md)) — discrete answers; parallel; cost = k × single_call
- Reflection / refinement ([S-25](../stacks/s25-reflection.md)) — open-ended drafts; sequential; needs an external check signal to terminate
- Planning ([S-26](../stacks/s26-planning.md)) — multi-step goals where errors compound over the horizon
- Extended thinking / reasoning tokens ([R-02](r02-reasoning-models.md)) — internal CoT budget; toggled; billed as output tokens

**Match compute to horizon.** A 1-step lookup wants k=1. A 20-step agent run wants planning *and* per-step checks. Uniformly scaling per-step samples on long-horizon tasks saturates early — Lee et al. (arXiv 2602.12276) found this empirically on WebArena.

**The honest limit.** Inference-time compute reduces variance, not bias. If the dominant reasoning path is wrong, voting amplifies the error ([S-29](../stacks/s29-false-consensus.md)). If the first draft is unsalvageable, reflection can't fix it. Set a compute cap; measure whether it moves the needle on your actual tasks.

## Receipt

> Verified 2026-06-26 — four tasks against llama3.2 via Ollama (localhost:11435), varying difficulty, k=1 baseline then k=7 majority vote.

```
Task 1 — "How many seconds in a week?"    (easy)
  k=1: 5/5 correct  |  k=7: 7/7 correct  |  entropy: 0.00 bits  (unanimous)

Task 2 — Bayesian base-rate problem        (medium)
  k=1: 4/5 correct  |  k=7: 7/7 correct  |  entropy: 0.00 bits  (unanimous)

Task 3 — 15th Fibonacci number             (medium)
  k=1: 5/5 correct  |  k=7: 7/7 correct  |  entropy: 0.00 bits  (unanimous)

Task 4 — "23 × 47?" (Ollama bridge injects metadata noise on some draws)
  k=1: 3/5 cleanly extractable (answer always 1081; 2/5 wrapped in status text)
  k=7: tally {"1081":5, "234710811081":2}  |  majority vote: 1081 -> CORRECT
       entropy: 0.86 bits  <- correctly flagged residual format ambiguity
```

**Two lessons.** First, entropy=0 on tasks 1–3 accurately said "stop here, you don't need more samples." That's the routing signal working: add compute only when you need it. Second, tasks 1–3 were ceiling-limited at k=1 — this particular model on tractable tasks gains nothing from extra samples. The gains documented in the literature require genuinely hard problems: Snell et al. (arXiv 2408.03314, 2024) show +27% on hard MATH questions where single-sample accuracy starts around 40–60%, not near 100%. At ceiling, majority vote is noise suppression at best; at ~50% single-sample accuracy, it's a meaningful rescue.

## See also

[S-24](../stacks/s24-self-consistency.md) · [S-25](../stacks/s25-reflection.md) · [S-26](../stacks/s26-planning.md) · [R-07](r07-post-training-rlvr.md) · [R-10](r10-speculative-decoding.md)

## Go deeper

Keywords: `test-time compute` · `inference-time scaling` · `pass@k` · `best-of-N` · `compute-optimal inference` · `vote entropy` · `CATTS` · `arXiv 2408.03314` · `arXiv 2602.12276`
