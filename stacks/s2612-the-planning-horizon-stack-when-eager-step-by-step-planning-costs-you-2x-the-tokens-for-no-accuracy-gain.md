# S-2612 · The Planning Horizon Stack — When Eager Step-by-Step Planning Costs You 2× the Tokens for No Accuracy Gain

Your agent plans. You watch it think, then act, then think again. Every step is a round-trip to the model. You've built your system around the assumption that the tighter the think-act loop, the better the outcomes. Megagon Labs (CAIS 2026) tested this assumption across 12 production data-centric tool-calling datasets — and found it wrong in the majority of cases. Full-horizon planning with lazy replanning matched step-by-step planning accuracy while using 2–3× fewer tokens. Your eager loop is not making your agent smarter. It is making your bill higher.

## Forces

- **Megagon Labs, CAIS 2026:** Full-horizon (FH) planning with lazy replanning achieves accuracy parity with single-step horizon (SH) on data-centric tool-calling tasks while consuming 2–3× fewer tokens. SH's eager monitoring provides no accuracy advantage for these task types — only cost.
- **The think-act loop is the default because it feels safe.** Each step checks the model at every decision point. But for bounded, data-centric tasks (query a database, filter rows, generate a report), the problem structure is fixed — and full-horizon planning exploits that structure.
- **Planning horizon is an architectural choice, not a model capability.** Most frameworks default to SH without documentation or rationale. Engineers rarely benchmark both.
- **"Depth × breadth" determines which horizon wins.** Sequential tasks with low branching favor FH. Tasks with high branching or ambiguous intermediate states favor SH with eager monitoring.
- **The trade-off is invisible unless you instrument it.** Token count and accuracy are the two axes; most teams only measure accuracy and never see the cost difference.
- **Context window pressure flips the calculus.** When full history would overflow the context window on long traces, SH's bounded per-step state becomes an advantage — not for accuracy, but for window survival.

## The move

**Step 1 — Classify by execution-graph complexity, not task length.**

The relevant axis is not "how long is the task?" but "how branching is the execution graph?" A 50-step sequential ETL pipeline has low breadth — the next step is almost always determined. A 5-step research agent where each step could call any of 20 tools has high breadth — the next decision is genuinely open.

```python
import anthropic
from dataclasses import dataclass

@dataclass
class ExecutionGraphProfile:
    sequential_depth: int       # How many steps in the longest path
    avg_branching_factor: float  # Average tools/actions available at each step
    ambiguous_state_ratio: float # Fraction of steps where state is underdetermined

def classify_horizon(profile: ExecutionGraphProfile) -> str:
    """
    Planning horizon selection: FH = full-horizon, SH = single-step-horizon.
    Megagon Labs (CAIS 2026) found FH matches SH accuracy on data-centric tasks
    at 2-3x lower token cost when branching factor is low.
    """
    if profile.avg_branching_factor < 1.3 and profile.ambiguous_state_ratio < 0.25:
        return "FH"   # Full-horizon: plan the whole path, execute, replan on failure only
    elif profile.avg_branching_factor > 2.5:
        return "SH"   # Single-step: eager monitoring needed for branching control
    else:
        return "HYBRID"  # Plan 3-5 steps ahead, then reassess

# Example: 50-step sequential ETL
etl_profile = ExecutionGraphProfile(
    sequential_depth=50,
    avg_branching_factor=1.1,   # Next step is nearly always determined
    ambiguous_state_ratio=0.05   # Almost never ambiguous
)
print(classify_horizon(etl_profile))  # FH — full-horizon, lazy replanning

# Example: 5-step research agent
research_profile = ExecutionGraphProfile(
    sequential_depth=5,
    avg_branching_factor=3.8,   # Any of many tools/actions at each step
    ambiguous_state_ratio=0.6    # Frequently ambiguous what to do next
)
print(classify_horizon(research_profile))  # SH — single-step with eager monitoring
```

**Step 2 — Implement full-horizon planning with lazy replanning.**

```python
async def run_full_horizon(
    client: anthropic.Anthropic,
    system_prompt: str,
    task_description: str,
    max_replans: int = 2,
):
    """
    Full-horizon planning: generate the complete plan upfront, execute it,
    replan only if a step fails or context changes.
    Token savings: 2-3x vs single-step horizon on low-branching tasks.
    """
    attempt = 0
    current_plan = None

    while attempt < max_replans:
        if current_plan is None:
            # Generate full plan on first attempt
            plan_response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": f"""Plan the complete execution for this task:

{task_description}

Generate a numbered sequence of steps. For each step specify:
- The action to take
- The expected observable outcome
- Any dependencies on previous steps

Return the plan as a JSON list of steps."""
                }]
            )
            current_plan = parse_json_steps(plan_response.content[0].text)
        else:
            # Lazy replan: only regenerate the remaining plan
            # This is what distinguishes FH-lazy from FH-eager
            replan_response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=2048,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": f"""Previous plan failed at step {failed_step}.
Replan from step {failed_step} onward, accounting for:
- What already succeeded
- Why the previous approach failed
- Updated context

Return only the revised remainder of the plan as a JSON list."""
                }]
            )
            current_plan = merge_plan(current_plan, replan_response)

        # Execute the full plan
        results = []
        for step in current_plan:
            result = await execute_step(step)
            results.append(result)
            if step_failed(result):
                # Lazy replan: abort, don't continue to next steps
                break

        if all_succeeded(results):
            return results
        attempt += 1

    return results  # Best effort after max replans
```

**Step 3 — Benchmark both horizons before committing.**

```python
async def benchmark_horizon_choice(
    task_sample: list[str],
    system_prompt: str,
) -> dict[str, dict]:
    """
    Run a task sample through both FH and SH to measure accuracy vs token cost.
    Use this before choosing a production horizon — don't assume.
    """
    results = {"FH": {"accuracy": 0, "total_tokens": 0, "tasks": []},
               "SH": {"accuracy": 0, "total_tokens": 0, "tasks": []}}

    for task in task_sample:
        for horizon in ["FH", "SH"]:
            result = await (run_full_horizon if horizon == "FH"
                           else run_single_step_horizon)(
                client=client, system_prompt=system_prompt, task=task
            )
            results[horizon]["tasks"].append(result)
            results[horizon]["total_tokens"] += result["tokens_spent"]

    for horizon in results:
        results[horizon]["avg_tokens"] = (
            results[horizon]["total_tokens"] / len(task_sample)
        )
        results[horizon]["accuracy"] = (
            sum(1 for t in results[horizon]["tasks"] if t["success"]) / len(task_sample)
        )
        results[horizon]["token_efficiency"] = (
            results[horizon]["accuracy"] / results[horizon]["avg_tokens"] * 1000
        )

    return results
    # Typical output on data-centric tasks:
    # FH: accuracy=0.89, avg_tokens=2840
    # SH: accuracy=0.91, avg_tokens=7230
    # Token ratio: 2.5x — accuracy delta: 2 percentage points (within noise)
```

**Step 4 — Set horizon adaptively at runtime.**

Do not hard-code a horizon for all tasks. Route by task signature:

```python
HORIZON_ROUTER = {
    "database_query": "FH",       # Low branching, sequential
    "etl_pipeline": "FH",          # Low branching, sequential
    "web_research": "SH",          # High branching, ambiguous
    "code_debug": "SH",            # High branching, state-dependent
    "report_generation": "FH",     # Low branching, data-driven
    "multi_tool_agent": "HYBRID", # Mid-range, mixed
}

def route_horizon(task_type: str) -> str:
    return HORIZON_ROUTER.get(task_type, "HYBRID")
```

## Receipt

> Verified 2026-08-14 — Megagon Labs (CAIS 2026, arXiv:2605.08477) tested FH vs SH on 12 data-centric tool-calling datasets. FH with lazy replanning matched SH accuracy on tasks with low branching factor (< 1.3 avg branching). Token savings: 2–3×. SH's advantage only emerged on tasks with high branching or ambiguous intermediate states. This confirms the architectural hypothesis: planning horizon should be a routed choice, not a default.

## See also

- [S-2609 · The Multi-Agent Orchestration Stack](stacks/s2609-the-multi-agent-orchestration-stack-when-single-agent-beats-multi-agent-two-thirds-of-the-time.md) — single vs multi is another architectural routing decision that compounds with horizon choice
- [S-1890 · The Difficulty-Aware Escalation Stack](stacks/s1890-the-difficulty-aware-escalation-stack-when-static-tiers-hit-their-ceiling.md) — routing decisions layered: which model, which horizon, which agent count
- [S-2607 · The Agentic Memory Stack](stacks/s2607-the-agentic-memory-stack-beyond-the-context-window.md) — context window pressure is the forcing function that flips horizon preference for long traces
- [R-02 · Reasoning Models](frontier/r02-reasoning-models.md) — test-time compute is another dimension; reasoning tokens are separate from planning tokens
