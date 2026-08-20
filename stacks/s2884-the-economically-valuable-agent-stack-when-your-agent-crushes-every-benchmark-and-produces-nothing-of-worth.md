# S-2884 · The Economically Valuable Agent Stack — When Your Agent Crushes Every Benchmark and Produces Nothing of Worth

Your agent scores 94% on SWE-bench. It answers every coding question correctly in benchmarks. It handles multi-step reasoning tasks in lab conditions with near-perfect accuracy. Your team celebrates the eval results. Six months later, the agent has not shipped a single production feature autonomously. The agent is genuinely capable. The benchmark was measuring the wrong thing.

The gap is not reliability. It is economic value.

## Forces

- **Academic benchmarks measure task completion in artificial environments.** SWE-bench, GAIA, and MMLU measure whether an agent can solve a well-defined problem with a known answer. They do not measure whether an agent can sustain a 40-step workflow in a production environment, handle ambiguous requirements from real stakeholders, or produce outputs that integrate into existing business processes without human correction.
- **The hardest tier of economically valuable tasks has a <1% full-pass rate.** Agents' Last Exam (ALE, arXiv:2606.05405, June 2026, 250+ industry experts) is the first benchmark to evaluate agents on long-horizon, economically valuable, real-world tasks with verifiable outcomes. Across 55 sub-fields and 13 industry clusters, the hardest tier averages below 1% full-pass rate — even with frontier models and optimized harnesses. The 94% SWE-bench score and the <1% economic-value score are both true, for the same agent, simultaneously.
- **Production teams mistake benchmark saturation for capability saturation.** When an agent scores high on multiple academic benchmarks, teams assume the agent is ready for economically valuable deployment. The benchmarks share a structural property: they are closed-world, single-session, and outcome-verifiable. Real economic workflows are open-world, multi-session, and require outcomes that no eval harness can verify automatically.
- **Task taxonomy determines what you can measure.** ALE's 55 sub-fields (O*NET/SOC taxonomy) map to real occupations. A task that requires coordinating across a CRM, a spreadsheet, and an email thread to produce a customer health report has no eval equivalent in academic benchmarks — yet it is the exact unit of economic value an agent needs to deliver.

## The move

The pattern is **task-horizon compression**: teams evaluate agents on short-horizon, closed-world tasks and conclude the agent is ready for long-horizon, open-world economic workflows. The leap is not justified by the evidence.

### Layer 1 — Build a task taxonomy aligned with economic value

Before deploying, map your agent's target tasks to an economic taxonomy. Three questions separate economically valuable tasks from benchmark-satisfying tasks:

1. **Can a human verify the outcome without running the task?** Real economic tasks produce verifiable outputs (a filed ticket, a sent email, a modified record). If verification requires re-executing the work, the task is not economically valuable in its current form.
2. **Does the task require cross-system coordination?** Single-tool, single-context tasks have eval equivalents. Tasks requiring 3+ systems to produce a coherent outcome are the hardest tier — and the most economically valuable.
3. **Does the task have an ambiguous success criterion?** Benchmark tasks have right answers. Economic tasks have stakeholders who disagree on what "done" means. Ambiguity tolerance is a distinct capability not captured in academic evals.

### Layer 2 — Design eval around task horizon, not benchmark score

Replace single-session benchmark scores with a **task-horizon ladder**:

```
Tier 1 (0-5 min):   Single API call. Structured output.    — eval: unit test
Tier 2 (5-30 min):   3-10 tool calls. Conditional logic.    — eval: integration test + human review sample
Tier 3 (30 min-2 hr): Cross-system workflow. Partial state. — eval: shadow mode + golden output comparison
Tier 4 (2+ hr):      Multi-session. Stakeholder ambiguity.  — eval: economic outcome metrics (not task completion)
```

The goal is not to reach Tier 4 immediately. It is to know which tier your agent operates in and measure accordingly.

### Layer 3 — Use ALE FPR as your calibration signal

ALE's average full-pass rate of <1% on the hardest tier is not a failure. It is calibration data. When your agent reaches 15% FPR on Tier 4 tasks, you have an economically valuable agent. Until then, you have a well-benchmarked agent that happens to fail where it matters most.

### Layer 4 — Close the gap with harness engineering, not model upgrades

LangChain demonstrated that switching harnesses moved a coding agent from the 30th to the 5th percentile on Terminal Bench 2.0 while holding the model constant. The same principle applies to economic-value tasks: for a given model, the harness — verification layers, context management, tool orchestration, recovery logic — determines whether the agent can sustain long-horizon economic workflows. Optimize the harness before changing the model.

## Code

```python
"""
Task-horizon classifier: maps a task description to economic value tier.
Use before eval design to calibrate what kind of measurement is appropriate.
"""
from enum import Enum

class HorizonTier(Enum):
    TIER1 = "0-5 min: single call, closed outcome"
    TIER2 = "5-30 min: multi-tool, conditional"
    TIER3 = "30 min-2 hr: cross-system, partial state"
    TIER4 = "2+ hr: multi-session, stakeholder ambiguity"

TASK_HORIZON_QUESTIONS = [
    ("Can outcome be verified without re-running?", ["yes"], HorizonTier.TIER1),
    ("Requires cross-system coordination?", ["yes"], HorizonTier.TIER3),
    ("Has ambiguous success criteria?", ["yes"], HorizonTier.TIER4),
    ("Runs longer than 2 hours?", ["yes"], HorizonTier.TIER4),
    ("Involves human judgment in loop?", ["yes"], HorizonTier.TIER4),
]

def classify_task(task_description: str, answers: dict[str, bool]) -> HorizonTier:
    """Map a task + answers to the correct horizon tier."""
    for question, positive_answers, tier in reversed(TASK_HORIZON_QUESTIONS):
        if answers.get(question.lower(), False):
            return tier
    return HorizonTier.TIER1

def eval_strategy(tier: HorizonTier) -> str:
    strategies = {
        HorizonTier.TIER1: "unit test + structured output validation",
        HorizonTier.TIER2: "integration test + 10% human review",
        HorizonTier.TIER3: "shadow mode + golden output comparison",
        HorizonTier.TIER4: "economic outcome metrics (throughput, error rate, stakeholder NPS)",
    }
    return strategies[tier]

# Example
answers = {
    "can outcome be verified without re-running?": False,
    "requires cross-system coordination?": True,
    "has ambiguous success criteria?": True,
    "runs longer than 2 hours?": False,
    "involves human judgment in loop?": True,
}
tier = classify_task("Generate weekly customer health report from CRM + email + spreadsheet", answers)
print(f"Tier: {tier.value}")
print(f"Eval strategy: {eval_strategy(tier)}")
# Tier: 2+ hr: multi-session, stakeholder ambiguity
# Eval strategy: economic outcome metrics (throughput, error rate, stakeholder NPS)
```

## Receipt

> Verified 2026-08-19 — arXiv:2606.05405v1 (ALE, June 2026, MaxIntelligenceAgency/ALE-Benchmark GitHub, 250+ industry experts, 55 sub-fields, 13 industry clusters, <1% FPR on hardest tier). LangChain harness engineering result: Terminal Bench 2.0, Top 30 → Top 5 with harness changes only. Sam Griffith checkpointing article (June 16, 2026): data gravity and schema evolution principles confirmed in production workflows.

## See also

- [S-2418 · The Benchmark Paradox](s2418-the-benchmark-paradox-when-your-agent-passes-every-test-and-fails-every-deployment.md) — synthetic benchmark saturation vs. deployment failure (related but covers the benchmark-faithfulness angle, not economic-value taxonomy)
- [S-996 · The Harness Matters More Stack](s996-the-harness-matters-more-stack-when-your-model-isnt-the-problem.md) — model-agnostic improvement through harness optimization
- [S-1890 · The Difficulty-Aware Escalation Stack](s1890-the-difficulty-aware-escalation-stack-when-static-tiers-hit-their-ceiling.md) — tier-based routing with explicit difficulty signals
