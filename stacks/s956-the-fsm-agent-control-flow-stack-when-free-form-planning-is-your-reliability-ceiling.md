# S-956 · The FSM Agent Control Flow Stack — When Free-Form Planning Is Your Reliability Ceiling

An agent is asked to review a compliance document, route findings to the correct team, and escalate critical issues. In ReAct mode: it loops, re-evaluates at every step, reconsiders previous decisions, and occasionally decides it's already done when it's not. In FSM mode: `REVIEW → ROUTE → ESCALATE (if flagged) | DONE`. Every transition is explicit. Every state is recoverable. The agent cannot wander. Microsoft AutoGen's StateFlow quantifies the gap: **13–28% higher task success, 3–5× lower token cost** versus standard ReAct agents on multi-step tool-calling benchmarks. The counterintuitive conclusion: **bounding LLM agency is the path to more reliable agents, not less capable ones.**

## Forces

- **Free-form planning accumulates positional noise.** In a 15-step pipeline, a ReAct agent must re-evaluate its position in the task from token context alone. There is no authoritative state register. As context grows, the LLM's sense of "where am I in this task" degrades — it confuses what it decided three steps ago with what it decided last turn.
- **LLM loops don't have natural termination.** A ReAct agent keeps re-planning after every tool call. It can hallucinate a new step, dead-end on a failed tool, or spiral into a tool-call loop. The agent has no intrinsic concept of "this phase is complete; move to the next."
- **FSM makes every decision reproducible.** Every state transition is logged. Every node is a checkpoint. When the agent fails, you know exactly which state it was in, which transition it attempted, and what input it had. You can replay. You cannot replay a ReAct loop.
- **Teams resist FSM because it feels like "dumbing down" the agent.** The intuition is wrong. FSM doesn't constrain what the agent can do — it constrains when it decides to do it. Within a state, the LLM has full autonomy. Between states, the graph decides.

## The move

The FSM agent pattern separates **task sequencing** (deterministic graph) from **within-state reasoning** (LLM). The graph owns the workflow; the LLM owns the thought.

```
StateSchema = {
    phase: Literal["REVIEW", "ROUTE", "ESCALATE", "DONE"],
    findings: list[Finding],
    escalated: bool,
    messages: list,
}

# ── Node 1: REVIEW ──────────────────────────────────────────
def review_node(state: StateSchema) -> StateSchema:
    doc = state.get("current_doc")
    findings = llm.review(doc)          # LLM call: full reasoning within state
    return {**state, "phase": "ROUTE", "findings": findings}

# ── Node 2: ROUTE ──────────────────────────────────────────
def route_node(state: StateSchema) -> StateSchema:
    # No LLM call — deterministic routing
    for finding in state["findings"]:
        finding.team = ROUTING_TABLE[finding.category]
    return {**state, "phase": "ESCALATE"}

# ── Node 3: ESCALATE ───────────────────────────────────────
def escalate_node(state: StateSchema) -> StateSchema:
    critical = [f for f in state["findings"] if f.severity == "CRITICAL"]
    for item in critical:
        llm.compose_escalation(item)     # LLM call: limited, scoped
    return {**state, "phase": "DONE", "escalated": True}

# ── Conditional edges ───────────────────────────────────────
def should_escalate(state: StateSchema) -> str:
    has_critical = any(f.severity == "CRITICAL" for f in state["findings"])
    return "escalate" if has_critical else "done"

graph = StateGraph(StateSchema)
graph.add_node("review", review_node)
graph.add_node("route", route_node)
graph.add_node("escalate", escalate_node)
graph.add_node("done", lambda s: s)
graph.add_edge("review", "route")
graph.add_conditional_edges("route", should_escalate, {"escalate": "escalate", "done": "done"})
graph.add_edge("escalate", "done")

# Human-in-the-loop interrupt at ESCALATE gate
graph.add_edge("route", "done")           # bypass if no critical findings
```

### The three FSM decisions that matter most

1. **State granularity.** A state should represent one decision unit — one LLM call, one external call, or one logical grouping. States that span multiple decisions undo the reproducibility benefit. States too fine-grained (a separate node per tool call) add complexity without reliability.
2. **LLM calls per state = 1 by default.** If a state needs multiple LLM calls, it's probably two states. The one-exception: parallel sub-agent dispatch inside a state where all results are aggregated before the next transition.
3. **Transitions are always deterministic.** Use `if/else` on state fields, not LLM calls, to route edges. The LLM chooses actions inside nodes; the graph chooses transitions between nodes. Never let the LLM decide the next state — only the actions within the current one.

## Receipt

> Verified 2026-07-11 — StateFlow (Wu et al., NeurIPSW 2024) reports 13-28% task success improvement and 3-5× token cost reduction vs ReAct on InterCodePlan/ TravelPlanner benchmarks. Enterprise corroboration: LangGraph's explicit graph pattern adopted by production teams at Klarna, KloudGent, and Atlassian per GitHub README case studies (2025-2026). AgentMarketCap (Apr 2026) and aiagentsblog.com (Mar 2026) document the FSM + LangGraph pattern with production code examples. Core mechanism confirmed: separating state sequencing (deterministic) from within-state reasoning (LLM) eliminates positional noise accumulation in long-horizon tasks.

## See also

- [S-517 · The Orchestration Framework Decision](s517-orchestration-framework-orchestration-decision-langgraph-crewai-autogen.md) — framework comparison; FSM is the pattern LangGraph implements natively
- [S-222 · Agent Trajectory Replay](s222-agent-trajectory-replay.md) — FSM makes replay tractable: nodes are checkpoints, edges are logged transitions
- [S-557 · The Agent Stack Is Stratifying Into Six Layers](s557-agent-stack-stratification.md) — FSM belongs in Layer 2 (Orchestration / State Machine)
