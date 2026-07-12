# S-897 · The OAEI Loop — When Your Agent Quality Has No Rising Floor

[Your agent is reliable this week. You upgraded the model and it regressed on three failure modes nobody noticed until users complained. Your monitoring shows green. The problem isn't the upgrade — it's that your quality signal degrades faster than your monitoring can detect. The OAEI loop (Observe → Annotate → Evaluate → Iterate) is the discipline that closes this gap: a continuous cycle that turns production behavior into ground-truth evaluators, so every iteration raises the floor, not just fixes the ceiling.]

## Forces

- **Unlabeled production data is wasted signal.** Every agent interaction contains a labeled failure or success — you just haven't extracted it. Random sampling misses the rare, high-severity failures that matter most.
- **Annotation is the bottleneck.** Domain experts are expensive and slow. Feeding them unprioritized traces wastes their time on benign cases while catastrophic failures wait in queue.
- **Offline evals are a snapshot, not a trend.** A single eval run tells you "is it good today?" — not "is it degrading?" and not "did the v2.1 upgrade hurt the use cases that matter most?"
- **Eval drift poisons your signal.** An LLM-as-judge evaluator that was 94% aligned with human judgment six months ago may be 71% aligned today as the model's style changes. Without recalibration, you're optimizing against a moving target.
- **[S-538](s538-agent-evaluation-harness.md) gives you the harness; [S-235](s235-production-failure-to-regression-test.md) gives you regression tests from failures; [S-678](s678-the-eval-to-guardrail-feedback-loop.md) gives you eval-to-guardrail policy. None of them give you the continuous cycle or the prioritization layer that makes the cycle actually work.**

## The move

The OAEI loop runs continuously in the background. Each phase feeds the next:

### Observe — capture traces, then prioritize

Capture full production traces: conversation history, tool call sequence, tool results, final output, and metadata (model version, latency, session length). Random sampling works for monitoring but starves the annotation queue.

Prioritize traces using anomaly signals, not random selection:

- **Empty or truncated tool responses** — agent operated on missing data
- **High re-plan rates** — agent abandoned its trajectory mid-task
- **Semantic mismatch** — LLM-as-judge confidence below threshold on final output
- **User escalation events** — human requested a different outcome
- **Cost spikes** — token usage 3σ above the user's baseline (context overflow proxy)

This prioritization list is the selection layer that makes annotation tractable. Without it, you annotate volume; with it, you annotate signal.

### Annotate — label failure modes with consistency tracking

Route prioritized traces to domain experts through an annotation queue. Each trace is labeled with:

- **Failure type** — hallucination, tool misuse, goal drift, empty response handling, constraint violation, policy breach
- **Severity** — P0 (catastrophic/wrong answer), P1 (degraded/recoverable), P2 (degraded/style)
- **Annotator confidence** — how certain is the reviewer this label is correct?
- **Reproducibility notes** — what inputs triggered this? (conversation length, specific phrases, tool state)

Track annotator consistency (inter-rater reliability). When two domain experts disagree on 30% of cases, the failure mode taxonomy is wrong — not the annotators. Fix the taxonomy first, then re-annotate.

Onboard new reviewers with 10–20 prior annotated runs as calibration examples. Sample each reviewer's decisions weekly for consistency. A reviewer whose decisions diverge from the consensus becomes a consistency problem, not a productivity metric.

### Evaluate — convert annotations to versioned evaluators

Each annotated failure mode becomes an automated evaluator:

- **Rule-based where possible** — exact-match on tool names, schema validation on outputs, regex on constrained fields. Rule-based evaluators don't drift with model style.
- **LLM-as-judge for semantic cases** — "did the agent respond accurately to the user's intent?" LLM-as-judge is required for semantic evaluation but is also the most drift-prone component.
- **Hybrid for complex cases** — rule-based gate + semantic judge on the pass-through. Catches 80% of failures with deterministic checks; semantic judge handles the remaining 20%.

Version every evaluator. When the annotator taxonomy changes, increment the evaluator version. Track the evaluator's historical alignment score (agreement with human labelers over time). When alignment drops below 85%, flag for recalibration — do not silently continue running a drifting evaluator.

### Iterate — track quality trends, not point-in-time scores

Run the evaluator set against every deployment gate. Track three trend metrics:

- **Pass rate by failure type** — which failure classes are improving, which are degrading?
- **Evaluator alignment drift** — is your LLM-as-judge still aligned with human ground truth?
- **Annotation coverage** — what percentage of your production trace volume has been annotated this month? Coverage below 10% means your eval set is thin.

If a model upgrade degrades pass rate on P0 failures by more than 2%, block the deployment or require explicit sign-off. Treat this as a release gate, not a post-deployment check.

## The pattern

The OAEI loop creates **Feedback Compounding**: each iteration makes the eval set more representative and the guardrails more precise. Teams that run evals without closing the loop (Observe → Annotate → Evaluate) have a ceiling — they catch known failure modes but miss novel ones. Teams that close the loop (full OAEI) have a rising floor — their eval set grows with every production failure they label.

The insight that trips most teams: **more evals does not mean better quality**. The bottleneck is annotation prioritization, not annotation volume. A queue that surfaces the 20 highest-signal traces per week outperforms one that labels 500 random traces per week — because the 20 traces have known, actionable failure modes while the 500 traces mostly confirm the agent is working fine.

## Receipt

> Receipt pending — 2026-07-10

## See also

- [S-538 · Agent Evaluation Harness](s538-agent-evaluation-harness.md) — the pinned eval set anti-regression pattern
- [S-678 · The Eval-to-Guardrail Feedback Loop](s678-the-eval-to-guardrail-feedback-loop.md) — closing the eval-to-runtime-policy circle
- [S-401 · Agent Drift: The Longitudinal Regression Problem](s401-agent-drift-the-longitudinal-regression-problem.md) — the degradation problem the OAEI loop prevents
