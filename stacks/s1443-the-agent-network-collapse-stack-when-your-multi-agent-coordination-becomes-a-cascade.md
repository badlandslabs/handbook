# S-1443 · The Agent Network Collapse Stack — When Your Multi-Agent Coordination Becomes a Cascade

Your multi-agent pipeline has a failure. Not in an agent — in the coordination layer. Agent Alpha handed a task to Agent Beta over A2A. Beta's downstream tool timed out. Beta wrote a failure state back to the shared task. Alpha interpreted the state as "in progress" and re-delegated. Now Gamma, Delta, and Epsilon are all operating on stale assumptions about what the task state is, while three downstream services are fielding duplicate requests from agents that don't know they're competing. The A2A task state machine has no deadlock detector. The MCP tool pool has no concurrency governor. The circuit breaker that would catch this in a microservices architecture doesn't exist in your agent framework. This is agent network collapse: not a single agent failing, but a coordination-level failure propagating through your entire agent mesh until nothing is sure what it's doing.

## Forces

- **A2A task state is shared mutable state across trust boundaries.** Unlike HTTP RPC calls (which are stateless and idempotent), A2A handoffs pass a mutable task object that multiple agents can read and write. When Beta crashes mid-handoff and Alpha re-delegates, you now have two agents operating on the same task with different assumptions about its state — a race condition with no transactional coordinator.
- **MCP tool pools have no concurrency governor.** When three agents discover the same MCP server as the path to the database, they don't negotiate access. They hammer it in parallel, triggering rate limits, exhausting connection pools, or creating write conflicts that none of them can see because each only observes their own tool call response.
- **Agents don't propagate their failures to dependents.** A microservice that crashes sends a 503 upstream, triggering the caller's circuit breaker. An A2A agent that crashes leaves a task in `working` state, and its calling agents have no way to detect the crash without polling. By the time anyone notices, the caller has re-delegated N times.
- **Safety shutdowns in one agent can trigger unsafe states in others.** When a high-stakes agent detects a policy violation and halts, its downstream consumers may not know why. They continue operating on stale assumptions — approving transactions, provisioning resources, or sending confirmation emails for work that was just cancelled upstream.
- **The blast radius is the entire mesh, not the failing node.** A single slow MCP server affects every agent that touches it. A malformed AgentCard causes incorrect routing across every orchestrator that reads it. A shared rate limit bucket means one noisy agent degrades the tool access for every other agent sharing its namespace.

## The move

### 1. Instrument the coordination layer, not just the agents

The failure is invisible to per-agent observability. You need:

```
# W3C Trace Context propagated across every A2A handoff
traceparent: 00-<64-bit hex>-<64-bit hex>-<2-digit flags>

# Task state as observable events, not just final values
TaskCreated(tid, agent, timestamp, parent_tid?)
TaskDelegated(tid, from_agent, to_agent, traceparent)
TaskStateChanged(tid, old_state, new_state, by_agent)
ToolCallDispatched(tid, agent, tool_name, mcp_server)
ToolCallCompleted(tid, agent, tool_name, duration_ms, status)
AgentHalted(tid, agent, reason_code, downstream_agents_affected[])
```

Without this instrumentation, a deadlocked agent looks identical to a slow one from every vantage point except the task log.

### 2. Govern MCP tool access with a concurrency budget

Do not let N agents share an MCP tool pool without a semaphore layer:

```python
# MCP tool concurrency governor
from collections import defaultdict
import asyncio, threading

class ToolConcurrencyGovernor:
    def __init__(self, max_concurrent_per_server: dict[str, int]):
        self._semaphores = {
            server: asyncio.Semaphore(limit)
            for server, limit in max_concurrent_per_server.items()
        }
        self._active: dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    async def call(self, server: str, tool_name: str, args: dict):
        async with self._semaphores[server]:
            with self._lock:
                self._active[server] += 1
                active = self._active[server]
            try:
                result = await self._dispatch(server, tool_name, args)
                return result
            finally:
                with self._lock:
                    self._active[server] -= 1

    async def _dispatch(self, server, tool_name, args):
        # actual MCP call
        ...
```

Set `max_concurrent_per_server` based on the upstream API's rate limits and your cost budget, not based on how many agents *want* to use it.

### 3. Implement A2A task lifecycle guardianship

Every A2A task delegation should be wrapped with:

- **Delegation timeout**: if the sub-agent doesn't return a terminal state within N seconds, mark the task as `orphaned` and notify upstream
- **State lease**: tasks should carry a `lease_expires_at` timestamp; if the delegating agent doesn't refresh the lease, other agents can infer the original is dead
- **Dependency DAG**: track which agents are downstream of which, so a halt in one node can trigger a coordinated shutdown of its consumers

```python
TASK_STATES = {
    "pending",      # created, not delegated
    "delegated",    # handed to sub-agent, lease_active
    "orphaned",     # delegator disappeared, no lease refresh
    "completed",    # terminal: success
    "failed",       # terminal: explicit failure
    "cancelled",    # terminal: upstream cancelled
}

def is_terminal(state: str) -> bool:
    return state in {"completed", "failed", "cancelled"}
```

### 4. Add a coordination circuit breaker

The circuit breaker pattern from microservices needs an agent-native variant:

```
# When any of these trigger, open the coordination circuit:
# - Task orphaned (no lease refresh within 3× expected duration)
# - >N% of concurrent tasks for a given tool server returning errors
# - Agent Halts event received from a downstream consumer
# - Circular delegation detected (Agent A → B → C → A)

When OPEN:
  - Block new delegations to the affected agent/server
  - Surface the coordination failure to human oversight
  - Do NOT re-delegate: every retry in a broken coordination state
    compounds the damage (S-1439)
```

The critical distinction from standard circuit breakers: when an agent's coordination circuit opens, you must also roll back any side effects the broken coordination caused. A failed A2A handoff may have already triggered tool calls in the sub-agent that succeeded before the circuit opened.

### 5. Test the mesh, not the agents

Unit tests verify each agent in isolation. What collapses production is the mesh. Test:

- **Failure injection**: kill an agent mid-handoff; verify the caller times out, marks the task orphaned, and does NOT re-delegate without a backoff
- **Race condition**: start two agents delegating the same subtask simultaneously; verify one is blocked or the task state is locked
- **Leased resource exhaustion**: saturate a shared MCP tool server; verify all agents degrade gracefully with throttling, not errors
- **Circular delegation**: configure a misrouted agent graph; verify detection triggers before any delegation is attempted
- **Cascade shutdown**: halt a high-order agent; verify dependents receive the halt signal and stop within their own configured timeout

## Receipt

> Verified [date] — [what was actually run, actual output, real tradeoffs]

## See also

- [S-1052 · The Cascade Stack](/stacks/s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — hallucination propagation through multi-agent fact channels
- [S-1070 · The Loop Guard Stack](/stacks/s1070-the-loop-guard-stack-when-agents-run-forever.md) — unbounded recovery loops within a single agent
- [S-1166 · The Cross-Agent Trace Fragmentation Problem](/stacks/s1166-the-cross-agent-trace-fragmentation-problem-when-every-agent-traces-itself-but-nobody-traces-the-handoff.md) — observability gap in A2A handoffs
- [S-1439 · The Self-Bounding Agent Stack](/stacks/s1439-the-self-bounding-agent-stack-when-your-recovery-logic-costs-more-than-the-bug.md) — when recovery logic without a ceiling becomes the primary failure mode
