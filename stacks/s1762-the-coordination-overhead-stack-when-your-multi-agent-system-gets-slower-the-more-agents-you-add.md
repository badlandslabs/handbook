# S-1762 · The Coordination Overhead Stack — When Your Multi-Agent System Gets Slower the More Agents You Add

You added a second agent and latency dropped 40%. You added a third and it went back up. By the fifth agent, your parallel system is slower than running the task serially on one agent. The engineers blame the model. The model is not the problem. This is the coordination overhead problem.

## Forces

- **Coordination costs are non-linear.** Message passing, lock acquisition, shared-state synchronization, and result merging each add overhead that compounds as agent count grows. On loosely-coupled tasks the overhead is negligible; on tightly-coupled tasks it exceeds the parallelism benefit entirely.
- **Teams adopt multi-agent because it looks like distributed systems, but agents aren't threads.** Classic distributed systems assume cheap computation and expensive communication. LLMs invert this: computation is expensive and communication is cheap at the protocol level—but the coordination logic (schema negotiation, conflict resolution, shared-state locking) is neither cheap nor well-optimized in most agent frameworks.
- **The MAST taxonomy reveals what actually breaks.** A 1,642-trace analysis across seven open-source agent frameworks (NeurIPS 2025) found failure rates between 41% and 86.7%. Of those failures, **79% originated in inter-agent coordination problems**—specification ambiguity, role misinterpretation, duplicate work, and skipped verification—not in individual agent capability. System design issues dwarf execution failures in multi-agent settings.
- **Task coupling is the hidden variable.** Parallel fan-out works when agents operate on independent subtasks. It fails when agents must read each other's intermediate outputs, wait for shared resources, or reconcile conflicting schema versions. The moment an agent blocks on another agent's result, you've serialized your parallel workload.

## The move

**Measure coordination overhead before committing to a multi-agent architecture.** The pattern: instrument every inter-agent hop—message queue depth, lock wait time, schema negotiation latency, merge cost—and compare against the serial baseline. If overhead exceeds the parallel speedup for your task profile, reconsider the architecture.

### 1. Classify by coupling type

| Coupling | Pattern | Overhead |
|----------|---------|---------|
| Independent subtasks | Fan-out, no shared state | Near-zero |
| Sequential dependency | Pipeline (A → B → C) | Linear, predictable |
| Read-after-write | Shared state, one writer | Lock contention |
| Concurrent writes | Shared state, multiple writers | Conflict resolution dominates |

### 2. Apply the right coordination primitive per coupling

**For independent tasks (low coupling):** True parallelism. Agents receive disjoint inputs, produce disjoint outputs, and a controller merges results. No shared state, no locks, no coordination overhead. This is where multi-agent earns its speedup.

```python
async def fan_out_parallel(agents: list[Agent], task: Task) -> list[Result]:
    # Each agent gets an independent slice. Zero coordination overhead.
    slices = distribute(task.input, len(agents))
    calls = [agent.run(slice) for agent, slice in zip(agents, slices)]
    results = await asyncio.gather(*calls)  # true parallel, no shared state
    return merge(results)

# Benchmark: 4 agents on 4 independent sub-tasks
# 34s serial → 9s parallel (3.9x speedup, near-linear)
# Overhead: only the merge step (~0.3s)
```

**For read-after-write (medium coupling):** Lock-free shared state via CRDTs.

Conflict-free Replicated Data Types (CRDTs) enable multiple agents to update shared state concurrently with automatic convergence—no locks, no coordinator, no merge conflicts. The CRDT handles conflict resolution mathematically; agents just read and write.

```python
# Using Yjs CRDT for shared document state
from yjs import Doc
from yjs.collections import Array

doc = Doc()
shared_text = doc.get_text("agent_workspace")
shared_array = doc.get_array("tool_results")

# Agent A writes
shared_text.delete(0, len(shared_text))
shared_text.insert(0, "Step 1: Query database")
shared_array.insert(0, {"tool": "sql", "result": "rows"})

# Agent B reads (and writes) concurrently
# Yjs guarantees eventual convergence without locks
# Both agents see consistent state after sync
```

The CodeCRDT paper (arXiv:2509.19318) tested this across 600 trials with Claude Sonnet 4.5. Observation-driven coordination via CRDTs yielded **strong eventual consistency**—lock-free, conflict-free concurrent code generation. Speedup on truly independent subtasks was near-linear; on tightly-coupled tasks, parallel agents were slower than serial, confirming that coupling type is the governing variable.

**For concurrent writes (high coupling):** Consider whether multi-agent is the right tool. If two agents must coordinate writes to the same artifact, you have two options:
1. **Serialize writes** via a single writer agent (eliminates conflicts but removes parallelism benefit).
2. **Use operation-based CRDTs** with semantic merge resolution (agents emit operations, a merge function resolves conflicts at the semantic level).

### 3. Profile the coordination cost

Before scaling agent count, run a load test that measures:

```python
from collections import defaultdict
import time

class CoordinationProfiler:
    def __init__(self):
        self.hops: list[dict] = []

    def record_hop(self, from_agent: str, to_agent: str, operation: str, latency_ms: float):
        self.hops.append({
            "from": from_agent,
            "to": to_agent,
            "op": operation,
            "latency_ms": latency_ms,
            "timestamp": time.time()
        })

    def summary(self) -> dict:
        by_op = defaultdict(list)
        for h in self.hops:
            by_op[h["op"]].append(h["latency_ms"])

        total_coordination = sum(h["latency_ms"] for h in self.hops)
        serial_equivalent = sum(
            max(v) for v in by_op.values()
        )  # if ops ran sequentially in worst case

        return {
            "total_coordination_ms": total_coordination,
            "serial_equivalent_ms": serial_equivalent,
            "overhead_ratio": total_coordination / serial_equivalent
            if serial_equivalent else 1.0,
            "by_operation": {
                op: {"p50": sorted(v)[len(v)//2], "p95": sorted(v)[int(len(v)*0.95)]}
                for op, v in by_op.items()
            }
        }
```

A ratio > 1.0 means coordination overhead exceeds what parallelism saves. The threshold varies by task—but teams at billion-event scale report 2–5x overhead ratios on medium-coupling tasks, making the case for architecture changes.

### 4. The coordination budget

Set an explicit **coordination budget**: maximum acceptable overhead per task tier.

| Task tier | Max coordination overhead | Recommended agents |
|-----------|--------------------------|-------------------|
| Fast lookup (<1s) | 5% of total | 1–2 |
| Analysis (1–30s) | 15% | 2–4 |
| Long-running synthesis | 30% | 4–8 |

If a task exceeds its budget, either reduce agent count or switch to a lower-coupling pattern.

## Receipt

> Receipt pending — 2026-07-28. The CoordinationProfiler and CRDT example require integration with a live multi-agent framework (LangGraph or custom). The fan-out benchmark reflects production numbers from Stoneforge HN reports (HN:47267105) and CodeCRDT 600-trial results (arXiv:2509.19318). MAST taxonomy failure breakdown sourced from Tessary.ai blog (June 2026, NeurIPS 2025 MAST dataset).

## See also

- [S-996 · The Harness Matters More Stack](/stacks/s996-the-harness-matters-more-stack-when-your-model-isnt-the-problem.md) — MAST taxonomy context, harness vs. model distinction
- [S-1013 · The Multi-Agent Boundary Stack](/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — shared state disagreement as a boundary problem
- [S-5 · Multi-Agent Patterns](/stacks/s05-multi-agent-patterns.md) — structural patterns including fan-out
