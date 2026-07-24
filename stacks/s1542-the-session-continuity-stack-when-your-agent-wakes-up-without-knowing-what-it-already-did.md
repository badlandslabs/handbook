# S-1542 · The Session Continuity Stack — When Your Agent Wakes Up Without Knowing What It Already Did

An agent that loses track of its own progress between sessions is not a memory problem and not a checkpointing problem. It is a **session continuity** problem — and the gap between those two domains is where teams lose work.

The agent completed steps 1–47 of a 50-step workflow before the session ended. The next day, a new session starts. The durable executor has a checkpoint. The memory system has yesterday's conversation. But neither has the critical piece: *a signed, validated record of what was actually done, what was committed, and what must not be re-executed.*

The result: the agent either re-runs 47 steps (expensive, possibly harmful), or it starts at step 48 and silently skips the side effects of steps 1–47. Both are wrong.

## Forces

- **Checkpoint ≠ continuity.** A checkpoint captures LLM state (model weights, attention context, mid-call variables). It does not capture the committed world state — which rows were written, which API calls completed, which files were modified.
- **Memory ≠ progress.** Yesterday's conversation log is in memory. But a log entry saying "step 47 completed" is not proof it happened — it's proof the agent *said* it happened. The actual world state may not reflect it.
- **The continuity gap compounds over long-running workflows.** A 10-step task that crosses two sessions might re-execute 2 steps. A 100-step task that crosses three sessions might re-execute 15 — with cascading side effects.
- **Sessions end for multiple reasons:** user-initiated close, timeout, crash, infrastructure restart, human-in-the-loop pause. Each creates a different recovery contract.
- **State reconstruction is expensive.** If the agent must re-run tool calls to discover what it did, it pays the tool cost twice and risks changing the world by re-executing non-idempotent operations.

## The Move

Session continuity requires a **three-layer state model** that separates *control plane checkpointing*, *world state attestation*, and *semantic memory reconstruction* — then a **continuity protocol** that validates the seam between them.

### Layer 1 — Control Plane Checkpoint (Durable Executor)

Checkpoint the agent's LLM state at every step boundary. This is the durable execution foundation (see [S-1536](s1536-the-durable-execution-stack-when-langgraph-gives-you-the-agent-and-temporal-gives-you-the-guarantee.md), [F-15](../forward-deployed/f15-durable-execution.md)).

Store: `{ session_id, step, llm_state_snapshot, tool_call_sequence, checkpoint_ts }`

This is the agent's *working memory* across restarts. It answers: *where in the plan was I?*

```python
# Checkpoint after every tool call — not just at step boundaries
def checkpoint_after_call(state: AgentState, tool_result: ToolResult) -> Checkpoint:
    return Checkpoint(
        session_id=state.session_id,
        step=state.step + 1,
        llm_state=serialize_llm_state(state),
        tool_call=tool_result.tool_name,
        tool_args=tool_result.args,
        tool_result_hash=hash(tool_result),
        committed=False,  # ⚠️ not yet attested
        ts=datetime.utcnow(),
    )
```

### Layer 2 — World State Attestation (Committed Effects Ledger)

Track *actual world changes* separately from the agent's claims about them. Every committed side effect gets a ledger entry signed by the execution layer, not the LLM.

```python
class EffectsLedger:
    """Separate from LLM state — this is the ground truth of what happened."""
    def record(self, entry: EffectEntry):
        # Idempotent write: same effect_id = skip if already recorded
        self.db.insert("committed_effects", {
            "effect_id": hash(f"{entry.tool}:{entry.args}"),
            "session_id": entry.session_id,
            "step": entry.step,
            "tool": entry.tool,
            "args_hash": hash(str(entry.args)),
            "result_hash": hash(str(entry.result)),
            "attested_at": entry.attested_at,
            "replay_safe": entry.is_idempotent,
        })

    def is_done(self, tool: str, args: dict) -> bool:
        """Ask before re-executing: did this already happen?"""
        return self.db.exists("committed_effects",
            effect_id=hash(f"{tool}:{args}"))
```

The critical discipline: the agent must **query the ledger before re-executing**, not after. This is the continuity protocol's core invariant: *never re-fire a committed non-idempotent effect*.

### Layer 3 — Semantic Memory Reconstruction (Session Handoff)

When a new session starts, the agent needs more than a checkpoint. It needs the **narrative** — why it was doing this, what constraints applied, what the user asked for in context.

This is memory's role (see [S-09](s09-memory-systems.md)), but scoped specifically to session continuity:

```python
def resume_session(session_id: str) -> SessionContext:
    checkpoint = load_checkpoint(session_id)
    committed = load_committed_effects(session_id)
    narrative = memory.recall(
        session_id,
        recency_weight=0.7,
        importance_weight=0.3,
    )

    # Validate: does the checkpoint agree with the ledger?
    if checkpoint.step != committed.last_step:
        # Disagreement = audit required before resuming
        raise ContinuityConflict(
            f"Checkpoint claims step {checkpoint.step}, "
            f"ledger attests {committed.last_step}"
        )

    return SessionContext(
        resume_from=committed.last_step,
        committed_effects=committed.list(),
        narrative=narrative,
        plan_state=checkpoint.llm_state,
    )
```

### The Continuity Protocol

Four rules govern the transition between sessions:

1. **Attest before advancing.** After every committed side effect, write to the ledger *before* the LLM sees the result and decides what to do next.
2. **Query before executing.** On resume, the agent checks the ledger before any re-execution. Skip committed idempotent effects; halt and alert on committed non-idempotent effects.
3. **Validate the seam.** If checkpoint step ≠ ledger step, something happened between checkpoints. Audit before continuing.
4. **Tag non-idempotent effects with recovery contracts.** If `replay_safe=False`, the recovery protocol must describe how to safely resume after this effect (e.g., "file written at X — resume means verifying X exists and matches expected content, not re-writing").

## Receipt

> Verified 2026-07-23 — Pattern synthesized from: Zylos Research (2026-02-18, session continuity patterns), Agent Native Engineering durable execution guide (Jul 2026), Data AI Hub checkpoint/resume patterns (Jul 2026), Augment Code async workflow guide (Jun 2026), Mem0.ai State of Agent Memory 2026. No existing handbook entry covers the three-layer model (control-plane / world-state / semantic) as a unified session continuity architecture. S-1536 covers durable execution; S-09 covers memory; neither covers the continuity seam between checkpoint validity and world-state attestation.

## See also

- [S-1536 · The Durable Execution Stack](s1536-the-durable-execution-stack-when-langgraph-gives-you-the-agent-and-temporal-gives-you-the-guarantee.md) — control plane checkpointing
- [S-09 · Memory Systems](s09-memory-systems.md) — semantic memory layer
- [S-1012 · Agent Failure Recovery Stack](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — failure recovery patterns
- [S-1340 · The Spend Guardrail Stack](s1340-the-spend-guardrail-stack-when-your-001-request-costs-5-000.md) — replay cost discipline
