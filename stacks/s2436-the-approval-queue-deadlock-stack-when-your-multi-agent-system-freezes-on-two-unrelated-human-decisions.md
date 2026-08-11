# S-2436 · The Approval Queue Deadlock Stack

When two agents each need the other's output — but both outputs require human approval — your multi-agent system freezes indefinitely on two decisions that no single person can make alone. The agents are healthy. The approvals are valid. The system is deadlocked.

## Forces

- **HITL gates feel safe and controllable.** Requiring human approval before sensitive actions is correct risk management. But each approval gate is a blocking wait, and blocking waits in a distributed system are the raw material for deadlock.
- **Agents are opaque to each other.** Agent A doesn't know that Agent B is waiting on it. Agent B doesn't know it's part of a circular dependency. The deadlock is invisible at the agent level.
- **Approval requests look individually reasonable.** "This agent needs external context to proceed" and "this agent needs the result to validate before signing off" are both valid reasons for blocking. The circular dependency only emerges at the system level.
- **Humans don't know they're paired.** Even if the dependency were visible, the two approvers don't know they're in a deadlock — they just see unrelated tasks sitting in their queue.

## The move

**Detect at the architecture level, not the agent level.** The standard agent toolkit — circuit breakers, loop detectors, retry budgets — won't catch this. You need distributed systems deadlock detection applied to your agent approval graph.

**Pattern 1: Acyclic handoff graph.** Structure agent-to-agent dependencies so the graph is provably acyclic. Every handoff goes one direction. If bidirectional communication is needed, it must be async and non-blocking (fire-and-forget with a callback, not a synchronous await).

**Pattern 2: Approval escrow with partial fulfillment.** When an agent blocks on another agent's pending approval, provide the approver with the *identity of the waiting downstream agent* and the *specific dependency*. Don't just show "pending" — show "this approval unblocks Agent X, which is currently blocked waiting on this approval." This makes the circular dependency visible to humans.

**Pattern 3: Timeout escalation with partial state release.** If an approval has been pending for longer than T minutes and the requesting agent has dependencies on other pending approvals, trigger escalation. At escalation, the system provides the approver with the full dependency chain and an option to either approve with caveats, delegate the decision, or mark the task for manual resolution. The key: partially-complete state from the blocked agent is preserved and surfaced, so the human approver isn't starting blind.

**Pattern 4: Conditional approval ("proceed if still needed").** Some approval gates can be marked as *conditional* — the approver pre-authorizes the action with a condition ("approve this IF Agent B confirms the data is still needed within 30 minutes"). The system checks the condition before executing, preventing blanket auto-approval.

**Pattern 5: Deadlock cycle detector.** Before queuing any approval request, the system traverses the pending-approval dependency graph. If a cycle is detected, it surfaces immediately rather than queuing silently. Surface it with: "This approval would create a deadlock with [Agent X's pending approval]. Options: [force-through], [split into two independent tasks], [escalate to manager]."

```python
# Minimal deadlock detector for approval graph
from collections import defaultdict

def detect_approval_deadlock(pending_approvals: list[dict]) -> list[list[str]]:
    """
    Returns any cycles in the pending-approval dependency graph.
    Each approval dict: {agent_id, blocking_on: list[str]}
    """
    graph = defaultdict(list)
    for approval in pending_approvals:
        for dep in approval.get("blocking_on", []):
            graph[approval["agent_id"]].append(dep)

    cycles = []
    visited = set()
    rec_stack = set()

    def dfs(node, path):
        visited.add(node)
        rec_stack.add(node)
        path.append(node)
        for neighbor in graph[node]:
            if neighbor not in visited:
                result = dfs(neighbor, path[:])
                if result:
                    cycles.append(result)
            elif neighbor in rec_stack:
                cycle_start = path.index(neighbor)
                cycles.append(path[cycle_start:] + [neighbor])
        rec_stack.remove(node)
        return None

    for node in graph:
        if node not in visited:
            dfs(node, [])
    return cycles


def queue_approval_with_deadlock_check(approval_request: dict, pending: list[dict]) -> dict:
    """
    Before queuing an approval, check for cycles.
    If a cycle is detected, return {status: 'DEADLOCK', cycle: [...], options: [...]}
    instead of silently queuing.
    """
    test_pending = pending + [approval_request]
    cycles = detect_approval_deadlock(test_pending)
    if cycles:
        return {
            "status": "DEADLOCK",
            "detected_cycle": cycles[0],
            "options": [
                "SPLIT: Break the dependent task into two independent sub-tasks",
                "FORCE: Override with manager approval (requires explicit authorization)",
                "ESCALATE: Route to designated deadlock resolver",
                "CANCEL": Abort the requesting workflow branch",
            ],
        }
    return {"status": "QUEUED", "queue_position": len(pending)}
```

```python
# Example: surfacing deadlock context to approvers
def surface_approval_context(approval_id: str, pending_approvals: list[dict]) -> dict:
    """
    When showing an approval to a human, include:
    - What this approval unlocks
    - Whether any downstream agents are waiting
    - Whether a deadlock is forming
    """
    approval = next((a for a in pending_approvals if a["id"] == approval_id), None)
    if not approval:
        return {}

    cycles = detect_approval_deadlock(pending_approvals)
    downstream_agents = [
        a["agent_id"] for a in pending_approvals
        if approval["agent_id"] in a.get("blocking_on", [])
    ]

    return {
        "approval_id": approval_id,
        "unblocks": downstream_agents,
        "deadlock_risk": bool(cycles),
        "dependency_chain": approval.get("blocking_on", []),
        "if_approved_will_enable": [
            {"agent": a["agent_id"], "action": a.get("action", "unknown")}
            for a in downstream_agents
        ],
    }
```

## Receipt

> Verified 2026-08-10 — Tian Pan (June 1, 2026, tianpan.co): "The Multi-Agent Deadlock That Hangs on Two Calendars." Documents the exact scenario: two agents cross a HITL boundary, land in different approval queues watched by different humans, and neither approver can resolve the deadlock because both need the other's agent to finish first. Ardua Labs (March 2026) catalogs "deadlock" as a first-class failure mode in multi-agent coordination. GitHub issue #6252 (openclaw/openclaw, Feb 2026): context truncation creates a related but distinct deadlock where the agent blocks waiting for context that was lost.

## See also

- [S-1034 · The Role Fence Stack](s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — deadlock from direct inter-agent calling; addresses the structural fix
- [S-2430 · The Inter-Agent Handoff Stack](s2430-the-inter-agent-handoff-stack-when-your-agent-hands-off-and-nobody-answers.md) — handoff contracts and acknowledgment; the non-blocking complement
- [S-995 · The Agent Failure Recovery Stack](s995-the-agent-failure-recovery-stack-when-your-agent-loops-hangs-or-hammers-itself-against-a-dead-end.md) — general failure recovery taxonomy; loop/hang detection
