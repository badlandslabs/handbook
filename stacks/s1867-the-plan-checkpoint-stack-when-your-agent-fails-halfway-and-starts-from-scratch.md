# S-1867 · The Plan Checkpoint Stack
When your agent fails at step 23 of a 47-step plan and has no option but to restart from step 1 — losing all completed work, burning another hour, and sometimes repeating the failure that broke it the first time.

## Situation

Your agent is mid-way through provisioning a 12-service infrastructure stack. Step 23 hits a transient network timeout on a Helm release. The agent has no savepoint to return to. It either crashes entirely (expensive) or continues with an inconsistent state (more expensive). Every long-horizon agent task has a failure point — and the difference between a 5-minute recovery and a 45-minute restart is a checkpoint architecture.

## Forces

- **Linear plans break non-linearly.** Reality diverges from the plan at step 12. Your agent's pre-committed sequence now has no valid continuation. But it was built to execute, not to rethink — so it keeps going on a broken foundation.
- **Rollback requires knowing what "done" means.** A traditional database transaction knows its commit point. An agent task doesn't — there's no natural unit of work with a clear atomic boundary. Define the unit wrong and you checkpoint too often (costly); too rarely and a single failure erases an hour of progress.
- **Side effects make naive restart dangerous.** If step 7 sent a real email, step 8 created a Jira ticket, and step 9 failed — restarting from 1 re-sends the email and duplicates the ticket. Checkpointing must be paired with idempotency keys or compensation logic.
- **Planner-executor architectures make this worse.** The Plan-and-Execute pattern pre-generates the full plan before execution starts. If the world changes between planning and step 15, the plan is stale — but the executor has no mandate to renegotiate it.

## The move

**Architecture: checkpoint savepoints at task-phase boundaries with optional replanning on restore.**

```
1. Partition the task into phases.
   A phase = a group of steps that produces a meaningful intermediate state
   and is safe to rollback to. Examples: "fetch all dependencies," "provision
   DB," "deploy service layer," "run smoke tests."

2. Save state after each phase completes.
   Checkpoint includes:
   - Plan progress (which phase, which step within phase)
   - Completed tool-call receipts (idempotency keys + outputs)
   - Working memory snapshot (if using a stateful executor)
   - Env snapshot (what the world looked like at phase start)

3. On failure, restore the last checkpoint and replay.
   - Replay is deterministic: re-run tool calls that succeeded, skip ones that
     failed, continue from the failure point.
   - Skip re-runs: compare tool-call inputs against receipts; skip if inputs
     are identical (idempotency key match).

4. On restore, optionally trigger replan (not restart).
   The replan gets the checkpoint state injected as context. The new plan
   starts from the recovery point, not from scratch.
   - Replan triggers: >N consecutive tool-call failures; external state change
     detected; tool unavailable for >X seconds.
   - Replan guardrails: do not delete the checkpoint — the replan revises
     the remaining steps; it doesn't replace completed work.

5. Side-effect guard: tag every stateful action with a phase-boundary key.
   Before replaying, check: has this action already been committed?
   If yes, skip. If the tool is not idempotent, use a compensation action
   (undo/reverse) before replaying.
```

### Concrete checkpoint schema

```python
@dataclass
class PlanCheckpoint:
    phase: int                    # 0-indexed phase number
    step_in_phase: int           # step within the current phase
    plan_revision: int           # monotonically increasing
    completed_receipts: list[ToolReceipt]  # tool_call_id + inputs + output
    world_state_hash: str        # SHA256 of relevant env vars / API states
    timestamp: datetime

def checkpoint_after_phase(phase: int, receipts: list[ToolReceipt]) -> PlanCheckpoint:
    return PlanCheckpoint(
        phase=phase,
        step_in_phase=0,
        plan_revision=current_plan_revision(),
        completed_receipts=receipts,
        world_state_hash=sha256(env_snapshot()),
        timestamp=datetime.utcnow()
    )

def restore_or_replan(checkpoint: PlanCheckpoint) -> Plan:
    # Option A: restore + continue
    return load_plan_from_checkpoint(checkpoint)

    # Option B: replan from checkpoint (if world changed)
    if world_changed(checkpoint.world_state_hash):
        return replan_from(checkpoint.completed_receipts)
    return load_plan_from_checkpoint(checkpoint)
```

### When NOT to checkpoint

- Single-step, stateless tasks (no side effects, no recovery cost).
- Tasks where the cost of checkpoint I/O exceeds the recovery cost.
- Fully idempotent tasks where "just restart" is cheap.

### Tooling hints

- **LangGraph**: `MemorySaver` + `CheckpointGrazer` for state persistence; pair with `interrupt_before` for manual approval gates.
- **AutoGen / CrewAI**: inject a `BaseSavePoint` abstraction in the executor's run loop; most teams implement this as a thin wrapper over Redis or SQLite.
- **LangSmith tracing**: emit checkpoint events as span annotations — `{"event": "checkpoint", "phase": 3, "plan_revision": 2}` — so traces show the save/restore cycle explicitly.

## Receipt

> Verified 2026-07-30 — Research-based synthesis from Zylos AI "Adaptive Replanning in AI Agents" (2026-03-20), Zylos AI "AI Agent Planning, Backtracking, and Adaptive Replanning" (2026-05-15), ICML 2026 "BRACE: Budgeted Replanning for Embodied Agents," OpenLegion "AI Agent Planning: ReAct, Tree of Thoughts, and Plan-and-Execute," laxaar.com "Agent Planning Techniques for Reliable Execution" (2026). Key pattern confirmed: the dominant production failure is linear-plan brittleness, not hallucination. BRACE (ICML 2026) explicitly frames replanning as a budgeted control loop — not just "retry" but a decision of *whether* to replan given token budget and latency SLO. Plan-and-Execute's staleness problem is well-documented; the fix is injecting checkpoint state into the replanner, not restarting the executor. No existing handbook entry covers the checkpoint/restore/replan cycle as a unified pattern.

## See also

- [S-1008 · The Orchestration Pattern Match Stack](s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — Plan-and-Execute vs ReAct tradeoffs
- [S-1844 · The Agent Recovery Stack](s1844-the-agent-recovery-stack-when-your-agent-crashes-on-step-47-and-starts-over-from-scratch.md) — crash recovery patterns (covers restart, not checkpoint)
- [S-1166 · The Cross-Agent Trace Fragmentation Problem](s1166-the-cross-agent-trace-fragmentation-problem-when-every-agent-traces-itself-but-nobody-traces-the-handoff.md) — trace context propagation for multi-phase pipelines
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state consistency across agent boundaries
