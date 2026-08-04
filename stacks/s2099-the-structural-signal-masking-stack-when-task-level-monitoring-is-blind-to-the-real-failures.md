# S-2099 · The Structural Signal Masking Stack — When Task-Level Monitoring Is Blind to the Real Failures

Your LLM-as-judge reports 87% quality. Your error rate dashboard is green. You ship with confidence — and then an auditor flags that your agent has been routing compliance-sensitive cases incorrectly for three days. No alerts fired. No error logs. Nothing in your monitoring stack flagged it. The agent was always answering, always spending tokens, always producing plausible outputs. The problem was never at the task level. It was structural.

This is the structural signal masking problem: your monitoring infrastructure is designed to catch task-level failures, but your agent's actual failure mode is an integration defect that makes task-level signals invisible.

## Forces

- **Aggregate metrics hide the distribution.** A mean accuracy of 87% can mean "reliable on easy cases, catastrophically failing on hard ones." Task heterogeneity means routine and complex cases share the same eval run — routine cases drown out the signal from high-severity failures.
- **Structural defects preempt task-level signals.** When an integration defect exists (wrong tool schema, broken retrieval, model-version mismatch), the system produces plausible-but-wrong outputs. The LLM judge scores these as acceptable because the surface looks fine. You cannot detect task-level quality when structural failure has already corrupted the output before the judge sees it.
- **LLM-as-judge variance becomes noise, not signal.** Judge instability (different scores on semantically identical outputs) is typically treated as a measurement problem. But in partially-integrated systems, high variance in judge scores is often a symptom of structural instability — the input distribution has shifted in ways the judge wasn't calibrated to detect.
- **Cross-run aggregation masks episodic failures.** A system that fails reliably on 5% of task types, but those 5% always succeed in isolation, will report high per-task accuracy while producing catastrophic outcomes in composite workflows.
- **Ground truth is often absent in production.** For regulated domains (audit, finance, legal, healthcare), ground truth correctness requires professional domain judgment. You cannot label production outputs fast enough to keep the monitoring system calibrated.

## The Move

The approach is a triangulated 3D × 3-scope monitoring matrix that decomposes what to measure and when to trust the signal. Instead of asking "is the agent accurate?", ask three orthogonal questions across three temporal scopes.

### The 3D × 3-Scope Matrix

**Three evaluative dimensions:**
- **Quality** — Does the agent produce correct outputs?
- **Suitability** — Are the outputs appropriate for the specific context and risk level?
- **Efficiency** — Is the agent consuming resources proportionally to task complexity?

**Three monitoring scopes:**
- **Within-run** — per-step behavior during a single agent invocation
- **Cross-run** — consistency and drift across multiple invocations of the same task
- **Structural** — integration health: tool availability, schema validity, retrieval freshness

Each cell in the matrix gets a different detection approach and alert threshold.

### Variance as Signal, Not Noise

Instead of discarding variance in LLM-as-judge scores, treat it as a first-class signal:

1. **Compute judge score variance** across semantically similar inputs. High variance on similar tasks is not measurement noise — it indicates structural instability upstream.
2. **Use EWMA thresholds** (Exponentially Weighted Moving Average) on within-run step-level metrics rather than static pass/fail cutoffs. Structural failures manifest as gradual metric shifts, not binary flips.
3. **Apply Mahalanobis distance** to characterize cross-run output distributions. When the distribution of agent outputs shifts in feature space (not just mean accuracy), even without ground truth, you have a structural signal.

### Severity Classification: E / H / S

Route every detected anomaly through a severity classifier:
- **E (Easy)** — Within-run quality score drops; within-run efficiency degrades. Task-level monitors detect this. Alert with standard PagerDuty routing.
- **H (Hard)** — Cross-run suitability variance spikes; cross-run quality scores on similar inputs diverge. Task-level monitors may detect the drift but cannot classify the severity. Requires human-in-the-loop triage.
- **S (Structural)** — Structural scope anomalies: tool latency spikes, schema version drift, retrieval recall collapse. Task-level monitors are blind to these. Triggers incident response, not quality alerts. The system has a broken foundation — task scores are unreliable until structural health is restored.

The key insight: **S-class events invalidate your task-level monitoring.** When structural defects are present, any task-level metric is unreliable. The MDM (Monitoring and Triage Methodology) mandates that S-class findings suspend task-level SLA tracking until structural integrity is confirmed.

### Ground Truth Augmentation Strategy

When ground truth is unavailable (the common production case):
1. **Adversarial sampling** — feed known edge cases with synthetic ground truth to calibrate judge reliability
2. **Inter-rater variance tracking** — track the spread between LLM judge and human reviewer; a widening spread indicates judge calibration drift
3. **Provenance tagging** — every output carries metadata about the structural state of the system at generation time, enabling post-hoc correlation of failures to structural events

## Receipt

> Verified 2026-08-03 — Core framework from Ferrara Boston et al., "Monitoring Agentic Systems Before They're Reliable" (arXiv:2606.02494, AgenticSE Workshop @ ACM CAIS 2026). The 3D×3 matrix (quality/suitability/efficiency × within-run/cross-run/structural) and E/H/S severity classification are the primary contribution. MDM algorithm and Mahalanobis distance approach confirmed from source. EWMA threshold methodology described in paper's alerting strategy section. Production urgency corroborated by Google Cloud AI Agent Trends 2026, Druid AI 2026 Benchmark (80–99.5% containment rates), and Machinelearningmastery agentic AI trends analysis (Jun 2026): "unpredictable and rapidly escalating LLM token costs, lack of mature evaluation and testing frameworks for non-deterministic workflows" — exactly the monitoring gap this stack addresses.

## See also

- [S-1000 · The Eval Gap Stack](stacks/s1000-the-eval-gap-stack-when-your-eval-suite-passes-but-production-fails.md) — single-run pass rate lies; this stack covers why even multi-run aggregate evals fail when structural defects are present
- [S-1005 · AI SRE](stacks/s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — behavioral regressions that look correct; the companion operational discipline for detecting what task-level dashboards miss
- [S-1014 · Evaluating Agents in Production](stacks/s1014-evaluating-agents-in-production-where-simplicity-beats-complexity.md) — LLM-as-judge instability; this entry explains when judge variance is measurement noise vs. a structural signal
