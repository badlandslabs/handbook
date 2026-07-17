# S-1252 · The Fleet Reachability Problem — When Your Agents Are Alive but Nobody Can Reach Them

Your monitoring dashboard shows five healthy agents. A direct probe to each agent returns success. Your orchestrator is unreachable. Every task in the queue stalls. The agents are alive. The fleet is dead. This is the fleet reachability problem: the central control plane is not the agents, but it is the gate between you and what the agents can do — and when it fails, your capable agents become inaccessible assets you cannot reach.

## Forces

- **Orchestrators are stateful, centralized, and complex.** They accumulate retry policies, cost controls, evaluation loops, state management, and routing logic until a single bug — a retry cascade, a memory leak, a bad deployment — brings down every agent the system manages. Capability and reachability are not the same thing, and teams that conflate them pay in production.

- **The registry is a claim, not a fact.** A health check that queries the orchestrator's internal state says "five agents ready." A live probe that calls each agent directly says "three are unreachable." The gap between these two answers is the fleet reachability problem. You are managing what you can see, not what actually exists.

- **Graceful degradation requires deliberate design.** The natural state of a multi-agent system with a dead orchestrator is full stop. Direct dispatch, schema-bound fallback lanes, and circuit breakers are not defaults — they require explicit engineering. Teams that ship these patterns only after an incident have already had the incident.

- **Fleet observability must survive control-plane failure.** If your monitoring lives in the orchestrator, the orchestrator's failure takes your visibility with it. The watcher needs independence from the watched.

## The Move

### 1. Separate the Control Plane from Execution Plane

Decouple agent executability from orchestration health. Workers should register with a discovery service (etcd, Consul, NATS) and expose a direct dispatch endpoint — not only through the orchestrator. This gives you two paths to an agent.

```
# Direct agent probe (independent of orchestrator)
POST /workers/agent-17/ping  →  {"status": "ready", "tasks_completed": 847}

# vs orchestrator-mediated dispatch
POST /orchestrator/dispatch  →  (requires orchestrator alive)
```

### 2. Treat Registry State as a Claim, Not a Fact

Always verify reachability with a live probe, not a cached registry read. The orchestrator's internal state can drift from reality — a registry entry says "ready" while the agent is in a deadlock.

```python
def dispatch_task(agent_id: str, task: dict) -> dict:
    # Step 1: Check registry (fast path)
    if not registry.is_registered(agent_id):
        return {"status": "error", "reason": "agent_not_registered"}

    # Step 2: Live probe (authoritative path)
    try:
        response = http.post(f"http://{registry.address(agent_id)}/ping", timeout=2)
        if response.status != 200:
            raise AgentUnreachable(agent_id)
    except (ConnectionError, TimeoutError):
        # Fall through to degraded mode
        pass

    # Step 3: Fallback to degraded mode
    return degraded_dispatch(agent_id, task)
```

### 3. Build Fallback Lanes as First-Class Paths

Degraded modes are not afterthoughts — they are production paths that run when the primary path fails. Design three tiers:

| Mode | Trigger | Behavior |
|------|---------|----------|
| **Orchestrated** | Control plane healthy | Full routing, retries, cost tracking |
| **Direct dispatch** | Orchestrator unreachable | Direct lane execution, basic retry |
| **Queued recovery** | Agent unreachable | Queue for later, alert, manual gate |

```python
def degraded_dispatch(agent_id: str, task: dict) -> dict:
    # Schema-bound handoff keeps degraded execution coherent
    validated_task = schema_validator.validate(task, TASK_SCHEMA)
    queue.push(validated_task, priority=task.get("priority", "normal"))
    return {"status": "queued", "lane": "degraded", "estimated_recovery": "unknown"}
```

### 4. Run an Independent Fleet Monitor

The watcher must not participate in the swarm it watches. A separate process — outside the orchestrator's process boundary — verifies liveness, loop risk, cost acceleration, and anomaly signals independently.

```
# Fleet monitor runs as an independent service
# Queries agents directly via /workers/{id}/status
# Alerts on: unreachable agents, cost spikes, loop detection
```

Key metrics for fleet health (independent of orchestrator):

- **Reachability rate**: fraction of agents responding to live probes
- **Queue depth per lane**: detects backpressure before users complain
- **Cost acceleration per agent**: catches runaway loops before the bill arrives
- **Message lag**: time between queue submission and agent acknowledgment

### 5. Schema-Bound Handoffs as the Degraded Contract

When the orchestrator dies, natural-language relay between surviving agents becomes noise. Schema-bound context ensures that agents executing in degraded mode have enough structured information to proceed without orchestrator-mediated context passing.

```python
TASK_SCHEMA = {
    "type": "object",
    "required": ["task_id", "action", "context", "priority"],
    "properties": {
        "task_id": {"type": "string", "format": "uuid"},
        "action": {"type": "string", "enum": ["analyze", "draft", "review", "escalate"]},
        "context": {"type": "object", "additionalProperties": True},
        "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
    }
}
```

## Receipt

> Receipt pending — 2026-07-17

Three converging sources establish the fleet reachability problem as a production-class failure mode in 2026:

1. **Exzil Calanza (June 3, 2026)** — "When the Orchestrator Dies but the Agents Live": defines the failure topology, establishes that registry claims ≠ live agent state, and proposes the live-probe-as-truth pattern. Incident cited: registry claimed five ready workers while direct probes found three unreachable.

2. **Cliff Robbins / grow-tomorrow.com (2026)** — "Why Your Agent Orchestrator Will Fail in Production": catalogs four failure modes (orchestrator crash, memory leak, retry cascade, latency spike), establishes that orchestration complexity grows with system maturity, and provides a complexity-risk table mapping added features to introduced failure modes.

3. **Zylos Research (2026-06-11)** — "Agent Fleet Observability": confirms independent fleet monitoring as a production requirement, distinguishes WebSocket control-plane telemetry from SSE telemetry feed, and establishes the Anthropon pattern (agent-to-collector pipe via gRPC/OTLP) as a fleet observability architecture.

## See also

- [S-1052 · The Cascade Stack](s1052-the-cascade-stack-when-one-wrong-answer-infects-your-entire-multi-agent-pipeline.md) — when agents trust each other incorrectly (complementary: this entry is about reachability; S-1052 is about correctness)
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement between agents
- [S-1251 · The Orchestration Patterns Stack](s1251-the-orchestration-patterns-stack-when-your-agent-chains-calls-but-nobody-knows-what-runs-next.md) — patterns for sequencing multi-agent calls (this entry covers the failure case; S-1251 covers the design patterns)
