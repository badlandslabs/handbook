# S-1750 · The Conflict Resolution Stack — When Your Parallel Agents Disagree on the Answer

Your fan-out pipeline dispatches the same task to three specialist agents. One recommends approving the transaction. One recommends declining it. One asks for more information. The pipeline needs an answer in under 200ms. Most systems silently pick the first result back or the most recent write — and the failure is invisible until something downstream breaks. This is not a prompt problem. It is a coordination problem, and it is the dominant failure mode of parallel agent topologies.

## Forces

- **Agents disagree 20–40% of the time** on identical inputs (Tian Pan, tianpan.co, May 2026). Sampling from different model providers, different temperature settings, or even the same model at different times produces non-identical outputs. This is not a bug — it is the expected behavior of non-deterministic systems.
- **Silent picking is the worst resolution strategy.** When agents disagree and the system arbitrarily selects one output, the chosen result may be the worst of the three. Without disagreement detection, there is no signal to escalate, retry, or involve a human.
- **The resolution strategy is task-dependent.** Voting works for classification and structured extraction. Consensus-based arbitration is needed for reasoning tasks. Exclusive-write locking is required for shared-state mutation. No single pattern fits all cases.
- **Distributed agents introduce the read-stale problem.** Agent A reads shared state, Agent B writes it before A acts. Agent A's read is now invalid, but the system has no mechanism to detect this unless writes are versioned or reads are lease-protected.
- **Resolution latency must be budgeted.** Fan-out pipelines have tight end-to-end SLAs. Three-way resolution with a quorum read adds latency that compounds on each parallel branch. Over-engineering resolution can defeat the purpose of parallelism.

## The move

### 1. Detect disagreement before resolving it

Every parallel branch must emit a structured result with a **result hash** — a deterministic hash of the output content. If multiple agents produce the same hash, they agree. If hashes differ, disagreement is flagged. This is cheap (O(n) over results) and gives you an exact count of how many agents diverged.

```python
import hashlib, json

def hash_result(output: dict) -> str:
    """Deterministic content hash for disagreement detection."""
    canonical = json.dumps(output, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]

# Fan-out results collected from parallel agents
results = [agent_a.run(task), agent_b.run(task), agent_c.run(task)]
result_hashes = [hash_result(r) for r in results]

unique_outputs = set(result_hashes)
if len(unique_outputs) == 1:
    # All agents agree — proceed with confidence
    agreed_output = results[0]
elif len(unique_outputs) == 2:
    # Minority/majority split — check which is the consensus
    from collections import Counter
    counts = Counter(result_hashes)
    consensus_hash, votes = counts.most_common(1)[0]
    agreed_output = results[result_hashes.index(consensus_hash)]
    flag_for_review(len(results) - votes)  # minority count
else:
    # Full disagreement — all three outputs differ
    escalate_to_human(results)
```

### 2. Use the right resolution strategy for the task type

| Task | Strategy | Example |
|------|----------|---------|
| Structured extraction (invoice parsing, classification) | Majority vote on result hash | Three agents parse the same PDF — take the most common field values |
| Reasoning / open-ended | Consensus arbitration | Route to a judge agent with all three outputs; the judge picks and explains |
| Shared-state mutation | Distributed locking + versioned writes | Only one agent writes to the CRM at a time; writes include a version number |
| High-stakes decisions | Two-phase: voting + human confirmation gate | Financial approvals: 2/3 agents must agree before auto-approval; otherwise human |

### 3. Version shared state to prevent read-stale races

For agents that read before writing shared state, attach a version or vector clock to every read. Writes must include the version they were based on. If the version has advanced, the write is rejected and the agent must re-read and retry.

```python
from dataclasses import dataclass
import time

@dataclass
class VersionedState:
    version: int
    data: dict
    updated_at: float

class SharedStateStore:
    def __init__(self):
        self._store: dict[str, VersionedState] = {}
        self._locks: dict[str, str] = {}  # resource -> lock holder

    def read(self, key: str, request_id: str) -> VersionedState | None:
        return self._store.get(key)

    def write(self, key: str, state: VersionedState, based_on: int, request_id: str) -> bool:
        """
        Optimistic write: succeeds only if no newer version exists.
        Returns True if write succeeded, False if version conflict.
        """
        current = self._store.get(key)
        if current and current.version > based_on:
            return False  # version conflict — re-read and retry

        self._store[key] = state
        return True

    def resolve_conflict(self, key: str, candidates: list[VersionedState]) -> VersionedState:
        """
        Last-write-wins with timestamp as tiebreaker.
        Replace with task-specific logic (e.g., majority vote on field values).
        """
        return max(candidates, key=lambda s: s.updated_at)
```

### 4. Handle the full disagreement lifecycle

```
disagreement_detected
  → classify severity (same-field vs different-recommendation vs incompatible-actions)
  → if minor (cosmetic) → majority-vote / lww (last-write-wins)
  → if major (different recommendations) → arbitration by judge agent
  → if incompatible (both say "do X" where X is mutually exclusive) → human escalation or rollback
  → log resolution path for drift detection
```

## Receipt

> Verified 2026-07-28 — Pattern derived from Tian Pan (tianpan.co, May 2026: 20-40% parallel agent disagreement rate) and Zylos Research (March 2026: CRDT-based distributed state synchronization for multi-agent systems). Code pattern follows the versioned-write / optimistic concurrency pattern standard in distributed systems, applied to agent coordination contexts. Receipt pending — production run not executed in this cycle.

## See also

- [S-961 · The Agent Harness Stack](s961-the-agent-harness-stack-when-the-llm-call-is-5-percent-of-the-work.md) — the orchestration layer that manages parallel dispatch
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement between agents at handoff boundaries
- [S-1022 · The Agent Drift Stack](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — how multi-agent systems degrade over time without code changes
- [S-988 · The Agent Fleet Resilience Stack](s988-the-agent-fleet-resilience-stack-when-your-orchestrator-dies-but-your-agents-keep-running.md) — fleet-level coordination under orchestrator failure
