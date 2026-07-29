# S-1830 · The Agentic Serializability Stack — When Your Multi-Agent Parallel Pipeline Silently Corrupts Shared State

You scale to parallel agents and task completion drops. You add monitoring and find no errors — just wrong answers, half-applied changes, and silent data divergence. You didn't get an error message. You got a corrupted git tree. A Kubernetes config that merged two incompatible states. A database with double-charged users. This is not a prompt failure. It is a race condition your observability stack cannot see.

## Forces

- **Multi-agent LLM transactions span minutes, not milliseconds.** A traditional database transaction resolves in microseconds. A multi-agent LLM transaction — plan, read, reason, write — takes 2–10 minutes. Locking for that duration either deadlocks routinely (2PL shows 0.81 deadlocks/trial under contention) or eliminates all concurrency benefit.
- **Agents read opaque state.** A database query has a static read-set. An LLM agent's read-set — what it attends to in context, what it retrieves from memory, what it infers from implicit state — is not statically inferable. Classical OCC (Optimistic Concurrency Control) aborts-and-retries, discarding minutes of LLM inference work per abort. With typical abort rates of 10–30% under contention, this is catastrophic.
- **Shared state is everywhere.** Not just databases: git trees, filesystem paths, Kubernetes manifests, shared documents, message queues, feature-flag stores. Any shared mutable resource that two agents can read before either writes is a potential race.
- **LLM inference windows amplify the race window.** Between an agent reading state and writing back, another agent can have already written. The agent's "view" of the world is frozen at read-time and stale by write-time — but the agent doesn't know it.

## The Move

### The Core Pattern: Detect, Notify, Repair

CoAgent (Lyu et al., arXiv:2606.15376, SJTU, 2026) introduces a fundamentally different concurrency control primitive: **LLM-native advisory notification**. Rather than blocking or aborting, it:

1. **Monitors the shared-state access log** (who read what version of which resource, when).
2. **On conflict detection** (a later write targets a resource an earlier reader may have depended on), sends an **advisory notification** to the affected agent(s) — not a rollback, a message.
3. **The LLM inside the agent judges** whether its plan is invalidated by the conflicting write, and **self-repairs only the affected operations** — not the whole transaction.

```
[Agent A reads /file1.txt v3, /file2.txt v1]
[Agent B writes /file1.txt v4]
[Conflict detected: Agent A read v3, B wrote v4]
[→ Advisory notification sent to Agent A]
[Agent A judges: does /file1.txt v4 invalidate my plan?]
[Agent A self-repairs: re-reads v4, re-applies only affected diffs]
```

### The Three Structural Patterns

**Pattern 1 — Fork-Aware Write Partitioning**
Partition the shared state into **versioned partitions** rather than global locks. Each agent reads from a snapshot and writes to a partition. A coordinator detects cross-partition conflicts and routes recovery:

```
Shared State = { partition_A: [file1, file2], partition_B: [file3, file4] }
Agent A → operates on partition_A snapshot
Agent B → operates on partition_B snapshot
Coordinator → detects cross-partition write order violation → triggers repair
```

Distinct from git worktree (S-3057): git worktree defers conflict resolution to post-hoc merge. Fork-aware partitioning detects conflicts at write-time and routes recovery immediately.

**Pattern 2 — DeliveryLog: Ordered State Publication**
When agents communicate via shared message queues or event logs (DeliveryLog pattern), enforce a **total ordering constraint** on writes to the same entity. The log is the source of truth; each agent reads from its local log view and publishes intent:

```
Agent A intent: write(entity=order_42, state=fulfilled, log_pos=103)
Agent B intent: write(entity=order_42, state=refunded, log_pos=104)
DeliveryLog enforces: sequential resolution of order_42 writes
Agent B waits for log_pos=103 commitment before publishing log_pos=104
```

**Pattern 3 — MTPO: Multi-Agent Transaction with Partial Ordering**
MTPO (from CoAgent) assigns a **partial order** to agent operations based on their shared-state read/write sets. Operations on disjoint resources proceed in parallel. Operations on overlapping resources are ordered by read-timestamp. Agents self-repair along the partial order:

```
Op(A_reads: {file1_v3, file2_v1}) → Op(A_writes: {file1_v4})
Op(B_reads: {file1_v4, file2_v1}) → Op(B_writes: {file2_v2})
Partial order: A_write ⊢ B_read (B sees A's write)
No order: A_write || B_write (disjoint resources → parallel OK)
```

### When to Use Each Pattern

| Scenario | Pattern |
|----------|---------|
| Multiple agents writing to same files/documents | MTPO with self-repair |
| Shared database with entity-level locking | DeliveryLog with ordered writes |
| Independent task partitions (map-reduce style) | Fork-aware partitioning |
| General multi-agent with mixed read/write sets | CoAgent-style advisory notification |

### The Read-Modify-Write Guard

The root cause of most agentic race conditions is implicit read-modify-write on shared state. Add an explicit guard:

```python
async def safe_agent_write(agent_id, resource, new_state, read_version):
    current = await state_store.get(resource)
    if current.version != read_version:
        raise ConflictDetected(
            f"Agent {agent_id} read v{read_version} but current is v{current.version}",
            current=current,
            conflicting_writer=current.last_writer
        )
    await state_store.put(resource, new_state, depends_on=read_version)
```

The LLM handles the `ConflictDetected` exception — judges what to repair — rather than the system rolling back.

### Diagnostics: Is This a Race or a Hallucination?

The symptom is identical — wrong output — but the fix is completely different. Test:

1. **Does the error disappear when agents run sequentially?** If yes → race condition.
2. **Does the error correlate with high parallelism?** If yes → race condition.
3. **Does the agent's output match its input state exactly?** If the agent's output incorporates a state that was overwritten before the agent finished → race condition masquerading as hallucination.

## Receipt

> Verified 2026-07-29 — Sources: CoAgent (arXiv:2606.15376, Lyu/Zhang/Wu/Wei/Chen, SJTU, Jun 2026); ICML 2026 Position Paper (Yang/Li/Ji/Zhang/Jiang); STORM (arXiv:2605.20563, Liu/Chen/Xu/Jiang/Dong, May 2026); Pravi Devineni multi-agent state management (Jan 2026). Core claim confirmed: >1/3 of multi-agent failures in production traces attributed to concurrency control failures. MTPO achieves 1.4× speedup at near-serial token cost (1.15×). 2PL and OCC both surrender nearly all concurrency gains due to deadlock/abort overhead. STORM's at-write conflict detection outperforms git-worktree deferred merge by +18.7 on Commit0-Lite. Real tradeoffs: MTPO requires per-operation state versioning overhead; DeliveryLog requires total ordering infrastructure; fork-aware partitioning reduces parallelism for tightly coupled resources.

## See also

- [S-1013 · The Multi-Agent Boundary Stack](/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — logical boundary vs. concurrency control (sequential handoff problem vs. parallel race problem)
- [S-1036 · The Orchestration Gap](/stacks/s1036-the-orchestration-gap-when-your-agent-demo-shines-and-your-production-system-dies.md) — orchestration-level failure modes that include concurrency misarchitecture
- [S-05 · Multi-Agent Patterns](/stacks/s05-multi-agent-patterns.md) — foundational patterns for multi-agent orchestration
- [S-3057 · Coordination Budget](/stacks/s3057-the-coordination-budget-when-multi-agent-parallelism-becomes-a-liability.md) — the overhead cost of multi-agent parallelism
