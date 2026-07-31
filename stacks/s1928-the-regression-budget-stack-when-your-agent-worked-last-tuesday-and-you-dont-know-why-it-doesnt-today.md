# S-1928 · The Regression Budget Stack — When Your Agent Worked Last Tuesday and You Don't Know Why It Doesn't Today

Your agent scored 94% on the evaluation suite before you shipped. Three weeks later, a customer reports the agent has been giving wrong answers since last Tuesday. Nothing changed in your code. The model version number is identical. The agent just... became worse — and you had no budget to catch it.

This is the regression budget gap: the absence of a contract between engineering and the business that says "this much quality degradation is unacceptable." Without one, you discover regressions the way you discover most things — through customer complaints.

## Forces

- **Benchmarks lie about tomorrow.** Standard evaluations measure a point in time. Production systems face silent model updates (GPT-4's accuracy on specific tasks dropped from 84% to 51% between March and June 2023 with no version change — Stanford/UC Berkeley), shifting user populations, and emergent prompt-chain dependencies. A score that says "passing today" says nothing about whether the agent is better or worse than it was last month.
- **Eval sets rot faster than code.** Examples drawn from the original product spec go stale as the product evolves. An agent passing 98% of golden tests while scoring 60% on real traffic is the canonical symptom. The gap between "what we test" and "what users do" grows with every product change.
- **Regression without measurement is invisible.** Teams conflating observability with evaluation can see every tool call an agent made without any signal about whether those calls were correct. By the time a regression surfaces in user outcomes, weeks of degraded performance have already shipped.
- **The regression budget forces the hard conversation.** "Is this degradation acceptable to ship?" is a business question, not an engineering one. Without a budget — a defined threshold that triggers a mandatory stop — the default answer is always "ship it."

## The move

**Build a regression budget: a time-indexed evaluation system that tracks capability trajectory, not just point-in-time pass/fail, and enforces a binary hold/go decision when degradation crosses the threshold.**

### 1. Layer the eval set across three depths

```
┌─────────────────────────────────────────────────────────┐
│  Layer 1: Core Competency (run on every commit)        │
│  10-20 assertions: does the agent do the canonical      │
│  thing it must always do? Fast, deterministic, cheap.   │
├─────────────────────────────────────────────────────────┤
│  Layer 2: Integration Coverage (run on every PR)        │
│  50-200 cases: tool call sequences, edge-case           │
│  handling, multi-turn trajectories. Captures the         │
│  difference between "right answer" and "right path."    │
├─────────────────────────────────────────────────────────┤
│  Layer 3: Production Traffic Sampling (continuous)      │
│  5% of live sessions re-run through offline judge.     │
│  Mirrors real input distribution, catches drift that    │
│  no pre-deployment suite anticipates.                   │
└─────────────────────────────────────────────────────────┘
```

Layer 3 is the most valuable and most neglected. Pre-deployment eval sets drift from real traffic by definition — by the time you write a test for an edge case, you've already shipped with it. Production sampling closes this loop continuously.

### 2. Track three signal classes for regression detection

Per the PAEF framework (arXiv:2605.01604, Pandey 2026), track drift across:

- **Output distribution** — has the agent's answer profile shifted? (e.g., more refusals, different sentiment, changed length distribution)
- **Tool call behavior** — has the agent changed its tool usage patterns? (different tools, different sequences, different retry rates)
- **User outcome signals** — downstream metrics: resolution rate, escalation rate, session abandonment. These are lagging but unambiguous.

Detect drift via population-level statistical tests (chi-squared for categorical outputs, KL divergence for distribution shift), not model-vs-model comparison. The goal is detecting change, not explaining it.

### 3. Define and enforce the regression budget

The budget is a threshold with a forced binary decision. For each core capability:

```python
class RegressionBudget:
    def __init__(self, capability: str, baseline_score: float, budget_pct: float = 5.0):
        self.capability = capability
        self.baseline_score = baseline_score      # established at go-live
        self.budget = baseline_score * (1 - budget_pct / 100)
        self.evaluated_at = []
        self.scores = []

    def check(self, new_score: float, cohort_size: int) -> "RegressionResult":
        """
        Regression check for a new evaluation run.
        """
        if cohort_size < 30:
            return RegressionResult(
                decision="INCONCLUSIVE",
                reason=f"Cohor size {cohort_size} below minimum 30",
                score=new_score,
                budget=self.budget
            )

        # Use Wilson score interval for small-sample correction
        from math import sqrt
        z = 1.96  # 95% confidence
        n = cohort_size
        p = new_score / 100.0
        margin = z * sqrt((p * (1 - p)) / n + z**2 / (4 * n**2)) / (1 + z**2 / n)
        center = (p + z**2 / (2*n)) / (1 + z**2 / n)
        lower_bound = max(0, (center - margin) * 100)
        upper_bound = min(100, (center + margin) * 100)

        if upper_bound < self.budget:
            return RegressionResult(
                decision="HOLD",
                reason=f"Score {new_score}% (95% CI lower: {lower_bound:.1f}%) "
                       f"below budget {self.budget:.1f}%",
                score=new_score,
                budget=self.budget,
                ci_lower=lower_bound,
                ci_upper=upper_bound,
                cohort_size=cohort_size
            )
        else:
            return RegressionResult(
                decision="GO",
                reason=f"Score {new_score}% (CI: {lower_bound:.1f}–{upper_bound:.1f}%) "
                       f"above budget {self.budget:.1f}%",
                score=new_score,
                budget=self.budget,
                ci_lower=lower_bound,
                ci_upper=upper_bound,
                cohort_size=cohort_size
            )

    def refresh_baseline(self, new_score: float, cohort_size: int):
        """
        Recalibrate baseline after intentional improvement.
        Call only after a deliberate code/model change, not continuously.
        """
        if cohort_size >= 100:
            self.baseline_score = new_score
            self.budget = new_score * (1 - 5.0 / 100)
            self.evaluated_at.append(datetime.now())
            self.scores.append(new_score)

from dataclasses import dataclass
from datetime import datetime

@dataclass
class RegressionResult:
    decision: str       # HOLD | GO | INCONCLUSIVE
    reason: str
    score: float
    budget: float
    ci_lower: float = None
    ci_upper: float = None
    cohort_size: int = None
```

The HOLD decision is the point of the whole system. It cannot be overridden by a developer oncall at 2am — it can only be overridden by whoever owns the business risk, who must be named in the alert.

### 4. Close the feedback loop: failed production → regression tests

For every production failure that meets the threshold (e.g., user marked outcome as bad, escalation triggered), write the failed interaction to a regression corpus:

```python
def capture_production_failure(trace: AgentTrace, outcome: OutcomeLabel) -> str:
    """
    Convert a failed production trace into a regression test case.
    Returns the test case ID for tracking.
    """
    if outcome not in (OutcomeLabel.ESCALATED, OutcomeLabel.FAILED, OutcomeLabel.NEGATIVE):
        return None

    test_case = {
        "id": f"reg_{trace.session_id[:8]}_{trace.timestamp:%Y%m%d%H%M%S}",
        "input": trace.user_message,
        "expected_tool_sequence": trace.tool_calls,   # ground truth from production
        "expected_outcome": outcome,
        "captured_at": trace.timestamp,
        "tags": extract_tags(trace),                  # auto-tag for categorization
        "source": "production_feedback"
    }

    # Store in regression corpus with production-traffic tag
    regression_store.add(test_case)
    # Also notify the eval-set curation queue for human review
    curation_queue.submit(test_case, priority=Priority.HIGH)

    return test_case["id"]
```

This is the flywheel that keeps the eval set current: production is the source of truth, and failures become tests. The alternative — a static eval set maintained by engineers who haven't shipped code in that area — is always stale.

## Receipt

> Verified 2026-07-31 — Research from: Zylos Research "AI Agent Longitudinal Evaluation" (Apr 14, 2026), PAEF framework (arXiv:2605.01604, Pandey, May 2026), AgentMode AM-137 "Agent Evaluation in Production" (May 5, 2026, Holding), Velsof "AI Agent Continuous Evaluation: 7 Battle-Tested Patterns" (Jun 12, 2026). Stanford/UC Berkeley GPT-4 regression stat cited from Zylos. Code examples are minimal implementations demonstrating the pattern. Production feedback capture pattern referenced from PAEF and Velsof's eval-view tool.

## See also

- [S-1924 · The Production Drift Gap](/stacks/s1924-the-production-drift-gap-stack-when-your-agent-is-operating-normally-and-falling-apart-simultaneously.md) — monitoring for behavioral change; this chapter covers the evaluation framework that makes drift visible
- [S-1925 · The Eval Gap](/stacks/s1925-the-eval-gap-stack-the-percentage-of-teams-that-watch-their-agents-but-dont-measure-them.md) — the measurement problem this chapter solves; S-1925 identifies the gap, S-1928 provides the fix
- [S-1654 · The Stale Amplification Stack](/stacks/s1654-the-stale-amplification-stack-when-your-agent-repeats-the-same-wrong-answer-faster.md) — same amplification logic as regression blindness: problems compound because the feedback signal is absent
