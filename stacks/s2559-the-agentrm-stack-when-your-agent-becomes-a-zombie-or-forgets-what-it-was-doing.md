# [S-2559] · The AgentRM Stack — When Your Agent Becomes a Zombie or Forgets What It Was Doing

Agents fail in two ways that no LLM improvement fixes: they get stuck (zombie processes holding resources) or they lose their mind (context degradation wipes working memory). These aren't model problems — they're OS problems wearing agent clothing. The fix is treating agent resources the same way operating systems have managed compute resources for 50 years.

## Forces

- Agent sessions are unbounded: unlike a process with a stack limit, an agent's context grows until it collapses
- Agent scheduling is naive: most frameworks use FIFO or single queues, causing priority inversion and starvation
- Zombie agents accumulate silently: a sub-agent that completes its task holds its context slot for minutes because nobody reaped it
- Context eviction is recency-biased: important system instructions get evicted because they were loaded first
- No admission control: every incoming request gets a full agent even when a lightweight handler would suffice
- Rate limits cascade: a single slow tool blocks the entire agent, causing retry storms that take down the whole system

## The move

**AgentRM** (arXiv:2603.13110, March 2026) maps five OS primitives directly onto agent resource management:

### 1. MLFQ Scheduler — Priority Without Priority Inversion

Multi-Level Feedback Queue separates agents by urgency class. Critical foreground tasks run in the top queue with the shortest time slices. Background research runs at the bottom with longer slices and voluntary yielding. Aging rules promote idle background tasks to prevent permanent starvation.

Key insight: don't give every agent the same priority. A customer-facing escalation needs sub-second scheduling. An async research task can yield.

```python
# MLFQ-inspired priority tiers (simplified)
PRIORITY_QUEUES = {
    "critical": {"quantum_ms": 500, "max_age": 3, "aging_rate": 0},
    "interactive": {"quantum_ms": 2000, "max_age": 6, "aging_rate": 1},
    "background": {"quantum_ms": 30000, "max_age": 999, "aging_rate": 2},
}

def schedule(agent_id: str, priority: str) -> AgentSession:
    queue = PRIORITY_QUEUES[priority]
    # If background agent has waited max_age, promote it one level
    if queue["aging_rate"] > 0 and agent.age_ticks >= queue["max_age"]:
        priority = promote(priority)
    return dequeue(priority)
```

### 2. Zombie Reaping — Clean Up Completed Agents

A sub-agent that finishes its task but never releases its context slot is a zombie. The reaper watches for completion signals (task_done event, final tool call, explicit `yield` opcode) and terminates the session, freeing its memory and slot.

Critical rule: reaping must be cooperative. Forcibly killing an agent mid-tool-call leaves side effects uncompensated. The reaper waits for the agent to reach a safe checkpoint.

```python
async def zombie_reaper(agent_registry: dict[str, AgentSession]):
    while True:
        await asyncio.sleep(5)  # poll every 5 seconds
        for agent_id, session in agent_registry.items():
            if session.state == "completed" and not session.has_open_tool_calls:
                await session.shutdown(graceful=True)
                del agent_registry[agent_id]
                metrics.increment("agent.reaped", tags={"reason": "completed"})
            elif session.idle_time > session.max_idle:
                # Zombie: alive but not doing anything
                if not session.has_side_effects_pending:
                    await session.shutdown(graceful=False)
                    metrics.increment("agent.reaped", tags={"reason": "zombie"})
```

### 3. Rate-Limit-Aware Admission Control — Don't Flood What's Already Stalled

Before spawning an agent, check rate limits for every tool it will call. If the search API has 20 remaining calls in the quota window, queue the agent rather than letting it hit 429s and retry. This prevents cascading failures from a single rate-limited tool blocking the entire agent pipeline.

```python
async def admission_control(task: Task, tools: list[Tool]) -> bool:
    for tool in tools:
        quota = await rate_limit_check(tool.name, window_seconds=60)
        if quota.remaining < task.estimated_tool_calls.get(tool.name, 1):
            await task.queue(delay=quota.reset_in_seconds)
            return False  # Deferred, not rejected
    return True  # Admitted
```

### 4. Three-Tier Context Lifecycle Manager — RAM vs. Storage vs. Hibernate

Map context tiers to OS memory hierarchy:

| Tier | OS Analogy | Content | Eviction Policy |
|------|-----------|---------|----------------|
| Hot | CPU cache | Last 3 tool calls + current instruction | Recency only |
| Warm | RAM | Session state + retrieved docs + system prompt | Importance-weighted (not recency) |
| Cold | Disk/hibernation | Full conversation history + learned facts | Time + outcome correlation |

**Importance-weighted eviction** is the critical insight. Standard LLM context management evicts by position (earliest first). But system instructions loaded at position 1 are more important than a tool result from step 40. Weight by: instruction type × retrieval freshness × action proximity.

```python
def context_eviction_priority(item: ContextItem) -> float:
    weights = {
        "system_instruction": 10.0,
        "user_directive": 8.0,
        "retrieved_fact": 5.0,
        "tool_result": 3.0,
        "reasoning_trace": 1.0,
    }
    base = weights.get(item.type, 1.0)
    # Boost by freshness: how recently was this relevant?
    freshness = 1.0 / (1.0 + item.age_turns)
    # Boost by proximity: is this near an action that just happened?
    proximity = 1.0 / (1.0 + abs(item.position - current_turn))
    return base * freshness * proximity
```

### 5. Hibernation — Pause, Don't Terminate

For long-running agents that need to wait (API quota, user response, dependency), hibernate rather than terminate. Serialize the full state to durable storage, release the GPU/context slot, wake on a trigger event. This is the agent equivalent of ` suspend-to-disk`.

```python
async def hibernate_agent(agent_id: str, wake_on: WakeTrigger):
    session = agent_registry[agent_id]
    state = session.serialize()  # full context + tool state + position
    hibernation_store.put(agent_id, state, ttl=wake_on.max_wait)
    await session.release_resources()  # free context slot, release GPU
    # Wake on trigger:
    #   - timer expiry
    #   - external webhook
    #   - upstream agent completion
```

## Receipt

> Verified 2026-08-13 — arXiv:2603.13110 (She, March 2026) confirmed: 40,000+ GitHub issues across OpenClaw, AutoGen, CrewAI, LangGraph, Codex, Claude Code. Problem taxonomy: cross-channel blocking (user messages blocked 6+ hours), zombie subagents (11+ minute hold after completion), agent amnesia (context eviction destroying working state). MLFQ scheduler reduced priority inversion by ~60% in simulated workloads. Three-tier context manager outperformed recency-only eviction on downstream task accuracy. Real-world deployment references: enterprise middleware adoption at MBZWAI.

## See also

- **[S-150 · The Context-Capacity Gap](/stacks/s150-the-context-capacity-gap-when-advertised-context-window-lies.md)** — Why advertised context windows lie and effective context is far smaller
- **[S-2512 · The Production Agent Floor](/stacks/s2512-the-production-agent-floor-stack-when-your-agent-returns-200-but-is-failing.md)** — Minimum viable observability signals for production agents
- **[S-420 · Agent Identity Governance: The AI-Principal Paradigm](/stacks/s420-agent-identity-governance-the-ai-principal-paradigm.md)** — NHI identity and the IAM mesh for agents
- **[S-1019 · The Ghost-Loop Stack](/stacks/s1019-the-ghost-loop-stack-when-llm-driven-control-flow-becomes-ungovernable.md)** — Deterministic state machines for agent control flow
