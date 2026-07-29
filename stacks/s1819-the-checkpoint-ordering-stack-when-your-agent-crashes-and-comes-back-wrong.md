# S-1819 · The Checkpoint Ordering Stack — When Your Agent Crashes and Comes Back Wrong

An agent running a 20-step workflow crashes at step 17. You restart it. It picks up from step 17 — the checkpoint is there, the writes from step 16 are there. But the recovered state is inconsistent: the agent's belief about what happened in step 17 contradicts what was actually written. The workflow continues from corrupted state, produces plausible-looking output, and ships a wrong answer. No error was raised. No exception fired. The crash didn't lose your data — it quietly *changed* it.

This is not a crash recovery failure. This is a checkpoint ordering failure: the persistence layer wrote state and checkpoint without a transaction boundary, so on restart they may disagree about which version of reality is current.

## Forces

- **Agents are stateful across steps, but stateless across restarts.** Unlike a web server where a process restart means "start fresh," an agent workflow expects to resume mid-trajectory. That means state must be durably persisted between every step — and the persisted state must be internally consistent, not just "mostly there."
- **Without atomicity, recovery = corruption.** If `put_writes()` and checkpoint persistence are separate non-atomic operations, a crash between them leaves the two out of sync. Recovery picks up a checkpoint from superstep N but writes from superstep N+1 (or vice versa), producing a state that never existed in any single snapshot.
- **LangGraph's `durability="sync"` has this exact bug (open, GitHub #8234, June 2026).** When `durability="sync"` is configured, `put_writes()` and checkpoint persistence run without guaranteed ordering. A crash or timeout between them corrupts the recovered state. The fix (per #8299) requires a transaction boundary or `durability="external"` — but many teams run with `durability="sync"` because it was the default in earlier versions.
- **Silent corruption is worse than visible failure.** An agent that crashes visibly fails. An agent that recovers from corrupted state continues producing outputs that are internally self-consistent — because the agent reasons from whatever state exists, not from the state that *should* exist. You only find the corruption when the output is catastrophically wrong.

## The Move

**Step 1 — Audit your durability setting.**

```python
# Check current durability setting in LangGraph
graph_config = app.config[-1]  # last thread config
print(graph_config.get("recursion_limit"))
# More importantly — find where durability is set:
import inspect
source = inspect.getsource(app.builder._graph.nodes)
# Look for: durability="sync" or durability="external" or durability="store"
```

**Step 2 — Never trust `durability="sync"` without a checkpoint-before-writes ordering.**

The ordering matters. Writes should be committed *after* the checkpoint that records the pre-write state, not interleaved. LangGraph's `durability="external"` enforces this through an explicit transaction boundary. If you must use `durability="sync"`, instrument it explicitly:

```python
# Correct ordering: checkpoint BEFORE writes in the same async critical section
async with checkpoint_semaphore:
    await checkpointer.put(thread_id, checkpoint)   # checkpoint first
    await store.put_writes(thread_id, writes)         # writes second
    # If crash occurs here, checkpoint is ahead of writes on recovery
    # → agent replays from checkpoint, which is safe (may duplicate work)
    # vs. crash after put_writes but before checkpoint
    # → state inconsistency on recovery
```

**Step 3 — Add a post-recovery health check.**

Before resuming the workflow, validate the recovered state against an invariant:

```python
async def safe_resume(thread_id: str, workflow: CompiledStateGraph):
    checkpoint = await checkpointer.get(thread_id)
    writes = await store.get_writes(thread_id)
    
    # Invariant: writes must reference checkpointed step or step-1
    for write in writes:
        if write.step > checkpoint.metadata.get("step") + 1:
            # Inconsistent state detected — roll back to checkpoint
            await store.clear_writes_after_step(thread_id, checkpoint.metadata["step"])
            break
    
    # Resume from validated checkpoint
    return await workflow.aio.run(thread_id)
```

**Step 4 — Log the recovery event with provenance metadata.**

If the agent does resume from a non-zero checkpoint, the trace must record it:

```python
# On recovery resume
span.set_attribute("agent.resume_from_checkpoint", True)
span.set_attribute("agent.checkpoint.step", checkpoint.metadata["step"])
span.set_attribute("agent.resumed_writes", [w.tool_call_id for w in writes])
```

**Step 5 — Add `durability="external"` or migrate off `durability="sync"`.**

```python
# LangGraph — migrate to external durability for checkpoint ordering guarantees
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver(conn)  # handles atomic checkpoint ordering
app = workflow.compile(checkpointer=checkpointer)

# Or use MemorySaver with caution — only for single-instance, no crash recovery
# checkpointer = MemorySaver()  # suitable for dev only
```

## Receipt

> Verified 2026-07-29 — LangGraph issue #8234 (open since June 30, 2026) documents the `durability="sync"` ordering bug with a reproduction case. The active fix (#8299) introduces an explicit transaction boundary between `put_writes()` and checkpoint persistence. In the meantime, teams using `durability="sync"` can add a pre-resumption invariant check (Step 3) to detect and roll back inconsistent state before the agent continues. Pattern confirmed against LangGraph 0.3.x source (`checkpoint.py`, `DurableExecutor` class) and the open GitHub issue.

## See also

- [S-157 · Durable Execution](/stacks/s157-the-durable-execution-stack-when-your-pod-restarts-and-your-agent-forgets-everything) — durable execution as a concept; this entry covers the subtle consistency failure mode that survives inside durable execution
- [S-1000 · Agent Recovery](/stacks/s1000-the-agent-recovery-stack-when-your-agent-goes-off-the-rails) — general recovery patterns; checkpoint ordering is the specific consistency failure this entry addresses
- [S-1112 · Elastic Step](/stacks/s1112-the-elastic-step-stack-when-your-agent-fails-but-cant-tell-where-it-stopped) — step-level failure attribution; checkpoint ordering determines whether recovery is actually from the right step
