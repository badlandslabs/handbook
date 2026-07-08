# S-700 · Parallel Agent Shared-State Divergence: The Silent Coordination Breakdown

[Your two agents run in parallel. Both read the same ticket queue. Both pick the same ticket. Both mark it "done." One overwrites the other's result. No error was raised. The work looks complete. The data is corrupt. This is not a handoff failure — it is a parallel-read staleness failure, and it is the dominant silent crash in multi-agent systems.]

## Forces

- **Parallel execution doesn't mean parallel awareness.** Two agents dispatched simultaneously both read the queue at T=0. By the time each completes their work at T=30s, the shared state has moved. What they read is not what they acted on.
- **Agents have no transactional awareness.** LLM agents don't hold locks. They don't check the resource version before writing. They read, decide, write — in isolation, with no visibility into what another agent is doing to the same data.
- **The failure is invisible to standard monitoring.** No exception. No timeout. No error code. The agents succeeded individually. The system state is wrong collectively.
- **This gets worse with latency.** Any I/O delay between read and write — network latency, API response time, tool execution — is a window where another agent can invalidate your read. The longer the read-to-write gap, the more likely the divergence.
- **Fan-out amplifies it.** A "dispatch 5 agents to handle 5 tickets" pattern with shared queue state creates 5× the divergence surface. One agent reading stale data is a bug. Five agents doing it is a production incident.

## The Move

### 1. Version every shared read

Before acting on any shared resource, capture a version identifier at read time. Compare it at write time. If the version changed, abort and retry.

```python
# Pseudocode — not a library, a pattern
def agent_work(agent_id, ticket):
    state = ticket_store.read(ticket.id)
    version = state.version  # captured at read time

    # ... agent reasoning, tool calls, etc. ...

    # At write time: verify staleness
    current = ticket_store.read(ticket.id)
    if current.version != version:
        raise StaleReadError(f"Agent {agent_id} read version {version} but current is {current.version}")
    ticket_store.write(ticket.id, state.with_result(...))
```

This converts a silent corruption into a detectable exception. The retry can re-read with the fresh version.

### 2. Use conditional writes instead of blind writes

Where the underlying store supports it (most K/V databases, many queues), use a conditional write: `write only if version == expected_version`. This turns the race into an atomic operation.

```python
# Atomic conditional write
ticket_store.write_if_version_matches(
    ticket_id=ticket.id,
    expected_version=version,
    new_state=state.with_result(result)
)
# Raises VersionConflictError on mismatch — no corruption possible
```

Most SQL databases support this via `UPDATE ... WHERE version = X`. Most object stores and queues can be wrapped with this pattern using compare-and-swap semantics.

### 3. Stamp every write with the version you read

If conditional writes aren't available, include the read version in the written record:

```python
ticket_store.write(
    ticket.id,
    result={...},
    read_version=version,  # stamp: "I read version X"
    agent_id=agent_id
)
```

Audit tooling can then detect divergence: any write whose `read_version` doesn't match the preceding write's `version` is a potential divergence event. This is post-hoc but actionable — it surfaces the pattern even when no exception fired.

### 4. Design for idempotent merge, not last-write-wins

The cleanest long-term fix: make agent results mergeable rather than overwriteable. The agent that writes second doesn't replace — it merges.

```python
# Instead of: ticket.result = new_result
# Do:
ticket.results.append({
    "agent_id": agent_id,
    "timestamp": now(),
    "result": result,
    "version_read": version
})
ticket.completed = all(r.agent_id in EXPECTED_AGENTS for r in ticket.results)
```

The supervisor that dispatched the parallel agents can then reason over all results, detect conflicts, and decide. Idempotent append doesn't corrupt — it accumulates.

### 5. Add a staleness guard to the dispatch layer

Before dispatching parallel agents that share a resource, the orchestrator should:

1. Capture the current version of the shared resource
2. Pass the version to each agent as a read-constraint
3. Reject any write that doesn't confirm the version is still current

```python
def dispatch_parallel(agents, shared_resource):
    baseline_version = resource_store.get_version(shared_resource)
    dispatch = [spawn(agent, read_constraint=baseline_version) for agent in agents]
    results = wait_all(dispatch)
    # Any result marked "stale" must be re-validated before use
    return [r for r in results if not r.stale]
```

This is the architectural gate: if the dispatch layer doesn't stamp versions, agents have no way to know they're stale. Version-stamping belongs at dispatch, not inside individual agents.

## When to Use Which

| Situation | Pattern |
|-----------|---------|
| Store supports conditional writes | Always use them — cleanest fix, zero divergence possible |
| Store is append-only | Idempotent merge — accumulate, then resolve |
| Store is read-heavy with occasional writes | Version stamping at read time + guard at dispatch |
| Agents are external / can't be modified | Dispatch-layer version guard only — protects the shared resource |
| Mixed: some tools support conditionals, some don't | Hybrid: conditional writes where available, version guards elsewhere |

## What This Doesn't Fix

This pattern addresses **parallel agents reading the same mutable shared state**. It does not address:
- **Sequential handoffs** — use S-691 (Agent Handoff Problem)
- **Orchestration pattern selection** — use S-694 (Multi-Agent Coordination)
- **Tool call failures** — use S-695 (Tool Call Failure Taxonomy)
- **Silent failure of the whole agent** — use S-655 (Silent Failure Detection)

## Receipt

> Verified 2026-07-06 — Pattern identified from practitioner field reports (Resomnium, 2026-04-02) on 5-agent production swarm coordination breakdown. Key mechanism: parallel agents reading shared state without transactional awareness. All four mitigation patterns (conditional writes, version stamps, idempotent merge, dispatch-layer version guard) are standard distributed-systems techniques applied specifically to the agentic context. No library required — implementation is ~20 lines per pattern.

## See also
- [S-691](s691-the-agent-handoff-problem-is-where-multi-agent-systems-die.md) — Sequential handoffs, not parallel reads
- [S-694](s694-multi-agent-pattern-coordination-beats-model-size.md) — Coordination pattern selection
- [S-655](s655-silent-failure-detection-production-agents.md) — Silent failures across agent seams
- [S-695](s695-tool-call-failure-taxonomy.md) — Tool call failure taxonomy
- [S-200](s200-agent-reliability-compounding.md) — Step-level reliability compounding
