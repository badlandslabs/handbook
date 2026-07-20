# S-1376 · The Advisory Concurrency Control Stack — When Your Parallel Agents Race to Corrupt the Same State

Your two agents are running in parallel. Both read the same ticket queue. Both pick ticket #447. Both mark it "resolved." One overwrites the other's result. No error was raised. The HTTP response was 200. The data is corrupt, and nobody notices until the customer calls. This is not a handoff failure — it is a **race condition in agent-clothes**, and it is the dominant silent crash mode for teams that scale their agents beyond one.

[S-700](../stacks/s700-parallel-agent-shared-state-divergence-the-silent-coordination-breakdown.md) covers the problem: parallel-read staleness and shared-state divergence. This entry covers the solution architecture — **advisory concurrency control** — the pattern that makes parallel agent execution safe without forcing a synchronous bottleneck.

## Forces

- **Classical concurrency control fails for agents.** Two-phase locking (2PL) and optimistic concurrency control (OCC) assume transactions complete in milliseconds. Agent tasks run for minutes to days. Blocking or aborting a 45-minute coding agent mid-run is not a viable failure mode.
- **Agents can self-heal in ways databases can't.** LLMs can distinguish *semantic* conflicts (two agents editing the same paragraph) from *irrelevant* interference (one agent reading a config file while another writes to a different one). Traditional CC treats all write-write pairs as conflicts; agents can reason about whether a conflict actually matters.
- **Enforcing mandatory control breaks the parallelization benefit.** If you serialize agent execution to avoid conflicts, you lose the 1.8x–3.7x wall-clock speedup that motivated parallel dispatch in the first place.
- **The naive fix (mutex everything) creates a new problem.** Global locking turns parallel agents into sequential agents — slower and more expensive than running one agent alone.

## The Move

**Advisory concurrency control** gives agents visibility and judgment into conflicts without imposing the blunt force of mandatory locks. The three primitives: **conflict judgment** (ask the LLM whether two operations actually interfere), **selective repair** (undo only the affected write, not the whole transaction), and **version-vector notifications** (alert the agent when shared state has changed since it read it).

### The CoAgent Pattern (arXiv:2606.15376, SJTU, ICML 2026)

The CoAgent framework formalizes this into a three-layer protocol:

**Layer 1 — Read with version tracking.** Every agent reads shared state tagged with a version vector. No locking. Just recording: *"I read ticket queue snapshot v14."*

**Layer 2 — Write with conflict registration.** Before writing, the agent registers its intended write. The system checks it against version vectors of concurrent writes. If a concurrent write touched the same resource, invoke the **conflict judge**.

**Layer 3 — Conflict judgment.** The LLM — given both the original read state and the intervening write — decides: does this conflict actually matter? Two agents writing to the same customer record = real conflict. Two agents writing to different sections of the same document = usually irrelevant. The judge is right ~95% of the time even on budget models (CoAgent evaluation, §7).

**Layer 4 — Selective repair.** When the judge says "real conflict," undo only the affected state, not the entire task. The agent re-reads the current version and re-applies only the conflicting write. Tasks that had no conflicts complete uninterrupted.

### Implementation Skeleton

```python
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict

@dataclass
class VersionVector:
    """Tracks agent's read snapshot per resource."""
    resource: str
    version: int
    agent_id: str
    read_at: float

@dataclass
class WriteIntent:
    """A pending write, registered before execution."""
    agent_id: str
    resource: str
    patch: dict
    base_version: int
    registered_at: float

class AdvisoryConcurrencyController:
    """
    Advisory CC for parallel agent systems.
    Agents self-report reads/writes; the controller
    orchestrates conflict detection without forced locks.
    """
    def __init__(self, judge_prompt: str):
        self.judge_prompt = judge_prompt
        self._reads: dict[str, VersionVector] = {}
        self._writes: list[WriteIntent] = []
        self._state: dict[str, dict] = {}
        self._versions: dict[str, int] = defaultdict(int)

    async def read(self, agent_id: str, resource: str) -> dict:
        """Read shared state, tracking the version vector."""
        state = self._state.get(resource, {})
        version = self._versions[resource]
        self._reads[f"{agent_id}:{resource}"] = VersionVector(
            resource=resource,
            version=version,
            agent_id=agent_id,
            read_at=asyncio.get_event_loop().time()
        )
        return state

    async def register_write(self, agent_id: str, resource: str,
                            patch: dict) -> str:
        """Register intent; system checks for conflicts."""
        base_version = self._versions[resource]
        intent = WriteIntent(
            agent_id=agent_id,
            resource=resource,
            patch=patch,
            base_version=base_version,
            registered_at=asyncio.get_event_loop().time()
        )
        self._writes.append(intent)

        # Check against all writes that committed since this agent read
        conflicts = []
        for w in self._writes[:-1]:  # exclude self
            if w.resource == resource:
                vv = self._reads.get(f"{agent_id}:{resource}")
                if vv and w.registered_at > vv.read_at:
                    if w.base_version >= vv.version:
                        conflicts.append(w)

        if not conflicts:
            return "CLEAR"

        # Invoke conflict judge
        conflict_summary = "\n".join(
            f"  Agent {w.agent_id} wrote to {resource} at v{w.base_version}"
            for w in conflicts
        )
        judgment = await self._call_judge(
            agent_id, resource, patch, conflict_summary
        )
        return judgment  # "CLEAR" | "RETRY_READ" | "ABORT"

    async def commit_write(self, agent_id: str, resource: str, patch: dict):
        """Commit a cleared write, bump version."""
        if resource not in self._state:
            self._state[resource] = {}
        self._state[resource].update(patch)
        self._versions[resource] += 1
        # Notify agents reading stale versions
        for key, vv in self._reads.items():
            if vv.resource == resource and vv.version < self._versions[resource]:
                pass  # notification via separate channel

    async def _call_judge(self, agent_id: str, resource: str,
                           intended_patch: dict,
                           conflict_summary: str) -> str:
        """
        LLM-as-judge for semantic conflict detection.
        Returns: 'CLEAR' (no real conflict), 'RETRY_READ' (re-read and re-apply),
                 or 'ABORT' (unresolvable — needs human review).
        """
        prompt = self.judge_prompt.format(
            agent_id=agent_id,
            resource=resource,
            intended=intended_patch,
            conflicts=conflict_summary
        )
        # In production: call your LLM here
        response = await llm_call(prompt)
        return parse_judgment(response)  # 'CLEAR' | 'RETRY_READ' | 'ABORT'
```

### When to Use Advisory CC vs. Mandatory CC

| Scenario | Pattern | Why |
|---------|---------|-----|
| Two agents picking from same queue | Advisory CC | Semantic judgment needed — "same ticket" vs "different tickets" |
| Multiple agents editing same document | Advisory CC | Interference is granular, not full-doc |
| Agent writing to production database | **Mandatory CC** | Undo cost is too high; use optimistic locking with abort |
| Agent deleting shared resources | **Mandatory CC** | Destructive writes need strong guarantees |
| Fan-out read-only agents | None needed | No shared state written; parallelism is free |

### The Notification Protocol

When a write commits to state that another agent read earlier, the controller emits a **version-change notification**:

```json
{
  "event": "state_changed",
  "resource": "ticket:447",
  "old_version": 14,
  "new_version": 15,
  "notified_agents": ["agent:enricher-v2", "agent:reviewer-v1"],
  "action": "re_read_recommended"
}
```

The receiving agent re-reads the state, reconciles, and continues. This is the key insight: the controller *warns*, the agent *decides*. The agent is never forcibly killed, rolled back, or blocked — it receives information and self-corrects.

## Receipt

> Verified 2026-07-19 — CoAgent arXiv:2606.15376 (Yang et al., SJTU, ICML 2026) describes advisory CC with three primitives (conflict judgment, selective repair, version-vector notifications). Evaluation: 95% judge accuracy even on DeepSeek v4 flash; passes all ten contended workloads within 5% of serial correctness; 1.8x–3.7x wall-clock speedup over sequential execution. ICML poster #122 confirms advisory CC outperforms mandatory approaches (2PL, OCC) on agent workloads by avoiding forced aborts of long-running tasks.

## See also

- [S-700 · Parallel Agent Shared-State Divergence](../stacks/s700-parallel-agent-shared-state-divergence-the-silent-coordination-breakdown.md) — the problem this solves
- [S-575 · Multi-Agent Is Not Multiplied Intelligence](../stacks/s575-multi-agent-is-not-multiplied-intelligence-when-agents-work-in-parallel-they-divide-it.md) — why parallelization needs coordination
- [S-1011 · The Rate-Limited Multi-Agent Pattern](../stacks/s1011-the-rate-limited-multi-agent-pattern-when-all-your-agents-attack-your-api-quota-together.md) — another concurrency failure mode
