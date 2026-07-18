# S-1288 · The Saga Compensation Stack — When Your Multi-Agent Workflow Partially Succeeds and Leaves the Database Wrong

Your agent pipeline books a hotel, charges the card, and sends the confirmation email. The email service goes down. The user's card is charged but no confirmation arrives. They contact support. This is not an agent failure — each step succeeded individually. This is a *system failure*: no compensation path exists when a multi-step workflow partially completes.

The saga pattern solves this. Every side-effecting step in an agentic workflow declares its compensation up front — the action that undoes it. When a downstream step fails fatally, the orchestrator replays those compensations in reverse order (LIFO). Agents don't roll back. They forward-roll an undo.

## Forces

- **Agents are non-transactional by default.** A traditional database transaction rolls back atomically. An agent workflow spans API calls, database writes, email sends, and file operations — none of which participate in a shared transaction. A failure at step 4 of 6 leaves steps 1–3 in an inconsistent state with no automatic recovery.
- **LLM inference failures don't roll back.** A failed LLM call mid-workflow may have already triggered downstream tool invocations. The LLM has no concept of ACID; it can't "undo" a tool call it made three turns ago.
- **LangGraph, CrewAI, and AutoGen provide no saga support.** All three handle retry-on-error for individual nodes. None handle cross-node compensation when a later node fails and earlier nodes must be rolled back.
- **The blast radius compounds with fan-out.** When one orchestrator fans out to 10 parallel sub-agents and 7 succeed, the compensation debt is 7 separate undo-actions — each of which may itself fail.
- **EU AI Act Article 14 mandates human oversight for high-risk automated decisions.** If your agent workflow makes a partially-executed irreversible decision, you need both a compensation path and an audit trail showing what happened and what was done.

## The Move

**Step 1: Declare compensation per step, not per agent.**
Every step in a multi-step agentic workflow has two actions: the forward action and its compensation. Write both into the workflow definition before execution begins.

**Step 2: Push compensations onto a durable stack.**
On success of each step, push the compensation closure onto a per-workflow compensation stack (Redis list, Temporal activity, or a simple array in a checkpoint). This stack survives agent restarts.

**Step 3: On fatal failure, pop and dispatch in LIFO order.**
When a step returns `FAILED_FATAL` (not a retryable error), trigger the saga manager. It pops each compensation from the stack and dispatches them as compensating actions, in reverse order of execution. Each compensation is itself a tool call or agent task — it can succeed, fail, or time out.

**Step 4: Handle compensation failure.**
A compensation that fails is not unrecoverable — it goes onto its own retry queue with backoff. Set a compensation timeout (e.g., 3 retries, 5-minute cap). Log compensation debt for human review if the saga doesn't close within the timeout.

**Step 5: Close the saga on full compensation or human escalation.**
A saga ends in one of three states: `COMPLETED` (all forward steps done), `COMPENSATED` (all compensations applied), or `ESCALATED` (compensation incomplete, human review required).

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Any
import redis, json

class SagaState(Enum):
    RUNNING = "running"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    COMPLETED = "completed"
    ESCALATED = "escalated"

@dataclass
class SagaStep:
    name: str
    forward: Callable[[], Any]       # Execute step N
    compensate: Callable[[Any], None]  # Undo step N (receives forward result)
    result: Any = None
    compensated: bool = False

class SagaManager:
    """LIFO compensation stack for multi-agent workflows.
    
    Each step registers a forward action and its compensation.
    On fatal failure, compensations run in reverse order.
    """
    def __init__(self, workflow_id: str, redis_client: redis.Redis):
        self.workflow_id = workflow_id
        self.r = redis_client
        self.steps: list[SagaStep] = []

    def add_step(self, name: str,
                 forward: Callable[[], Any],
                 compensate: Callable[[Any], None]) -> SagaStep:
        step = SagaStep(name=name, forward=forward, compensate=compensate)
        self.steps.append(step)
        return step

    def execute(self) -> SagaState:
        """Run all steps. On fatal failure, compensate in LIFO order."""
        for step in self.steps:
            try:
                step.result = step.forward()
                # Persist step result to durable store (survives restart)
                self._checkpoint(step)
            except FatalError as e:
                step.result = e
                return self._compensate()
        return SagaState.COMPLETED

    def _compensate(self) -> SagaState:
        self._update_status(SagaState.COMPENSATING)
        failed_step = next(
            (s for s in reversed(self.steps) if s.result is not None and not isinstance(s.result, FatalError)),
            None
        )
        # Only compensate steps that actually ran (up to and including failed step)
        steps_to_compensate = []
        for s in reversed(self.steps):
            if s.result is not None and not isinstance(s.result, FatalError):
                steps_to_compensate.append(s)
            if s is failed_step:
                break

        for step in steps_to_compensate:
            for attempt in range(3):
                try:
                    step.compensate(step.result)
                    step.compensated = True
                    self._checkpoint(step)
                    break
                except Exception as e:
                    if attempt == 2:
                        # Log compensation debt, escalate
                        self._log_debt(step, e)
                        self._update_status(SagaState.ESCALATED)
                        return SagaState.ESCALATED

        self._update_status(SagaState.COMPENSATED)
        return SagaState.COMPENSATED

    def _checkpoint(self, step: SagaStep):
        key = f"saga:{self.workflow_id}:steps"
        self.r.lpush(key, json.dumps({
            "name": step.name,
            "result": str(step.result),
            "compensated": step.compensated
        }))

    def _update_status(self, state: SagaState):
        self.r.set(f"saga:{self.workflow_id}:status", state.value)

    def _log_debt(self, step: SagaStep, error: Exception):
        self.r.lpush(f"saga:{self.workflow_id}:debt", json.dumps({
            "step": step.name,
            "error": str(error),
            "escalated_at": "now"
        }))


class FatalError(Exception):
    """A non-retryable error that triggers saga compensation."""
    pass


# --- Example: Agentic hotel booking saga ---

def book_hotel(guest_id: str) -> str:
    # Returns reservation_id
    return f"res_{guest_id}"

def charge_card(reservation_id: str) -> str:
    # Returns charge_id
    return f"chg_{reservation_id}"

def send_confirmation_email(reservation_id: str) -> None:
    # Returns None on success, raises FatalError if email service is down
    raise FatalError("SMTP connection refused")

def cancel_reservation(reservation_id: str) -> None:
    print(f"Cancelling reservation {reservation_id}")

def refund_charge(charge_id: str) -> None:
    print(f"Refunding charge {charge_id}")


# Agentic workflow using the saga
def book_hotel_saga(workflow_id: str, guest_id: str) -> SagaState:
    r = redis.Redis(host='localhost', db=0)
    saga = SagaManager(workflow_id, r)

    saga.add_step(
        name="reserve",
        forward=lambda: book_hotel(guest_id),
        compensate=lambda res_id: cancel_reservation(res_id)
    )
    saga.add_step(
        name="charge",
        forward=lambda: charge_card(saga.steps[-1].result),
        compensate=lambda chg_id: refund_charge(chg_id)
    )
    saga.add_step(
        name="email",
        forward=lambda: send_confirmation_email(saga.steps[0].result),
        compensate=lambda _: None  # Email has no compensation — log for manual outreach
    )

    return saga.execute()
    # Outcome:
    #   - COMPLETED: all 3 steps succeeded
    #   - COMPENSATING → COMPENSATED: email failed, charges refunded, reservation cancelled
    #   - ESCALATED: compensation itself failed, human reviews compensation debt
```

## Receipt
> Receipt pending — 2026-07-18
> Requires running against a real Redis-backed saga with a hotel booking workflow and simulated SMTP failure.

## See also

- [S-783](s783-agents-fail-gracefully-when-you-design-the-recovery-loop-first.md) — Recovery loop design first
- [S-1003](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — Failure recovery taxonomy for agents
- [S-1247](s1247-the-durable-execution-stack-when-langgraph-meets-temporal-and-your-agent-stops-dying-halfway-through.md) — Durable execution with Temporal + LangGraph
- [S-785](s785-sub-agent-result-accountability-in-fan-out-pipelines.md) — Fan-out pipeline result accountability
- [S-1047](s1047-the-agentic-dead-letter-queue-when-your-agent-fails-mid-task-and-the-task-just-disappears.md) — Dead letter queue for stuck tasks
