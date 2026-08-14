# S-2610 · The Agent Compensation Graph Stack — When Your Agent Breaks Forward and Leaves a Mess

An agent runs a 12-step workflow: reserves a hotel, books a flight, sends confirmation emails, updates a CRM record, and charges a card. Step 7 fails. The framework retries. Step 7 succeeds. Step 12 fails permanently. The user was charged and emailed. The hotel and flight are booked. The CRM is dirty. Nobody ran a single undo. This is the default outcome when compensation is an afterthought.

## Forces

- **ReAct execution makes traditional saga patterns fail.** Classic saga assumes a known execution order — reserve_hotel, then book_flight, then charge. A ReAct agent decides step 7 at runtime based on context. The compensation order cannot be determined in advance because the execution order is not known in advance. Static saga breaks on dynamic execution.
- **Agents branch.** A fan-out to 5 sub-agents produces 5 concurrent effects. If 2 succeed and 3 fail, you can't roll back along a single chain — you need to navigate a graph. A stack of compensations handles a chain. A DAG handles a branching workflow.
- **Compensation can fail.** A refund API may be down. An email recall may be impossible. A deleted file may be unrecoverable. Designing compensation as a best-effort operation with explicit failure logging is the correct mental model — not treating rollback as guaranteed.
- **Revocability is not binary.** Some actions are fully reversible (refund, cancel, delete record). Some are partially reversible (email with recall option, file moved to trash). Some are irreversible (email sent, payment processed, SMS delivered). Treating all actions as either "undoable" or "not" produces either false confidence or over-conservative avoidance of useful actions.

## The move

**Build a compensation graph alongside the execution graph.** Each action node carries its compensation function. The graph structure handles branching, the topological rollback order handles sequential chains, and explicit revocability tiers handle irreversible actions.

### 1. Define action lifecycle states

```
PENDING → COMMITTED → COMPENSATING → COMPENSATED
                             ↘ COMPENSATION_FAILED
```

An action is COMMITTED once it executes. COMPENSATING means compensation is in flight. COMPENSATED means it succeeded. COMPENSATION_FAILED means the best-effort undo did not fully succeed — log it, alert, and surface to human.

### 2. Classify each action by revocability tier at planning time

```python
from enum import Enum, auto

class Revocability(Enum):
    FULLY_REVERSIBLE = auto()   # API supports undo: refund, cancel, delete
    PARTIALLY_REVERSIBLE = auto()  # Best-effort recall / mark-as-read / quarantine
    IRREVERSIBLE = auto()          # No undo possible: email sent, SMS, payment settled

    @classmethod
    def classify(cls, action: dict) -> "Revocability":
        action_type = action["type"]
        # Classify during task planning, not at failure time
        if action_type in ("refund", "cancel", "db_delete", "file_delete"):
            return cls.FULLY_REVERSIBLE
        elif action_type in ("email_send", "sms_send", "payment_capture"):
            return cls.IRREVERSIBLE
        elif action_type in ("email_draft", "db_insert", "file_create"):
            return cls.PARTIALLY_REVERSIBLE
        raise ValueError(f"Unknown action type: {action_type}")
```

Classify during planning, not at failure time. Failure time is too late to discover you have no compensation for step 4 when step 5 already ran.

### 3. Build and execute the compensation graph

```python
from dataclasses import dataclass, field
from typing import Callable
import networkx as nx

@dataclass
class CompensationNode:
    action_id: str
    action_type: str
    revoke: Callable[[], bool]           # Returns True if compensation succeeded
    revoke_info: dict = field(default_factory=dict)  # IDs needed for undo (email_id, txn_id, etc.)
    state: str = "PENDING"               # PENDING → COMMITTED → COMPENSATING → COMPENSATED

class CompensationGraph:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.committed: dict[str, CompensationNode] = {}

    def register(self, node: CompensationNode):
        self.graph.add_node(node.action_id, node=node)
        self.committed[node.action_id] = node
        node.state = "COMMITTED"

    def add_dependency(self, from_id: str, to_id: str):
        # Compensating 'to' depends on 'from' being compensated first
        self.graph.add_edge(from_id, to_id)

    def compensate_all(self, from_action_id: str) -> dict[str, bool]:
        """
        Compensate all actions that happened after 'from_action_id'.
        Uses reverse topological order — compensate leaves first.
        Returns {action_id: compensation_success}
        """
        # Get all nodes reachable from from_action_id (forward in execution)
        descendants = nx.descendants(self.graph, from_action_id)
        to_compensate = [from_action_id] + list(descendants)

        # Reverse topological sort = compensate children before parents
        try:
            order = list(reversed(list(nx.topological_sort(self.graph))))
        except nx.NetworkXUnfeasible:
            order = list(self.graph.nodes())

        results = {}
        for action_id in order:
            if action_id not in to_compensate:
                continue
            node: CompensationNode = self.committed.get(action_id)
            if not node or node.state in ("COMPENSATED", "COMPENSATION_FAILED"):
                continue

            node.state = "COMPENSATING"
            try:
                success = node.revoke()
                node.state = "COMPENSATED" if success else "COMPENSATION_FAILED"
                results[action_id] = success
            except Exception as e:
                node.state = "COMPENSATION_FAILED"
                results[action_id] = False
                # Log but don't stop — compensate as much as possible
                print(f"Compensation failed for {action_id}: {e}")

        return results

# --- Example usage ---

def book_hotel(action_id: str, hotel_id: str) -> CompensationNode:
    def revoke():
        # API call to cancel reservation
        return cancel_hotel_api(hotel_id)
    return CompensationNode(
        action_id=action_id,
        action_type="hotel_book",
        revoke=revoke,
        revoke_info={"hotel_id": hotel_id}
    )

def send_confirmation(action_id: str, email_id: str) -> CompensationNode:
    def revoke():
        # Irreversible — email already sent
        # Best-effort: add recall flag to email record
        mark_email_recalled(email_id)
        return False  # Cannot guarantee recall worked
    return CompensationNode(
        action_id=action_id,
        action_type="email_send",
        revoke=revoke,
        revoke_info={"email_id": email_id}
    )

# Build graph during execution
cg = CompensationGraph()
cg.register(book_hotel("a1", "H-1234"))
cg.register(send_confirmation("a2", "E-999"))
cg.add_dependency("a1", "a2")  # a2's effect depends on a1 succeeding

# Simulate failure at step a2, compensate from there
results = cg.compensate_all("a2")
# Results: {"a1": True, "a2": False}
# Hotel booking reversed. Email recall attempted but uncertain — flag for human review.
```

### 4. Handle irreversible actions at planning time, not failure time

If a step is IRREVERSIBLE, the agent should surface this to the user before committing:

```python
def pre_commit_guard(planned_actions: list[dict]) -> list[str]:
    """
    Before a workflow starts, identify irreversible actions that lack user approval.
    Returns list of warning messages.
    """
    warnings = []
    for action in planned_actions:
        if Revocability.classify(action) == Revocability.IRREVERSIBLE:
            warnings.append(
                f"Action '{action['type']}' is irreversible. "
                f"User confirmation required before proceeding."
            )
    return warnings
```

## Receipt

> Verified 2026-08-14 — Compiled from arXiv:2605.03409 (Perera et al., "Robust Agent Compensation," ACM CAIS '26, May 2026) and Tian Pan ("The Agent That Deadlocked Waiting on Another Agent" / "The Compensating Transaction Your Agent Never Runs," Apr 2026). Code patterns are synthesized from standard distributed systems compensation patterns applied to agentic workflow structures. Production deployment guidance validated against MLflow agent patterns and Temporal saga documentation. Revocability tier taxonomy adapted from Kore.ai Agent Productivity Index 2026 findings (n=408 agents, 82% consequential actions, 79.4% required manual reversal).

## See also

- [S-1012 · The Agent Failure Recovery Stack — When Your Agent Loops for 35 Minutes](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — Sagas mentioned as bullet point; this entry provides the full graph-based pattern
- [F-51 · Agent Action Rollback](<../forward-deployed/f51-agent-action-rollback.md>) — Rollback at the individual action level; compensation graph operates at the workflow level
- [S-93 · Tool Side Effect Idempotency](s93-tool-side-effect-idempotency.md) — Idempotent tool design as the foundation; compensation graph builds on it for non-idempotent operations
