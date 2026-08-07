# S-2197 · The Orchestration Plan Blindspot Stack — When Your Multi-Agent DAG Looks Perfect and Fails Silently

You reviewed the orchestration diagram. The DAG is clean: five specialist agents, clear dependencies, parallel where possible, sequential where required. You greenlit it. Three weeks into production, the system is deadlocking, the token bill is 4× the estimate, and agents are producing conflicting outputs. The problem isn't the model, the tools, or the prompts. It's the plan. Orchestration quality has no CI gate, no regression test, and no benchmark — until now.

## Forces

- **Existing benchmarks conflate orchestration with execution.** AgentBench, GAIA, and WebArena evaluate end-to-end success — which means a bad plan that gets lucky because the workers are capable will score well. A good plan that gets unlucky will score poorly. You cannot distinguish plan quality from execution quality in any current benchmark
- **Orchestration failures are structural, not stochastic.** A deadlock, a token explosion, or a coordination conflict isn't a model error — it's a property of the DAG. It will fail the same way every time, with 100% reproducibility. But there's no tool to catch it before deployment
- **47 failure modes are unique to multi-agent orchestration** (Microsoft Research, 2026) and don't appear in single-agent evaluations. Teams discover them only in production, usually after they've caused incidents
- **Token economics make orchestration bugs expensive.** A workflow split across four agents that each re-receive the full conversation costs 4× the input tokens. Audited pilots have burned 12× the tokens of equivalent single-agent baselines — not because of model inefficiency, but because the DAG re-sends context on every handoff
- **Orchestration is designed once, runs forever.** Unlike prompts or models, the DAG is architecture. Bugs compound over every invocation, not just the one where you noticed the problem

## The move

### 1. Isolate orchestration from execution with OrchBench

OrchBench (Ren, He, Zhang et al., arXiv:2607.25656v1, July 2026) is the first benchmark that evaluates *only* the orchestration plan, independently of worker capabilities. It works by replacing workers with deterministic simulators — a DAG executor that runs the plan exactly as authored, returning deterministic outputs. This separates three questions that end-to-end evaluation conflates:

- Is the plan sound? (orchestration quality — what OrchBench measures)
- Are the workers capable? (model quality — evaluated separately)
- Are the tools reliable? (infrastructure quality — evaluated separately)

Use OrchBench as the first gate in your multi-agent CI pipeline. Run it before any model-level evaluation.

```python
# OrchBench-style orchestration plan evaluation
from orchbench import Orchestrator, Simulator, PlanEvaluator

# Define the DAG
plan = Orchestrator.dag(
    tasks=[
        Task(id="triage",     agent="router",     depends_on=[]),
        Task(id="research",   agent="searcher",    depends_on=["triage"]),
        Task(id="synthesize", agent="writer",       depends_on=["research"]),
        Task(id="review",     agent="reviewer",    depends_on=["synthesize"]),
        Task(id="publish",    agent="publisher",    depends_on=["review"]),
    ],
    resources={"max_concurrent": 3, "token_budget": 50000},
)

# Evaluate in simulation — no real model calls
simulator = Simulator(workers={"router": MockRouter(), ...})
result = PlanEvaluator.evaluate(plan, simulator, metrics=[
    "deadlock_detection",
    "token_budget_safety",
    "coordination_conflict",
    "parallelism_efficiency",
    "critical_path_length",
])

assert result.deadlock_count == 0, f"Deadlock detected: {result.deadlock_path}"
assert result.token_budget_safety > 0.95, f"Token budget exceeded by {1 - result.token_budget_safety:.0%}"
assert result.parallelism_efficiency > 0.7, f"Only {result.parallelism_efficiency:.0%} of available parallelism used"
```

### 2. Screen for the seven structural failure modes

Before deployment, evaluate your DAG against these seven structural properties. Each corresponds to a real-world failure category from Microsoft Research's 2026 multi-agent taxonomy:

**Deadlock detection.** Map all inter-agent dependencies. Verify there are no circular wait chains. Even a two-agent mutual-wait cycle will halt the system indefinitely:

```python
def detect_deadlock(dag: list[Task]) -> list[list[str]]:
    """Build dependency graph, find strongly connected components."""
    graph = {t.id: set(t.depends_on) for t in dag}
    # Tarjan's algorithm for SCCs with size > 1
    sccs = tarjan_scc(graph)
    return [scc for scc in sccs if len(scc) > 1]

# S-1029 covers deadlock recovery patterns; this entry covers pre-deployment detection
```

**Token budget safety.** Compute the worst-case token cost for each agent given the DAG's re-send behavior. An agent receiving full conversation context on every handoff from a 3-agent pipeline pays 3× input tokens per turn:

```python
def token_budget_analysis(dag: list[Task], avg_context_size: int) -> dict:
    """Per-agent and total token cost with handoff re-send overhead."""
    agent_call_counts = {}
    for task in topological_sort(dag):
        agent_call_counts[task.agent] = agent_call_counts.get(task.agent, 0) + 1

    results = {}
    total = 0
    for agent, calls in agent_call_counts.items():
        cost = calls * avg_context_size  # tokens burned on handoffs
        results[agent] = {"calls": calls, "handoff_tokens": cost}
        total += cost

    return {"per_agent": results, "total_handoff_overhead": total}
```

**Coordination conflict.** When two agents operate on shared state without synchronization, the last writer wins — silently. Detect shared-resource access patterns in the DAG:

```python
def detect_coordination_conflicts(dag: list[Task], resource_map: dict) -> list[Conflict]:
    """Find agents writing to the same resource without a sequencer."""
    writer_map = defaultdict(list)  # resource -> [task_ids]
    for task in dag:
        for res in task.writes:
            writer_map[res].append(task.id)

    conflicts = []
    for resource, writers in writer_map.items():
        if len(writers) > 1:
            # Check if there's a sequencing task between them
            if not has_serialization_gate(dag, writers):
                conflicts.append(Conflict(resource, writers))

    return conflicts
```

**Parallelism efficiency.** The DAG's critical path length divided by its total execution time under maximum parallelism gives you parallelism efficiency. An efficiency below 0.5 means the plan isn't exploiting the parallelism it claims:

```python
def parallelism_efficiency(dag: list[Task]) -> float:
    """Critical path / (sum of all task durations / max_concurrent)."""
    tasks = {t.id: t for t in dag}
    durations = {t.id: t.estimated_duration for t in dag}

    # Critical path via longest-path in DAG
    critical_path = longest_path(dag)

    # Ideal time with infinite parallelism
    ideal_time = sum(durations.values()) / dag[0].max_concurrent if dag else 0

    return sum(critical_path) / ideal_time if ideal_time > 0 else 0
```

### 3. Test the plan under adversarial execution

OrchBench's key insight is that simulation lets you inject failure modes without touching real infrastructure. Build a failure injector that simulates worker failures, tool timeouts, and model degradations — then verify your plan's resilience properties:

```python
from orchbench.fault_injection import FaultInjector, FailureMode

injector = FaultInjector(
    failures=[
        FailureMode("researcher", "timeout", probability=0.3),
        FailureMode("synthesizer", "hallucination", probability=0.1),
        FailureMode("reviewer", "timeout", probability=0.2),
    ],
    seed=42,
)

results = []
for trial in range(100):
    result = evaluator.evaluate(plan, simulator, injector=fault_injector)
    results.append(result)

# Aggregate resilience properties
resilience = {
    "deadlock_rate": sum(1 for r in results if r.deadlocked) / len(results),
    "timeout_recovery_rate": sum(1 for r in results if r.recovered_from_timeout) / len(results),
    "mean_completion_pct": np.mean([r.completion_ratio for r in results]),
    "token_variance": np.std([r.token_cost for r in results]),
}
assert resilience["deadlock_rate"] < 0.01, f"Deadlock rate {resilience['deadlock_rate']:.0%} too high"
assert resilience["token_variance"] < 0.2 * np.mean([r.token_cost for r in results]), "Token cost too variable"
```

### 4. Use MASBENCH to characterize tasks before choosing an architecture

MAS-Orchestra (Zhang, Jiang, Li et al., arXiv:2601.14652, ICML 2026) introduces MASBENCH, a controlled benchmark that characterizes tasks along five axes: **Depth** (reasoning steps), **Horizon** (task duration), **Breadth** (parallelism potential), **Parallel** (independent subtasks), and **Robustness** (failure propagation). The key finding: multi-agent gains depend critically on task structure. The wrong architecture on the wrong task type destroys value:

| Task Characteristic | Single Agent | Supervisor | Parallel Workers | Full Orchestra |
|---|---|---|---|---|
| Low depth, short horizon | ✓ Optimal | Overhead | Overhead | Overhead |
| High depth, long horizon | Fails | ✓ Optimal | Suboptimal | Suboptimal |
| High breadth, parallelizable | Suboptimal | OK | ✓ Optimal | Overhead |
| High robustness requirement | Single point | ✓ With fallback | OK | ✓ Best |
| High coordination need | N/A | OK | Fails | ✓ Optimal |

Use this matrix to select architecture before designing the DAG.

### 5. Add the orchestration CI gate to your pipeline

```yaml
# .github/workflows/orchestration-ci.yml
- name: Orchestration Plan Evaluation
  run: |
    orchbench evaluate \
      --plan stacks/pipelines/production-researcher/dag.yaml \
      --simulator mock_workers \
      --metrics deadlock,token_budget,coordination,parallelism,resilience \
      --fail-threshold deadlock=0,token_budget_safety=0.95,parallelism_efficiency=0.65
    # Fails CI if any structural property violates the threshold
```

## Receipt

> Verified 2026-08-05 — Sources: arXiv:2607.25656v1 (OrchBench, Ren et al., July 2026): simulation-based orchestration plan isolation, DAG evaluation metrics, 5-axis plan characterization; arXiv:2601.14652 (MAS-Orchestra, Zhang et al., ICML 2026): MASBENCH task characterization taxonomy, architecture selection matrix; Microsoft Research 2026 multi-agent failure taxonomy (47 unique failure modes); Velocity Software (May 2026): token economics of multi-agent handoffs (4×–12× overhead); Zylos Research (May 2026): specification failures (42%), coordination breakdowns (37%), verification gaps (21%) as dominant failure categories. Code examples synthesized from the OrchBench reference implementation pattern and standard DAG analysis. Distinct from S-999 (orchestration patterns), S-1008 (pattern selection), and S-1013 (boundary/state management) — this entry covers the pre-deployment structural evaluation of the plan itself, not the architectural pattern selection.

## See also

- [S-999 · The Orchestration and Memory Stack](/opt/data/handbook/stacks/s999-the-orchestration-and-memory-stack-when-your-agent-needs-to-know-what-it-already-knew.md) — architecture patterns for multi-agent systems; this entry covers plan evaluation before architecture is finalized
- [S-1013 · The Multi-Agent Boundary Stack](/opt/data/handbook/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — shared state management between agents; coordination conflicts are the failure mode this entry's detection patterns prevent
- [S-1179 · The Reasoning-Planning Gap](/opt/data/handbook/stacks/s1179-the-reasoning-planning-gap-when-your-agent-reasons-well-but-plans-poorly.md) — why step-wise greedy reasoning fails for long-horizon tasks; complements this entry's plan evaluation by explaining why plans fail even when individual steps look correct
