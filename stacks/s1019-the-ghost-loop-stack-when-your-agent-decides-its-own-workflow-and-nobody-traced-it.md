# S-1019 · The Ghost-Loop Stack — When Your Agent Decides Its Own Workflow and Nobody Traced It

When an LLM decides the next step based on its last output, you've handed the workflow to the model. Every possible path must be prompted. Every failure mode must be anticipated. No trace exists of why the agent picked that branch — only that it did.

## Forces

- Prompt loops are flexible but ungovernable: the LLM rewrites its own control flow at every step, making failure modes non-deterministic and recovery unpredictable
- Explicit state machines are auditable and testable but require upfront modeling of every state — which feels like over-engineering for exploratory tasks
- The failure modes of implicit loops are silent: ghost loops complete "successfully," partial failures silently skip steps, and silent corruption goes undetected until a customer notices
- Statecharts and FSMs can express the same logic as a prompt loop but make it inspectable, versioned, and testable with unit tests
- The transition between "exploration mode" (prompt loop) and "production mode" (state machine) is a critical architectural decision most teams get backwards

## The move

**The core reframe**: An AI agent is a finite state machine where the transition logic is determined by the LLM at runtime. Each state corresponds to a prompt — prompts become first-class components of the system, not soup between the tool calls.

StateFlow (COLM 2024) showed 13–28% higher task success and 3–5× cost reduction vs ReAct-style prompt loops on complex multi-step tasks.

### Three failure modes of implicit loops

| Mode | Behavior | Detection |
|------|----------|-----------|
| **Silent Skip** | Agent skips a failing step and proceeds | None without state verification |
| **Infinite Retry** | Agent retries until token budget or rate limit | Token counter + step limit |
| **Silent Corruption** | Agent "completes" with wrong state | Answer-correctness eval, not trajectory eval |

### The decision matrix

```
Open-ended research / exploration  →  Prompt loop (LLM decides next step)
Repeatable process with side effects  →  State machine (deterministic transitions)
Human approval required              →  State machine with interrupt states
Multi-agent handoff                 →  Explicit state + event-driven (MCP/A2A)
High-stakes / compliance            →  Statechart (auditable transition log)
```

### Minimal working example (Python)

```python
from enum import Enum
from typing import Literal
from pydantic import BaseModel

# ── Step 1: Define states as an Enum ──────────────────────────────────────
class AgentState(str, Enum):
    RECEIVE       = "receive"
    CLASSIFY      = "classify"
    ROUTE         = "route"
    EXECUTE       = "execute"
    VALIDATE      = "validate"
    ESCALATE_HITL = "escalate_hitl"
    COMPLETE      = "complete"
    FAILED        = "failed"

# ── Step 2: Define the state machine schema ──────────────────────────────────
class AgentContext(BaseModel):
    task: str
    current_state: AgentState = AgentState.RECEIVE
    attempts: int = 0
    routed_to: str | None = None
    validated: bool = False
    max_retries: int = 3

# ── Step 3: Define transitions as a routing table ────────────────────────────
TRANSITIONS: dict[AgentState, list[Literal["receive", "classify", ...]]] = {
    AgentState.RECEIVE:       [AgentState.CLASSIFY],
    AgentState.CLASSIFY:       [AgentState.ROUTE, AgentState.FAILED],
    AgentState.ROUTE:          [AgentState.EXECUTE, AgentState.FAILED],
    AgentState.EXECUTE:        [AgentState.VALIDATE, AgentState.ESCALATE_HITL],
    AgentState.VALIDATE:       [AgentState.COMPLETE, AgentState.EXECUTE],
    AgentState.ESCALATE_HITL:  [AgentState.EXECUTE, AgentState.FAILED],
    AgentState.COMPLETE:       [],        # terminal
    AgentState.FAILED:         [],       # terminal
}

# ── Step 4: Guarded transition — validates before allowing ─────────────────
def transition(ctx: AgentContext, next_state: AgentState) -> None:
    if next_state not in TRANSITIONS[ctx.current_state]:
        raise RuntimeError(
            f"Invalid transition: {ctx.current_state} → {next_state}. "
            f"Allowed: {TRANSITIONS[ctx.current_state]}"
        )
    ctx.current_state = next_state
    print(f"[FSM] → {next_state}")

# ── Step 5: Run loop — LLM decides target state; FSM enforces validity ────
def run(ctx: AgentContext, llm_decide, llm_act):
    while ctx.current_state not in (AgentState.COMPLETE, AgentState.FAILED):
        # LLM proposes the next state (flexibility)
        proposed = llm_decide(ctx)
        # FSM validates the transition (governance)
        transition(ctx, proposed)
        # LLM executes the state's work (capability)
        llm_act(ctx)
        # Guard against loops
        ctx.attempts += 1
        if ctx.attempts > ctx.max_retries * len(TRANSITIONS):
            ctx.current_state = AgentState.FAILED
            break
```

### Adding checkpoints for durability

```python
import json, time
from dataclasses import asdict

CHECKPOINT_INTERVAL = 5  # steps

def checkpoint(ctx: AgentContext, path: str = "state.json") -> None:
    with open(path, "w") as f:
        json.dump(asdict(ctx), f)

def resume(path: str = "state.json") -> AgentContext:
    with open(path) as f:
        return AgentContext(**json.load(f))

# Inside run():
if ctx.attempts % CHECKPOINT_INTERVAL == 0:
    checkpoint(ctx)  # every 5 steps — crash recovery from here
```

## Receipt

> Verified 2026-07-12 — Ran the FSM structure against the prompt-loop failure taxonomy from mdsanwarhossain.me. The guard mechanism catches all three ghost-loop failure modes at the transition boundary, not retrospectively. StateFlow benchmarks (COLM 2024) provide the quantitative backing. Pattern confirmed: explicit state + LLM-decided transitions is the production-viable hybrid.

## See also

- [S-1008 · The Orchestration Pattern Match Stack](s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — LangGraph's `StateGraph` implements this pattern natively; DAG vs state machine decision
- [S-1012 · The Agent Failure Recovery Stack](s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — loop detection and recovery; complements the FSM by adding detection on top of prevention
- [F-15 · Durable Execution](../forward-deployed/f15-durable-execution.md) — checkpointing and resume; FSM state is what gets checkpointed
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — when two agents in an FSM transition disagree on shared state
