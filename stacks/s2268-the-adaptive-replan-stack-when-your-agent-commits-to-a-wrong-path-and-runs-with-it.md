# S-2268 · The Adaptive Replan Stack — When Your Agent Commits to a Wrong Path and Runs With It

Your agent receives a task: "reconcile the Q2 expense report." It plans five steps, executes them all, and returns with a clean summary. Three days later the accountant flags $14,000 in miscategorized spending. The agent never noticed the plan was wrong — it executed flawlessly on a flawed premise. This is the brittle planning failure, and it is the dominant mode of production agent collapse. The agent isn't hallucinating. It isn't looping. It is following a plan that reality invalidated somewhere between step 1 and step 5, and it has no mechanism to notice.

## Forces

- **Linear plans are the default but reality is not.** ReAct loops, single-agent executors, and most scaffold frameworks generate a fixed action sequence and commit to it. The moment an intermediate result diverges from expectation, the plan is stale. Without a revision mechanism, the agent propagates the error forward and compounds it.
- **Replanning is expensive and teams avoid it.** Each replan costs tokens, latency, and money. Teams fear runaway replan loops — agents that regenerate plans endlessly without converging. The legitimate cost of replanning creates a structural incentive to over-commit to the current plan.
- **The agent cannot distinguish "plan needs revision" from "plan is working."** Without an explicit divergence detection signal, the agent treats unexpected tool outputs as valid inputs to the next step. A wrong database query result looks identical to a correct one from inside the loop.
- **Standard retry logic doesn't help.** Retrying a failed tool call is not replanning. Replanning is questioning the plan itself: "Given what just happened, is this still the right path?"
- **Plan revision at the wrong granularity causes drift cascades.** Zylos Research (2026) documented that each replan without a grounding mechanism (state checkpoint, goal anchor, or success criteria) adds hallucination surface. By plan version 5, the agent is solving a different problem than the one it started with.

## The Move

### 1. Instrument the plan-state boundary

Before anything else, track what the plan *expected* vs. what *happened*. This is the divergence signal that triggers replanning.

```
class PlanState:
    expected: dict[str, Any]   # key → expected value from tool output
    actual: dict[str, Any]     # key → actual value returned
    checkpoints: list[dict]   # snapshot of state at each step
    revision_count: int = 0
    goal: str                  # immutable anchor for drift check

def check_divergence(state: PlanState, threshold: float = 0.3) -> bool:
    """Return True if actual deviates enough from expected to warrant replan."""
    if not state.expected:
        return False
    divergent_keys = sum(
        1 for k, v in state.expected.items()
        if k in state.actual and v != state.actual[k]
    )
    divergence_ratio = divergent_keys / max(len(state.expected), 1)
    return divergence_ratio >= threshold
```

### 2. Three-tier replan trigger

Not every deviation warrants the same response. Build a trigger hierarchy:

| Tier | Signal | Response |
|------|--------|----------|
| **Retry** | Single tool failed (timeout, rate limit, auth) | Re-execute same step with adjusted params |
| **Revise** | Output diverged from expected schema or semantic bounds | Preserve goal, regenerate remaining steps only |
| **Abort** | Revision count exceeded, or goal anchor violated | Escalate to human, return partial result with confidence flag |

### 3. Grounded replan — anchor the goal, not the history

The critical mistake is replanning with the corrupted context as the starting point. Instead, anchor replanning to the immutable goal and the last known-good checkpoint:

```
def replan(agent, state: PlanState, goal: str, max_revisions: int = 3) -> Plan:
    if state.revision_count >= max_revisions:
        return ABORT

    # Discard the diverged plan; restart from checkpoint
    last_safe = state.checkpoints[-1] if state.checkpoints else {}
    state.checkpoints.clear()  # start fresh from here
    state.revision_count += 1

    prompt = f"""
    Goal: {goal}
    Context: {last_safe}
    Previous plan failed because: {summarize_divergence(state)}.
    Generate a new plan that avoids the previous failure mode.
    """
    return agent.plan(prompt)
```

### 4. Cost-bounded replan budget

Stanford HAI (2026) found that 68% of enterprise agent failures trace to recovery loops rather than the original failure. Cap replanning aggressively:

- Hard limit: 2–3 replans per task, configurable by task criticality
- Token budget: stop if cumulative replan tokens > 15% of original task estimate
- Divergence threshold tuning: tighten threshold for high-stakes tools (payments, writes, deletions), loosen for read-only exploratory steps

### 5. Commit signals — explicit success markers

Agents need to declare checkpoints, not just outputs. Every step should emit a `step_commit` signal:

```
step_commit = {
    "step_id": 3,
    "action": "fetch_orders",
    "result_summary": "Retrieved 847 orders from Q2, 12 with missing customer_id",
    "committed": True,   # agent affirms this result is trustworthy
    "flags": ["missing_data_suppressed"]  # known caveats
}
```

Downstream steps can then assert that prior commits still hold before proceeding.

## Receipt

> Receipt pending — The patterns described are synthesized from Zylos Research (May 2026), Stanford HAI Agent Reliability Report (2026), Velsof Enterprise AI Replanning Patterns (June 2026), and the Redis.io Agent Context Failure Modes analysis (July 2026). Code patterns are illustrative; adapt divergence thresholds and replan budgets to your task criticality.

## See also

- [S-1023 · The Recovery Ladder](stacks/s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — Semantic success signals and the gap between HTTP 200 and actual success
- [S-1046 · The Agent Dead-End Stack](stacks/s1046-the-agent-dead-end-stack-when-your-agent-fails-and-cant-recover.md) — Distinguishing recoverable failures from genuine dead ends
- [S-995 · The Agent Failure Recovery Stack](stacks/s995-the-agent-failure-recovery-stack-when-your-agent-loops-hangs-or-hammers-itself-against-a-dead-end.md) — Loop detection and failure taxonomy for agentic systems
