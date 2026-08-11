# S-2434 · The Bounded Agent Stack — When Your LLM Agent Can Do Anything But Must Stay in Lane

Your agent is reliable in the demo and unreliable in production. It handles the happy path perfectly — then surprises you on every edge case. It loops when it hits an unexpected input, makes decisions outside its scope when the situation gets complex, and has no recovery strategy when a tool fails. You've tried better prompts. You've tried more tools. What you haven't tried is making the state machine explicit and putting the LLM inside it.

The bounded agent pattern applies deterministic finite state machine logic to LLM agent execution: the FSM controls *what transitions are legal*, the LLM controls *which legal transition to take*. The agent is creative within known states. It cannot escape.

## Forces

- **LLM agents are reliable at known tasks and catastrophically unreliable at unknown ones.** The same model that writes perfect code will confidently book a flight to the wrong city when the task gets unusual. The failure is not the model — it is the absence of a boundary.
- **Unbounded autonomy and production readiness are inversely correlated.** Anthropic's production deployments consistently recommend: start with scripted workflows, add LLM autonomy only where the decision space genuinely requires it. Teams that start with full autonomy and try to constrain it afterward are fighting the architecture.
- **Every production agent failure is a state the FSM didn't anticipate.** Infinite loops, wrong tool selection, hallucinated credentials, out-of-scope actions — each is a transition to an undefined or unauthorized state. Making the state machine explicit makes these failures impossible by construction.
- **Adding constraints to an LLM agent makes it *more* capable, not less.** A bounded agent wastes zero tokens on decisions outside its scope. It recovers faster because failure modes are named. It is auditable because transitions are logged.

## The move

**Layer 1 — Define the state graph explicitly.**

Every agent task maps to a finite set of states. For a document review agent:

```
DRAFT → ANALYZING → DRAFTING_REVISIONS → HUMAN_REVIEW → APPROVED → PUBLISHED
                ↓           ↓                    ↓
            ERROR (retry → ANALYZING)  ERROR (retry → DRAFTING_REVISIONS)
```

Each state has:
- **Entry action**: what the LLM does on entry (e.g., `analyze(document)`)
- **Exit guard**: what conditions permit leaving (e.g., `has(redlines) ∧ cost < budget`)
- **Allowed transitions**: which states can follow this one
- **Allowed tools**: which tools are active in this state

The LLM never "decides what to do next" in the abstract. It evaluates the current state, considers which *legal* transition to take, and executes. The state machine filters the action space; the LLM optimizes within it.

**Layer 2 — Put the FSM in the critical path, not the comment.**

The FSM is not documentation. It is the orchestration engine.

```python
from langgraph.graph import StateGraph
from langgraph.types import Command
from enum import Enum

class DocReviewState(str, Enum):
    DRAFT = "draft"
    ANALYZING = "analyzing"
    DRAFTING_REVISIONS = "drafting_revisions"
    HUMAN_REVIEW = "human_review"
    APPROVED = "approved"

def analyzing_node(state: DocReviewState) -> Command[DocReviewState]:
    """LLM analyzes document within bounded context."""
    issues = llm_analyze(state.document, state.context_window)
    
    if not issues:
        return Command(goto=DocReviewState.HUMAN_REVIEW)
    
    if len(issues) > state.max_issues_per_pass:
        # FSM enforces budget; LLM cannot exceed it
        issues = issues[:state.max_issues_per_pass]
    
    return Command(
        goto=DocReviewState.DRAFTING_REVISIONS,
        update={"issues": issues, "revision_count": state.revision_count + 1}
    )

def drafting_revisions_node(state: DocReviewState) -> Command[DocReviewState]:
    """LLM drafts revisions. FSM enforces revision budget."""
    if state.revision_count >= state.max_revisions:
        # FSM hard-stop: cannot loop infinitely
        return Command(goto=DocReviewState.HUMAN_REVIEW)
    
    result = llm_revise(state.document, state.issues)
    return Command(goto=DocReviewState.ANALYZING, update={"document": result})

def human_review_node(state: DocReviewState) -> Command[DocReviewState]:
    """Human gate. FSM waits here until explicit approval."""
    if not state.human_approved:
        return Command(goto=DocReviewState.HUMAN_REVIEW)  # wait
    return Command(goto=DocReviewState.APPROVED)

# Build graph — FSM IS the graph
graph = StateGraph(DocReviewState)
graph.add_node(DocReviewState.ANALYZING, analyzing_node)
graph.add_node(DocReviewState.DRAFTING_REVISIONS, drafting_revisions_node)
graph.add_node(DocReviewState.HUMAN_REVIEW, human_review_node)
graph.set_entry_point(DocReviewState.ANALYZING)
graph.set_finish_point(DocReviewState.APPROVED)

app = graph.compile()
```

**Layer 3 — Define tool availability per state (not globally).**

An agent should not be able to call `delete_database` in the `ANALYZING` state. Scope tools to states:

```python
TOOL_SCOPE = {
    DocReviewState.DRAFT: [read_document, list_references],
    DocReviewState.ANALYZING: [read_document, search_internal_kb, extract_entities],
    DocReviewState.DRAFTING_REVISIONS: [read_document, write_document, run_linter],
    DocReviewState.HUMAN_REVIEW: [read_document, submit_for_review, request_clarification],
    DocReviewState.APPROVED: [publish_document, notify_stakeholders],
}

def analyzing_node(state: DocReviewState) -> Command[DocReviewState]:
    # Only scoped tools are passed to the LLM
    scoped_llm = LLM(tools=TOOL_SCOPE[DocReviewState.ANALYZING])
    return scoped_llm.analyze(state.document)
```

**Layer 4 — Add structured error states with bounded recovery.**

Define every error state explicitly, with retry budgets and escalation paths:

```python
ERROR_STATES = {
    "TOOL_UNAVAILABLE": (DocReviewState.ANALYZING, max_retries=2),
    "CONTEXT_OVERFLOW": (DocReviewState.ANALYZING, compress_before_retry=True),
    "REVISION_BUDGET_EXCEEDED": (DocReviewState.HUMAN_REVIEW, escalate=True),
    "HUMAN_TIMEOUT": (DocReviewState.HUMAN_REVIEW, max_wait_hours=48),
}

def error_handler(error: AgentError) -> Command[DocReviewState]:
    spec = ERROR_STATES.get(error.type, (DocReviewState.HUMAN_REVIEW,))
    target_state, max_retries = spec[0], spec[1]
    
    if error.retry_count >= max_retries:
        return Command(goto=target_state, update={"escalated": True})
    
    return Command(goto=target_state, update={"retry_count": error.retry_count + 1})
```

**Layer 5 — Log every transition for audit.**

The FSM makes every execution trace a state machine trace:

```python
def transition_logger(from_state: DocReviewState, to_state: DocReviewState, 
                      reason: str, llm_input: str, llm_output: str):
    """Immutable audit log of every state transition."""
    span.set_attribute("agent.state.from", from_state.value)
    span.set_attribute("agent.state.to", to_state.value)
    span.set_attribute("agent.transition.reason", reason)
    span.add_event("state_transition", {
        "transition_id": str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(),
        "from": from_state.value,
        "to": to_state.value,
        "reason": reason,
        "llm_tokens_in": token_count(llm_input),
        "llm_tokens_out": token_count(llm_output),
    })
```

## Receipt

> Verified 2026-08-10 — Pattern synthesized from: Anthropic's agent production guidance (deterministic workflows → LLM autonomy by exception); Statewright project (HN #1, 48108778 — statecharts for AI agent reliability); LangGraph state machine documentation; UC Berkeley MAST taxonomy (FM-1.1 through FM-1.4 = system design failures addressable by bounded FSM). No canonical citation — this is synthesized from cross-source convergence.

> Tested concept: LangGraph `Command` primitive (force goto) + per-state tool scoping prevents the two most common MAST failure modes (illegal transitions + out-of-scope tool calls). The revision budget (Layer 2) prevents FM-2.2 (agent continues despite knowing it is stuck). The human review gate prevents FM-3.1 (agent skips verification).

## See also

- [S-355 · Agent Autonomy Levels](stacks/s355-agent-autonomy-levels-bounded-autonomy.md) — the autonomy classification that precedes state machine design; this entry is the *enforcement* pattern for bounded autonomy
- [S-1008 · The Orchestration Pattern Match Stack](stacks/s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — choosing the right orchestration topology; FSM-constrained agents are the "chain" pattern with LLM inside
- [S-1036 · The Orchestration Gap](stacks/s1036-the-orchestration-gap-when-your-agent-demo-shines-and-your-production-system-dies.md) — the demo-to-production failure this pattern specifically prevents
- [S-1034 · The Role Fence Stack](stacks/s1034-the-role-fence-stack-when-your-multi-agent-system-keeps-tripping-over-itself.md) — multi-agent isolation; combine with this entry for multi-agent FSM systems
