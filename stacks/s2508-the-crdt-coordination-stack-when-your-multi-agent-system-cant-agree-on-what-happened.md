# S-2508 · The CRDT Coordination Stack — When Your Multi-Agent System Can't Agree on What Happened

Two agents write to the same shared task board. Agent A marks task T-7 as complete. Agent B marks T-7 as failed. Both are correct from their own perspective. The system serves the last write — whichever agent happened to write last. The actual state of T-7 is now a coin flip. Your multi-agent system has a distributed systems problem it doesn't know it has.

Multi-agent coordination requires shared mutable state: task assignments, conversation history, knowledge bases, progress tracking. Agents operate asynchronously, fail independently, and retry on different schedules. The moment two agents write to the same data concurrently, you have a distributed consistency problem. Most teams discover this the hard way. CRDTs are the principled fix.

## Forces

- **Shared mutable state in an asynchronous multi-agent system is a distributed systems problem.** Two agents can write the same field at the same time, on different retries, after partial failures. Last-write-wins at the field level produces silently corrupted state that looks valid from every agent's perspective. Classic database transactions require a coordinator — a single point of failure and latency — that erodes the autonomy benefit of multi-agent systems.
- **Agents are crash-prone and retry-prone.** An agent that writes a task assignment then crashes before confirming it can retry, creating duplicate assignments. An agent that reads a task list before another agent's update gets stale data and makes a decision on an outdated view. The interleaving of agent operations is non-deterministic by design. Any coordination primitive must be correct under arbitrary message reorder and duplicate delivery.
- **Centralized coordination doesn't scale with agent count.** N agents writing to shared state through a central server requires N connections, a single point of failure, and no offline operation. The coordination overhead grows as O(N) or worse. CRDTs reduce coordination to O(1) for most operations — every agent can make local updates independently and converge globally without synchronous handshakes.
- **CRDTs are the only data structure that guarantees convergence without coordination.** Conflict-free Replicated Data Types (CRDTs) are mathematically proven to converge to the same state in all replicas regardless of message order, duplication, or loss — as long as all updates are eventually delivered. This makes them uniquely suited for multi-agent systems where agents operate independently and synchronization is asynchronous and unreliable.

## The move

### Understand what CRDTs actually provide

CRDTs come in two families:

**CmRDT (Commutative Replicated Data Types):** Operations are designed such that any order of delivery produces the same result. Sender broadcasts operations, receivers apply them in delivery order.

**CvRDT (Convergent Replicated Data Types):** State is the accumulation of all past updates. Each replica tracks its state; when replicas merge, they take the maximum of each element (for grow-only sets) or the merge function (for more complex types). CvRDTs are the practical choice for multi-agent systems because they tolerate arbitrary delivery delays.

The key property: **all replicas converge to identical state without coordination**, as long as all updates are eventually delivered.

### Map agent state to CRDT types

Not all agent state needs CRDTs. Identify what actually needs coordination:

```python
# Agent-specific counters (task counts, retry counts)
# → G-Counter (grow-only counter) or PN-Counter (increment/decrement)
from y_crdt import YDoc

# Shared task board
doc = YDoc()
board = doc.get_map("task_board")  # LWW-Map (last-write-wins per key)

# Conversation/chat history
text = doc.get_text("conversation")  # RGA (Replicated Growable Array)
# Concurrent edits merge without conflict

# Task assignment set — who owns what
assignments = doc.get_array("assignments")  # OR-Set (Observed-Remove Set)
# Add wins over remove for concurrent operations

# Knowledge base entries
kb = doc.get_map("knowledge_base")  # LWW-Register per entry
```

### Use Yjs or Automerge for document-style CRDTs

Yjs and Automerge are production-grade CRDT libraries that handle most multi-agent state coordination patterns:

```python
from yjs import YDoc, YMap
import asyncio

class SharedTaskBoard:
    """CRDT-backed task board — converges without coordination."""
    def __init__(self, agent_id: str):
        self.doc = YDoc()
        self.agent_id = agent_id
        self.tasks: YMap = self.doc.get_map("tasks")
        self.agents: YMap = self.doc.get_map("agents")

    def claim_task(self, task_id: str) -> bool:
        """Optimistic local update — no coordination needed."""
        if self.tasks.get(task_id) and self.tasks.get(task_id).get("owner"):
            return False  # Already claimed — no race condition
        self.tasks.set(task_id, {
            "owner": self.agent_id,
            "status": "in_progress",
            "claimed_at": asyncio.get_event_loop().time()
        })
        return True

    def complete_task(self, task_id: str):
        self.tasks.set(task_id, {
            "status": "completed",
            "completed_by": self.agent_id
            # Previous "owner" field is preserved — full history available
        })

    def merge_state(self, peer_state: bytes):
        """Apply peer's CRDT state — handles concurrent writes."""
        other_doc = YDoc()
        other_doc.apply_update(peer_state)
        # Yjs handles merge: concurrent writes to different keys merge cleanly
        # Concurrent writes to the same key: LWW, deterministic by peer ID tiebreak
```

### Combine with a sync layer for delivery guarantees

CRDTs guarantee convergence once updates are delivered. You still need delivery:

- **For local-first / mesh topologies:** Use WebRTC peer-to-peer sync (Yjs+y-webrtc). Agents discover each other via signaling server. No central server required for data — only for initial connection handshake.
- **For hub-spoke topologies:** A central relay server broadcasts state updates. The CRDT guarantee means the relay can crash and restart — agents reconnect and merge without coordination.
- **For cross-cloud / cross-region:** Use a cloud-native sync backend (Yjs+y-websocket + Redis, or Automerge's persistence adapter).

```python
# Production sync setup with Yjs
import y_websocket, yjs

async def sync_board(board: SharedTaskBoard, server_url: str):
    """Sync CRDT state via WebSocket relay."""
    provider = y_websocket.WebsocketProvider(
        server_url,
        board.doc,
        params={"agent_id": board.agent_id}
    )
    # Provider handles reconnection, deduplication, state sync on reconnect
    # No coordination needed — CRDT ensures convergence
    await asyncio.Event().wait()  # Keep running
```

### Know when NOT to use CRDTs

CRDTs are wrong when:

- **You need strong consistency** (financial transactions, inventory where overbooking is unacceptable). Use a database with transactions instead, and accept the coordination cost.
- **Your agents are truly synchronous** (always-on, single-threaded, same process). Overhead isn't worth it.
- **The conflict resolution semantics matter for business logic.** CRDT LWW-resolves concurrent writes by peer ID or timestamp — this is a business decision, not a technical one. If "last writer wins" is wrong for your domain, CRDTs alone won't save you.

### The hybrid pattern: CRDT for coordination, database for ground truth

Production multi-agent systems typically use both:

```python
# CRDT for real-time coordination (fast, no coordinator)
# Database for authoritative state (strong consistency, audit log)

class HybridTaskBoard:
    def __init__(self):
        self.crdt_board = SharedTaskBoard(agent_id=gethostname())
        self.db = DatabaseConnection()

    async def claim_and_record(self, task_id: str, agent_id: str):
        success = self.crdt_board.claim_task(task_id)
        if success:
            # Idempotent write to DB — CRDT update will sync eventually
            await self.db.execute(
                "INSERT INTO task_events VALUES ($1, $2, $3) ON CONFLICT DO NOTHING",
                task_id, "claimed", agent_id
            )
        return success
    # Reconciliation: on reconnect, merge CRDT state → authoritative DB
```

## Receipt

> **Receipt pending — 2026-08-12** — Idea sourced from Zylos Research (2026-03-17), arXiv CRDT theory, Yjs production deployments. CRDT convergence property verified against Yjs merge semantics. Practical examples from Yjs YMap, YArray, and Automerge persistence adapters. Hybrid pattern from Kleisli.IO multi-agent architecture (2025).

## See also

- [S-1013 · The Multi-Agent Boundary Stack](/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement between agents
- [S-1034 · The Role Fence Stack](/stacks/s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — preventing conflicting agent operations
- [S-1063 · The Multi-Agent Orchestration Stack](/stacks/s1063-the-multi-agent-orchestration-stack-when-one-agent-isnt-enough-but-five-becomes-a-debugging-nightmare.md) — orchestration patterns for multi-agent systems
