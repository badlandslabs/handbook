# S-1029 · The Agentic RAG Control Stack — When Your Retrieval Loop Runs All Night Without Answering

You shipped agentic RAG because basic RAG couldn't handle multi-hop questions. The agent plans, retrieves, evaluates, revises — sounds right. In production you watch the token counter climb past the estimate. Then past it again. Then you find the trace: 47 retrieval steps, no answer, $18.72 on a single query. The model didn't fail. The control loop did. This is the **agentic RAG control stack problem** — and "the model got worse" is the wrong diagnosis every time.

## Forces

- **Agentic RAG is RAG plus a control system. Control systems need constraints.** The loop (plan → retrieve → evaluate → decide → repeat) gives the agent flexibility but no boundaries. An agent uncertain about whether it has enough context will retrieve again — and again, and again. Without explicit stopping rules, the loop runs until the context window fills or the budget exhausts.
- **Retrieval quality degrades under loop pressure.** Early in the loop, queries are precise. By iteration 15, the agent is broadening and rephrasing in ways that drift from the original intent. This is *retrieval thrash* — not a retrieval problem, but a control problem: the agent is searching for a signal it already retrieved but didn't recognize.
- **Tool storms compound token cost exponentially.** Agentic RAG loops often call multiple tools per iteration (vector search, reranker, web search, knowledge graph). A 20-step loop with 3 tools per step is 60 API calls. Each call adds latency and cost. The Microsoft Research finding — 30x cost variance on identical tasks — is largely explained by uncontrolled loop depth, not model inconsistency.
- **Context bloat creates a secondary hallucination surface.** Each iteration injects retrieved chunks into context. Without a discard strategy, context fills with stale, irrelevant, or redundant chunks. The LLM confidently synthesizes from a noisy context, producing fluent wrong answers. The failure looks like a model hallucination; the fix is in the control layer.
- **Stopping rules need to be grounded in retrieval quality, not model confidence.** The agent's own "I have enough context" judgment is unreliable — models are systematically overconfident. A budget-based stop (max N iterations) is a floor, not a ceiling. Quality-based stops (answerability score, convergence detection, citation overlap check) are what actually prevent runaway loops.

## The move

**Build the control plane first, not last.**

### 1. Retrieval quality gate (before generation)

```python
from dataclasses import dataclass
import numpy as np

@dataclass
class RetrievalResult:
    chunks: list[str]
    scores: list[float]
    query: str

def check_retrieval_quality(result: RetrievalResult) -> dict:
    """
    Three signals: score spread, answerability, novelty.
    Fail fast on any gate before continuing the loop.
    """
    avg_score = np.mean(result.scores)
    score_spread = max(result.scores) - min(result.scores)
    
    # Signal 1: Average score too low → corpus lacks the answer
    score_gate = avg_score < 0.6
    
    # Signal 2: Scores too flat → agent can't discriminate; likely retrieving noise
    spread_gate = score_spread < 0.15
    
    # Signal 3: Chunk overlap with recent retrievals → thrashing
    novelty_ratio = len(set(result.chunks)) / max(len(result.chunks), 1)
    novelty_gate = novelty_ratio < 0.3
    
    return {
        "proceed": not any([score_gate, spread_gate, novelty_gate]),
        "reason": "score_low" if score_gate 
             else "spread_flat" if spread_gate 
             else "novelty_low" if novelty_gate 
             else "ok",
        "avg_score": avg_score,
        "novelty_ratio": novelty_ratio
    }
```

### 2. Convergence detection

```python
def detect_convergence(history: list[dict], window: int = 3) -> bool:
    """
    Check if last `window` answers are semantically similar.
    If the agent keeps producing the same answer after new retrievals,
    additional retrieval is unlikely to help — the ceiling is the corpus.
    """
    if len(history) < window:
        return False
    
    recent_answers = [h["answer_text"] for h in history[-window:]]
    # Simple token-overlap proxy; production use embedding cosine
    first_tokens = set(recent_answers[0].split()[:20])
    all_same = all(
        set(a.split()[:20]) == first_tokens 
        for a in recent_answers
    )
    return all_same
```

### 3. Token budget with tiered response

```python
@dataclass
class LoopBudget:
    max_iterations: int = 8       # hard cap
    max_tokens_per_step: int = 4096  # budget per retrieval injection
    warning_at: float = 0.6        # fraction of max context used
    
    def should_stop(self, iteration: int, context_tokens: int) -> str:
        if iteration >= self.max_iterations:
            return "iter_limit"
        if context_tokens > self.warning_at * (128_000 if iteration > 4 else 64_000):
            return "context_warning"
        return "ok"

def tiered_response(budget_hit: str, gathered_chunks: list[str], 
                    generation_model) -> str:
    """
    Graceful degradation when the loop hits a budget limit.
    Don't return nothing; return the best effort with confidence signal.
    """
    if budget_hit and not gathered_chunks:
        return "I don't have sufficient context to answer. [CONFIDENCE: NONE]"
    
    # Force conservative generation with explicit citation requirement
    context = "\n\n".join(gathered_chunks[-3:])  # most recent only
    prompt = f"""Answer from the provided context only. 
If the context doesn't fully answer the question, say so explicitly.
Do not introduce information not in the context.
Context: {context}"""
    
    return generation_model.generate(prompt) + "\n\n[CONFIDENCE: PARTIAL — retrieval loop did not fully converge]"
```

### 4. Observability: trace the control loop, not just the pipeline

The minimum viable agentic RAG trace must include:
- Iteration count, retrieval steps per iteration
- Score distribution per retrieval (not just the top-K)
- Context fill rate (% of max tokens used at each step)
- Convergence signal status (novelty ratio, answerability score)

Without these signals, you cannot distinguish "model got worse" from "loop went off the rails."

## Receipt

> Verified 2026-07-13 — Code concepts from: Mostafa Ibrahim, "Agentic RAG Failure Modes" (TDS, Mar 2026); TheClutch.dev interview on detection strategies; Microsoft Research token consumption analysis showing 30x variance driven by loop depth. Patterns confirmed: retrieval thrash, tool storms, and context bloat are distinct failure modes with distinct fixes. Convergence detection and quality-gated stopping rules are the primary mitigations. Production trace from Zylos Research: 92.5% of production agents still deliver to humans, not downstream software — the control layer is the bottleneck preventing full automation.

## See also

- [S-100](s100-agentic-rag.md) — Agentic RAG architecture basics (plan → retrieve → generate loop)
- [S-221](s221-agentic-rag-production-loop.md) — Production RAG loop design patterns
- [S-979](s979-the-loop-detector-stack-when-your-agent-runs-all-night-draining-your-budget.md) — Loop detection and circuit breakers (general agent loops)
- [S-308](s308-production-rag-the-three-levers-youre-not-pulling.md) — Retrieval engineering levers (chunking, hybrid search, reranking)
