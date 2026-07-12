# S-988 · The Agent Fleet Resilience Stack — When Your Orchestrator Dies but Your Agents Keep Running

Your five-agent swarm is mid-flight on a critical data pipeline. The orchestrator process crashes. Kubernetes restarts it in 8 seconds. But those 8 seconds cost you: three agents completed their work and wrote outputs that no one consumed, one agent timed out waiting for a task assignment that never came, and the restarted orchestrator has no idea what the fleet was doing — so it re-queues everything from scratch. The agents were fine. The system wasn't. The orchestrator is the single point of failure that nobody named until the third outage.

## Situation

You're running a multi-agent system in production. The orchestrator — the central process that decomposes tasks, assigns work, and aggregates results — is treated like any other service. If it crashes, you restart it. What the restart checklist doesn't account for: the agents it was coordinating are still running, possibly completing work that is now orphaned, or about to contend with duplicated work from a fresh orchestrator that doesn't know what state the fleet is in.

This is not a Kubernetes problem. Kubernetes can restart the orchestrator process. This is a coordination state problem: the orchestrator holds the in-flight picture of the fleet in memory, and that picture is not persisted, not replicated, and not recoverable from the agents themselves.

## Forces

- **The orchestrator is the brain, but the agents do the work.** When the brain dies, the body keeps moving. Agents in a multi-agent system are typically long-running processes — they don't crash just because the coordinator restarted. They continue executing, writing to shared state, or waiting on queues. The restarted orchestrator faces a fleet it cannot observe.
- **Agent heartbeat is not the same as agent liveness.** An agent process being alive (returning 200 OK from a health endpoint) tells you nothing about whether it has work, whether its work is stale, or whether it is blocked on a dependency that will never resolve. A true fleet resilience model needs to know what every agent was *doing* when the orchestrator went down.
- **Task state lives in the orchestrator's memory.** In most agent frameworks — LangGraph, CrewAI, OpenAI Agents SDK — the task graph, task status, and agent assignments are maintained in-process. When the process restarts, that state is gone. The agents may still hold work in their input queues. The messages may still be in the message broker. But the orchestrator's map of the world is gone.
- **Naive restart creates duplication and contention.** The instinct after a crash is to re-queue failed tasks. But agents that kept running during the restart will also produce results. You now have two producers for the same task and a downstream consumer that doesn't know which output to trust.
- **Gartner reports 40% of multi-agent pilots fail within six months of production deployment.** A significant fraction of these failures trace to a single root cause: the orchestration layer has no resilience architecture, and a single process restart cascades into a full-system anomaly.

## The Move

The fix has four layers: **observable state persistence**, **agent heartbeat with task context**, **graceful degradation contracts**, and **recovery protocols**.

### 1. Persist Task State Outside the Orchestrator

Never hold task state in orchestrator memory. Use an external task store:

```python
from datetime import datetime
from enum import Enum
import uuid

class TaskStatus(Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    ORPHANED = "orphaned"       # orchestrator died mid-task
    STALE = "stale"             # agent heartbeat missed
    SUPERSEDED = "superseded"   # re-queued by new orchestrator

class TaskRecord:
    task_id: str
    status: TaskStatus
    assigned_agent: str | None
    created_at: datetime
    updated_at: datetime
    heartbeat_at: datetime | None  # last agent heartbeat
    result_ref: str | None         # pointer to output artifact
    attempt: int = 1
    orchestrator_instance: str     # which orchestrator owns this
    priority: int = 0
```

The orchestrator writes every state transition to this store before acting. A restart means the new orchestrator reads the store, finds tasks in `ASSIGNED` or `IN_PROGRESS` states, and treats them as candidates for recovery — not for blind re-queue.

### 2. Agent Heartbeat with Task Context

Agents must emit heartbeats that include what they're doing, not just that they're alive:

```python
import asyncio
from datetime import datetime, timedelta

async def agent_heartbeat(agent_id: str, task_id: str, step: str, subtask: str):
    await task_store.update(task_id, {
        "status": TaskStatus.IN_PROGRESS,
        "heartbeat_at": datetime.utcnow(),
        "assigned_agent": agent_id,
        "current_step": step,      # "calling_web_search"
        "current_subtask": subtask, # "finding regulatory citations"
        "orchestrator_instance": current_orchestrator_id,
    })

# Orchestrator monitors for stale heartbeats
async def detect_stale_tasks(heartbeat_timeout: timedelta = timedelta(seconds=30)):
    cutoff = datetime.utcnow() - heartbeat_timeout
    stale = await task_store.query(
        status=TaskStatus.IN_PROGRESS,
        heartbeat_before=cutoff
    )
    for task in stale:
        await task_store.update(task.task_id, {
            "status": TaskStatus.STALE,
            "stale_since": datetime.utcnow(),
        })
        emit_alert(f"Agent {task.assigned_agent} missed heartbeat for task {task.task_id}")
```

The key insight: a missing heartbeat means the task is either still running legitimately (increase the timeout) or the agent is stuck. A heartbeat that shows `step="waiting_on_dep"` tells you the agent isn't dead — it's blocked, and re-queueing would create a duplicate.

### 3. Schema-Bounded Degraded Contracts

When the orchestrator is unreachable, agents don't stop. They switch to a degraded-mode contract that defines what they can safely do alone:

```python
from dataclasses import dataclass

@dataclass
class DegradedModeContract:
    """What an agent can do when it can't reach the orchestrator."""
    max_retries_per_step: int = 2
    block_on_dependency: bool = True       # don't proceed if dep is STALE
    allow_result_write: bool = True         # safe for read-only agents
    allow_retry_dependent: bool = False     # don't re-do tasks that depend on STALE tasks
    emit_completion_signal: bool = True      # always write result even if orchestrator is down

    def is_safe_to_proceed(self, task_record: TaskRecord) -> bool:
        if task_record.status == TaskStatus.STALE:
            return False  # upstream agent is stuck
        if task_record.status == TaskStatus.SUPERSEDED:
            return False  # already re-queued by new orchestrator
        return True
```

The probe-and-schema pattern from Exzil Calanza's research: a live probe tells you the agent lane exists. A schema tells you what can be safely sent to it. Both are required for safe degraded-mode operation.

### 4. Recovery Protocol (The Restart Handshake)

When the orchestrator restarts, it doesn't blindly re-queue. It runs a recovery protocol:

```python
async def orchestrator_recovery():
    instance_id = str(uuid.uuid4())
    
    # Step 1: Claim ownership of orphaned tasks
    orphaned = await task_store.query(
        status=TaskStatus.ASSIGNED,
        orchestrator_instance=PREVIOUS_INSTANCE,  # cleared on startup
    )
    
    # Step 2: Probe each agent for its actual state
    for task in orphaned:
        agent = await agent_registry.get(task.assigned_agent)
        try:
            probe = await agent.probe(task.task_id)
            if probe.state == "completed" and probe.result_ref:
                # Agent finished during restart window — absorb result
                await task_store.update(task.task_id, {
                    "status": TaskStatus.COMPLETED,
                    "result_ref": probe.result_ref,
                    "completed_during_recovery": True,
                })
            elif probe.state == "in_progress":
                await task_store.update(task.task_id, {
                    "status": TaskStatus.IN_PROGRESS,
                    "orchestrator_instance": instance_id,
                })
            elif probe.state == "failed":
                await task_store.update(task.task_id, {
                    "status": TaskStatus.ORPHANED,
                    "failure_reason": probe.error,
                })
        except AgentUnreachable:
            # Agent is truly dead — mark orphaned for re-assignment
            await task_store.update(task.task_id, {
                "status": TaskStatus.ORPHANED,
                "orchestrator_instance": instance_id,
            })
    
    # Step 3: Re-assign only the genuinely orphaned tasks
    truly_orphaned = await task_store.query(status=TaskStatus.ORPHANED)
    for task in truly_orphaned:
        await re_assign_task(task, instance_id)
```

The handshake prevents duplication: completed-during-recovery tasks are absorbed, not re-queued. Only tasks where the agent is truly dead or the result is lost get re-assigned.

## Receipt

> Verified 2026-07-12 — Schema and heartbeat patterns derived from Exzil Calanza's "Single Point of Failure in 2026 AI Fleets" (production research, Jul 2026) and Zylos Research "AI Agent Self-Healing and Failure Recovery" (2026-05-06). Recovery handshake pattern from general distributed-systems recovery literature applied to agent contexts. Code is structurally representative; production deployment requires adaptation to your task store (Postgres, Redis, etc.) and agent transport.

## See also

- [S-986 · Coordination Breakdown](s986-the-coordination-breakdown-pattern-when-your-multi-agent-system-is-its-own-worst-enemy.md) — shared-state inconsistency; S-988 addresses the complementary failure mode (orchestrator death, not agent disagreement)
- [S-979 · Loop Detector](s979-the-loop-detector-stack-when-your-agent-runs-all-night-draining-your-budget.md) — node-level liveness; S-988 addresses fleet-level resilience and recovery
- [S-245 · Agent Stack Stratification](s245-the-agent-stack-is-stratifying.md) — orchestration is not a commodity; the resilience gap is evidence
- [S-248 · Agent Stack Is Stratifying](s248-the-agent-stack-is-stratifying.md) — the controller/sandbox distinction; agent lifecycle management is a distinct concern from execution isolation
