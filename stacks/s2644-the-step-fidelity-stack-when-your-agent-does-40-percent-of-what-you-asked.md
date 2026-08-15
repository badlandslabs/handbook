# S-2644 · The Step-Fidelity Stack — When Your Agent Does 40% of What You Asked

You wrote a 12-step workflow in SOUL.md. You put "MANDATORY" in bold before every step. You added a checklist. The agent acknowledged every instruction. At the end, it reported success. It completed steps 1–4, summarized, and called it done. Steps 5–12 never ran.

This is not a prompt quality problem. It is a generation-vs-execution problem.

## Forces

- **LLMs generate plausible completions, not execute instructions.** When a model receives a multi-step workflow, it predicts the most likely token sequence given the context. If the most natural-sounding continuation after step 3 is a summary and conclusion, the model generates that — even when steps 4–12 are in the prompt. The model is working exactly as designed; the mismatch is between text-generation semantics and task-execution semantics.
- **Attention decay makes later steps statistically invisible.** Transformer attention is non-uniform. Content appearing earlier in the context — or buried mid-prompt — receives systematically lower attention weight. Steps 8–12 in a 12-step prompt are attended to less than steps 1–4, making omission of late steps a structural bias, not a random failure.
- **Prompt directives don't create execution constraints.** Adding "MANDATORY", "CRITICAL", "DO NOT SKIP", or numbered checklists changes what the model generates, not what it executes. The model still generates tokens; it does not run a for-loop over a checklist.
- **Silent partial completion looks identical to full completion in logs.** An agent that completes steps 1–4 and reports success has a clean log, a zero exit code, and a confident completion message. Dashboards see green. No alert fires.
- **The failure compounds at scale.** A single 12-step workflow at 90% step-fidelity produces 28% failure rate (0.9¹²). A 20-step workflow at 95% fidelity produces 36% failure rate. Teams running 10+ step agents report average task-completion rates of 40–60% in production — not because the model is weak, but because the structural enforcement layer is missing.

## The move

### 1. Replace instruction budgets with execution contracts

A task graph is not a prompt — it is a directed graph where nodes represent operations (tool calls, API calls, data transformations) and edges represent mandatory dependencies. The graph is not read by the agent; it is executed by the orchestrator.

```
# Task graph (not a prompt — a data structure)
workflow = [
    {"id": "fetch_users", "tool": "db_query", "deps": []},
    {"id": "enrich_records", "tool": "enrich_api", "deps": ["fetch_users"]},
    {"id": "validate_schema", "tool": "schema_check", "deps": ["enrich_records"]},
    {"id": "write_batch", "tool": "db_insert", "deps": ["validate_schema"]},
    {"id": "send_notifications", "tool": "notify", "deps": ["write_batch"]},
]
```

The orchestrator traverses the graph. It executes `fetch_users`, passes the result to `enrich_records`, passes that to `validate_schema`, and so on. The agent cannot skip `validate_schema` because the orchestrator requires its output as an input to `write_batch`. Step completion is structural, not prompted.

Frameworks: LangGraph (stategraph edges), Temporal (activity dependencies), Microsoft AutoGen (task graphs), crewAI (process flows), Beads + OpenClaw (dependency-aware orchestration).

### 2. Validate step completion at the orchestrator boundary

Every node in the graph has a **completion criterion**: a predicate that the orchestrator evaluates to determine whether the node's output is valid. This is not the agent grading its own work — it is the infrastructure checking the infrastructure.

```python
def validate_node(node_id: str, output: Any, graph: WorkflowGraph) -> bool:
    validators = {
        "fetch_users": lambda o: isinstance(o, list) and len(o) > 0,
        "enrich_records": lambda o: all("enriched" in r for r in o),
        "validate_schema": lambda o: o.get("valid") is True,
        "write_batch": lambda o: o.get("rows_written") == len(o.get("batch", [])),
        "send_notifications": lambda o: o.get("delivered") == o.get("sent"),
    }
    return validators[node_id](output)
```

The orchestrator halts the workflow and routes to a dead-letter queue if validation fails. The agent cannot paper over a failed validation step by generating a plausible next-step summary.

### 3. Detect step-skipping through execution tracing

When step-fidelity failures do occur, they must be caught before they propagate. Log the actual execution trace — which nodes ran, in what order, with what inputs and outputs — separately from the agent's self-reported completion status. Compare them.

```python
# Orchestrator traces what actually happened
execution_log.append({
    "node": node_id,
    "ran": True,
    "output_valid": validate_node(node_id, output, graph),
    "reported_complete": False,  # orchestrator sets this
})

# Agent reports completion independently
# If execution_log shows nodes without output_valid=True,
# the agent reported success without a valid execution

missing = [n for n in graph.nodes if n not in executed_node_ids]
assert len(missing) == 0, f"Step-fidelity failure: {missing} never ran"
```

This is the structural equivalent of the "agent grading its own homework" problem — but shifted: the orchestrator grades the execution graph, not the agent.

### 4. Calibrate step granularity with attention budgets

FlowSteer (arXiv:2602.01664) shows that agents trained with step-skipping suppression achieve significantly higher task completion rates. For prompt-based systems, a heuristic: if a workflow has more steps than can fit in the first 50% of context, it is too long. Break it into sub-graphs. Each sub-graph should complete within 2–3 steps of the agent's natural stopping point.

A 12-step workflow run by a single agent has ~40% expected completion. The same 12-step workflow as three 4-step sub-graphs, each with its own orchestrator checkpoint, has ~74% expected completion (0.9⁴ × 0.9⁴ × 0.9⁴).

### 5. Log the gap between acknowledged and executed

The simplest leading indicator: after the agent acknowledges a plan, log which steps the orchestrator actually executed. Track the ratio:

```
step_fidelity_rate = nodes_executed / nodes_acknowledged
```

Alert if fidelity drops below 0.85. The gap between acknowledgment and execution is the step-fidelity signal. It predicts downstream quality degradation before output scoring can detect it.

## When to reach for this

- Multi-step workflows (5+ steps) where partial completion is indistinguishable from full completion in outputs
- Agents that "summarize" mid-workflow and report success without running remaining steps
- Task-completion rates below 70% in production despite prompt engineering
- Regulated workflows where audit trails must show all required steps ran, not just that a plausible final message was generated

## See also

- [S-1019 · The Ghost-Loop Stack](s1019-the-ghost-loop-stack-when-your-agent-decides-its-own-workflow-and-nobody-traced-it.md) — implicit vs. explicit control flow; this entry's orchestrator-level enforcement vs. S-1019's tracing-only approach
- [S-928 · Phantom Completion](s928-the-phantom-completion-stack-when-your-agent-says-done-but-nothing-happened.md) — tool errors absorbed into success narratives; the validation step in S-2644 structurally prevents this by checking outputs at node boundaries
- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — loop detection and budget enforcement; S-2644 adds step-completion enforcement to scaffold's loop/budget guards

> Receipt pending — 2026-08-14. Sources: Trilogy AI Center of Excellence "Why Your AI Agents Skip Steps" (March 26, 2026), arXiv:2602.01664v2 FlowSteer (Jan 2026), arXiv:2606.16871v1 Human-on-the-Bridge (Jun 2026), arXiv:2604.03527v1 Topaz explainable routing (Apr 2026), arXiv:2605.01604v1 Agentic AI in the Wild failure modes (May 2026).
