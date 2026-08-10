# S-2417 · The Read-Modify-Write Trap — When Your Parallel Agents Produce Garbage and Call It Reasoning

Your three agents are running in parallel. Account status agent, fee calculator, compliance checker. Each reads the account record, makes its change, writes back. The result: an account that is simultaneously "active" (written first), has fees applied twice (last-write-wins), and passes compliance (the checker read before the status write landed). No error fired. Every tool call succeeded. The downstream agent that tries to use this record produces output that looks like reasoning failure — but the model was faithfully processing the garbage your concurrency architecture handed it.

This is the read-modify-write trap: the classic race condition, except it wears an LLM's face. It is misdiagnosed as hallucination more than any other failure in production multi-agent systems.

## Forces

- **Last-write-wins is the default and nobody chose it.** Every agent framework with shared-state access defaults to no locking. The first agent to write back wins. The other two overwrite it. The system has no idea. LLM-based agents make this worse: their outputs look so confident processing corrupted state that engineers assume the model failed, not the database.

- **Agent reads are non-atomic snapshots.** An LLM agent reads a tool response and holds it in context for the next N reasoning steps. During those steps, other agents may have already written updates. The agent's "view" of shared state becomes stale the moment it finishes reading — but the agent doesn't know this.

- **The symptom is confidence, not an error.** Silent state corruption is the most dangerous class of concurrency bug: the system reports success, the agent produces coherent output from incoherent inputs, and nobody thinks to check whether the read was still valid when the agent decided to act on it.

- **Parallel execution is the whole point — and the whole problem.** You introduced parallelism for throughput. Your agents are correct individually. The failure is systemic: the architecture assumed independent actors but built shared state.

## The move

**Four patterns, in order of structural correctness:**

### 1. Advisory locks with read-your-writes confirmation

Before any agent reads shared state, it acquires an advisory lock. After writing, it verifies the write landed by re-reading and comparing. If the read-your-write check fails, the agent retries from the read step.

```python
import threading
from contextlib import contextmanager

class AccountRecord:
    def __init__(self, record_id: str):
        self.record_id = record_id
        self._lock = threading.Lock()
        self._version = 0
        self._data = {}

    @contextmanager
    def acquire(self, agent_id: str):
        """Advisory lock for shared-state access."""
        acquired = self._lock.acquire(timeout=5)
        if not acquired:
            raise TimeoutError(f"{agent_id} could not acquire lock for {self.record_id}")
        try:
            yield
        finally:
            self._lock.release()

    def read(self) -> dict:
        return {"version": self._version, **self._data}

    def write(self, agent_id: str, updates: dict) -> bool:
        self._data.update(updates)
        self._version += 1
        # Read-your-writes confirmation
        confirmed = self.read()
        assert confirmed["version"] == self._version, f"{agent_id}: write confirmation failed"
        return True

    def read_modified_write(self, agent_id: str, modifier_fn):
        """Atomic read-modify-write with lock and confirmation."""
        with self.acquire(agent_id):
            snapshot = self.read()
            result = modifier_fn(snapshot)
            self.write(agent_id, result)
```

### 2. Optimistic concurrency control with version vectors

Instead of locking, use version numbers. Each agent reads the current version, makes its modification, and writes back only if the version hasn't changed. If it has, retry.

```python
def optimistic_update(record, agent_id: str, modifier_fn, max_retries=3):
    for attempt in range(max_retries):
        snapshot = record.read()
        current_version = snapshot["version"]
        new_state = modifier_fn(snapshot)
        # Attempt CAS (compare-and-swap)
        if record.compare_and_swap(current_version, agent_id, new_state):
            return True
        # Version changed — another agent wrote. Retry.
    raise ConcurrencyError(f"{agent_id}: failed after {max_retries} version conflicts")
```

### 3. Event-sourced write log (append-only, never overwrite)

Replace mutable shared records with an append-only event log. Each agent appends its intent as an event. A reconciliation process applies events in order, resolving conflicts deterministically. Agents never read stale state — they read the log and compute the current state themselves.

```python
@dataclass
class AccountEvent:
    agent_id: str
    timestamp: float
    intent: dict  # {"type": "activate"} or {"type": "apply_fee", "amount": 50}

class EventLog:
    def __init__(self, record_id: str):
        self.record_id = record_id
        self._events: list[AccountEvent] = []

    def append(self, event: AccountEvent):
        self._events.append(event)

    def current_state(self) -> dict:
        """Reconstruct state by replaying all events in order."""
        state = {}
        for event in self._events:
            if event.intent["type"] == "activate":
                state["status"] = "active"
            elif event.intent["type"] == "apply_fee":
                state["fees"] = state.get("fees", 0) + event.intent["amount"]
            elif event.intent["type"] == "compliance_check":
                state["compliance"] = event.intent["result"]
        return state

    def agent_snapshot(self, agent_id: str) -> dict:
        """Return state as known to a specific agent at its read time."""
        return self.current_state()  # Reconstruct on read, no stale cache
```

### 4. Publish-subscribe instead of shared database

Agents never read shared state directly. Instead, they publish events and subscribe to specific event types. The orchestrator maintains the authoritative state and emits it as a stream. This eliminates shared mutable state entirely — the coordination surface moves from a shared database to a message bus.

```python
# Instead of: agent reads account_record.state
# Use: agent subscribes to account state changes
async def fee_agent(account_id: str, bus: MessageBus):
    async for event in bus.subscribe(f"account.{account_id}.changed"):
        if event["field"] == "status" and event["value"] == "active":
            # Only now does the fee agent know the account is active.
            # No stale read possible — events are ordered.
            await apply_fees(account_id)
```

**The selection rule:** Start with advisory locks for rapid prototyping (minimal code change). Migrate to optimistic concurrency for read-heavy workloads. Switch to event-sourcing when conflict resolution needs to be auditable. Go pub-sub when you need total ordering guarantees without a central database bottleneck.

## Receipt

> Verified 2026-08-10 — Concurrent write patterns validated against production failure case documented at tianpan.co/blog/2026-04-12-race-conditions-in-concurrent-agent-systems. Advisory lock + read-your-writes pattern is standard in Postgres advisory locking (`SELECT pg_advisory_lock(key)`) and Redis (`WATCH/MULTI/EXEC`). Optimistic concurrency with version vectors is implemented in Datomic, Firestore, and most NoSQL databases. Event-sourced write log is the CQRS pattern applied to agent state. Pub-sub elimination of shared state is the actor model (Akka, Erlang/OTP) — 30+ years of production validation. The specific LLM-masking symptom (confident output from corrupted state) is documented in multiple 2026 post-mortems but has no formal study.

## See also

- [S-986 · Coordination Breakdown Pattern](stacks/s986-the-coordination-breakdown-pattern-when-your-multi-agent-system-is-its-own-worst-enemy.md) — independent reads of shared state as invisible failure
- [S-1013 · Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — untyped handoffs and silent overwrites
- [S-988 · Agent Fleet Resilience](stacks/s988-the-agent-fleet-resilience-stack-when-your-orchestrator-dies-but-your-agents-keep-running.md) — orchestrator crash during parallel execution
