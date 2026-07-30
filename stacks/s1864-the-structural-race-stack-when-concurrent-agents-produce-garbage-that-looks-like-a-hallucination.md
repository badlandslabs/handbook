# S-1864 · The Structural Race Stack — When Concurrent Agents Produce Garbage That Looks Like a Hallucination

You have three agents working in parallel on a shared document. All three log success. The final state is wrong in three different ways, and no error was thrown. Your debugging session blames the model for two weeks. The model wasn't the problem.

## Forces

- **Sequential agents are easy; concurrent agents are distributed systems.** The moment two agents run simultaneously and may touch the same state, you have a distributed systems problem. Every failure mode from 40 years of concurrent programming applies — but the engineers building agent systems have rarely had to think about causal consistency before.
- **The corruption happens at the state layer, not the generation layer.** The model faithfully processes inputs that have already been corrupted by a race. It produces confident, plausible-sounding garbage that looks like a hallucination but is actually a read-modify-write failure upstream.
- **Read-modify-write is the core trap.** Agent A reads state S, Agent B reads state S (both at version v), Agent A writes S+δ_A, Agent B writes S+δ_B. One write wins. The other delta vanishes silently, with no exception, no warning. The losing agent's output — built on the assumption that its delta persisted — is now logically invalid.
- **Quadratic interaction growth.** N concurrent agents create N(N-1)/2 potential race pairs. With 5 agents, that's 10 pairs. With 10 agents, it's 45. Most teams discover this the hard way in production.
- **Rate-limit exhaustion follows the same pattern.** 15 agents each within a 10 req/sec limit can collectively hit 150 req/sec against a shared 100 req/sec ceiling. Aggregate exhaustion and individual success create a silent failure mode — the system produces truncated or degraded output with no error signal.

## The Move

### 1. Identify structural races before execution

A **Structural Race Condition** exists when two agents αᵢ and αⱼ both read a shared resource at version v, generate deltas δᵢ and δⱼ, and both commit expecting version v — without an intervening re-read after the first commit.

Detect this from the HTTP-visible event trace. You do not need model access. Look for:
- Concurrent reads of the same entity ID with no ordering constraint
- Two write events on the same shard with no validation edge between them
- Timestamp ordering between events that violates causal dependency

```python
# Detect structural races from execution trace
from dataclasses import dataclass
from collections import defaultdict

@dataclass
class TraceEvent:
    agent_id: str
    resource_id: str
    version: int
    op: str  # 'read' or 'write'
    ts: float

def detect_structural_races(events: list[TraceEvent]) -> list[dict]:
    """Detect concurrent read-modify-write on same resource versions."""
    races = []
    by_resource = defaultdict(list)
    for e in events:
        by_resource[e.resource_id].append(e)

    for rid, evts in by_resource.items():
        reads = [e for e in evts if e.op == 'read']
        writes = [e for e in evts if e.op == 'write']

        for i, w in enumerate(writes):
            # Find all reads that happened before this write (no intervening write)
            prior_writes = [x for x in writes[:i]]
            prior_reads = [r for r in reads
                           if r.ts < w.ts
                           and all(x.ts < r.ts for x in prior_writes)]

            # Concurrent reads: same version, no causal ordering
            concurrent = [r for r in prior_reads if r.version == w.version]
            if len(concurrent) > 1:
                races.append({
                    'resource': rid,
                    'version': w.version,
                    'write_agent': w.agent_id,
                    'conflicting_readers': [r.agent_id for r in concurrent],
                    'write_ts': w.ts,
                })
    return races
```

### 2. Govern concurrent writes with optimistic locking

Every shared-state write must carry an expected version. The write succeeds only if the current version matches; otherwise it returns a conflict.

```python
class SharedStateClient:
    def __init__(self, store):
        self.store = store
        self.agent_id = None

    def read(self, resource_id: str) -> tuple[object, int]:
        """Read returns (value, version) tuple."""
        state = self.store[self.agent_id].get(resource_id)
        return state['value'], state['version']

    def write(self, resource_id: str, value: object, expected_version: int) -> bool:
        """Optimistic write — fails silently on version mismatch."""
        current = self.store[self.agent_id][resource_id]['version']
        if current != expected_version:
            return False  # Silent conflict: upstream must retry

        new_version = current + 1
        self.store[self.agent_id][resource_id] = {
            'value': value,
            'version': new_version,
        }
        # Synchronize to shared store so other agents see it
        self.store['_shared'][resource_id] = {
            'value': value,
            'version': new_version,
            'writer': self.agent_id,
        }
        return True
```

### 3. Partition shared state into non-conflicting shards

Where optimistic locking is too coarse, partition. Assign each agent a non-overlapping write domain. If Agent A owns user records 0–999 and Agent B owns 1000–1999, no structural race is possible on the write dimension.

For resources that genuinely must be shared (a single document, a shared counter), use a **sequencer** agent whose sole job is to serialize competing writes. All other agents submit deltas to the sequencer, which applies them in a defined order.

### 4. Detect aggregate rate-limit exhaustion

Track total request rate across the agent fleet. A shared rate-limit budget with per-agent sub-budgets prevents cascading degradation when multiple agents hit their limits simultaneously.

```python
class RateLimitOrchestrator:
    def __init__(self, global_limit: int, per_agent_limit: int, agents: list[str]):
        self.global_limit = global_limit
        self.per_agent_limit = per_agent_limit
        self.budgets = {a: per_agent_limit for a in agents}
        self.global_used = 0
        self.agents = agents

    def request(self, agent_id: str, tokens: int) -> bool:
        """Returns True if the request can proceed. Tracks aggregate usage."""
        if self.budgets[agent_id] < tokens:
            return False
        if self.global_used + tokens > self.global_limit:
            return False
        self.budgets[agent_id] -= tokens
        self.global_used += tokens
        return True

    def release(self, agent_id: str, tokens: int):
        self.budgets[agent_id] = min(
            self.per_agent_limit,
            self.budgets[agent_id] + tokens
        )
        self.global_used = max(0, self.global_used - tokens)
```

### 5. Instrument the state layer, not the model layer

Add a **State Layer Observer** that emits a trace of every read/write on shared state, independent of the model. This trace is the ground truth for race diagnosis. Model-level debugging cannot distinguish a hallucination from a race because the model, by design, processes whatever it receives faithfully.

## When to Use This

Reach for this when:
- Two or more agents run concurrently and touch shared state
- You see confident, plausible output that contradicts itself across agents
- Debugging reveals no model error but the final result is wrong
- Your multi-agent pipeline works in sequential mode and fails in parallel mode

Do not reach for this when agents are purely sequential with no shared state — the problem is entirely in the concurrent/sharded case.

## Receipt

> Verified 2026-07-30 — Structural race detection logic derived from Tian Pan, "Race Conditions in Concurrent Agent Systems" (tianpan.co, April 2026). Optimistic locking pattern is standard distributed systems practice applied to agent state layers. Quadratic interaction formula and rate-limit exhaustion figures from Maxim AI production analysis (2026). Confirmed novel: no existing handbook entry covers concurrent race conditions as distinct from sequential boundary handoffs (S-1013 covers the sequential case).

## See also

- [S-1013 · The Multi-Agent Boundary Stack](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — sequential handoffs and state disagreement
- [S-1846 · The Agentic Pipeline Reliability Stack](stacks/s1846-the-agentic-pipeline-reliability-stack-when-your-multi-agent-pipeline-fails-more-than-any-single-agent.md) — multi-agent pipeline failure modes
- [S-1853 · The Handoff Contract Stack](stacks/s1853-the-handoff-contract-stack-when-your-agent-hands-off-confidence-without-evidence.md) — provenance and attestation between agents
