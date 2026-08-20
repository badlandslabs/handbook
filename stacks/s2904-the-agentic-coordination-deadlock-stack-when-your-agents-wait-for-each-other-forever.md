# S-2904 · The Agentic Coordination Deadlock Stack — When Your Agents Wait for Each Other Forever

Your ticket-routing pipeline has two agents. Agent A (classifier) needs the category to route correctly. Agent B (categorizer) needs the priority level to pick the right classification taxonomy. Agent A asks B for the category. Agent B asks A for the priority. Neither can answer without the other's output. Both wait forever. Your pipeline is stuck with no error, no timeout, no alert — just two agents who have both concluded they are waiting on each other. This is agentic coordination deadlock: circular wait in the agents' reasoning graph, not in their code.

## Forces

- **Convergent reasoning produces symmetric failure.** Multiple agents reasoning from the same context reach the same conclusions — including the same next-step dependency. When two agents independently decide to wait on each other, the circular wait is not a bug in either agent; it is an emergent property of both agents reasoning correctly about the same problem simultaneously. The dining philosophers problem, now running on an LLM.
- **Agents are concurrent and non-deterministic.** Even on a single machine, agents behave as distributed processes: they call tools, await responses, and make decisions asynchronously. The four Coffman conditions for deadlock — mutual exclusion, hold-and-wait, no preemption, circular wait — all apply. Most agentic engineers haven't read the 40-year distributed systems literature that covers exactly this ground (COMPEL Framework, AITE M1.2-Art12, 2026).
- **Standard retry logic worsens, not fixes, the problem.** A timed-out agent retries the same blocked operation. The other agent, also retrying, now holds a resource the first agent needs. Retry waves from N agents amplify rather than resolve the contention. Coordination failures account for 37% of multi-agent system failures in production; systems without formal orchestration see 41–87% failure rates (tianpan.co, Apr 2026).
- **Detecting deadlock is harder than preventing it.** The system shows no errors — HTTP 200, normal token usage, agents "thinking." A pipeline that stalls for 45 minutes looks identical to one that is processing slowly in standard observability. TraceFix (ACM CAIS '26) found deadlock/livelock rates of 31.1% in unverified agent coordination protocols.

## The move

**Prevent: break circular wait at design time.**

The Coffman condition you can eliminate in software is circular wait. Enforce total resource ordering: assign every inter-agent resource (state, lock, handoff) a numeric acquisition order, and require all agents to acquire in ascending order only.

```python
# Simplified: total ordering on shared resources
# Each resource gets a priority; all agents acquire in priority order.
ACQUISITION_ORDER = [
    "priority_signal",   # priority first
    "classification",     # category second
    "routing_decision",  # route last
]

def safe_acquire(agent_name: str, resources: list[str]) -> bool:
    """Acquire resources in globally agreed order. Returns False on deadlock."""
    acquired = []
    for r in sorted(resources, key=lambda x: ACQUISITION_ORDER.index(x)):
        if not try_acquire(r):
            for held in acquired:
                release(held)
            return False  # Would create circular wait — abort
        acquired.append(r)
    return True
```

**Prevent: explicit handoff contracts.**

Replace implicit dependencies with declared preconditions. Agent B announces "I need priority_signal before I can produce classification." Agent A reads this before deciding to wait. If the precondition is unmet, Agent A handles the fallback path instead of blocking.

```python
# Handoff contract: declare upstream needs explicitly
@dataclass
class AgentContract:
    provides: str          # "classification"
    requires: list[str]    # ["priority_signal"]
    max_wait_seconds: int  # 30 — timeout instead of indefinite block
    fallback: str          # "skip_categorization"
```

**Prevent: protocol verification before deployment.**

TraceFix (Xia et al., ACM CAIS '26) synthesizes coordination protocols from task descriptions, uses TLA+ model checking (TLC) to find deadlock/livelock counterexamples, and iteratively repairs them. Verified protocols reduced DL/LL from 31.1% to 14.1% in ablation — over 50% reduction. The key insight: generating a correct concurrent protocol is hard, but checking one is mechanical.

```python
# TraceFix-style: specify protocol, verify before shipping
# Protocol spec (TLA+):
# VARIABLES state, waiting_for, held_resources
# Protocol == /\ \A a,b \in Agents: held(a) \cap held(b) = {}
#            /\ waiting(a) # {} => \E r \in waiting(a): acquire_order(r) > last_acquired(a)
# TLC: ModelCheck(Protocol, num_agents=5, iterations=1000)
# Counterexample found => protocol has deadlock; fix acquisition order
```

**Detect: behavioral stall guard.**

Instrument agents with a stall detector that fires if fewer than N tool calls complete in a time window with no terminal state.

```python
from threading import Timer

class StallGuard:
    def __init__(self, agent_id: str, window_seconds=180, min_steps=5):
        self.agent_id = agent_id
        self.steps = 0
        self.timer = Timer(window_seconds, self._on_stall)
        self.timer.start()

    def step(self):
        self.steps += 1
        self.timer.cancel()
        self.timer = Timer(180, self._on_stall)
        self.timer.start()

    def _on_stall(self):
        if self.steps < 5 and not self._terminal():
            alert(f"Agent {self.agent_id} may be deadlocked: "
                  f"{self.steps} steps in {window_seconds}s, no terminal state")
```

**Detect: Conway alignment check.**

The COMPEL Framework (2026) and Cemri et al. (2025) note that agent topology should mirror organizational structure. If your agent graph has circular dependencies that your org chart does not have, you have a design problem before a runtime problem. Validate the agent dependency graph is a DAG at startup.

**Recover: global coordinator timeout.**

When stall guard fires, the coordinator takes over: aborts blocked agents, re-queues the task with a simpler agent (no inter-agent dependency), and logs the deadlock pattern for protocol repair.

## Receipt

> Verified 2026-08-20 — Source materials: tianpan.co (Apr 2026, 37% coordination failure stat, 25-95% deadlock range); TraceFix CAIS '26 (Xia et al., arXiv:2605.07935, 31.1%→14.1% DL/LL reduction via TLA+ verification); Cemri et al. 2025 (14 failure modes); COMPEL Framework AITE M1.2-Art12 (four coordination topologies); Resomnium (Apr 2026, coordination breakdown five-step pattern). Code examples are realistic Python/TLA+ — not run against a live system. The TraceFix workflow (TLA+ synthesis → TLC model check → repair loop) is described from the paper; the Python stall guard and ordering primitives are illustrative of the pattern.

## See also

- [S-1011 · Rate-Limited Multi-Agent Pattern](stacks/s1011-the-rate-limited-multi-agent-pattern-when-all-your-agents-attack-your-api-quota-together.md) — synchronized retry waves compound the coordination failure
- [S-1034 · Role Fence Stack](stacks/s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — role boundaries prevent agents from acquiring resources outside their domain
- [S-1830 · Agentic Serializability Stack](stacks/s1830-the-agentic-serializability-stack-when-your-multi-agent-parallel-pipeline-silently-corrupts-shared-state.md) — shared-state corruption shares a root cause with deadlock: no global acquisition discipline
- [S-1046 · Agent Dead-End Stack](stacks/s1046-the-agent-dead-end-stack-when-your-agent-fails-and-cant-recover.md) — coordination deadlock is a specific class of unrecoverable dead end
