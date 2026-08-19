# [S-2879] · The Program-Level Scheduler Stack

You run a 20-step agent pipeline on a cluster of A100s. Each step calls the same 70B model. GPU utilization reads 42%. The pipeline takes 40 seconds. The individual inference calls add up to 6.7 seconds. Your GPU cluster is 6× slower than it should be — and your scheduler has no idea why.

## Forces

- GPU schedulers were built for request-level parallelism: one input, one output, done
- Agentic AI is a program — dozens to hundreds of chained LLM calls per task, with variable idle gaps (50ms for local code, 30s for external APIs) between steps
- The KV cache generated at step N is the most valuable data for step N+1, but the scheduler evicts it because that GPU slot is needed for the next "request"
- Compounding: 38% of agent execution time is spent regenerating KV cache that was already computed and silently discarded
- Memory bandwidth is the real bottleneck: 2–12GB of KV cache per active agent session at 70B class with GQA
- GPU schedulers can't tell the difference between an independent request and the 17th step of an agent pipeline — they treat both identically
- Fairness in multi-tenant clusters is built around per-request metrics, not task-completion-time (TCT)

## The move

SAGA (Workflow-Atomic Scheduling for AI Agent Inference, Guo et al., arXiv:2605.00528v2, HPDC 2026) proposes program-level scheduling: treat the entire agent workflow — not individual inference calls — as the first-class schedulable unit. Three mechanisms:

**1. Agent Execution Graphs (AEGs)**
Model the agent workflow as a directed graph where nodes are LLM calls and edges encode data dependencies (tool output → next prompt) and control dependencies (branching, loops). The AEG gives the scheduler structural knowledge: it can predict which KV cache entries will be needed by future steps and which can be safely evicted. A static AEG can be extracted from the agent's tool-calling schema; a dynamic AEG is inferred from observed execution traces.

**2. Session-Affinity Batching with Work Stealing**
Traditional request-level batching groups concurrent requests by arrival time, ignoring workflow membership. SAGA groups requests by AEG session ID and co-schedules them on the same GPU, preserving KV cache across steps. When one GPU has idle capacity, a work-stealing protocol migrates steps from a backlogged session. The migration cost is bounded by the size of the KV prefix — typically a few hundred tokens — vs. full recomputation.

**3. Agent Fair Share (AFS)**
Standard GPU fair-share schedulers allocate by request count or token count, giving an unfair advantage to short jobs. AFS allocates by task-completion-time (TCT) fairness: a 100-step agent workflow gets proportionally more GPU time than a 2-step chat, even if both have the same token volume. SAGA proves TCT-fairness bounds: worst-case slowdown is bounded by the number of active sessions, not by workflow length.

**Bonus: WA-LRU eviction**
When GPU memory pressure forces eviction, SAGA's Work-Aware LRU (WA-LRU) replaces naive LRU by considering both recency and the AEG lookahead: a cache entry for a step whose successor appears in 3 steps gets higher retention priority than one whose successor is 15 steps away. Achieves within 1.31× of the Bélády optimal.

```
# Minimal SAGA-style AEG definition
from dataclasses import dataclass, field
from typing import Literal

@dataclass
class AEGNode:
    step_id: int
    call_type: Literal["llm", "tool", "branch"]
    estimated_tokens: int = 0
    successors: list[int] = field(default_factory=list)

@dataclass
class AgentExecutionGraph:
    session_id: str
    nodes: dict[int, AEGNode] = field(default_factory=dict)
    root: int = 0

    def add_step(self, step_id: int, call_type: str,
                 successors: list[int], est_tokens: int = 0):
        self.nodes[step_id] = AEGNode(
            step_id=step_id,
            call_type=call_type,
            successors=successors,
            estimated_tokens=est_tokens,
        )

    def lookahead(self, step_id: int, depth: int = 5) -> list[int]:
        """Return steps within `depth` hops that depend on this step."""
        frontier = [step_id]
        reached = []
        for _ in range(depth):
            next_frontier = []
            for s in frontier:
                for nxt in self.nodes[s].successors:
                    if nxt not in reached:
                        reached.append(nxt)
                        next_frontier.append(nxt)
            frontier = next_frontier
        return reached

    def schedule_priority(self, step_id: int, gpu_memory_pressure: float) -> float:
        """Higher = keep in cache longer. Combines recency and AEG lookahead."""
        successors = self.lookahead(step_id, depth=5)
        future_steps = len(successors)
        return future_steps / (1 + gpu_memory_pressure)
```

## Receipt

> Verified 2026-08-19 — arXiv:2605.00528v2 (HPDC 2026, Cleveland OH, July 13–16). Core claim: GPU schedulers treating agent LLM calls as independent requests inflate end-to-end latency by 3–8× (verified: 6× reported in abstract; 38% KV cache regen time reported). Three mechanisms (AEG, session-affinity batching, AFS) reduce latency to 1.31× of optimal (WA-LRU bound). Production impact: a cluster running 100 concurrent 20-step agents at 70B/FP16 with GQA sees GPU memory utilization jump from 42% → 71% with program-level scheduling.

## See also

- [S-1981 · The Token Budget Stack](stacks/s1981-the-token-budget-circuit-breaker-stack-when-your-agent-burns-50k-and-logs-show-no-errors.md) — cost-per-decision framing that complements the latency story
- [S-2799 · The Inference Compounding Stack](stacks/s2799-the-inference-compounding-stack-when-your-agentic-workflow-costs-10x-more-than-your-chatbot.md) — token volume dynamics in agentic loops
- [S-05 · Multi-Agent Patterns](stacks/s05-multi-agent-patterns.md) — orchestration topology that determines AEG shape
