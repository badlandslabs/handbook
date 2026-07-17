# S-1200 · The Context Window Cliff — When Your Agent Falls Off a Million-Token Wall Mid-Task

Your agent is three steps into a six-step task. It has the user's codebase, two retrieved RAG chunks, a tool result from step 2, and its own reasoning so far — all stuffed into a model that claims 1M tokens. Then the API returns `context_length_exceeded`. Or worse: it doesn't. The model silently truncates the oldest context, your system prompt gets cut, and the agent continues with half its instructions gone — confidently, without any error. By the time you notice, the task is complete and wrong.

This is the **context window cliff**: not a soft budget problem (S-02) or a content-type pruning choice (S-192), but a hard constraint that activates mid-trajectory with catastrophic, silent failure modes. The window doesn't announce when it's running out. It just stops.

## Forces

- **The cliff is invisible until you're past it.** Providers return errors on hard overflow — but many deployments don't propagate those errors to the agent. The model that silently truncates is indistinguishable, at the API level, from one that returned normally.
- **Context accumulation is non-linear.** System prompts, tool schemas, RAG chunks, and conversation history compound faster than teams estimate. A task that fit in testing hits the wall in production when real-world data enters the context.
- **Mid-task truncation corrupts the trajectory, not just the output.** When an agent's system-level instructions are silently dropped, every subsequent step runs on corrupted context. The failure is causal, not isolated.
- **Hard constraints don't negotiate.** A circuit breaker or timeout fires and stops. The context window hits the wall and the agent keeps going — on less context, with no signal that anything changed.

## The move

Three layers: **proactive monitoring, architectural hard-stops, and trajectory recovery.**

### Layer 1 — Context Watermark (proactive)

Track context usage at every step. Model advertised limits are not the ceiling:

```python
def context_watermark(agent_state: AgentState, model: str) -> tuple[float, str]:
    """Returns (fill_ratio, warning_level)"""
    MAX_TOKENS = {
        "claude-sonnet-4": 200_000,
        "gpt-4.5": 128_000,
        "gemini-2.5-pro": 1_000_000,
    }
    limit = MAX_TOKENS.get(model, 128_000)
    # Reserve 15% headroom for the output token budget
    safe_limit = int(limit * 0.85)
    fill_ratio = agent_state.token_count / safe_limit

    if fill_ratio >= 0.95:
        return fill_ratio, "CRITICAL"  # hard stop
    elif fill_ratio >= 0.80:
        return fill_ratio, "WARNING"    # trigger compaction
    elif fill_ratio >= 0.65:
        return fill_ratio, "CAUTION"   # log, monitor trend
    return fill_ratio, "OK"
```

The 15% headroom is not paranoia — it's the output token budget. An agent that hits the wall mid-generation is worse than one that errors mid-step, because the partial output may be wrong and the recovery cost is higher.

### Layer 2 — Hard Architecture (structural)

Treat context limits as architectural constraints, not operational knobs. Two patterns:

**Checkpoint-before-context (async):** Before any high-context operation (RAG retrieval, codebase scan, tool call with large output), snapshot the agent's trajectory to durable storage. If the subsequent step overflows, restore from checkpoint and retry with tighter context constraints:

```python
async def bounded_agent_step(
    agent: Agent,
    task: str,
    checkpoint_store: CheckpointStore,
    context_budget: int = 80_000,  # tokens — architectural ceiling, not soft preference
) -> AgentResult:
    trajectory = await checkpoint_store.snapshot(agent.current_state())

    result = await agent.run(task)

    if result.overflow_detected:
        # Roll back, compact, retry — with tighter constraints
        await agent.restore(trajectory)
        compacted_task = compress_task(task, strategy="aggressive")
        return await agent.run(
            compacted_task,
            context_budget=int(context_budget * 0.6),  # 40% tighter
            overflow_guard=True,
        )

    return result
```

**Hard ceiling enforcement at the scaffold level:** Block any operation that would push the context past the architectural ceiling before the API call is made. Do not discover overflow after the fact:

```python
MAX_CONTEXT_TOKENS = 80_000  # architectural constant, not per-call parameter

def enforce_context_ceiling(prompt_tokens: int, system_tokens: int,
                           tool_schemas: int, reserved: int = 5_000) -> None:
    ceiling = MAX_CONTEXT_TOKENS - reserved
    if prompt_tokens + system_tokens + tool_schemas > ceiling:
        raise ContextCeilingExceeded(
            f"Would exceed hard ceiling: {prompt_tokens + system_tokens + tool_schemas} > {ceiling}"
        )
```

This moves the failure from "silent wrong output" to "explicit error you can handle."

### Layer 3 — Trajectory Recovery (when the cliff is hit)

When overflow happens despite Layers 1 and 2, recovery follows a hierarchy:

| Level | Trigger | Response |
|---|---|---|
| Soft | Fill ratio 80–94% | Trigger compaction (summarize oldest turns, prune intermediate reasoning) |
| Hard | Fill ratio ≥95% or API error | Roll back to last checkpoint, resubmit with reduced scope |
| Escalation | 2+ consecutive overflows | Split task, run sub-tasks independently, merge results |

The merge step is the hard part. A task split mid-execution produces partial outputs that need intelligent recombination:

```python
def merge_partial_results(subtask_results: list[SubtaskResult],
                          original_task: str) -> str:
    merger = ChatCompletion(
        model="claude-sonnet-4",
        system=(
            "You are a result synthesizer. The user asked one task that was split "
            "into subtasks due to context constraints. Each subtask returned a "
            "partial result. Produce ONE coherent answer that incorporates all "
            "partial results faithfully. Do not add information not in the partials."
        ),
    )
    return merger.complete(
        f"Original task: {original_task}\n\n"
        + "\n---\n".join(
            f"Subtask {i+1}: {r.answer}" for i, r in enumerate(subtask_results)
        )
    )
```

## The Contrarian Angle

The instinct is to reach for a larger context window. Gemini offers 2M. Llama 4 Scout offers 10M. But research from arXiv:2511.22729 and operational data from Fordel Studios (March 2026) show that larger windows don't fix the cliff — they move it. Agents with 1M-token windows still overflow, because they consume proportionally more context (more RAG chunks, longer tool outputs, more verbose reasoning). The constraint is not the window size; it is the **failure to treat context as a managed resource with explicit accounting at every step.** The teams that solve this don't buy bigger windows — they build tighter scaffolding.

## Receipt

> Verified: 2026-07-16 — Watermark pattern validated against Redis blog (Feb 2026) on context overflow taxonomy. Checkpoint-before-context derived from arXiv:2601.07190 (Focus Agent) pattern of autonomous snapshot-before-compress. Hard ceiling enforcement at scaffold level is operational practice from Fordel Studios production agents (March 2026). Split-and-merge recovery is described in arXiv:2511.22729. Benchmark gap evidence: SWE-Bench Verified models hitting 80%+ while real-world code agents still overflow mid-task (tianpan.co, April 2026). Hard constraint vs. soft budget distinction confirmed against Redis context overflow failure modes.

## See also

- [S-02 · Context Budget](s02-context-budget.md) — the soft budget approach this entry complements
- [S-192 · Content-Type Context Pruner](s192-content-type-context-pruner.md) — the pruning strategy to use in Layer 1's CAUTION/WARNING phases
- [S-1032 · The Dead Letter Stack](s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — related silent failure pattern; context overflow is a specific trigger
