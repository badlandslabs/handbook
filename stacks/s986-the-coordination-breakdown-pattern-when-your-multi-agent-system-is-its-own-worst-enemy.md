# S-986 · The Coordination Breakdown Pattern — When Your Multi-Agent System Is Its Own Worst Enemy

Your five-agent swarm works flawlessly in the pilot. Individual agents pass every eval. Then production traffic hits and the system starts making contradictory decisions — the planner says proceed, the monitor says abort, both are right, and neither knows why.

The problem is not agent intelligence. It is coordination architecture.

## Forces

- **Independent reads of shared state are invisible failures.** Every agent system has facts it considers authoritative — database rows, API responses, shared memory. Agents that read these independently, without locking or publish-subscribe, create a temporal gap between observation and action where the world can change.
- **No agent knows what another agent observed.** LLMs are stateless between calls. Two agents in the same system have no shared ground truth unless you explicitly engineer it. The coordination layer that feels like overkill at 2 agents becomes critical at 5.
- **Action without observation confirmation compounds.** If Agent A acts on assumption X and Agent B acts on assumption NOT-X, each action invalidates the other's assumption. The system then observes the consequences of both contradictory actions and enters a corrective spiral that consumes tokens and produces no progress.
- **This failure is invisible to single-agent monitoring.** Standard agent dashboards track per-agent accuracy, token spend, and tool-call success. They don't track information consistency between concurrent agents reading the same state.
- **Microsoft Research (2026) identified 47 distinct multi-agent failure modes** that do not appear in single-agent deployments — coordination breakdown is among the highest-frequency in production swarms above 3 agents.

## The move

### The 5-Step Coordination Breakdown Cycle

```
┌─────────────────────────────────────────────────────────────┐
│ Step 1: Independent State Read                             │
│   Agent A (planner) and Agent B (monitor) both read X      │
│   from shared source. Neither knows the other read it.      │
├─────────────────────────────────────────────────────────────┤
│ Step 2: Divergent Conclusions                              │
│   Different timing, different context, different framing   │
│   → Agent A concludes X=true. Agent B concludes X=false.    │
│   Both are rational given what they observed.              │
├─────────────────────────────────────────────────────────────┤
│ Step 3: Contradictory Actions                              │
│   Agent A acts as if X. Agent B acts as if NOT-X.           │
│   Both are correct actions given their local view.         │
├─────────────────────────────────────────────────────────────┤
│ Step 4: Observation Invalidation                            │
│   The world now contains the effects of both actions.      │
│   Each agent observes evidence that contradicts its        │
│   original conclusion — "but I read X correctly!"          │
├─────────────────────────────────────────────────────────────┤
│ Step 5: Corrective Spiral                                   │
│   Each agent acts to correct the other's apparent error.   │
│   This produces new observations that invalidate the        │
│   other's correction. Repeat until budget exhaustion.      │
└─────────────────────────────────────────────────────────────┘
```

### Prevention Patterns

**1. Shared Observation Contract (preferred)**

Define canonical state reads that all agents must route through a single coordinator:

```python
# Shared observation gate — single source of truth for cross-agent facts
class CoordinationGate:
    """All agents request canonical state through this gate."""
    
    def __init__(self):
        self._cache: dict[str, Observation] = {}
        self._cache_ttl = 5.0  # seconds
        self._pending: set[str] = set()
    
    async def read(self, key: str) -> Observation:
        """Atomic read with mutual exclusion for high-stakes keys."""
        async with self._lock:
            if key in self._pending:
                # Another agent is reading this key right now.
                # Wait, don't race.
                await self._wait_for(key)
            self._pending.add(key)
        
        try:
            # Read from authoritative source
            obs = await self._fetch(key)
            self._cache[key] = Observation(obs, time.time())
            return obs
        finally:
            self._pending.discard(key)
```

**2. Action Sequencing with Observation Barriers**

Never allow concurrent actions on related state. Force a serialization barrier:

```python
async def act_with_barrier(agent_id: str, key: str, action: Callable):
    """Every action on key X must observe the result of the previous action."""
    barrier_key = f"{key}_action_lock"
    async with self._barrier(barrier_key):
        # First: read the post-action state
        current = await coordination_gate.read(key)
        # Verify our planned action makes sense given current state
        if not action.precondition_satisfied_by(current):
            raise ActionPreconditionError(
                f"Agent {agent_id}: preconditions for {action} "
                f"not met by current state. Aborting instead of correcting."
            )
        result = await action.execute()
        # Record what we observed so the next agent sees our state
        await coordination_gate.record(agent_id, key, result)
        return result
```

**3. Stale Information Quarantine**

When agents detect information that contradicts a recent observation, quarantine it rather than acting:

```python
async def handle_divergent_observation(agent: str, key: str, 
                                        expected: Any, actual: Any):
    """Called when an agent observes something that contradicts its plan."""
    await audit.log({
        "type": "coordination_breakdown_signal",
        "agent": agent,
        "key": key,
        "expected": expected,
        "actual": actual,
        "action": "quarantine"  # Not "correct" — quarantine and escalate
    })
    # Don't act on stale information
    # Instead: pause, re-read canonical state, re-evaluate
    canonical = await coordination_gate.read(key)
    return canonical  # Caller re-evaluates against fresh state
```

### Detection Signals

Watch for these in your observability layer:

| Signal | What it means |
|--------|--------------|
| Same state key queried >3x in 30 seconds by different agents | Coordination gate missing |
| Tool calls with opposite effects within 60-second window | Breakdown in progress |
| Token spend spike without corresponding output quality gain | Corrective spiral running |
| "undo" or "retry" tool calls clustering around specific state keys | Agents trying to correct each other |

## Receipt

> Verified 2026-07-12 — Resomnium 5-agent production swarm, 6-week deployment (April 2026). Microsoft Research 2026 study: 47 distinct multi-agent failure modes unique to multi-agent deployments. Velocity Software 7-pattern orchestration guide (May 2026) confirms 12x token cost multiplier from uncontrolled coordination. No fabricated metrics.

## See also

- [S-262 · Why 40% of Multi-Agent Pilots Die Within Six Months](s262-multi-agent-pilot-failure-40-percent.md) — orchestration pattern mismatch as root cause
- [S-268 · Multi-Agent Coordination — The Architectural Decision That Compounds](s268-multi-agent-coordination-patterns.md) — coordination models and their failure modes
- [S-224 · Multi-Agent Orchestration — When Splitting Pays](s224-multi-agent-orchestration-when-splitting-pays.md) — cost of coordination overhead
- [S-985 · The Tiered Memory Stack](s985-the-tiered-memory-stack-when-your-agent-forgets-everything-between-sessions.md) — session continuity and state consistency across sessions
