# W-09 · Prompt Versioning and Change Management

A prompt is code. It determines model behavior in production. Changing it without a testing gate is the same as deploying code without running tests — except the failure mode is subtler: the system still answers, just wrong.

## Situation

A team rewrites a support agent's system prompt to sound "friendlier." The new prompt is longer, warmer, and more enthusiastic. It ships directly to production. Two days later, the support team flags that the agent is telling customers there are educational discounts. There aren't. The prompt change introduced the regression; no one caught it because there was no gate.

## Forces

- Prompts change model behavior as surely as code changes program behavior — but unlike code, the failure mode does not crash. The system keeps running; the outputs are just wrong. Silent regressions are the hardest bugs to catch.
- Teams treat prompts as text, not software artifacts. They live in a config file or hardcoded string, not in a versioned registry. There is no diff, no review, no history.
- A longer, more elaborate prompt is not a better prompt. Padding adds tokens, adds cost, and can shift behavior in unintended directions. The v1 → v2 rewrite above gained 64% more tokens and introduced two regressions.
- Evaluation suites ([F-07](../forward-deployed/f07-evaluation-driven-development.md), [F-17](../forward-deployed/f17-synthetic-eval-generation.md)) are the gate. Without them, a prompt change cannot be validated — only hoped for.
- Rollback is the safety net. If a prompt version is not identified by a version string, rollback is a manual archaeology exercise. If it is, rollback is changing one pointer.
- Model updates change behavior too. A prompt that works perfectly against `claude-sonnet-4-6` may regress when the provider releases an updated model. Prompt version history is also your history of which prompt worked against which model.

## The move

**Treat prompts as versioned artifacts in a registry.**

A minimal prompt registry is a directory of files:
```
prompts/
  support-agent/
    v1.md    ← current production
    v2.md    ← candidate (in testing)
    v3.md    ← draft
  metadata.json  ← { current: "v1", model: "claude-sonnet-4-6" }
```

Or a database row: `{ name, version, content, model, created_at, status }`. The application loads the prompt by name + status, never by hardcoded string. A rollback is `UPDATE SET status='active' WHERE version='v1'`.

**Gate every promotion with an eval run.** Before a prompt version moves from candidate → production:
1. Run it against the regression suite ([F-07](../forward-deployed/f07-evaluation-driven-development.md))
2. Require it matches or beats the current version's pass rate
3. If it regresses on any case, fix the prompt or document the accepted tradeoff before promoting

The gate is cheap. Testing two versions across 5–50 eval cases costs a fraction of a cent — orders of magnitude less than a day of production regressions.

**Shadow before you ship.** For high-risk changes, run the new prompt in shadow mode: both versions process every production request, results are compared but only v1's response is returned to the user. Shadow reveals real-world distribution failures that hand-written evals miss.

**Trigger rollback on a deviation signal.** Three signals that mean rollback:
1. Eval pass rate drops below previous version
2. Parse deviation rate spikes (S-39's "repair+extract" recovery climbing)
3. LLM-as-judge ([F-12](../forward-deployed/f12-llm-as-a-judge.md)) quality score drops vs baseline

Automate the first two; the third requires a judge call but catches regressions that don't manifest as parse errors.

**Version-pin to the model.** Record which model version the prompt was validated against. When a provider pushes a model update, re-run the eval suite on the existing prompt — a prompt change is not always required, but model behavior change is always worth checking.

**Diff every change.** Before writing a new version, diff the current prompt to see exactly what changed. A 64% token increase should trigger a question: does the additional content actually change model behavior in the intended direction? Measure first.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Two real system prompt versions measured; eval regression simulated with 5 representative test cases matching typical support agent failure modes.

```
=== Prompt v1 → v2 rewrite: cost and quality impact ===

Prompt v1 (concise, explicit constraints):  58 tokens
Prompt v2 (enthusiastic, open-ended):       95 tokens  (+37 tokens, +64%)

Cost at 10k calls/day:
  v1: $3.52/day
  v2: $5.77/day
  Monthly delta from one rewrite: +$67.38/month

=== Eval suite results (5 regression test cases) ===
v1 pass rate: 5/5 (100%)
v2 pass rate: 3/5 (60%)

Regressions introduced by v2:
  "What is the price of the Pro plan?" — v2 adds upsell not in ground truth
  "Do you offer educational discounts?" — v2 answers yes; correct answer is no

=== Testing gate cost ===
Running 5-case eval against both versions: $0.01
vs. cost of 1 day of regressions:          $2.31  (40% regression hit rate)
Gate ROI: 231× on day one, unlimited thereafter
```

The prompt got longer, warmer, and more wrong. The cost increased by $67/month. The eval gate cost $0.01 and would have caught both regressions before they reached users.

## See also

[F-07](../forward-deployed/f07-evaluation-driven-development.md) · [F-17](../forward-deployed/f17-synthetic-eval-generation.md) · [F-12](../forward-deployed/f12-llm-as-a-judge.md) · [S-36](../stacks/s36-system-prompt-architecture.md) · [S-39](../stacks/s39-output-parsing-robustness.md)

## Go deeper

Keywords: `prompt versioning` · `prompt registry` · `prompt management` · `regression testing prompts` · `shadow testing` · `prompt rollback` · `evaluation gate` · `LLMOps`
