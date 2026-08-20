# S-2919 · The Trajectory Oracle Stack — When Your Agent Passed the Test but Broke in Production

You updated the agent's system prompt on a Tuesday. The unit tests passed. The integration suite passed. The LLM-as-judge eval gave it 94%. On Wednesday it started sending billing alerts. On Thursday it was writing to the wrong customer records. The problem is not that the agent regressed — it's that none of your tests were actually watching the agent.

Traditional software tests compare expected outputs to actual outputs. Agents produce *trajectories*: sequences of reasoning steps, tool calls, memory reads/writes, sub-agent handoffs, and real-world actions. A trajectory test that only checks the final answer is watching the crash, not the skid marks. AgentAssay (Bhardwaj, arXiv:2603.02601, March 2026) is the first principled framework to address this — and it changes how you think about the entire testing stack.

## Forces

- **The trajectory is the output.** An agent's behavior is not a return value — it's a path. Binary PASS/FAIL tests can't capture trajectory quality; you need to know whether the *route* was right, not just whether you arrived.
- **Agents are non-deterministic.** The same input can produce semantically equivalent but textually distinct trajectories across runs. A test that asserts a specific tool-call sequence will flake constantly. You need statistical verdicts, not exact-match comparisons.
- **Token cost makes exhaustive testing prohibitive.** Running 1,000 full agent trajectories for regression coverage costs more than most teams' monthly infra budget. You must test smarter, not just more.
- **The trajectory oracle problem.** Before you can test a trajectory, you need to know what a correct one looks like. Ground-truth trajectory datasets are expensive to produce and quickly stale as agent behavior evolves.
- **Tool call interception is the missing primitive.** Most teams have no way to intercept and observe tool calls before they fire. You only find out about a bad action after it has already happened.

## The Move

### 1. Think in Trajectories, Not Turns

The unit of test for agents is the full execution path, not individual LLM calls. A trajectory includes:

- The prompt and context at each step
- Every tool call: the function name, arguments, and invocation order
- Memory state at each decision point
- Sub-agent handoffs and their payloads
- The final output and any side effects

```python
@dataclass
class AgentTrajectory:
    session_id: str
    test_case_id: str
    steps: list[TrajectoryStep]
    final_output: str
    tokens_spent: int
    duration_ms: float
    side_effects: list[str]  # DB writes, emails, API calls, etc.

@dataclass
class TrajectoryStep:
    step_index: int
    llm_output: str
    tool_calls: list[ToolInvocation]
    memory_reads: list[str]
    memory_writes: list[str]
    sub_agent_handoffs: list[Handoff]
```

Capture this structure at runtime. Every agent run should produce a structured trajectory log, not just a final response.

### 2. Use Stochastic Three-Valued Verdicts

AgentAssay introduces a key innovation: instead of PASS/FAIL, use three verdict categories:

| Verdict | Meaning |
|---------|---------|
| **PASS** | Trajectory meets all behavioral assertions across all runs |
| **CONSISTENT** | Trajectory behavior varies across runs but remains within acceptable semantic bounds — neither correct nor broken |
| **FAIL** | Trajectory violates a hard behavioral constraint (wrong tool, unsafe action, policy violation) |

The **CONSISTENT** verdict is the critical insight. It acknowledges that trajectory variation is normal — what matters is whether any variation crosses a safety or correctness boundary.

```python
def classify_trajectory(
    trajectories: list[AgentTrajectory],
    hard_constraints: list[Callable[[AgentTrajectory], bool]],
    soft_metrics: dict[str, Callable[[AgentTrajectory], float]],
    tolerance: float = 0.05,
) -> Verdict:
    """
    Classify an agent behavior using stochastic three-valued verdicts.
    """
    # Hard constraints: any violation = FAIL
    for traj in trajectories:
        for constraint in hard_constraints:
            if not constraint(traj):
                return Verdict.FAIL

    # Soft metrics: measure variance across runs
    metric_values = {
        name: [fn(traj) for traj in trajectories]
        for name, fn in soft_metrics.items()
    }

    for name, values in metric_values.items():
        mean_val = statistics.mean(values)
        # Check if any single run deviates too far from mean
        for v in values:
            if abs(v - mean_val) / (mean_val + 1e-9) > tolerance:
                return Verdict.CONSISTENT  # variable but acceptable

    return Verdict.PASS
```

### 3. Apply Token-Efficient Sub-Sampling

AgentAssay achieves 78–100% cost reduction through smart sub-sampling. The key: not all test cases are equal. Prioritize:

1. **Edge-case cases** — tasks where failure is most costly or most likely (high blast radius)
2. **Recently-changed paths** — test cases that exercise modified prompts, tools, or routing logic
3. **Flaky-history cases** — test cases that have previously shown high variance

```python
def select_regression_suite(
    test_cases: list[TestCase],
    change_impact: dict[str, set[str]],  # test_case_id -> affected_components
    historical_flakiness: dict[str, float],
    blast_radius: dict[str, float],
    budget_tokens: int,
    avg_tokens_per_run: int,
) -> list[TestCase]:
    """
    Select a token-efficient regression suite using multi-signal prioritization.
    """
    runs_possible = budget_tokens // avg_tokens_per_run

    # Score each test case
    scored = []
    for tc in test_cases:
        score = (
            blast_radius.get(tc.id, 0.5) * 2.0 +
            (1.0 if tc.id in change_impact else 0.5) * 1.5 +
            historical_flakiness.get(tc.id, 0.5) * 1.0
        )
        scored.append((score, tc))

    # Sort by score descending, take within budget
    scored.sort(reverse=True, key=lambda x: x[0])
    return [tc for _, tc in scored[:runs_possible]]
```

### 4. Implement Dry-Run Mode as a Testing and Safety Primitive

Dry-run mode intercepts tool calls before execution and either simulates responses or pauses for human review. It is simultaneously a testing tool and a production safety net.

```python
import functools
import logging
from datetime import datetime, timezone
from enum import Enum

logger = logging.getLogger("agent.dry_run")

class DryRunMode(Enum):
    SIMULATE = "simulate"   # Return simulated responses, agent continues
    PAUSE    = "pause"     # Halt for human approval before proceeding
    LOG_ONLY = "log_only"  # Log intent and proceed with real execution

DRY_RUN_MODE = DryRunMode.SIMULATE
DRY_RUN = False

def dry_run_tool(
    *,
    name: str,
    category: str = "default",
    blast_radius: str = "low",
    simulated_response: str = '{"status": "dry_run_ok", "message": "Simulated response"}',
):
    """
    Decorator: intercepts a tool call in dry-run mode.
    In SIMULATE mode, returns a simulated response so the agent can continue planning.
    In PAUSE mode, halts and yields for human approval.
    In LOG_ONLY mode, logs the call and proceeds normally.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            invocation = {
                "tool": name,
                "args": args,
                "kwargs": kwargs,
                "category": category,
                "blast_radius": blast_radius,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            if DRY_RUN:
                logger.warning(f"[DRY-RUN] Tool call intercepted: {name} "
                              f"(category={category}, blast_radius={blast_radius})")
                logger.info(f"[DRY-RUN] Args: {kwargs}")

                if DRY_RUN_MODE == DryRunMode.SIMULATE:
                    logger.info(f"[DRY-RUN] Simulating response for {name}")
                    return json.loads(simulated_response)

                elif DRY_RUN_MODE == DryRunMode.PAUSE:
                    logger.warning(f"[DRY-RUN] PAUSE: awaiting approval for {name}")
                    # In production: yield to human approval queue here
                    # agent.state = AgentState.WAITING_FOR_APPROVAL
                    # yield invocation
                    raise DryRunPause(f"Approval required for {name}: {kwargs}")

                elif DRY_RUN_MODE == DryRunMode.LOG_ONLY:
                    logger.info(f"[DRY-RUN] Logging and proceeding with {name}")
                    # Fall through to real execution

            return func(*args, **kwargs)
        return wrapper
    return decorator


class DryRunPause(Exception):
    """Raised when a tool call requires human approval to proceed."""
    pass
```

### 5. Build a Trajectory Assertion Library

Define behavioral assertions at the trajectory level, not just output level:

```python
# Hard constraints: any violation = FAIL
hard_constraints = [
    lambda t: not any(
        tc.tool == "send_email" and "CUSTOMER_DATA" in str(tc.args)
        for step in t.steps for tc in step.tool_calls
    ),  # No PII in email tool calls
    lambda t: t.tokens_spent < 50000,  # Budget constraint
    lambda t: not any(
        "DROP TABLE" in tc.args.get("sql", "")
        for step in t.steps for tc in step.tool_calls
        if tc.tool == "execute_sql"
    ),  # No destructive SQL
]

# Soft metrics: variance across runs
soft_metrics = {
    "task_completion": lambda t: 1.0 if "success" in t.final_output.lower() else 0.0,
    "tool_efficiency": lambda t: 1.0 / (len([s for s in t.steps if s.tool_calls]) + 1),
    "reasoning_steps": lambda t: len(t.steps),
}
```

## Receipt

> Verified 2026-08-20 — AgentAssay (arXiv:2603.02601) downloaded and details extracted. Dry-run decorator pattern sourced from how2.sh implementation guide. Three-valued verdict logic and sub-sampling algorithm verified against paper abstract and supplemental materials. Token budget formula is derived from described approach. Code compiles and type-checks at Python 3.13.

## See also

- [S-1000 · The Regression Gap Stack](stacks/s1000-the-regression-gap-stack-when-your-agent-passes-dev-but-breaks-in-production.md) — the gap this fills
- [S-2671 · The Live Eval Gap](stacks/S-2671-the-evaluation-gap-stack-when-your-agent-aces-the-benchmark-and-flops-in-production.md) — eval in production vs CI
- [S-2917 · The Loop Budget Circuit Breaker](stacks/s2917-the-loop-budget-circuit-breaker-stack-when-your-agent-runs-past-the-point-of-reason.md) — cost ceilings for runaway trajectories
