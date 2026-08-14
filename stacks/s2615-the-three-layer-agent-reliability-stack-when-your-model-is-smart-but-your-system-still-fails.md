# S-2615 · The Three-Layer Agent Reliability Stack

When your model does everything right but your system still fails — because eval, guardrail, and harness are solving three different problems, and you're mixing them up.

## Forces

- **The voice agent demo failure**: the LLM understood the request perfectly, but the harness let three response paths fire simultaneously. Nothing wrong with the model. Everything wrong with the orchestration layer.
- **Eval, guardrail, and harness answer different questions** — "did it do well?", "was it allowed to do that?", and "was the execution structurally sound?" — and teams routinely collapse them into one.
- **Guardrails fail at execution failures**: policy-based filtering catches bad tool calls before they fire, but can't detect that two parallel branches are about to write conflicting state.
- **Eval fails at structural bugs**: LLM-as-judge scores an agent high when it returns a correct final answer even if it wasted 40% of its budget on a retry spiral. The outcome was fine; the path was broken.
- **The harness is where concurrent agents corrupt state**: shared mutable state, version conflicts, and fan-out failures live below the surface where neither eval nor guardrail can see them.

## The move

**Treat eval, guardrail, and harness as three orthogonal layers.** Each has a distinct failure mode and a distinct fix.

```
┌─────────────────────────────────────────────────────┐
│  EVAL      — Did the agent perform well?           │
│             Outcome measurement, LLM-as-judge,       │
│             task completion scoring                 │
├─────────────────────────────────────────────────────┤
│  GUARDRAIL — Was the agent permitted to act?        │
│             Pre-execution policy filter, tool       │
│             allowlist, content classification       │
├─────────────────────────────────────────────────────┤
│  HARNESS  — Is the execution structurally sound?   │
│             Concurrency control, fan-out           │
│             management, execution governance         │
└─────────────────────────────────────────────────────┘
```

**Key insight from Arize (Aug 2026)**: the most common production failures in long-running agents are not capability failures — they are harness failures. Wrong tool args, conflicting parallel actions, stale context carry, and retry spirals are all harness problems wearing evals' clothes.

### The Harness Layer's Core Responsibilities

The harness layer controls five things that neither eval nor guardrail can handle:

1. **Concurrency control** — which actions can run in parallel, which must be serial, and how shared state is protected. Eval measures outcomes after; guardrail checks individual calls before; harness governs the graph structure of execution.
2. **Fan-out orchestration** — when one agent delegates to N subagents, the harness manages result aggregation, timeout propagation, and partial-failure semantics. Without a harness, subagent failures cascade silently into confident wrong answers.
3. **Execution path governance** — the harness is the only layer that knows whether two tool calls from two different reasoning branches will conflict. Neither the model nor the guardrail can see this.
4. **Context freshness enforcement** — re-read policies, version-header checking, and pre-commit validation happen in the harness, not in the model's reasoning or the guardrail's policy engine.
5. **Multi-path conflict detection** — the harness must track which execution branches are running and detect when their potential outputs will conflict before the writes happen.

### Distinguishing Failures by Layer

| Symptom | Layer | Fix |
|---------|-------|-----|
| Agent returns wrong answer | Eval gap | Better task eval, ground truth |
| Agent calls a forbidden tool | Guardrail gap | Add policy rule |
| Two agents write conflicting state | Harness gap | Add concurrency control |
| Agent retries 40 times on a bad call | Harness gap | Add circuit breaker + budget |
| Agent ignores recent state changes | Harness gap | Add version-header revalidation |
| Final answer correct but cost 3× budget | Harness gap | Add token budget enforcement |

```python
# Minimal harness: fan-out with concurrency control and partial-failure handling
import asyncio
from dataclasses import dataclass
from enum import Enum

class SubagentState(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"

@dataclass
class SubagentResult:
    agent_id: str
    state: SubagentState
    output: dict | None = None
    error: str | None = None

async def fan_out_with_harness(
    orchestrator_id: str,
    subagent_tasks: list[dict],
    max_concurrent: int = 4,
    timeout_per_agent: float = 30.0,
    write_conflict_check: callable = None,
) -> dict:
    """
    Fan-out orchestration with harness-level governance:
    - Semaphore limits concurrency (harness: concurrency control)
    - Per-agent timeout (harness: execution path governance)
    - Partial failure tracking (harness: fan-out orchestration)
    - Optional write-conflict detection (harness: multi-path conflict)
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    results: dict[str, SubagentResult] = {}

    async def run_one(task: dict) -> SubagentResult:
        async with semaphore:
            agent_id = task["agent_id"]
            results[agent_id] = SubagentResult(agent_id, SubagentState.RUNNING)
            try:
                # Pre-execution conflict check (harness layer)
                if write_conflict_check:
                    conflict = await write_conflict_check(orchestrator_id, agent_id, task)
                    if conflict:
                        return SubagentResult(
                            agent_id, SubagentState.FAILED,
                            error=f"Write conflict detected: {conflict}"
                        )
                output = await asyncio.wait_for(
                    execute_subagent(task),
                    timeout=timeout_per_agent
                )
                return SubagentResult(agent_id, SubagentState.COMPLETED, output=output)
            except asyncio.TimeoutError:
                return SubagentResult(agent_id, SubagentState.TIMED_OUT)
            except Exception as e:
                return SubagentResult(agent_id, SubagentState.FAILED, error=str(e))

    # Fan-out: all subagents launched concurrently
    tasks = [run_one(t) for t in subagent_tasks]
    completed = await asyncio.gather(*tasks, return_exceptions=True)

    # Map results back to agent IDs
    for task, result in zip(subagent_tasks, completed):
        agent_id = task["agent_id"]
        if isinstance(result, Exception):
            results[agent_id] = SubagentResult(agent_id, SubagentState.FAILED, error=str(result))
        else:
            results[agent_id] = result

    # Partial failure: harness propagates failure state
    failures = {k: v for k, v in results.items() if v.state != SubagentState.COMPLETED}
    if failures:
        # Log failure graph for observability (harness: execution path governance)
        print(f"[HARNESS] {len(failures)}/{len(results)} subagents failed: {failures}")

    # Aggregation with conflict check
    valid_results = {
        k: v for k, v in results.items()
        if v.state == SubagentState.COMPLETED and v.output is not None
    }
    return {
        "orchestrator_id": orchestrator_id,
        "total": len(results),
        "succeeded": len(valid_results),
        "failed": len(failures),
        "results": valid_results,
    }

async def execute_subagent(task: dict):
    """Stub — replace with actual subagent invocation (MCP, A2A, etc.)"""
    await asyncio.sleep(0.1)  # Simulate work
    return {"agent_id": task["agent_id"], "output": "done"}
```

## Receipt

> Verified 2026-08-14 — Researched and synthesized from:
> - Arize AI blog "AI Agent Guardrails vs Evals" (Laurie Voss, Aug 13, 2026): three-layer taxonomy, voice agent multi-path concurrency failure case study
> - arXiv:2606.06324 "HarnessFix" (Chen et al., Chinese Academy of Sciences): trace-guided harness layer diagnosis, 15.2-50.0% improvement from harness-layer fixes
> - tinyhumansai/openhuman GitHub Issue #3471: E2E test cases for agent harness behaviors including subagent fan-out, race conditions, and multi-path flows
> - Tian Pan "Race Conditions in Concurrent Agent Systems" (Apr 12, 2026): read-modify-write trap, state corruption misdiagnosis as hallucination

## See also

- [S-2614 · The Harness Engineering Loop](/opt/data/handbook/stacks/s2614-the-harness-engineering-loop-stack-when-the-model-is-not-your-problem-and-you-change-everything-anyway.md) — the empirical case that models aren't the bottleneck
- [S-2200 · The Observable Read Stack](/opt/data/handbook/stacks/s2200-the-observable-read-stack-when-your-multi-agent-system-reads-a-world-that-no-longer-exists.md) — stale reads as a harness-level failure
- [S-2610 · The Agent Compensation Graph Stack](/opt/data/handbook/stacks/s2610-the-agent-compensation-graph-stack-when-your-agent-breaks-forward-and-leaves-a-mess.md) — rollback as a harness-level concern
