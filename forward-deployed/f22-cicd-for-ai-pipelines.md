# F-22 · CI/CD for AI Pipelines

An AI agent is a software artifact with a non-deterministic test surface. Standard CI/CD handles code changes. AI CI/CD must also handle prompt changes, model version changes, and behavioral regressions that do not crash — they just answer wrong.

## Situation

A team merges a prompt update, a model version bump, and a new tool implementation in the same week. Each change passes unit tests. A week later, 15% of production requests return subtly wrong answers. The regression was introduced by the prompt change but nobody ran evals before merging. Without behavioral gates, every AI deploy is a trust exercise.

## Forces

- Behavioral regressions in AI systems are silent. The system runs, requests complete, logs show 200s. The failure surface is the quality of the answer, which only an eval or a user sees.
- AI pipelines have three independent change vectors that all affect output: code (tools, parsers, orchestration), prompts ([W-09](../workspace/w09-prompt-versioning.md)), and model versions. Each needs its own gate.
- Eval runs are probabilistic, not deterministic. A deterministic test either passes or fails. An eval that asks "does this output match the ground truth?" has a distribution. Run each eval case multiple times and take majority if the pass rate is close to the threshold.
- Shadow testing is the only way to know how a change behaves on real production traffic distribution. Hand-written evals cover the cases you imagined; shadow reveals the ones you didn't.
- The eval suite itself is a production artifact. It must be versioned, reviewed, and tested — not treated as a config file someone edits when a test is inconvenient to pass.
- Rollback requires a fast path. In software CI/CD, rollback reverts a commit. In AI CI/CD, rollback means reverting the prompt version, model pin, or code — three separate levers. Know which one triggered the regression before rolling back the wrong one.

## The move

**Three-stage gate: PR eval → shadow → production monitor.**

**Stage 1 — PR eval gate.** On every PR that changes a prompt, tool, or orchestration logic:
1. Run the candidate against the eval suite ([F-07](f07-evaluation-driven-development.md))
2. Compare pass rate to the current production version (baseline)
3. Block merge if pass rate drops below baseline on any regression category

This is the cheapest gate — $0.03 for 20 eval cases. It catches regressions before they reach any user.

```yaml
# .github/workflows/eval.yml (illustrative)
on: [pull_request]
jobs:
  eval:
    steps:
      - uses: actions/checkout@v4
      - run: npm install
      - run: node scripts/run-evals.js --prompt prompts/candidate.md --baseline prompts/production.md
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - run: node scripts/check-regression.js  # exits 1 if pass rate < baseline
```

**Stage 2 — Shadow run on merge.** After merge to main, before production deploy:
1. Route 10% of live production traffic to both the new and old version in parallel
2. Return only the old version's response to users
3. Log and diff both responses; flag significant divergence for human review

Shadow is the bridge between eval (known cases) and production (real distribution). It runs without user impact and surfaces distribution drift that eval suites miss.

**Stage 3 — Post-deploy monitoring.** For 60 minutes after a production deploy:
1. Watch parse deviation rate ([S-39](../stacks/s39-output-parsing-robustness.md)) — a spike in repair+extract recoveries means the new version changed output format
2. Watch LLM-as-judge ([F-12](f12-llm-as-a-judge.md)) quality score vs baseline (sample 5% of responses)
3. Auto-rollback to the previous version if either metric exceeds a threshold

**Separate the three change vectors.** Version prompts, model pins, and code independently. When a regression fires:
- Parse deviation spikes → likely prompt or model version change (output format changed)
- Eval pass rate drops on specific categories → prompt regression
- New failure modes not in eval → code change (tool behavior changed)

This lets you rollback the right lever without touching what's working.

**Gate the eval suite itself.** Eval cases are production assets. Require review on any change to the eval suite — especially deletions. "Remove the failing test" is the same failure mode in software CI/CD.

## Receipt

> Verified 2026-06-26 — Node.js, `gpt-tokenizer`. Cost model computed from real token measurements: 30-token support system prompt, 20-case eval run, 100-call shadow sample, 1k req/day production baseline with 15% regression hit rate.

```
=== AI CI/CD cost model (1k req/day agent) ===

Stage 1 — PR eval gate (20 cases × 2 versions):
  Input + output: 4,600 tokens
  Cost per deploy: $0.03

Stage 2 — Shadow (100 calls, 10% of prod traffic):
  Cost per merge:  $0.17/day (shadow runs for one day, then stops)

Stage 3 — Post-deploy monitor:
  Judge samples (5% × 1k calls = 50 samples):  negligible
  Parse deviation: in-process, $0

Full CI gate cost per deploy:  $0.20

=== Without the gate ===
Silent regression at 15% hit rate, +30 tok/bad call:
  Token waste/day:   4,500 tokens   ($0.03/day)
  Per month:        135,000 tokens   ($0.82)
  Trust cost:        unquantified — wrong answers served to real users
  ROI ratio:         4× on token cost alone; higher when trust cost is included

=== Stage cadence ===
PR open:    run 20-case eval, block merge on regression     ($0.03)
Merge:      shadow 100 prod calls for 1 day, flag drift    ($0.17/day)
Deploy:     monitor parse deviation + judge score 60 min   (~$0)
```

The ROI case is not primarily cost — it's trust. Token waste from a 15% regression rate is measurable but small. The trust cost of users receiving wrong answers for a week before anyone notices is not.

## See also

[W-09](../workspace/w09-prompt-versioning.md) · [F-07](f07-evaluation-driven-development.md) · [F-17](f17-synthetic-eval-generation.md) · [S-39](../stacks/s39-output-parsing-robustness.md) · [F-12](f12-llm-as-a-judge.md) · [F-26](f26-behavioral-drift-detection.md)

## Go deeper

Keywords: `AI CI/CD` · `eval gate` · `shadow testing` · `model versioning` · `behavioral regression` · `LLMOps` · `post-deploy monitoring` · `prompt testing pipeline` · `GitHub Actions for AI`
