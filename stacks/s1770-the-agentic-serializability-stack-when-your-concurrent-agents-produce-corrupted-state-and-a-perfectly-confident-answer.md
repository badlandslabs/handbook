# S-1770 · The Agentic Serializability Stack — When Your Concurrent Agents Produce Corrupted State and a Perfectly Confident Answer

Two agents are running in parallel. One is a planning agent. One is an execution agent. Both are reasoning correctly, making good tool calls, producing well-formed outputs. But the final state of your system is corrupted. A customer record has conflicting fields. A document has contradictory sections. A deployment has inconsistent configuration. The agent confidently presents the result as correct.

The model didn't hallucinate. Your concurrent agents executed a race condition, and the model processed garbage as if it were ground truth.

This is the agentic serializability problem: distributed-systems concurrency bugs that look like LLM failures because the corrupted output is perfectly confident. The agent isn't wrong — it correctly reasoned from the state it was given. The problem is that the state it was given was already corrupted by a concurrent write.

## Forces

- **Classical concurrency control assumes fast transactions. Agents are slow transactions.** Two-phase locking (2PL) and optimistic concurrency control (OCC) assume transactions complete in milliseconds. An agent working on a complex task runs for minutes. Holding a lock that long defeats the purpose of parallelism — you serialize what you meant to parallelize.

- **Agents have opaque read sets.** A database transaction's read set is statically inferable from the SQL. An agent's read set emerges dynamically from tool calls, memory retrieval, and context window contents. You cannot pre-declare what the agent will read, so you cannot reserve it.

- **Agents have expensive abort costs.** If a database transaction aborts, you retry in milliseconds. If an agent's transaction aborts, you discard minutes of inference work, re-spend the API budget, and re-run the reasoning. Retry is not cheap.

- **More capable agents write more, making races more destructive.** The better your agent is at tool use, the more writes it will attempt. Capability and corruption scale together.

## The Move

### The Failure Pattern (The Canary Anomaly)

Reproducible in any shared-state multi-agent setup:

```
T=0s   Agent A reads task state v1: {status: "pending", owner: "A"}
T=0s   Agent B reads task state v1: {status: "pending", owner: "A"}
T=30s  Agent A writes: {status: "approved", owner: "A"}     → commits v2
T=30s  Agent B writes: {status: "in_review", owner: "B"}    → commits v3
T=30s  Result: v3 wins. Agent A's approval is silently dropped.
        No error. No conflict notification. Both agents report success.
```

The same pattern in a file-editing scenario:

```
Agent A reads file_v1, edits line 3, writes back → v2
Agent B reads file_v1 (same version), edits line 7, writes back → v3
Agent A's line 3 edit is silently lost. Both agents believe they succeeded.
```

### Layer 1 — Optimistic Concurrency Control (Minimum Viable)

Add a version token to shared state. Check it on write.

```python
# Shared state with version token
state = {"version": 5, "status": "pending", "owner": None}

def read_state():
    return store.get(), version=state["version"]

def write_state(new_state, expected_version):
    current = store.get()
    if current["version"] != expected_version:
        raise ConcurrencyConflict(
            f"Version mismatch: expected {expected_version}, got {current['version']}. "
            "Another agent modified this state. Retry."
        )
    new_state["version"] = current["version"] + 1
    store.put(new_state)
    return new_state

# In the agent loop:
snapshot, ver = read_state()
# ... agent reasoning over snapshot ...
try:
    result = write_state( enriched_state, ver)
except ConcurrencyConflict as e:
    # Abort and retry: re-read current state, re-reason
    return retry_agent_task(task_id)
```

The retry cost is real. Budget for it in your SLO: if agent runs average 4 minutes and retry is 4 minutes, a single conflict doubles task time. For high-contention resources, this is unworkable.

### Layer 2 — Write Partitioning (Lightweight Correctness)

Partition the write surface so agents can only modify specific attributes of shared objects. No locking needed because agents can't overwrite each other's fields.

```python
SHARED_SCHEMA = {
    "task.status": ["planner"],      # Only the planner writes status
    "task.assigned_agent": ["router"], # Only the router assigns
    "task.result": ["executor"],      # Only the executor writes result
    "task.audit_log": ["*"],          # All agents can append
}

def write_state(agent_id, field, value):
    if agent_id not in SHARED_SCHEMA[field]:
        raise PermissionError(f"{agent_id} cannot write {field}")
    state[field] = value
    state["audit_log"].append({"agent": agent_id, "field": field, "value": value})
```

This is the structural fix for most multi-agent workflows. If your agents have distinct roles, their write surfaces rarely overlap. Enforce it at the infrastructure layer, not in the prompt.

### Layer 3 — DeliveryLog / S-Bus (Architectural Pattern)

S-Bus (arXiv:2605.17076) proposes treating HTTP as the coordination substrate: every shared-state GET request is logged in a server-side DeliveryLog per agent. On commit, the agent's read-set is reconstructed from the log. If the log shows a newer version was delivered during reasoning, the commit is rejected — not based on a version number the agent checked, but based on what the agent actually read.

```python
# S-Bus middleware pattern (conceptual)
# Every GET to shared state returns a DeliveryLog entry
class SBusMiddleware:
    def __init__(self, store):
        self.store = store
        self.delivery_logs = defaultdict(list)  # agent_id → list of reads

    def get(self, agent_id, key):
        value, seq = self.store.get_with_sequence(key)
        entry = {"key": key, "value": value, "seq": seq, "ts": time.time()}
        self.delivery_logs[agent_id].append(entry)
        return value

    def commit(self, agent_id, writes, read_log):
        for entry in read_log:
            current_val, current_seq = self.store.get_with_sequence(entry["key"])
            if current_seq > entry["seq"]:
                raise SerializabilityViolation(
                    f"{agent_id} read stale data: {entry['key']} at seq {entry['seq']} "
                    f"but latest is {current_seq}"
                )
        # All reads were fresh — apply writes atomically
        self.store.apply_all(writes)
```

This gives serializability semantics without per-agent locks. The HTTP middleware owns the coordination, not the agent.

### Layer 4 — CoAgent Serializability (Research-Grade)

CoAgent (arXiv:2606.15376) identifies why classical CC protocols fail in agent settings:

| Classical Assumption | Agent Reality |
|--------------------|--------------|
| Transaction: milliseconds | Agent: minutes to hours |
| Read set: statically inferable | Read set: broad, opaque |
| Writes: buffered until commit | Writes: take immediate effect |
| Abort: cheap | Abort: discards inference |

CoAgent proposes **fork-aware concurrency control**: agents fork shared state at the start of a reasoning step, and the fork is validated at commit. Validated forks can be merged. Invalidated forks trigger re-reasoning. The key insight is that "fork on read, validate on write" mirrors how agents actually work — reasoning over a snapshot — and adds the validation step that prevents the silent corruption.

## Receipt

> Verified 2026-07-28 — Pattern synthesized from Tian Pan's "Race Conditions in Concurrent Agent Systems" (April 2026), arXiv:2606.15376 "CoAgent: Concurrency Control for Multi-Agent Systems" (Lyu et al., SJTU, June 2026), and arXiv:2605.17076 "S-Bus: Automatic Read-Set Reconstruction for Multi-Agent LLM State Coordination" (May 2026). Production failure rates of 41–86% for concurrent multi-agent state corruption reported across documented deployments. The DeliveryLog/S-Bus pattern and CoAgent fork-validation are active research; the optimistic locking and write-partitioning patterns are production-proven. The core insight — that concurrent agent state corruption masquerades as hallucination — is documented across Tian Pan, Ardua Labs (R.004), and production incident reports from multi-agent platform teams (2025–2026).

## See also

- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement between agents; this entry covers the concurrent-write variant
- [S-1011 · The Rate-Limited Multi-Agent Pattern](s1011-the-rate-limited-multi-agent-pattern-when-all-your-agents-attack-your-api-quota-together.md) — concurrent agents overwhelming shared resources; related thundering-herd failure mode
- [S-541 · Agent Drift Detection](s541-agent-drift-detection.md) — behavioral regression detection; serializability violations can produce drift-like symptoms (quality degradation over time from accumulated corrupt state)
