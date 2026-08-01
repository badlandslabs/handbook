# S-1975 · The Scaffold Spectrum Stack — When Your Agent Architecture Is Invisible and Untestable

You chose your model carefully. You spent two weeks comparing GPT-4o, Claude Sonnet, and Gemini 2.5. But your agent's performance is determined by something nobody benchmarks and nobody tests: the scaffold. The control loop, the context strategy, the tool definition layer — the plumbing that determines whether your model succeeds or silently fails. An 11–15 point performance spread exists for the same model across different scaffolds, dwarfing most inter-model differences. Most teams have no way to measure it.

## Forces

- **Scaffolds resist discrete classification.** They occupy positions along continuous spectra, not neat categories. Control strategies range from fixed pipelines to Monte Carlo Tree Search. Tool counts range from 0 to 37. Context compaction spans seven distinct strategies. Traditional taxonomy fails — you cannot compare scaffolds by type.
- **Trajectory analysis misses the scaffold.** Agent benchmarks observe what agents *do* — tool call sequences, success rates, token counts. They never examine the code that determines *why*. A scaffold can generate identical-looking trajectories with opposite failure modes.
- **The scaffold is the hard part.** Five loop primitives (ReAct, generate-test-repair, plan-execute, multi-attempt retry, tree search) function as composable building blocks. Eleven of 13 studied open-source agents compose multiple primitives — but the interactions between primitives are where production failures emerge, not in the primitives themselves.
- **Scaffold choice is irreversible and invisible.** Switching scaffolds requires rebuilding the agent's core reasoning infrastructure. Unlike prompts, scaffolds are code. Unlike model weights, they are not shipped with evals.
- **Resource management is the unloved dimension.** Control architecture and tool interfaces get attention. Resource management — how the scaffold handles context budget, token accounting, and memory pressure — is systematically under-engineered, yet directly determines whether long-running agents survive or crash silently.

## The move

### The 12-Dimensional Scaffold Map

Map every agent scaffold across 12 dimensions organized into three layers. This is the only framework derived from source-code analysis of real systems, not from capability surveys.

**Layer 1: Control Architecture (4 dimensions)**
- **Control primitive:** ReAct | generate-test-repair | plan-execute | multi-attempt | tree search
- **Control composition:** single primitive | 2+ primitives composed | adaptive switching
- **Planning horizon:** zero-shot | single-step lookahead | full trajectory planning
- **Recovery strategy:** none | retry-within-turn | full rollback

**Layer 2: Tool & Environment Interface (4 dimensions)**
- **Tool count:** range 0–37 across production systems
- **Tool definition style:** hardcoded | generated | dynamically discovered
- **Environment model:** stateless | stateful | partial observability handling
- **Sandboxing:** none | process | container | VM

**Layer 3: Resource Management (4 dimensions)**
- **Context strategy:** full history | truncation | summarization | structured compression | pointer-based
- **Token budgeting:** none | soft cap | hard cap | adaptive budget
- **Memory model:** ephemeral | persistent | hybrid
- **Error propagation:** silent | logged | structured failure modes

### The Spectrum Positioning Test

For each dimension, plot your scaffold's position. Gaps between dimensions are where failures live:

```
Fixed pipeline ─────────────── MCTS
     ↑                          ↑
  s1027 (loops forever)    No safety bounds
```

### The Five Primitives and Their Composition Failures

| Primitive | Strength | Failure Mode | Composites With |
|-----------|----------|-------------|-----------------|
| ReAct | General-purpose reasoning | Token spiral under ambiguous goals | plan-execute, multi-attempt |
| Generate-test-repair | Correctness at cost of latency | Infinite repair loops without exit signal | multi-attempt, tree search |
| Plan-execute | Structured long-horizon tasks | Brittle plan execution; context loss on failure | ReAct, retry |
| Multi-attempt retry | Reliability under transient failure | Escalating wrongness; each attempt compounds error | all |
| Tree search | Thorough exploration | Exponential token cost; context explosion | generate-test-repair |

### The Scaffold Audit Protocol

Run this before choosing or building any scaffold:

1. **Inventory your primitives.** List every control loop in your scaffold. Most agents have 2–4 interacting loops. If you cannot name them all, you cannot test them all.
2. **Measure per-dimension position.** Score each of the 12 dimensions. The gaps — dimensions scored low or ambiguous — are your failure surface.
3. **Stress-test the composition.** Where two primitives meet, inject failure. If a generate-test-repair loop is wrapped by a multi-attempt retry, what happens after 5 failed repairs? If a ReAct planner calls a plan-execute worker, what survives a context overflow in the worker?
4. **Measure the scaffold gap.** Run the same task with two different scaffolds on the same model. The difference is your scaffold contribution to performance. If you cannot measure it, you cannot improve it.
5. **Treat resource management as Tier 1.** Context strategy and token budgeting are not operational concerns — they are architectural decisions that determine whether your agent survives a long task or silently degrades.

### Context Strategy Spectrum

The seven strategies from most to least aggressive:

1. **Full history** — everything retained, no compaction
2. **Round-window** — last N turns retained
3. **Importance-weighted** — retain high-salience messages, drop low
4. **Semantic compression** — summarize by topic cluster
5. **Structural compression** — preserve structure, compress prose (S-1962)
6. **Pointer-based** — external store, reference by pointer (arXiv:2511.22729)
7. **Tiered retrieval** — different storage backends by memory type

Pointer-based is the only strategy that preserves full tool outputs without information loss. Every compression strategy risks fidelity loss. Choose deliberately.

```python
# Minimal scaffold audit — score your 12 dimensions
# Run this against your production scaffold

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List

class ControlPrimitive(Enum):
    REACT = auto()
    GENERATE_TEST_REPAIR = auto()
    PLAN_EXECUTE = auto()
    MULTI_ATTEMPT = auto()
    TREE_SEARCH = auto()
    CUSTOM = auto()

class ContextStrategy(Enum):
    FULL_HISTORY = 7      # no compression
    ROUND_WINDOW = 6      # last N turns
    IMPORTANCE_WEIGHTED = 5
    SEMANTIC_COMPRESSION = 4
    STRUCTURAL_COMPRESSION = 3
    POINTER_BASED = 2     # external store
    TIERED_RETRIEVAL = 1  # backend by type

@dataclass
class ScaffoldProfile:
    """Map your agent's scaffold across 12 dimensions."""
    control_primitives: List[ControlPrimitive] = field(default_factory=list)
    control_composition: str = "single"  # single | multi | adaptive
    planning_horizon: str = "zero-shot"  # zero-shot | single-step | full-trajectory
    recovery_strategy: str = "none"  # none | retry | rollback
    tool_count: int = 0
    tool_definition_style: str = "hardcoded"
    environment_model: str = "stateless"
    sandboxing: str = "none"  # none | process | container | vm
    context_strategy: ContextStrategy = ContextStrategy.FULL_HISTORY
    token_budgeting: str = "none"  # none | soft | hard | adaptive
    memory_model: str = "ephemeral"
    error_propagation: str = "silent"

    def audit_gaps(self) -> List[str]:
        """Identify scaffold gaps — dimensions with high failure risk."""
        gaps = []
        if len(self.control_primitives) > 1 and self.recovery_strategy == "none":
            gaps.append("multi-primitive composition with no recovery strategy")
        if self.context_strategy.value <= 4:
            gaps.append(f"context compression at level {self.context_strategy.value} — check fidelity")
        if self.tool_count > 20 and self.token_budgeting == "none":
            gaps.append(f"{self.tool_count} tools with no token budget — context explosion risk")
        if self.control_composition == "multi" and self.planning_horizon == "zero-shot":
            gaps.append("multi-primitive scaffold with no lookahead — reactive only")
        return gaps

# Usage: profile = ScaffoldProfile(
#     control_primitives=[ControlPrimitive.REACT, ControlPrimitive.MULTI_ATTEMPT],
#     control_composition="multi",
#     planning_horizon="single-step",
#     recovery_strategy="retry",
#     tool_count=12,
#     context_strategy=ContextStrategy.ROUND_WINDOW,
#     token_budgeting="hard",
# )
# print(profile.audit_gaps())
```

## Receipt

> Verified 2026-08-01 — Scaffold dimensions and primitives from arXiv:2604.03515v1 (Rombaut, Huawei Canada, Apr 2026), source-code analysis of 13 open-source coding agent scaffolds. Context strategy spectrum and pointer-based architecture from arXiv:2511.22729 (IBM Research Brazil, Nov 2025). Scaffold gap statistics (11–15 point spread) from AlphaEval cited in the scaffold taxonomy paper. All five loop primitives and their failure modes documented from the same source.

## See also

- [S-1027 · The Scaffold Stack](/stacks/s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — scaffold loop detection and graceful stop
- [S-1336 · The Scaffold-Is-the-Model Stack](/stacks/s1336-the-scaffold-is-the-model-stack-when-your-agent-performance-has-nothing-to-do-with-the-llm-you-chose.md) — scaffold as the primary performance lever
- [S-1962 · The Recursive Fidelity Stack](/stacks/s1962-the-recursive-fidelity-stack-when-your-summarization-middleware-silently-inverts-your-most-important-constraints.md) — structural compression as a fidelity risk
- [S-1548 · The Reasoning Token Tax Stack](/stacks/s1548-the-reasoning-token-tax-stack-when-your-agent-quietly-spends-9x-what-you-budgeted.md) — resource management and cost control
