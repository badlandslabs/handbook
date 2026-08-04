# S-2104 · The Error Propagation Stack — When Your Agent's Final Answer Looks Right but the Reasoning Chain Is Broken

Your agent passes the task. The output is correct. The user is satisfied. Six months later you discover the agent was making downstream tool calls based on a hallucinated intermediate assumption, and every downstream decision was built on a foundation that happened to work out by luck. End-to-end evaluation gave you a pass — but the failure was already in the DAG.

## Forces

- **End-to-end checks hide the node that matters.** An outcome check verifies the final output, not the intermediate reasoning steps that produced it. A task can succeed despite three failed reasoning steps if later steps accidentally compensate — masking the exact failure mode that will bite you when inputs change.
- **63% of step-level failures propagate from upstream.** Guo et al. (HKU / Stellaris AI, ACL 2026, arXiv:2604.23581) measured on 450 production traces: the majority of observable failures are not local to the step that fails — they are inherited from upstream nodes in the execution graph. Fixing the visible failure without fixing the source produces a false pass.
- **Ad-hoc trace inspection doesn't scale.** A team running 50 agent workflows with hundreds of steps per run cannot manually review every trajectory. Without a structured evaluation framework, you discover error propagation only when it surfaces in production — by which point it has already corrupted downstream state.

## The move

AgentEval (Guo et al., ACL 2026) formalizes agent workflow executions as **evaluation DAGs** — directed acyclic graphs where each node represents a workflow step carrying typed quality metrics, and edges encode upstream dependencies. The key insight: by representing the workflow as a DAG and annotating each node with step-level quality signals, you can automatically propagate failure attribution backward through the dependency chain and identify the root-cause node.

### Build the evaluation DAG from traces

Capture every workflow step as a node with typed metadata:

```
Node = {
  step_id,           # unique per run
  step_type,         # reasoning | tool_call | synthesis | memory_fetch | ...
  inputs,            # upstream node outputs (dependencies)
  outputs,           # what this step produced
  quality_metrics,   # per-type scoring
  error_tags         # classified failures
}
```

Edges: `step_B → step_C` if step_C consumes output from step_B.

### Score each node with typed quality metrics

GPT-4o-as-judge scores each node against step-type-specific rubrics (5 metric types covering correctness, coherence, tool-call accuracy, retrieval precision, output format). Node scores become the inputs for downstream propagation analysis.

### Propagate failures backward with greedy parent strategy

When a node fails, trace its inputs backward through the DAG. The **greaky parent strategy**: if a downstream node fails and at least one of its upstream parents also has degraded quality scores, attribute the failure to the parent with the highest error correlation — recursively, until you reach a node with no upstream errors or no correlated parents. This is the root cause. On production traces, this achieves **72% root cause accuracy**, approaching the human ceiling of 81%.

### Classify failures with a hierarchical taxonomy

21 failure subcategories across 3 levels:
- **Level 1** (category): planning, reasoning, tool use, memory, synthesis
- **Level 2** (mechanism): hallucination, context miss, schema mismatch, tool unavailability, etc.
- **Level 3** (specific): e.g., `tool_call / wrong_argument_type / string_vs_int_schema_mismatch`

Consistent taxonomy across runs enables trend analysis: which failure categories dominate? Are they getting better or worse across versions?

### Gate CI/CD on DAG-level metrics, not just outcome

Add a post-run evaluation step that:
1. Converts the raw trace to an evaluation DAG
2. Scores all nodes
3. Propagates failures backward to identify root cause
4. Fails the pipeline if any node's quality score drops below threshold OR if a propagated failure is detected in a previously-clean node
5. Emits a structured failure report with root-cause node ID for triage

This alone improves failure detection **recall from 0.41 to 0.89** (2.17×) over end-to-end evaluation. It also reduces median root cause localization from **4.2 hours to 22 minutes**.

### Key implementation decisions

- **Start from existing traces.** You don't need to instrument the agent — parse its execution log into DAG nodes post-hoc. The DAG is a view, not a modification.
- **Five metric types are sufficient.** Cover the common step types (reasoning, tool_call, synthesis, memory, format) rather than trying to score every dimension. Over-granular scoring dilutes signal.
- **Calibrate the judge.** Use 10–20 human-annotated traces to tune the GPT-4o judge prompt. Without calibration, κ drops below 0.7 and false attributions spike.
- **Propagate only when upstream error explains downstream failure.** If a downstream node fails but all upstream scores are clean, the failure is local — don't propagate. Propagating clean errors generates false positives.

```python
# Minimal error propagation attribution
def attribute_root_cause(node_id: str, dag: DAG) -> str | None:
    node = dag[node_id]
    if node.score >= threshold:
        return None  # local success

    # Greedy parent: find first upstream with degraded quality
    for parent_id in dag.upstream(node_id):
        parent = dag[parent_id]
        if parent.score < threshold:
            # Recurse to see if parent failure has its own upstream cause
            upstream_cause = attribute_root_cause(parent_id, dag)
            return upstream_cause or parent_id
    return node_id  # no correlated upstream → local root cause
```

## Receipt

> Verified 2026-08-04 — Source: Guo et al. (HKU + Stellaris AI), "AgentEval: DAG-Structured Step-Level Evaluation for Agentic Workflows with Error Propagation Tracking" (arXiv:2604.23581, ACL 2026 Industry Track). Key metrics: 2.17× recall improvement (0.41→0.89), Cohen's κ=0.84 human consistency, 72% root cause accuracy vs 81% human ceiling, 4.2h→22min RCA improvement on 450 production traces. GitHub: bettyguo/AgentEval. Additional sourcing: paper notes summary at zhaoyang97/Paper-Notes-en.

## See also

- [S-1001 · The Agent Evaluation Stack](/opt/data/handbook/stacks/s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — benchmarks vs. production; this entry is the evaluation *mechanism* S-1001 argues you need
- [S-1009 · The Agentic RCA Stack](/opt/data/handbook/stacks/s1009-the-agentic-rca-stack-when-your-agent-has-to-figure-out-why-it-broke.md) — root cause analysis workflow; this entry automates RCA attribution into the evaluation loop
- [S-1012 · The Agent Failure Recovery Stack](/opt/data/handbook/stacks/s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — detection and recovery; DAG-level scoring feeds directly into which recovery strategy to use
- [S-1856 · The Belief State Boundary](/opt/data/handbook/stacks/s1856-the-belief-state-boundary-when-your-agent-knows-something-it-cant-prove.md) — upstream assumptions that contaminate downstream reasoning; this entry provides the structural mechanism for detecting that contamination
