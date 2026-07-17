# S-1241 · The Long-Horizon Collapse: When Your Agent Slowly Falls Apart Over Hours, Not Seconds

Your agent passes SWE-bench at 75%. It solves the 9 a.m. task perfectly. By 3 p.m., it has abandoned its original plan, started over twice, and delivered a wrong answer it insists is correct. No error was raised. The task just got longer, and your agent got worse at it. This is not a model quality problem. It is a horizon problem.

Standard reliability metrics model failures as independent events. Step 1 fails at 5%, step 2 fails at 5%, so the chain fails at ~10%. This is wrong for agents on real tasks. HORIZON (Wang et al., arXiv:2604.11978, Apr 2026) — a cross-domain diagnostic benchmark across 3100+ trajectories on GPT-5 and Claude models — found that agent degradation is **super-linear**: agents fail *faster* than independent error compounding would predict. pass@1 drops from 76.3% on short tasks to 52.1% on very-long tasks. The Graceful Degradation Score collapses from 0.90 to 0.44. The model doesn't just accumulate errors — something structural breaks as horizon increases.

## Forces

- **Early commitment is the default.** LLMs are trained to produce answers, not to reserve judgment. When a plan is wrong, the agent doubles down rather than backtracking — because changing course mid-trajectory reads as "failing" to the model's reward signal. HO/HI (actions taken vs. minimum needed) ratios blow past 2x on hard tasks because the agent replans by abandoning, not by correcting.

- **Context poisoning is cumulative, not binary.** As the context window fills with the agent's own prior reasoning and tool outputs, each subsequent step operates on a noisier signal. The agent has read its own confabulations and incorporated them. The longer the task, the more the agent argues with a version of reality it generated itself.

- **Benchmarks measure the wrong horizon.** SWE-bench Verified tasks take minutes. Production agent tasks take hours. The model that scores 75% on short tasks falls below 25% on tasks that take a human engineer hours to complete (Tian Pan, Apr 2026). Benchmarks don't test for planning fidelity over time — they test for solution existence.

- **Graceful degradation collapses super-linearly.** An agent that handles 90% of failures gracefully on short tasks drops to 44% on long ones. The same error modes (tool failures, permission errors, dead ends) that trigger clean recovery on short tasks become unrecoverable cascades on long ones, because the error state has propagated too far to isolate.

## The move

**Diagnose the intrinsic horizon before architecting the agent.**

Measure HO/HI (Observed Horizon / Intrinsic Horizon) on your actual task distribution. Tasks where HO/HI > 2x are horizon-compromised — they will degrade super-linearly regardless of model quality. This is a topology signal, not a tuning signal.

```python
import anthropic
from collections import Counter

client = anthropic.Anthropic()

# Task horizon profiler — run on a sample of real tasks
def profile_task_horizon(task_prompt: str, max_steps: int = 50) -> dict:
    """
    Returns observed horizon vs. intrinsic horizon ratio.
    Lower ratio = more efficient path following.
    """
    tool_sequence = []
    messages = [{"role": "user", "content": task_prompt}]

    for step in range(max_steps):
        response = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1024,
            tools=[{"name": "think", "description": "reasoning", "input_schema": {"type": "object", "properties": {"thought": {"type": "string"}}}},
                   {"name": "bash", "description": "shell", "input_schema": {"type": "object", "properties": {"cmd": {"type": "string"}}}},
                   {"name": "write_file", "description": "write", "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}}}],
            messages=messages,
        )

        # Count meaningful tool calls (not retries, not backtracks)
        tool_calls = [e.text for e in response.content
                      if hasattr(e, 'type') and e.type == 'tool_use']
        tool_sequence.extend(tool_calls)

        # Check completion
        assistant_text = " ".join(e.text for e in response.content
                                  if hasattr(e, 'type') and e.type == 'text')
        if "task complete" in assistant_text.lower() or "done" in assistant_text.lower():
            break

        messages.append(response.to_dict()["content"][0])

    # Estimate intrinsic horizon: minimum unique tool types needed
    unique_tools = set(tool_sequence)
    intrinsic = len(unique_tools)  # floor estimate

    # Observed horizon = total steps with tool calls
    observed = len(tool_sequence)

    ratio = observed / max(intrinsic, 1)

    return {
        "intrinsic_horizon": intrinsic,
        "observed_horizon": observed,
        "ho_hi_ratio": ratio,
        "tool_sequence": tool_sequence,
        "degraded": ratio > 2.0,
        "severely_degraded": ratio > 3.0,
    }


# Profile a batch and flag horizon-compromised tasks
def flag_horizon_compromised(tasks: list[str], sample_size: int = 20) -> dict:
    from random import sample
    profiled = [profile_task_horizon(t) for t in sample(tasks, min(sample_size, len(tasks)))]
    degraded = [p for p in profiled if p["degraded"]]
    severely = [p for p in profiled if p["severely_degraded"]]

    avg_ratio = sum(p["ho_hi_ratio"] for p in profiled) / len(profiled)

    return {
        "total_profiled": len(profiled),
        "degraded_count": len(degraded),
        "severely_degraded_count": len(severely),
        "degraded_pct": len(degraded) / len(profiled) * 100,
        "avg_ho_hi_ratio": round(avg_ratio, 2),
        "recommendation": "topology_review" if len(degraded) / len(profiled) > 0.3 else "acceptable",
    }
```

**Design for horizon-compromised tasks:**

1. **Subdivide at natural breakpoints.** If HO/HI > 2x, the task is too long for one agent. Split at named checkpoints (milestones, files, stages) and use a supervisor-agent that assigns sub-tasks. Each sub-agent operates within a shorter horizon.

2. **Add checkpoint verification before continuing.** At each natural milestone, run a lightweight judge: "Was the last step's output correct and complete?" Fail-fast rather than propagating bad state into the next horizon segment.

3. **Track the plan-to-action ratio as a reliability signal.** An agent that deviates from its stated plan 3x in a row is in a degraded state. This is a leading indicator long before the final output is wrong.

4. **Budget for super-linear degradation, not linear.** If your task has 5 steps, plan for 35% reliability (0.9^5). If it has 20 steps, plan for 12% (0.9^20) — not 80%. The reliability multiplication law (S-1240) applies, but the super-linear collapse means even that formula is optimistic past HO/HI = 2x.

## Receipt

> Verified 2026-07-17 — HORIZON benchmark (arXiv:2604.11978, Wang et al., Apr 2026) provides the primary data: pass@1 76.3% → 52.1% super-linear collapse across task horizons; HO/HI ratio as diagnostic metric; four identified failure modes (early commitment, error accumulation, plan abandonment, recovery failure). Tian Pan (tianpan.co, Apr 2026) confirms <25% on tasks taking hours vs. 75% on SWE-bench. Zylos Research (May 2026) documents benchmark exploitability (SWE-bench, WebArena, OSWorld all gamed). The super-linear finding is distinct from S-1240's independent-error multiplication model — HORIZON shows errors are correlated in a way that accelerates degradation beyond the product formula. HO/HI profiler implemented as Python above; receipt pending full benchmark run against a real task distribution.

## See also
- [S-1240 · The Reliability Multiplication Law](stacks/s1240-the-reliability-multiplication-law-when-95-percent-per-step-accuracy-means-36-percent-task-completion.md) — the independent-error model that S-1241's super-linear collapse exceeds
- [S-817 · The Trajectory Eval Stack](stacks/s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — testing path quality; S-1241 explains *why* the path degrades over time
- [S-1037 · The Evaluation Gap](stacks/s1037-the-evaluation-gap-when-your-agent-scores-high-and-fails-in-production.md) — benchmark vs. production alignment; S-1241 adds the temporal/hierarchical dimension
- [S-1192 · The Five-Layer Caching Stack](stacks/s1192-the-five-layer-caching-stack-for-agentic-workloads.md) — context accumulation is a root cause of long-horizon collapse; caching limits but doesn't eliminate it
