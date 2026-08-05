# S-2158 · The Eval Blindness Stack — When Your Measurement Function Reports Healthy While Your Agent Is Failing

You ship a new agent to production. Every metric looks green. Task completion rate: 94%. Latency: within SLA. Error rate: 0.3%. Three weeks later, a customer escalates: the agent has been giving wrong policy advice to 18% of users — consistently, confidently, and silently. Your eval passed. Your monitoring passed. The agent was failing the entire time. This is evaluation blindness: the measurement function produces readings indistinguishable from a healthy state while the system is actually failing, with no auxiliary signal flagging the gap. It is the most dangerous failure mode in production AI because it defeats the very mechanism you built to detect failure.

## Forces

- **Your monitoring stack is part of the failure surface, not separate from it.** When the agent's failure mode aligns with what your metrics measure, you see nothing. When the measurement function itself degrades in lockstep with the system it monitors, blindness is structural — no alert configuration closes the gap.
- **The mean time to detect (MTTD) for evaluation failures spans months.** arXiv:2608.02786 (Bajaj, Aug 2026) found MTTD ranges of 6 orders of magnitude across failure classes: infrastructure failures surface in minutes to hours; evaluation failures take weeks to months. The monitoring tools most teams rely on for evaluation-class failures are the ones most likely to be blind to them.
- **Silently failing incidents are 52% of all LLM failures — and 81% are critical or high severity.** Of the 50 labeled real-world LLM incidents in the companion taxonomy (priyanka25aug/llm-failure-taxonomy, MIT licensed), 53% were silent. These aren't edge cases — they are the majority.
- **100% of C4 (evaluation) class failures are silent.** The paper's 6-class taxonomy places evaluation failures last because they are the hardest to detect: the failure is in what you're measuring, not just what the system is doing.

## The move

### 1. Map your measurement functions to failure classes

The paper's taxonomy defines 6 failure classes. Most teams monitor C2 (infrastructure) and C5 (operational), but miss C4 (evaluation) and C6 (correctness):

| Class | Name | MTTD | Typical Detection |
|-------|------|------|-----------------|
| C1 | Model Drift | Days–weeks | Periodic eval |
| C2 | Infrastructure | Minutes–hours | APM, health checks |
| C3 | Hallucination | Hours–days | Output sampling |
| C4 | **Evaluation** | **Weeks–months** | **Eval suite → blindness risk** |
| C5 | Operational | Minutes–hours | Ops monitoring |
| C6 | Correctness | Hours–days | Spot-check sampling |

C4 is the danger zone: your eval suite is both the monitor and the thing being monitored. When it goes blind, you lose the only signal that could catch it.

### 2. Apply the formal blindness test

For each measurement function M and failure class F you care about, ask: **can M produce a healthy reading while F is actively occurring?** If yes, M is blind to F. The paper provides the formal definition:

> M exhibits evaluation blindness w.r.t. F if ∀ ε > 0: P(M(s) ∈ healthy_δ) > 1 − ε while the system is in a failure state from F, and no auxiliary signal distinguishes the readings.

Practically: if your task-completion-rate metric hits 94% while the agent gives wrong policy advice 18% of the time, your metric is blind. The task completed. The advice was wrong. Your measurement measured task completion, not task correctness.

### 3. Add orthogonal measurement channels

When the primary measurement channel is blind, you need a second channel that measures a different property. Not a second eval on the same dimension — a channel that can't fail in the same way:

```python
# Primary channel (blind to correctness drift)
task_completion_rate = completed_tasks / total_tasks

# Orthogonal channel: claim-level correctness sampling
# Different failure mode — measures output quality, not completion
async def sample_correctness(agent, n=100, seed=42):
    """Random sample of agent outputs judged against ground truth."""
    rng = random.Random(seed)
    failures = 0
    for _ in range(n):
        prompt = rng.choice(golden_dataset)
        output = await agent.run(prompt)
        if not ground_truth_matches(output, prompt.expected):
            failures += 1
    return failures / n  # Orthogonal signal — can't be gamed by completion behavior

# The blindness gap: primary shows green, orthogonal reveals drift
primary_rate = task_completion_rate()       # → 0.94 (blind)
correctness_rate = sample_correctness(agent, n=200)  # → 0.76 (reveals the gap)
```

The key property: orthogonal channels must be **uncorrelated with the blind failure mode**. If both metrics measure completion, they're jointly blind.

### 4. Detect measurement function corruption

Measurement function corruption is the worst case: the eval itself is compromised. Signs:

- **Variance collapse**: LLM-judge scores show suspiciously low variance. High variance in LLM-as-judge is a structural signal (from a prior pattern), not noise — zero variance means the judge stopped discriminating.
- **Correlation with system state**: If your eval scores correlate with your agent's latency or token count rather than its output quality, the measurement function is measuring the wrong thing.
- **Dataset contamination**: Eval data has leaked into training or prompt context. Run a contamination detector before each eval run.

```python
async def detect_measurement_corruption(eval_run, prev_run):
    variance_ratio = eval_run.judge_score_variance / prev_run.judge_score_variance
    if variance_ratio < 0.1:  # Variance collapsed — judge stopped discriminating
        alert("CRITICAL: Judge variance collapsed. Eval may be blind.")
    
    score_latency_corr = pearson(eval_run.scores, eval_run.latencies)
    if abs(score_latency_corr) > 0.7:  # Scores correlate with speed, not quality
        alert("WARN: Judge scores correlate with latency. Wrong measurement dimension.")
    
    contamination_rate = await check_contamination(eval_run.dataset, eval_run.train_set)
    if contamination_rate > 0.05:
        alert("CRITICAL: Dataset contamination detected.")
```

### 5. Build an eval-health monitor for the eval itself

Treat your measurement infrastructure as a production service with its own SLO:

```python
# Eval infrastructure health check
class EvalHealthMonitor:
    def __init__(self, eval_runs: list[EvalRun]):
        self.runs = eval_runs
    
    def check(self) -> dict[str, Any]:
        latest = self.runs[-1]
        prev = self.runs[-2] if len(self.runs) > 1 else None
        
        health = {
            "judge_variance_ok": latest.judge_score_variance > 0.01,
            "score_distribution_stable": self._check_distribution_shift(latest, prev),
            "golden_dataset_current": latest.dataset_age_days < 30,
            "orthogonal_channel_aligned": self._check_alignment(latest),
            "blindness_risk": self._assess_blindness_risk(latest),
        }
        return health
    
    def _check_alignment(self, run: EvalRun) -> bool:
        # Primary and orthogonal channels should agree within tolerance
        gap = abs(run.primary_metric - run.orthogonal_correctness_rate)
        return gap < 0.10  # Alert if gap exceeds 10 percentage points
    
    def _assess_blindness_risk(self, run: EvalRun) -> str:
        signals = [
            run.judge_score_variance < 0.01,
            run.dataset_age_days > 60,
            run.orthogonal_gap > 0.15,
            run.score_latency_correlation > 0.5,
        ]
        risk = sum(signals)
        if risk >= 3:
            return "CRITICAL — eval likely blind"
        elif risk >= 2:
            return "HIGH — eval quality degraded"
        elif risk >= 1:
            return "MEDIUM — monitoring recommended"
        return "LOW"
```

## Receipt

> Verified 2026-08-05 — arXiv:2608.02786 (Bajaj, Aug 3 2026) provides the empirical basis: 53/100 incidents silent (52%), 81% critical/high, 100% of C4 failures silent. Companion taxonomy at github.com/priyanka25aug/llm-failure-taxonomy provides 6-class, 24-subclass failure taxonomy with labeled dataset. The 6-order-of-magnitude MTTD range across failure classes is the most counterintuitive finding — it means the faster-detected failures (C2: infrastructure) get the most engineering investment, while the slowest-detected (C4: evaluation) are precisely where you're most blind.

## See also

- [S-190 · The Correctness SLO Stack](stacks/s190-the-correctness-slo-stack-when-your-dashboard-says-99-4-percent-and-your-customer-says-the-feature-has-been-broken-for-3-weeks.md) — The upstream problem: semantic failures that don't register as errors
- [S-2153 · The Eval Infrastructure Stack](stacks/s2153-the-eval-infrastructure-stack-when-your-evaluation-is-lying-to-you-about-everything.md) — Stale golden datasets; complementary: this entry covers the eval going stale, S-2158 covers the eval going blind
- [S-114 · The Self-Correction Illusion](stacks/s114-the-self-correction-illusion-when-your-agent-finds-everyone-elses-bugs-but-misses-its-own.md) — The agent declaring success while failing; related circularity: eval blindness is the infrastructure-level version of the same problem
