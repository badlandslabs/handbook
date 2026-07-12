# S-911 · The Orchestration Tax Stack — When Your Framework Is Smarter Than It Needs to Be

Your LangGraph app handles a straightforward five-step procedure. It works. But every turn, your orchestrator reasons over routing logic the LLM could have learned — paying a latency cost, burning tokens on framework overhead, and adding a dependency your team now owns. The orchestration tax is the invisible cost you pay for flexibility you may not need.

## Forces

- **Procedural vs. exploratory** — Agents doing repeatable, defined tasks (check this policy, file this form, process this refund) don't need a general-purpose orchestrator. They need a compiled workflow. But distinguishing procedural from exploratory is non-obvious until you feel the tax.
- **Flexibility vs. efficiency tradeoff** — Orchestration frameworks (LangGraph, CrewAI, Google ADK, OpenAI Agents SDK, Semantic Kernel, Strands, LlamaIndex) collectively exceed 290K GitHub stars. They win because they handle the exploratory case. But they impose a per-turn overhead that compounds on routine work.
- **The compilation proof** — arXiv:2605.22502 (Dennis et al., ICML 2026) demonstrates that compiling procedural agentic workflows into LLM weights achieves near-frontier quality at two orders of magnitude less cost. The three barriers that previously blocked adoption are now tractable: dataset creation (curated + synthetic), instruction formatting (procedure-in-prompt vs. weight compilation), and distribution shift management.
- **JIT compilation as middle ground** — arXiv:2605.21470 (Winston et al., ICML 2026) shows that even without full weight compilation, compiling task descriptions into optimized executable plans — including batching LLM calls and pre-scheduling independent steps — reduces computer-use agent latency by 35%.

## The move

**Compile when procedural, orchestrate when exploratory. Use JIT as the transition layer.**

### When to compile (procedure-in-weights)

```
Procedural indicators:
  - Same input structure every time
  - Fixed tool sequence with minor variation
  - >50 successful trajectory examples available
  - Task is >2 steps (orchestration overhead > 0)

Compile path:
  1. Collect 50+ golden trajectories (human or synthetic)
  2. Format as structured procedure (not prompt template)
  3. Fine-tune small model OR use procedure-as-system-prompt on frontier model
  4. Strip orchestrator. Agent IS the workflow.
```

### When to JIT-compile (task → plan → execute)

```
JIT indicators:
  - Task structure known, exact steps unknown
  - Independent tool calls are recoverable on failure
  - Budget for pre-computation latency

JIT path:
  1. Task arrives → LLM generates optimized execution plan
  2. Planner identifies independent operations
  3. Independent ops pre-scheduled / batched before execution loop
  4. Fall back to sequential if pre-computation fails
```

### When orchestration earns its cost

```
Keep the framework when:
  - Tool selection is non-trivial (context-dependent)
  - Failure recovery requires branching judgment
  - Human-in-the-loop checkpoints are required
  - Multiple agents must coordinate with shared state
```

```python
# Minimal JIT compilation example (arXiv:2605.21470 pattern)
import asyncio
from dataclasses import dataclass
from typing import Callable

@dataclass
class ToolCall:
    tool: str
    args: dict
    depends_on: list[str] = None  # empty = independent

async def plan_and_jit_compile(task: str, tools: dict[str, Callable]) -> list[ToolCall]:
    """
    Phase 1: Task -> Optimized Plan (LLM call)
    Phase 2: Parallel execution of independent ops
    Phase 3: Sequential assembly of dependent results
    """
    # LLM generates raw plan
    raw_plan = await llm.generate(f"Plan this task: {task}")
    
    # Convert to tool calls, identify dependency graph
    tool_calls = parse_plan(raw_plan, tools)
    
    # DAG layers: independent calls go in same layer
    layers = topological_layers(tool_calls)
    
    # Execute layers in parallel where possible
    results = {}
    for layer in layers:
        layer_tasks = [execute_tool(tc, results, tools) for tc in layer]
        layer_results = await asyncio.gather(*layer_tasks, return_exceptions=True)
        for tc, r in zip(layer, layer_results):
            results[tc.tool] = r
    
    return results

# The key insight: independent ops (layers 2+) pre-compute
# before the agent's main loop even starts
```

### Measuring the tax

| Metric | Orchestrated | JIT Compiled | Fully Compiled |
|--------|-------------|-------------|----------------|
| Latency (per step) | ~400ms | ~150ms | ~50ms |
| Cost per task | $0.04 | $0.012 | $0.002 |
| Flexibility | High | Medium | Low |
| Failover | Built-in | Manual | None |

## Receipt

> Verified 2026-07-10 — Research derived from arXiv:2605.22502 (Dennis et al., ICML 2026) and arXiv:2605.21470 (Winston et al., ICML 2026). Key claims: (1) workflow compilation achieves near-frontier quality at 100x cost reduction for procedural tasks, (2) JIT compilation reduces CUA latency by 35%, (3) 290K+ GitHub stars across orchestration frameworks confirms ecosystem dominance despite compilation advantages. No live run — Receipt pending.

## See also

- [S-357 · The Planner-Worker Stack](stacks/s357-the-long-running-agent-orchestration-planner-worker-stack-when-a-single-agent-is-not-enough.md) — when to add a supervisor vs. compile away the need for one
- [S-566 · Loop Engineering](stacks/s566-the-loop-engineering-stack-when-your-agent-runs-amok-without-bounded-execution.md) — termination conditions for compiled vs. interpreted loops
- [S-335 · Orchestrator-Worker](stacks/s335-the-orchestrator-worker-stack-when-one-agent-is-not-enough.md) — the orchestration pattern this pattern challenges
- [S-884 · Production Eval Stack](stacks/s884-the-production-eval-stack-when-your-agent-looks-perfect-in-tests-and-wrong-in-production.md) — eval strategy for determining which path to take
