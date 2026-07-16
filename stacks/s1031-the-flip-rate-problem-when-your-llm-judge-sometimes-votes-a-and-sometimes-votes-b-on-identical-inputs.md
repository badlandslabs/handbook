# [S-1031] · The Flip Rate Problem

*When your LLM judge votes A on run one, B on run two, and tie on run three — all on identical inputs. Running a single evaluation is not validation; it is a coin flip with extra steps.*

Your eval pipeline runs on every PR. The LLM-as-judge gates merges. Your coverage dashboard is green. What nobody notices is that running the same 500-item eval set again — same judges, same inputs, same temperature — produces a different answer for roughly 1 in 7 items. For 28% of your test questions, it flips more than 20% of the time. One category reaches 56%. Your "measurement" has a measurement problem.

This is the **flip rate** problem: LLM judges are stochastic, and single-trial evaluation systematically overstates reliability.

## Forces

- **LLM-as-judge stochasticity is structural, not thermal.** Temperature=0 does not make LLMs deterministic. Sampling decisions within transformer attention heads introduce run-to-run variation that is invisible in single-trial design.
- **CI/CD gates are binary but your measurement is probabilistic.** A judge that flips 13.6% of the time on a 500-item eval produces a ±7-point confidence interval on your pass/fail decision. You are gating on noise.
- **The fix — repeated trials — costs N×.** Getting to 95% eval fidelity requires 11 repeated trials per item. At scale, that is 5,500 API calls per evaluation run. Most teams choose the cheaper path and accept the noisy answer.
- **Flip rate correlates with task difficulty.** Reasoning-heavy questions show the highest flip rates (up to 56%). Simple factual comparison questions show the lowest. You cannot treat flip rate as a uniform fudge factor — it varies by question type.
- **Prompt template choice flips outcomes independently.** 25% of verdicts change when you swap one reasonable prompt template for another — on the same judge, same inputs. Prompt engineering is not just about score levels; it affects consistency too.

## The Move

**1. Measure flip rate before trusting any judge.**

Run each eval item 3–5 times and compute the flip rate:

```
Flip Rate = 1 - (majority_vote_count / N_trials)
```

For pairwise comparison, a flip from A→B or B→A (excluding ties) is the event. For pointwise scoring, a flip is any score change > 1 point. Set a threshold: FR > 15% on a question category disqualifies that category from single-trial gating.

**2. Budget for N-trial fidelity when stakes are high.**

For production quality gates (regression detection, model selection), use the minimum trials needed for your target fidelity:

| Desired Fidelity | Required Trials |
|-------------------|-----------------|
| 90% | 5 |
| 95% | 11 |
| 99% | 21 |

Run trials in parallel batches to avoid confounding temporal drift. Track flip rate over time — if it increases, the judge model may be degrading.

**3. Stratify flip rate by question type.**

Run a flip rate audit across your eval categories. Flag high-flip categories for mandatory multi-trial evaluation or human review. Low-flip categories (factual comparison, formatting checks) can stay on single-trial.

```python
# Flip rate audit across eval categories
def flip_rate_by_category(eval_items, judge_model, n_trials=5):
    results = {}
    for category, items in group_by_category(eval_items):
        verdicts = []
        for item in items:
            trial_results = [
                judge_pairwise(item.prompt, item.response_a, item.response_b)
                for _ in range(n_trials)
            ]
            verdicts.append(trial_results)
        flips = sum(1 for v in verdicts if len(set(v)) > 1) / len(verdicts)
        results[category] = {"flip_rate": flips, "n_items": len(items)}
    return results
    # Flag: {category: "reasoning", flip_rate: 0.31} → require N=11 trials
    # Flag: {category: "format", flip_rate: 0.04} → single-trial OK
```

**4. Combine flip rate with cross-judge agreement.**

Flip rate measures *intra-judge* reliability. Cross-judge κ (from S-1024) measures *inter-judge* reliability. You need both. A judge with low flip rate but low κ is consistent with itself but wrong. A judge with high flip rate and high κ is noisy and unreliable. The product is what matters:

> Reliable eval signal = low flip rate × high cross-judge κ

Flag judges where flip rate + κ together fall below a composite threshold. Route high-stakes evaluations to judges passing both filters.

**5. Use majority vote with abstention for noisy items.**

For items with flip rate > 20%, the honest answer is "unresolved." Don't force a binary gate on a noisy measurement. Mark these as `REVIEW_REQUIRED` and either run additional trials or escalate to human annotation. The eval dashboard should show `N_UNRESOLVED` alongside `SCORE` — treating uncertain items as 100% resolved is the same class of error as ignoring null measurements.

## Receipt

> Verified 2026-07-13 — arXiv:2606.13685 (Yagubyan, April 2026): 29 tasks, 2 OpenAI judges (GPT-4o-mini, GPT-4.1-mini), mean flip rate 13.6%, 28% of questions exceed 20% FR, max 56% on reasoning tasks. 11 trials needed for 95% fidelity. QA Skills .sh eval guide (June 2026) confirms pairwise mode is most flip-prone; prompt template swaps flip 25% of verdicts.

## See also

- [S-1024 · The Kappa Deflation Problem](s1024-the-kappa-deflation-problem-when-your-llm-judge-reports-85-but-has-kappa-0.48.md) — inter-judge reliability and chance-corrected agreement
- [S-451 · LLM-as-Judge Failure Modes: The Echo Chamber Problem](s451-llm-as-judge-failure-modes.md) — systematic judge biases (position, verbosity, self-preference)
- [S-230 · Agent Harness Engineering](s230-agent-harness-engineering-the-eval-layer-production-demands.md) — building eval harnesses that can accommodate multi-trial design
