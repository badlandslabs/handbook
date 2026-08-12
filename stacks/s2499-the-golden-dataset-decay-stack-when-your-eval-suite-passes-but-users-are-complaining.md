# [S-2499] · The Golden Dataset Decay Stack

Your eval suite reports 87% pass rate. You shipped the prompt change. Users started complaining within a week. The score went up — but the agent got worse on the cases that actually matter. This is not a regression. This is your golden dataset measuring what you already solved, not what is breaking right now.

## Forces

- Teams treat eval sets like constitutions: authoritative, permanent, expensive to touch. Six months of product evolution, model updates, and input distribution shift turn a precision instrument into a lagging indicator.
- Adding test cases makes this worse, not better — each new case captures the distribution you already solved, overfitting the old problem and making the set less sensitive to the new one.
- Improving the agent can *lower* your eval score if the eval set captured the previous broken behavior. The signal goes green; the product goes dark.
- The team sees green checks and ships. Nobody looks at whether the eval set still reflects what users actually ask.
- Eval-set construction is expensive and slow. By the time a new test case reaches CI, the problem it targets has already evolved.

## The move

### Three mechanisms of decay

**Distribution shift** — User queries change faster than your eval set. A customer-support agent trained on Q1 queries will see Q3 queries with different vocabulary, intent distribution, and edge-case vocabulary. The eval set still measures Q1 performance accurately. It says nothing about Q3.

**Ground truth drift** — The "correct" answer changes. Product policies evolve, API behavior changes, business rules update. If your eval set was written against a knowledge base that has since changed, every test case that references it produces a false negative — the agent is right, the eval says wrong.

**Synthetic contamination** — Eval cases written by the team or generated from the model's own outputs inherit the model's quirks. The agent passes because it recognizes the distribution it was trained on, not because it generalizes. This is eval-set overfitting.

### Detection signals

```
# Signal 1: Eval pass rate is high but user-reported failure rate is rising
eval_pass_rate: 0.87    # green
user_complaint_rate: 0.12  # trending up, not reflected in evals

# Signal 2: New production failure patterns never appear in eval regressions
# Check: how many bug reports from last 30 days have corresponding eval cases?
production_bug_cases_with_eval: 2 / 47   # < 5%

# Signal 3: Eval set age vs. product churn rate
eval_set_age_days > 90 AND product_policy_changes > 15  # red flag

# Signal 4: Coverage decay ratio
# What % of last month's user queries would be covered by current eval set?
cohort_coverage = len(eval_set_keywords ∩ last_month_query_keywords) / len(last_month_query_keywords)
# Below 0.4 = eval set is measuring the wrong half
```

### The rotation protocol

1. **Sample production traffic weekly.** Capture 200–500 real user queries as eval candidates. Classify them into existing test categories and "orphaned" — cases no current eval covers.
2. **Orphan triage.** Every orphaned case is either noise or a new failure class. A human expert decides in under 2 minutes per case. The ones worth keeping become new eval cases; the rest are logged.
3. **Staleness scoring.** Each eval case carries a `last_verified` timestamp and a `policy_version` reference. Cases older than 60 days or referencing outdated policies are flagged `STALE` and excluded from the pass-rate calculation until refreshed.
4. **Ground-truth versioning.** Tie eval cases to the specific product version or policy snapshot they were written against. When the referenced version is deprecated, the case auto-flags for review.
5. **Rotation budget.** Aim to replace 10–15% of the eval set per quarter. Not add — replace. This prevents accumulation of obsolete cases and forces triage of the old.

```python
# Minimal staleness gate for CI
import hashlib, datetime

def eval_case_staleness(case: dict, max_age_days: int = 60) -> bool:
    last_verified = datetime.date.fromisoformat(case["last_verified"])
    age = (datetime.date.today() - last_verified).days
    policy_match = case.get("policy_version") == current_policy_version()
    return age > max_age_days or not policy_match

def ci_pass_rate(cases: list[dict], threshold: float = 0.85) -> bool:
    fresh = [c for c in cases if not eval_case_staleness(c)]
    if not fresh:
        return False  # can't ship with all cases stale — forces triage
    return sum(run_eval(c) for c in fresh) / len(fresh) >= threshold
```

### The contamination check

Run eval cases through a separate model or a deterministic reference (not the agent under test). If the reference also "passes" a case the agent fails, the case may be testing something the agent never learned. If the reference also fails the case, the ground truth may be wrong.

## Receipt

> Receipt pending — 2026-08-11

## See also

- [S-401 · The Agent Drift Stack](s401-the-agent-drift-the-longitudinal-regression-problem.md) — longitudinal eval tracks agent behavior over time; this entry tracks eval-set relevance over time
- [S-1497 · The Lucky Recovery Stack](s1497-the-lucky-recovery-stack-mining-production-traces-for-masked-failures.md) — production trace mining feeds the rotation protocol in this entry
- [S-1010 · The Agent Eval Stack](s1010-the-agent-eval-stack-when-you-cannot-trust-your-tests.md) — broader eval architecture; this entry focuses on dataset decay specifically
