# S-2362 · The A2A Blocking State Stack — When Your Agentic Workflow Stops at the Worst Moment

Your multi-agent workflow is humming along. The triage agent dispatched to the researcher, the researcher handed to the validator, the validator hit a form field it couldn't resolve — and then everything stopped. No error. No crash. Just a task in `input-required` state, sitting in the protocol, blocking the entire pipeline. Your orchestrator either polls forever, reports success prematurely, or throws an unhandled exception. This is the A2A blocking state failure, and it is the silent killer of production agentic systems.

## Forces

- **A2A defines five task states — most implementations handle two.** The A2A v1.0 protocol (Linux Foundation, April 2026, 150+ supporters) specifies: `submitted → working → input-required/completed/failed/canceled`. Production SDKs (StrandsAgents, CrewAI, LangGraph adapters) ship full streaming support for `working` but ship `input-required` as unimplemented or ignored. A GitHub issue filed December 2025 and fixed only in June 2026 (strands-agents/sdk-python #1371) documents this exact gap across multiple frameworks — meaning the production ecosystem spent six months with a known protocol state that nobody handled.

- **The `input-required` state is not an error — it is the protocol working correctly.** Unlike `failed`, which signals something broke, `input-required` means the agent hit a genuine ambiguity, missing context, or external dependency that it cannot resolve autonomously. In human collaboration, this is normal. In an automated pipeline, it is an architectural sinkhole: the orchestrator has no defined response.

- **Silence is the wrong response.** The three common orchestrator behaviors on `input-required` are all wrong: polling forever (resource leak), reporting task completion (silent data loss), or crashing (unhandled exception). None reflects what actually happened — the agent paused at a decision boundary and needs resolution.

- **A2A encodes the blocking state with structured data.** The `TaskStatusUpdate` message carries a `data` field with the blocking reason, acceptable input types, and suggested queries. This is a rich signal — most orchestrators drop it entirely.

## The move

**Handle `input-required` as a first-class workflow state, not an exception.**

The A2A task lifecycle is a state machine. Your orchestrator must treat it as one.

### State machine contract

```python
from enum import Enum
from dataclasses import dataclass
from typing import Optional

class A2ATaskState(str, Enum):
    SUBMITTED = "submitted"
    WORKING = "working"
    INPUT_REQUIRED = "input-required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"

@dataclass
class TaskStatus:
    state: A2ATaskState
    agent_name: str
    blocking_reason: Optional[str] = None       # what blocked progress
    required_input_type: Optional[str] = None    # e.g. "user_confirmation", "document_id", "escalation_code"
    suggested_queries: Optional[list[str]] = None # protocol-suggested resolution prompts

# Valid transitions (A2A v1.0 state machine):
VALID_TRANSITIONS = {
    A2ATaskState.SUBMITTED: {A2ATaskState.WORKING, A2ATaskState.CANCELED, A2ATaskState.FAILED},
    A2ATaskState.WORKING: {A2ATaskState.INPUT_REQUIRED, A2ATaskState.COMPLETED, A2ATaskState.CANCELED, A2ATaskState.FAILED},
    A2ATaskState.INPUT_REQUIRED: {A2ATaskState.WORKING, A2ATaskState.CANCELED},  # ← must re-queue
    A2ATaskState.COMPLETED: {},   # terminal
    A2ATaskState.FAILED: {},      # terminal
    A2ATaskState.CANCELED: {},    # terminal
}
```

### The resolution protocol

For each `input-required` event, route to one of three handlers based on the `required_input_type`:

```python
async def handle_input_required(
    task_id: str,
    status: TaskStatus,
    context: WorkflowContext,
) -> None:
    """Route a blocking state to the correct resolution handler."""

    reason = status.blocking_reason or "unspecified"
    input_type = status.required_input_type

    match input_type:
        # Case 1: Human-in-the-loop required
        case "user_confirmation" | "human_approval":
            await queue_for_human_review(
                task_id=task_id,
                question=status.suggested_queries or [f"Agent blocked: {reason}"],
                escalation_priority=determine_priority(status, context),
            )

        # Case 2: External data dependency — resolve programmatically
        case "document_id" | "entity_reference" | "missing_context":
            resolution = await resolve_data_dependency(
                blocking_reason=reason,
                context=context,
            )
            await send_task_push_notification(
                task_id=task_id,
                message={
                    "role": "user",
                    "content": resolution,
                },
            )

        # Case 3: Capability gap — escalate to a specialist agent
        case "capability_required" | "escalation_code":
            specialist = await discover_specialist_agent(
                required_capability=extract_capability(status.suggested_queries),
            )
            await redirect_task(
                original_task_id=task_id,
                target_agent=specialist,
            )

        # Case 4: Unknown — surface for triage
        case _:
            await escalate_to_orchestrator(
                task_id=task_id,
                raw_status=status,
                reason=f"unhandled input_required type: {input_type}",
            )
```

### Streaming listener that never drops states

The most reliable pattern: a dedicated state machine listener that processes every `TaskStatusUpdate`, not just `working` streams:

```python
async def a2a_task_listener(
    task_id: str,
    response: ServerStreamingResponse,
    state_machine: dict[str, A2ATaskState],
) -> None:
    """Process every A2A state transition, including input-required."""
    async for event in response.events:
        if event.type == "status":
            update: TaskStatusUpdate = event.data
            new_state = A2ATaskState(update.state)

            if new_state not in VALID_TRANSITIONS.get(state_machine["current"], {}):
                log.warning(
                    f"Unexpected transition {task_id}: "
                    f"{state_machine['current']} -> {new_state}"
                )

            state_machine["current"] = new_state

            if new_state == A2ATaskState.INPUT_REQUIRED:
                status = TaskStatus(
                    state=new_state,
                    agent_name=update.agent_name,
                    blocking_reason=update.data.get("blocking_reason"),
                    required_input_type=update.data.get("required_input_type"),
                    suggested_queries=update.data.get("suggested_queries"),
                )
                await handle_input_required(task_id, status, context)

            elif new_state == A2ATaskState.COMPLETED:
                await deliver_artifact(task_id, update)

            elif new_state in {A2ATaskState.FAILED, A2ATaskState.CANCELED}:
                await handle_terminal_state(task_id, new_state, update)
```

### Key rules

- **Never assume completion = success.** A task that stops emitting `working` events without reaching `completed` is in `input-required` until proven otherwise.
- **Store the task state machine durably.** If your orchestrator process crashes while a task is in `input-required`, resume should pick up from the blocking state, not restart the task.
- **Use the `suggested_queries` field.** A2A encodes the resolution prompt the agent needs — surface it to the human reviewer or use it as the resolution prompt.
- **Set a timeout on `input-required`.** If the blocking state exceeds a configurable SLA without resolution, escalate to dead-letter handling (see S-1032).

## Receipt

> Verified 2026-08-09 — Research: A2A v1.0 specification (a2a-protocol.org, April 2026), A2A task lifecycle documentation (autolearningagents.com, July 2026), strands-agents/sdk-python #1371 GitHub issue (created 2025-12-19, fixed 2026-06-19 with PR #2245), Linux Foundation A2A announcement (HPCwire, April 9, 2026). The five-state model, the `input-required` data structure, and the SDK implementation gap are real and documented. Code patterns follow the A2A v1.0 protocol specification.

## See also

- [S-1423 · The A2A Protocol Stack](s1423-the-a2a-protocol-stack-when-your-agents-need-to-collaborate-on-tasks-they-didnt-plan.md) — foundational A2A framing (this entry covers the specific blocking state gap S-1423 doesn't)
- [S-1140 · The Protocol Sandwich Stack](s1140-the-protocol-sandwich-stack-when-mcp-alone-isnt-enough-and-a2a-alone-is-too-much.md) — MCP + A2A layer confusion as the root cause of incomplete implementations
- [S-1032 · The Dead Letter Stack](s1032-the-dead-letter-stack-when-your-agent-fails-silently-and-bills-you-loudly.md) — what to do with tasks that stay blocked past the SLA
- [S-1054 · The Agent Interrupt Stack](s1054-the-agent-interrupt-stack-when-your-agent-is-going-off-rails-and-you-cant-stop-it-cleanly.md) — HITL patterns for unblocking workflows
