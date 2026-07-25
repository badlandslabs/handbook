# S-1631 · The Structural Signal Masking Stack — When Your Task-Level Metrics Are Lying to You

Your monitoring dashboard is green. Mean accuracy 87%. Error rate under 0.5%. P99 latency stable. You're about to ship. Then you discover your agent has been failing catastrophically on a specific task cluster for three weeks — and your metrics never noticed. The problem isn't that your agent degraded. It's that your monitoring was structurally blind. Structural integration defects were masking the task-level signal the whole time.

## Situation

You deploy a multi-agent pipeline: a planner agent calls a tool-selector agent, which calls a per-domain specialist agent, which calls a verifier. Each agent has 92%+ accuracy in isolation. Your end-to-end test suite passes. You ship. Three weeks later, a domain expert flags that all outputs for the manufacturing-sector task cluster are subtly wrong. Not wrong enough to crash — just wrong enough to be useless.

You dig into the monitoring data. Everything looks fine. Accuracy stayed above 86% the entire time. The failure was invisible because it lived at the *structural* level — a version mismatch between the tool-selector's API schema and the specialist's expected format — not at the *task* level, which was where your monitoring looked.

## Forces

- **Structural defects dominate the failure landscape in partially-integrated agentic systems.** At early maturity stages, the biggest risk isn't "the agent got the wrong answer" — it's that the integration scaffolding (schema contracts, tool bindings, state passing) silently broke. Task-level monitoring was never going to catch this.
- **Aggregate metrics lie when task distributions are heterogeneous.** A system reporting 87% mean accuracy can be performing perfectly on 80% of tasks while failing entirely on 20% — if the failing tasks are clustered by input type, your aggregate hides both the failure and the pattern.
- **LLM evaluators introduce variance that can exceed the signal.** When you use an LLM-as-judge for task-level scoring, the judge itself has non-trivial disagreement rates. If the judge's variance is larger than the performance gap you're trying to detect, your "measurement" is dominated by noise.
- **Ground truth is often professional judgment, not binary.** Whether a customer-service response is "good" depends on tone, accuracy, policy compliance, and customer sentiment — none of which are binary. Asking a monitoring system to detect regressions in this space requires a fundamentally different signal than pass/fail unit tests.
- **Suitability and efficiency are orthogonal to quality.** A correct answer delivered 45 seconds late, on the wrong topic, at 5x the token budget, is not a successful agent interaction. Quality metrics alone miss the dimensions that determine whether an agent is fit for its purpose.

## The move

Decompose agentic system monitoring into a **3D × 3-scope framework** before you try to detect task-level regressions:

### Three Dimensions (what to measure)

1. **Quality** — Did the agent produce the right output?
   - Task success rate, factual accuracy, policy compliance
   - Use LLM-as-judge with variance tracking, not just point estimates
   - Tag scores by input cluster to detect distribution-dependent failures

2. **Suitability** — Is the agent the right tool for the task?
   - Task-agent matching rate (did the right specialist handle the task?)
   - Escalation rate (did it know when to punt?)
   - Over-specialization: agent solving easy tasks with heavyweight models

3. **Efficiency** — What did it cost to get there?
   - Token count per session, per task type
   - Step count vs. optimal step count (was the path efficient?)
   - Latency P50/P90/P99 — not just average

### Three Monitoring Scopes (when to measure)

1. **Within-run** — Is this trajectory correct as it executes?
   - Step-level trace quality gates
   - Tool-call success/failure at each step
   - Budget checkpoints (abort if token spend exceeds threshold mid-run)

2. **Cross-run** — Is the agent consistent over time?
   - Rolling accuracy on reference task set (detect drift before users feel it)
   - Variance in LLM-judge scores (widening variance = unstable evaluation, not just unstable agent)
   - Error rate by task cluster over rolling windows

3. **Structural** — Is the integration scaffold intact?
   - Schema compatibility checks between agent interfaces (run on every deploy)
   - Tool availability and response-time health checks
   - API contract versioning — detect breaking changes before they propagate

### Variance as the primary characterization signal

In systems with high task heterogeneity and uncertain scoring, **variance is more informative than mean**. Track:

```
Δ-accuracy = accuracy(task_cluster_A) - accuracy(task_cluster_B)
Judge_variance = stddev(judge_scores_across_repeated_evals)
Output_diversity = entropy(output_distribution_per_task_type)
```

If any of these spike, investigate structurally before investigating task-level. Structural defects manifest as *variance anomalies*, not *mean shifts*.

### The monitoring priority order

When you're building from scratch: **structural → cross-run → within-run**. Fix the scaffold first. A task-level accuracy monitor on a broken integration is measuring noise.

## Receipt

> Receipt pending — 2026-07-25. Source: arXiv:2606.02494 (Ferrara Boston et al., Reins AI / Veraitech, AgenticSE 2026, Agentic Software Engineering workshop, ACM CAIS 2026). 3D × 3-scope framework applied at a mid-size enterprise contact-center deployment; structural defects accounted for 60% of observed failures in partially-integrated agentic assembly. Paper proposes MDM (Multi-Dimensional Monitoring) algorithm with per-axis adaptive thresholds via EWMA and Mahalanobis-distance-based joint anomaly detection.

## See also

- [S-997 · The Agent Observability Stack](/stacks/s997-the-agent-observability-stack-when-the-agent-looks-okay-but-decides-wrong.md) — covers the observability gap; structural monitoring complements trajectory-level observability
- [S-1546 · The Intelligence Entropy Stack](/stacks/s1546-the-intelligence-entropy-stack-when-your-agent-degrades-for-no-reason-you-can-measure.md) — explains why degradation is silent by default; this entry explains why monitoring misses it even when it's not silent
- [S-1005 · AI SRE](/stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — SLOs and error budgets for agentic systems; the 3D framework provides the measurement schema SLOs need
