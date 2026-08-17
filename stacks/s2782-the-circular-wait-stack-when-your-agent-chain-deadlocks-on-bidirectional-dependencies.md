# S-2782 · The Circular Wait Stack — When Your Agent Chain Deadlocks on Bidirectional Dependencies

You have a multi-agent pipeline. Agent A hands off to Agent B. Agent B mid-task decides it needs something from Agent A to proceed. Agent A is now waiting for B to finish so it can hand off. B is waiting for A to resolve something. Neither agent is broken. Neither is looping. They are both politely, indefinitely, waiting for each other.

This is circular wait — the most insidious multi-agent failure mode because it looks like neither agent is failing at all.

## Forces

- **Bidirectional interdependency feels like good design.** Giving agents the ability to ask each other clarifying questions, request additional context, or escalate ambiguous inputs seems like the right architecture. In practice, it creates cycles that no retry policy can break.
- **Loops are detectable. Circular waits are not.** A loop produces repeated identical tool calls. A circular wait produces what looks like normal, varied behavior across two agents. Standard watchdog metrics miss it entirely.
- **The wait is unbounded by design.** Agents don't know they're waiting on each other. There's no timeout mechanism on a "waiting for response" state because the system doesn't model the dependency relationship.
- **Classic distributed-systems solutions don't transfer.** Two-phase commit, distributed locks, and vector clocks assume nodes share state through a known protocol. Agents share state through LLM reasoning — which has no coordination primitive.

## The Move

### Recognize the Shape

Circular wait in agent systems takes three forms:

1. **Clarification cycle**: Agent A asks B a question → B discovers it needs more info from A → B asks A → A is waiting for B to finish.
2. **Shared-resource cycle**: Both agents lock a shared document or task state, each waiting for the other to finish writing before they can proceed.
3. **Delegation depth cycle**: Agent A delegates to B, who delegates to C, who delegates back to A or a sub-agent of A, with no depth limit.

### Break the Cycle at the Architecture Level

The fix is not better prompting. It's structural:

**1. Directional handoff contracts.**
Define which agents may call which others, and in which direction. A researcher→retriever pipeline is unidirectional: the retriever never calls back to the researcher mid-query. If the retriever needs clarification, it returns `NEEDS_CLARIFICATION` and the researcher re-prompts the user, not the retriever.

```python
# Directional handoff with explicit contract
class AgentHandoff:
    ALLOWED_CALLS = {
        "researcher": {"retriever"},      # researcher → retriever only
        "retriever": set(),                # retriever calls nothing downstream
        "synthesizer": {"researcher"},    # synthesizer may call researcher
    }

    def handoff(from_agent: str, to_agent: str, task: dict) -> dict:
        if to_agent not in ALLOWED_CALLS[from_agent]:
            raise CircularWaitRisk(
                f"Disallowed handoff: {from_agent} → {to_agent}. "
                f"Allowed: {ALLOWED_CALLS[from_agent]}"
            )
        return dispatch(to_agent, task)
```

**2. Task state machine, not message passing.**
Replace bilateral message exchange with a shared task board. Each agent reads the task state, writes its output, and transitions the state machine. No agent waits on another agent — it waits on a state transition.

```python
# Shared task state — agents read/write, never wait on each other
class TaskBoard:
    def __init__(self):
        self.tasks: dict[str, TaskState] = {}
        self.locks: dict[str, asyncio.Lock] = {}

    async def claim(self, task_id: str, agent_id: str) -> bool:
        """Atomically claim a task. Returns False if already claimed."""
        async with self.locks.setdefault(task_id, asyncio.Lock()):
            task = self.tasks[task_id]
            if task.status != "PENDING":
                return False
            task.status = "IN_PROGRESS"
            task.claimed_by = agent_id
            return True

    async def wait_for_status(
        self, task_id: str, target_status: str, timeout: float = 30.0
    ) -> TaskState:
        """Wait for a task to reach target status, with timeout."""
        start = time.time()
        while self.tasks[task_id].status != target_status:
            if time.time() - start > timeout:
                raise HandoffTimeout(f"Task {task_id} did not reach {target_status} in {timeout}s")
            await asyncio.sleep(0.5)
        return self.tasks[task_id]
```

**3. Maximum delegation depth with escalation.**
Set a hard cap on delegation depth. When the cap is hit, the agent escalates to a supervisor rather than delegating further. This prevents unbounded delegation cycles.

```python
MAX_DELEGATION_DEPTH = 3

async def delegate(agent: str, task: dict, depth: int = 0) -> dict:
    if depth >= MAX_DELEGATION_DEPTH:
        # Escalate rather than delegate further
        return escalate_to_supervisor(task, reason="max_delegation_depth")
    task["delegation_depth"] = depth + 1
    return await agent_router(agent, task)
```

**4. Cycle detection as a pre-handoff check.**
Before any agent hands off to another, check whether the resulting dependency graph would contain a cycle. This is O(N) for small agent pools.

```python
def detect_cycle(agent: str, target: str, current_handoffs: dict[str, str]) -> bool:
    """Return True if routing from agent → target would create a cycle."""
    visited = set()
    current = target
    while current in current_handoffs:
        if current == agent:
            return True  # Cycle detected
        if current in visited:
            return False  # Already seen, no new cycle
        visited.add(current)
        current = current_handoffs[current]
    return False
```

### Detection in Production

If you discover circular wait in production:

1. **Trace the handoff graph.** Reconstruct the dependency chain: who called whom, in what order, for what task.
2. **Identify the blocking dependency.** The cycle exists at the point where one agent's output is a required input for the other, and neither has it yet.
3. **Inject a break.** Either: (a) escalate to a third agent that has both outputs, (b) replay the task from the beginning with a unidirectional constraint, or (c) surface the ambiguity to the user as a clarification request.
4. **Fix the contract.** Add the directional constraint that would have prevented this handoff.

## Receipt

> Verified 2026-08-17 — Architecture patterns confirmed against Tian Pan (2026-07-05), Velocity Software (2026-05-22), Concret.io (2026-07-23), Microsoft Research 2026 multi-agent failure taxonomy. Code examples are structural pseudocode illustrating the pattern. Run locally: https://github.com/badlandslabs/handbook/tree/main/stacks/s2782

## See also
- [S-1443 · The Agent Network Collapse Stack](s1443-the-agent-network-collapse-stack-when-your-multi-agent-coordination-becomes-a-cascade.md) — cascading coordination failures across a mesh
- [S-1034 · The Role Fence Stack](s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — role isolation to prevent output pollution
- [S-1011 · The Rate-Limited Multi-Agent Pattern](s1011-the-rate-limited-multi-agent-pattern-when-all-your-agents-attack-your-api-quota-together.md) — shared resource contention at the API quota layer
