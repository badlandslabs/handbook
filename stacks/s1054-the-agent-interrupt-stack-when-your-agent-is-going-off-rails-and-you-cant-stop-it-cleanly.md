# S-1054 · The Agent Interrupt Stack — When Your Agent Is Going Off Rails and You Can't Stop It Cleanly

Your agent is 47 steps into refactoring your payment service. It just deleted a migration file and is about to commit. You hit Stop — but now the workspace is in an unknown state, half the changes are staged, and there's no way to resume where it left off. You didn't want to kill it; you wanted to pause it. But "pause" wasn't in the architecture. This is the agent interrupt problem — and it is one of the most operationally significant gaps in production agentic systems today.

## Forces

- **Hitting Stop destroys state.** A hard termination loses context, intermediate results, uncommitted changes, and any recovery path. Agents don't have a clean suspend-to-disk concept like an OS process. When you kill the process, you lose everything in memory.
- **Letting it run risks irreversible damage.** A payment-refactoring agent that commits bad code, sends emails, or deletes records cannot undo those actions with a retry. The blast radius of "continue" grows with every step.
- **F-193 (Escalation Gating)** handles approvals before irreversible actions — but not mid-run corrections while the agent is still in a valid state. Approval gates are decision points; interrupt handles are correction points.
- **LangGraph's `interrupt_before`** is the canonical implementation primitive, but most agents aren't built on LangGraph, and even those that are rarely wire interrupt handling into every tool call.
- **Human-in-the-loop is legally mandated for high-risk decisions** under the EU AI Act (2026) for agents in credit, employment, and essential services — making this a compliance requirement, not a UX preference.

## The Move

The interrupt stack has four components: **interrupt gates**, **state externalization**, **approval queues**, and **clean resumption**. These are not four separate systems — they are one pipeline.

### 1. Instrument Interrupt Gates at Every High-Risk Tool

Not every tool call needs an interrupt. Gate the ones that are irreversible, high-value, or ambiguous:

```python
# interrupt_gates.py
HIGH_RISK_TOOLS = {
    "git_commit", "git_push", "send_email",
    "delete_file", "db_write", "payment_execute",
    "user_delete", "deploy_to_production",
}

class InterruptGate:
    def __init__(self, checkpoint_store, approval_queue):
        self.checkpoint = checkpoint_store
        self.queue = approval_queue

    def should_interrupt(self, tool_name: str, params: dict) -> bool:
        if tool_name not in HIGH_RISK_TOOLS:
            return False
        # Threshold-based: interrupt above dollar/value threshold
        value = params.get("value") or params.get("amount", 0)
        if value and float(value) > self.approval_threshold:
            return True
        # Irreversibility-based: always interrupt destructive tools
        if tool_name in {"delete_file", "user_delete"}:
            return True
        return False

    def enter_approval(self, agent_id: str, tool_name: str, params: dict, state_snapshot: dict):
        self.checkpoint.save(agent_id, state_snapshot, reason=f"awaiting_approval:{tool_name}")
        self.queue.enqueue({
            "agent_id": agent_id,
            "tool": tool_name,
            "params": params,
            "checkpoint_id": self.checkpoint.id,
            "queued_at": datetime.utcnow().isoformat(),
        })
        return self.checkpoint.id  # returned to caller as interrupt signal
```

### 2. Externalize State at Every Interrupt Point

LangGraph makes this native with `StateSnapshot` serialization. Without it, capture what the agent needs to resume:

```python
# state_externalizer.py
import json
from datetime import datetime

def snapshot_agent_state(agent_state: dict) -> str:
    """Serialize the minimum state needed to resume."""
    return json.dumps({
        "memory_contents": agent_state.get("memory", []),
        "conversation_history": agent_state.get("history", []),
        "intermediate_results": agent_state.get("results", {}),
        "progress_markers": agent_state.get("markers", {}),
        "checkpoint_index": agent_state.get("step", 0),
        "agent_id": agent_state.get("agent_id"),
        "snapshot_at": datetime.utcnow().isoformat(),
    }, default=str)

def resume_from_snapshot(snapshot: str, agent) -> None:
    state = json.loads(snapshot)
    agent.memory = state["memory_contents"]
    agent.history = state["conversation_history"]
    agent.results = state["intermediate_results"]
    agent.markers = state["progress_markers"]
    # Skip completed steps
    agent.current_step = state["checkpoint_index"]
```

### 3. Build an Approval Queue, Not a Blocking Modal

Don't make the agent wait synchronously for a human. An approval queue decouples the agent from the human decision window:

```python
# approval_queue.py
from queue import Queue
from enum import Enum

class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

class ApprovalQueue:
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl = ttl_seconds
        self._queue: Queue = Queue()

    def enqueue(self, item: dict) -> str:
        self._queue.put(item)
        return item["checkpoint_id"]

    def get_pending(self) -> list[dict]:
        items = []
        while not self._queue.empty():
            item = self._queue.get()
            if self._is_expired(item):
                item["status"] = ApprovalStatus.EXPIRED
            items.append(item)
        return items

    def approve(self, checkpoint_id: str, reviewer_id: str) -> None:
        # In production: POST to the agent's resume endpoint
        resume_signal(checkpoint_id, action="approve", reviewer=reviewer_id)

    def reject(self, checkpoint_id: str, reviewer_id: str, reason: str) -> None:
        resume_signal(checkpoint_id, action="reject", reviewer=reviewer_id, reason=reason)
```

### 4. Wire Resumption with Full Context Restoration

The agent's main loop checks for pending approvals on every iteration:

```python
# agent_main.py
class AgentLoop:
    def __init__(self, agent, gate, queue):
        self.agent = agent
        self.gate = gate
        self.queue = queue

    def step(self):
        tool_name, params = self.agent.decide_next_action()

        if self.gate.should_interrupt(tool_name, params):
            snapshot = snapshot_agent_state(self.agent.state)
            checkpoint_id = self.gate.enter_approval(
                agent_id=self.agent.id,
                tool_name=tool_name,
                params=params,
                state_snapshot=snapshot,
            )
            self.agent.wait_forApproval(checkpoint_id)
            # wait_forApproval blocks — use a lightweight polling loop or
            # event-based callback that restores state when signal arrives

        elif self.agent.has_pending_approval():
            # Resume from checkpoint
            checkpoint = self.gate.checkpoint.load(
                self.agent.pending_approval_id
            )
            resume_from_snapshot(checkpoint.snapshot, self.agent)
            self.agent.clear_pending_approval()
            action = self.agent.pending_action  # restored from checkpoint
            self.agent.execute(action)
        else:
            self.agent.execute(self.agent.decide_next_action())

    def wait_forApproval(self, checkpoint_id: str, poll_interval: int = 5):
        while True:
            approval = self.queue.check_status(checkpoint_id)
            if approval["status"] == "approved":
                self.pending_action = approval["approved_params"]
                self.pending_approval_id = checkpoint_id
                return
            elif approval["status"] == "rejected":
                self.pending_action = None
                self.pending_approval_id = checkpoint_id
                return
            time.sleep(poll_interval)  # non-blocking poll
```

### The EU AI Act Compliance Angle

For agents in regulated sectors, the EU AI Act (effective 2026) requires human oversight for high-risk automated decisions. The interrupt stack is the engineering implementation of that mandate. Document your interrupt gates in the system's technical documentation: which tools are gated, what thresholds trigger approval, and what the resumption path looks like. A regulator asking "how does a human override this agent?" should get an architecture diagram, not a shrug.

## Receipt

> Verified 2026-07-13 — Channel's interrupt/approval architecture (channel.tel, May 2026) confirms the 4-category model (irreversible, high-value, ambiguous intent, new context). Antigravity Lab's checkpoint/resume workflow (antigravitylab.net, Apr 2026) validates the state externalization pattern. Prefactor.tech (May 2026) documents real-world runaway costs ($1,200/incident from 47 retries, $336k/month from unbounded iterations) that interrupt gates would have prevented.

## See also

- [F-193 · Agent Escalation Gating](forward-deployed/f193-agent-escalation-gating.md) — approval before irreversible actions; complementary to interrupt
- [S-1003 · The Agent Failure Recovery Stack](stacks/s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — checkpoint/resume for crash recovery vs. checkpoint/resume for human review
- [S-355 · Bounded Autonomy](stacks/s355-the-agent-autonomy-levels-stack-when-your-agent-goes-from-helpmate-to-autonomous-weapon.md) — the autonomy model that makes interrupt gates a tier in a larger spectrum
