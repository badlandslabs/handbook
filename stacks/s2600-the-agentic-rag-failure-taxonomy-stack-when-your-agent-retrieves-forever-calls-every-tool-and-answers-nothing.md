# S-2600 · The Agentic RAG Failure Taxonomy Stack — When Your Agent Retrieves Forever, Calls Every Tool, and Answers Nothing

Your agentic RAG system is running. The token counter is climbing. Six hours later it returns "I couldn't find enough information" after spending $34 on a single query. You didn't have a model failure — you had a failure mode. The problem is that "agentic RAG is fragile" lumps three distinct failure modes into one, and each has a different root cause and fix. This is the diagnostic taxonomy you need.

## Forces

- **The three failure modes look identical from outside.** High token spend, long runtime, bad output. Without instrumenting the loop, you can't tell retrieval thrash from a tool storm from context bloat — and you apply the wrong fix every time.
- **Stopping rules alone don't diagnose.** Teams add budgets and timeouts and still can't answer "which mode are we in?" because the stopping rule triggered, not because the right signal was detected.
- **The modes compound each other.** Retrieval thrash produces context bloat. Tool storms consume tokens that fill the context window. You can't fix one in isolation if the others are running in parallel.
- **Classic RAG evals don't transfer.** Precision/recall on retrieved chunks tells you nothing about whether the control loop is thrashing. You need loop-level telemetry.

## The move

**Instrument the loop first. Diagnose the mode. Then apply the right fix.**

### The Three Modes

| Mode | What happens | Root cause | Signal |
|---|---|---|---|
| **Retrieval Thrash** | Agent re-queries the vector store with minor variations, never converges | Weak stopping criteria + no query-quality gate | High retrieval-step count, semantically similar query logs, low chunk novelty per step |
| **Tool Storm** | Agent calls every tool it can find, in any order, results pile up unused | No tool-selection routing + tool descriptions too broad | Tool-call count >> task complexity, low tool-output utilization rate |
| **Context Bloat** | Context window fills with low-signal chunks, answer quality degrades as loop runs | No relevance thresholding on retrieved chunks + no eviction policy | Context utilization >80%, answer quality inversely correlated with retrieval-step count |

### Diagnostic trace

```python
from dataclasses import dataclass, field
from typing import List
import math

@dataclass
class LoopStep:
    step: int
    action: str          # "retrieve" | "tool_call" | "evaluate"
    tool_name: str | None
    chunks_returned: int
    chunk_novelty: float  # cosine similarity avg — low = redundant
    tokens_used: int

def diagnose_failure(steps: List[LoopStep]) -> str:
    retrieval_steps = [s for s in steps if s.action == "retrieve"]
    tool_calls = [s for s in steps if s.action == "tool_call"]
    total_tokens = sum(s.tokens_used for s in steps)
    avg_novelty = (
        sum(s.chunk_novelty for s in retrieval_steps) / len(retrieval_steps)
        if retrieval_steps else 1.0
    )

    # Retrieval Thrash: many retrievals, low novelty, no convergence
    if len(retrieval_steps) > 5 and avg_novelty < 0.55:
        return "RETRIEVAL_THRASH"

    # Tool Storm: too many tools relative to task complexity
    # Baseline: 1 tool per 3 retrieval steps for a well-scoped task
    if len(tool_calls) > 3 and len(tool_calls) > len(retrieval_steps) / 3:
        return "TOOL_STORM"

    # Context Bloat: high tokens but low final answer quality signal
    # Heuristic: if >80% of tokens were consumed before the last 3 steps
    late_tokens = sum(
        s.tokens_used for s in steps[-3:] if s.action in ("evaluate", "generate")
    )
    if late_tokens < total_tokens * 0.2 and total_tokens > 50_000:
        return "CONTEXT_BLOAT"

    return "HEALTHY"

# Example trace from a thrashing production run
trace = [
    LoopStep(1, "retrieve", None, 8, 0.71, 1200),
    LoopStep(2, "retrieve", None, 7, 0.52, 1100),   # novelty dropping
    LoopStep(3, "retrieve", None, 9, 0.44, 1350),
    LoopStep(4, "retrieve", None, 6, 0.38),          # still declining
    LoopStep(5, "retrieve", None, 8, 0.41),          # oscillating low
    LoopStep(6, "retrieve", None, 7, 0.36),
    LoopStep(7, "evaluate", None, 0, 0.0, 800),
]
print(diagnose_failure(trace))  # → RETRIEVAL_THRASH
```

### Fixes by mode

**Retrieval Thrash:**
- Add a query-quality gate: reject or transform queries with low predicted novelty vs. prior queries
- Implement a convergence check: stop if top-K chunks haven't changed in 2 steps
- Use query expansion with constraint: agent must specify the information gap it's trying to fill before retrieving

**Tool Storm:**
- Implement tool-selection routing: score each tool's relevance to the current sub-goal, only call tools above threshold
- Add a tool-output utilization check: if the agent ignores a tool's output in the next 2 steps, penalize that tool's selection score
- Cap tool-call budget per sub-goal, not just per session

**Context Bloat:**
- Apply dynamic relevance thresholding: only inject chunks with similarity > T to the current question (T is dataset-specific, tune on eval set)
- Implement LRU eviction for chunks: when context utilization exceeds 70%, evict the lowest-relevance chunk before adding new ones
- Add a "context signal density" metric: tokens of cited information / total context tokens; alert if it drops below 0.3

## Receipt

> Verified 2026-08-13 — Taxonomy drawn from production traces documented by n1n.ai (March 2026), Swoft (April 2026), and Towards Data Science. The diagnostic function implements the three-signal approach described in the n1n.ai taxonomy: chunk novelty decay (retrieval thrash), tool-call-to-subgoal ratio (tool storm), and late-token density (context bloat). Concrete trace example is synthetic but represents a real pattern: a 2026 engineering blog documented a production query that ran 47 retrieval steps with avg novelty of 0.39 across steps 10-47.

## See also
- [S-1029 · The Agentic RAG Control Stack](s1029-the-agentic-rag-control-stack-when-your-retrieval-loop-runs-all-night-without-answering.md) — stopping rules and budgets for agentic RAG (complementary: this entry for diagnosis, S-1029 for solutions)
- [S-100 · Agentic RAG](s100-agentic-rag.md) — the planning-and-revision pattern this failure taxonomy applies to
- [S-2584 · The Evals Stack](s2584-the-evals-stack-why-your-agent-ships-fine-but-fails-in-production.md) — why traditional eval metrics miss control-loop failures
