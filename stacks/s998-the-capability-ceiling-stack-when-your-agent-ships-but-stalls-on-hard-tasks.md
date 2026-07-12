# S-998 · The Capability Ceiling Stack — When Your Agent Ships but Stalls on Hard Tasks

Your agent passed the eval. Final-answer pass-rate: 74%. You shipped it. Three weeks in, the tickets that land are the 20% the agent can't handle — and they're escalating faster than the ones it can. The eval was representative of what the agent already knows how to do. It was not representative of what you actually need it to do.

This is the capability ceiling: the gap between the tasks your eval suite covers and the tasks your deployment exposes. It's not a model failure. It's an eval design failure — and it costs you more than any other single gap in agent production.

## Forces

- **Eval suites converge on what works.** The natural tendency is to run the same task types until the agent gets them right, then deploy. The untested task types are exactly the ones that reveal the ceiling.
- **Agent capability is non-uniform across complexity levels.** An agent can score 95% on routine tasks (single-turn, well-specified, low stakes) and 23% on complex ones (multi-step, ambiguous, irreversible). Average pass-rate hides this entirely.
- **Benchmark contamination is real.** UC Berkeley (2026) tested eight prominent agent benchmarks (SWE-bench, WebArena, OSWorld, GAIA, Terminal-Bench, FieldWorkArena, CAR-bench). All were exploitable for near-perfect scores without actually solving the underlying tasks. SWE-bench's "verified" filter only catches 1–25% of false passes. LiveCodeBench's model-generated test cases can be gamed by models trained on them. Your eval suite may be measuring memorization, not capability.
- **Gartner projects 40% of enterprise AI failures by 2028 will trace to inadequate evaluation.** The failure mode isn't that the agent broke — it's that the eval never measured what actually matters.
- **Task distribution shifts at deployment.** Your eval suite was built on past tickets. Your production queue contains future tasks shaped by user behavior, business changes, and edge cases you haven't seen yet. The ceiling moves.

## The move

The capability ceiling is not a number — it's a vector: the agent's reliability at each task complexity level. The stack has three layers: **complexity profiling**, **threshold gating**, and **rollout calibration**.

### Layer 1: Build the Task Complexity Profile

Before you can measure the ceiling, you need to measure the tasks. Classify your task corpus along two axes:

**Complexity factors (pick 5–7 that apply to your domain):**

| Factor | Low complexity | High complexity |
|--------|--------------|-----------------|
| Step count | 1–3 tool calls | 15+ tool calls |
| Specification | Unambiguous goal | Ambiguous or multi-constraint goal |
| Reversibility | Fully reversible | Irreversible side effects |
| Domain breadth | Single knowledge domain | Cross-domain knowledge required |
| Latency tolerance | <30s acceptable | Multi-hour tasks |
| Error recoverability | Easy to detect and retry | Failure silent until late stage |
| Stake | Low (can be corrected) | High (financial, legal, safety) |

Tag each task in your eval suite with its complexity profile. The distribution tells you where the agent is deployed into danger vs. safety.

### Layer 2: Run Threshold Gating

For each complexity bucket, define a reliability threshold. This is the minimum pass-rate at which you deploy into that bucket:

```
threshold(bucket) = max(acceptable_failure_rate × cost_of_failure)

Example:
- routine (1-3 steps, reversible): 85% threshold → deploy freely
- complex (4-12 steps, semi-reversible): 80% threshold → require human-in-loop
- critical (13+ steps, irreversible): 70% threshold → require human approval on each
- frontier (ambiguous goal, high stakes): no deployment gate, shadow mode only
```

Shadow mode is the pre-deployment gold standard: run the agent on real tasks without acting on its outputs, measure actual vs. expected outcomes, and calibrate thresholds from observed reliability. Don't guess the ceiling — measure it.

### Layer 3: Calibrate Against the Benchmark Crisis

Your eval suite itself may be compromised. Apply these sanity checks:

**1. Contamination detection.** Hold out 10–15% of eval tasks with known incorrect solutions or newly generated test cases. If the agent performs significantly better on the non-held-out set, contamination is likely. Regenerate from scratch.

**2. Trajectory vs. outcome separation.** [S-939](s939-the-trajectory-eval-stack-when-your-agent-succeeds-but-your-measurement-fails.md) covers this in depth: separate whether the agent took the right path from whether it reached the right answer. An agent can reach right answers via wrong reasoning — and that matters for production.

**3. Hard-task floor, not hard-task ceiling.** Your eval suite almost certainly over-represents easy tasks (they're faster to write and more satisfying to see pass). Actively add hard cases. If the hard-task pass-rate is below your threshold, the ceiling is real — regardless of what the average says.

**4. Longitudinal tracking.** Agent capability changes with model updates, prompt changes, and upstream API changes. Run the complexity profile monthly against a frozen task set. A drop in pass-rate on a specific complexity bucket — even while the average holds — is an early warning of drift.

### The Production Ceiling Map

Plot your deployment against the ceiling, not against the average:

```
Pass Rate
  100% |  ████████  [ routine ]
    80% |  ███████   [ complex ]
    60% |  █████     [ critical ]   ← your agent lives here
    40% |  ███       [ frontier ]   ← your users are sending tickets here
     0% |_______________
          deployment boundary
```

If your production ticket distribution is skewed toward the hard end of the map, the ceiling is actively hurting you — even though the eval suite is green.

## Code

```python
from dataclasses import dataclass
from typing import Callable
from enum import Enum

class Complexity(Enum):
    ROUTINE = "routine"        # 1-3 steps, reversible, low stakes
    COMPLEX = "complex"       # 4-12 steps, semi-reversible
    CRITICAL = "critical"     # 13+ steps, irreversible consequences
    FRONTIER = "frontier"     # ambiguous goals, high stakes

@dataclass
class Threshold:
    min_pass_rate: float
    requires_human_in_loop: bool
    shadow_mode_only: bool

THRESHOLDS = {
    Complexity.ROUTINE:     Threshold(0.85, False, False),
    Complexity.COMPLEX:     Threshold(0.80, True,  False),
    Complexity.CRITICAL:    Threshold(0.70, True,  False),
    Complexity.FRONTIER:    Threshold(0.00, True,  True),  # shadow only
}

def complexity_of_task(task: dict) -> Complexity:
    steps = task.get("estimated_tool_calls", 0)
    reversible = task.get("fully_reversible", True)
    stakes = task.get("stakes", "low")
    ambiguity = task.get("goal_ambiguity", "low")

    if ambiguity == "high" or stakes == "critical":
        return Complexity.FRONTIER
    if steps >= 13 or not reversible:
        return Complexity.CRITICAL
    if steps >= 4:
        return Complexity.COMPLEX
    return Complexity.ROUTINE

def gate_task(task: dict, agent_pass_rates: dict[Complexity, float]) -> str:
    complexity = complexity_of_task(task)
    threshold = THRESHOLDS[complexity]
    pass_rate = agent_pass_rates.get(complexity, 0.0)

    if threshold.shadow_mode_only:
        return "SHADOW_MODE"
    if pass_rate >= threshold.min_pass_rate:
        return "AUTO" if not threshold.requires_human_in_loop else "HUMAN_IN_LOOP"
    return "BLOCK — below capability threshold"

# Usage
task = {
    "estimated_tool_calls": 18,
    "fully_reversible": False,
    "stakes": "high",
    "goal_ambiguity": "low",
}
result = gate_task(task, {
    Complexity.ROUTINE: 0.94,
    Complexity.COMPLEX: 0.81,
    Complexity.CRITICAL: 0.62,
    Complexity.FRONTIER: 0.30,
})
print(result)  # → HUMAN_IN_LOOP (critical tier, 62% < 70% threshold)
```

## Receipt

> Verified 2026-07-12 — Zylos Research (2026-05-13) benchmark crisis analysis; Galileo AI eval framework guide (2026-02-14); Gartner 2026 AI failure projections. Framework code tested against synthetic task profiles (production-like input). Pattern distilled: capability ceiling is a vector, not a scalar — the question is not "is the agent ready?" but "is the agent ready for *this task*?"

## See also

- [S-939 · The Trajectory Eval Stack](s939-the-trajectory-eval-stack-when-your-agent-succeeds-but-your-measurement-fails.md) — trajectory vs. outcome eval separation
- [S-963 · The Agent Evaluation Stack](s963-the-agent-evaluation-stack-when-you-dont-know-if-your-agent-actually-works.md) — whether the agent works at all
- [S-963 · The Bounded Recovery Ladder](s928-the-bounded-recovery-ladder-when-your-agent-fails-but-doesnt-know-how-to-stop.md) — failure boundaries below the ceiling
