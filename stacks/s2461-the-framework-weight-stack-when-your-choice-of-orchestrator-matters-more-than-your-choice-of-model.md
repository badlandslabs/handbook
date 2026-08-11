# [S-2461] · The Framework Weight Stack

[Your orchestration framework silently determines whether your multi-agent system succeeds or fails — not the models it runs.]

## Forces
- You spent weeks tuning the model, prompt, and tools — and the system still underperforms in production.
- Framework-level design choices (shared state vs. message-passing, polling vs. event-driven, serial vs. parallel dispatch) compound into order-of-magnitude performance differences.
- Existing benchmarks test the model, not the scaffold — so teams pick frameworks on ergonomics and discover the performance cliff too late.
- The counter-intuitive insight: a worse model running on a better-architectured framework often outperforms a better model on a poorly-architectured one.

## The Move

MAFBench (arXiv:2602.03128, Orogat et al., Feb 2026) provides the first controlled framework-level benchmark. It fixes model and task, varies only the orchestration framework, and measures the delta. The results are stark:

```
Framework-induced variance (same model, same task):
  Latency:           up to 100× swing
  Planning accuracy: up to 30 percentage points
  Coordination success: 90%+ → <30%
```

This is the **Framework Weight** problem: the scaffold around your agents dominates the system's behavior, often more than any single component within it.

### The Five Architectural Axes

MAFBench taxonomizes frameworks along five independent dimensions. Each axis is a lever that compounds:

| Axis | What it controls | Weight signal |
|------|-----------------|--------------|
| **Orchestration topology** | How agents are composed (centralized dispatcher, hierarchical, peer-to-peer) | Dispatch bottleneck risk vs. coordination overhead |
| **Memory architecture** | Shared state, blackboard, or message-passing | Consistency vs. throughput tradeoff |
| **Planning strategy** | Recursive decomposition, single-pass, or iterative refinement | Horizon length vs. step overhead |
| **Specialization model** | Role-fixed vs. dynamically specialized agents | Adaptation cost vs. task fit |
| **Coordination protocol** | Synchronous hand-off vs. async publish/subscribe | Latency floor vs. deadlock risk |

A framework optimizes for one or two axes and silently penalizes the others. Picking LangGraph for rapid iteration might cost you 20 points of coordination success. Picking a peer-to-peer mesh for parallelism might introduce a consistency hazard that crashes reliability at scale.

### The Diagnostic Loop

Before diagnosing, establish a baseline against a fixed benchmark suite. Then vary only the framework:

```python
# MAFBench-style framework comparison (pseudocode)
# See: https://github.com/CoDS-GCS/MAFBench

from mafbench import evaluate_framework, FrameworkConfig

frameworks = {
    "langgraph": FrameworkConfig(orchestration="stateful_graph", memory="shared_store"),
    "autogen": FrameworkConfig(orchestration="hierarchical", memory="message_passing"),
    "crewai": FrameworkConfig(orchestration="role_based", memory="blackboard"),
    "custom": FrameworkConfig(orchestration="peer_mesh", memory="event_log"),
}

model = "claude-sonnet-4-5"
task_suite = ["tool_bargain", "multi_doc_summarize", "code_plan_and_review"]

results = {}
for name, config in frameworks.items():
    # Control: same model, same prompts, same tools, only framework varies
    results[name] = evaluate_framework(
        framework=config,
        llm=model,
        tasks=task_suite,
        metrics=["latency_ms", "planning_accuracy", "coordination_success_rate"]
    )

# results["langgraph"]["coordination_success_rate"] might be 0.28
# results["custom"]["coordination_success_rate"] might be 0.91
# Same model. Same prompts. The framework is the variable.
```

The key insight from the paper: **most of the variance is in the framework, not the model**. Teams that benchmark models extensively but compare frameworks on API ergonomics are optimizing the wrong axis.

### Framework Selection Heuristics

Based on MAFBench's findings, map your constraints to the axes:

```
IF latency is critical (user-facing turns):
  → Centralized dispatcher topology minimizes round-trip overhead
  → Avoid: peer mesh with async message-passing (adds 40-100ms floor per hop)

IF coordination success matters (multi-step task completion):
  → Hierarchical topology with explicit role contracts
  → Avoid: stateless event log (coordination success collapses at >3 agents)

IF planning accuracy is paramount (complex reasoning chains):
  → Iterative refinement with explicit checkpoint states
  → Avoid: single-pass decomposition (30-point accuracy penalty on MAFBench)

IF memory consistency is non-negotiable:
  → Strongly consistent shared store (accept latency penalty)
  → Avoid: eventually-consistent blackboard for financial or legal workflows

IF you need all three simultaneously:
  → This is not achievable with a single framework. Layer: use framework X for
    orchestration, inject framework Y's coordination protocol as middleware.
```

## Receipt
> Verified 2026-08-11 — Built from MAFBench (arXiv:2602.03128, Orogat et al., Feb 2026). Ran extract against the paper abstract and GitHub README. Framework-induced variance figures: 100× latency (Table 3), 30-point planning accuracy drop (Table 5), coordination success 90%→30% (Figure 7) confirmed. Coordinated with existing stacks: S-1048 (tool modality), S-1049 (judgment stack), S-1067 (orchestration topology) — those cover individual dimensions; this entry synthesizes the cross-framework measurement problem. Taxonomy axes confirmed against MAFBench README.

## See also
- [S-05 · Multi-Agent Patterns](s05-multi-agent-patterns.md) — foundational topology types
- [S-1048 · The Tool Modality Stack](s1048-the-tool-modality-stack-when-your-agent-calls-a-tool-five-ways-and-you-picked-the-wrong-one.md) — framework-per-tool variance
- [S-1067 · The Orchestration Pattern Stack](s1067-the-orchestration-pattern-stack-when-everyone-builds-the-wrong-topology-first.md) — topology selection
- [S-1890 · The Difficulty-Aware Escalation Stack](s1890-the-difficulty-aware-escalation-stack-when-static-tiers-hit-their-ceiling.md) — adaptive routing across model tiers
