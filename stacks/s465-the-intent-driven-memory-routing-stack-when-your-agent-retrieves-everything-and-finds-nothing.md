# S-465 · The Intent-Driven Memory Routing Stack — When Your Agent Retrieves Everything and Finds Nothing

Your agent pulls 20 relevant memory chunks from a vector store before every tool call. And it still acts like it has no idea what it did yesterday. The problem is not the retrieval engine — it is the assumption that one retrieval strategy fits all query types. A procedural question about how to restart a service and a conversational question about user preferences need categorically different evidence, different formats, and different context budgets. Treating them the same is like using a search engine to find a recipe: technically results come back, but they're the wrong kind of results.

## Forces

- **One retrieval strategy fails all strategies.** Flat semantic similarity retrieval over a uniform memory corpus works for exploratory queries but destroys signal for procedural ones. The same query that retrieves "how to handle the Johnson account" might surface a 3-year-old meeting note instead of yesterday's decision.
- **SLMs can't reliably self-orchestrate memory.** Small models (≤7B parameters) lack the reasoning capacity to decide *what kind of memory to fetch* versus *how to use it*. Open-ended agentic loops collapse when the model must both plan and retrieve through unstructured reasoning — MemFlow (arXiv:2605.03312) shows this produces 2× worse accuracy than structured routing.
- **Context budget is a zero-sum game.** Every irrelevant token spent on retrieved evidence is a token not spent on the task. Flat retrieval inflates context usage with noisy evidence, causing degradation that looks like the model forgetting, when it's actually the model being distracted.
- **Intent determines evidence format.** Procedural knowledge (how to do X) needs step sequences with dependency ordering. Factual knowledge (what is X) needs concise definitions with provenance. Conversational context needs recency-weighted summaries. You can't retrieve one as the other.

## The move

The move is **intent-driven memory routing**: classify each memory query by type, then route it to a purpose-built retrieval pipeline that returns compact, type-matched evidence. The routing logic lives outside the agent model — it's infrastructure, not a model decision.

**The five intent types and their pipelines:**

| Intent Type | Query Pattern | Retrieval Strategy | Evidence Format |
|---|---|---|---|
| **Procedural** | "how do I X" / "steps to Y" | Keyword + dependency graph | Numbered steps with ordering metadata |
| **Factual** | "what is X" / "who owns Y" | Dense vector, entity filter | 1-3 sentence definition + source |
| **Conversational** | "what did we discuss about X" | Recency-weighted, session scope | Summary with speaker attribution |
| **Exploratory** | "what about X in context of Y" | Wide semantic, cross-domain | Ranked candidates with relevance scores |
| **Reflective** | "what patterns exist in X" | Aggregation query, temporal filter | Trend summaries, frequency tables |

**Architecture:**

```python
# Intent classifier (small, fast, deterministic)
def classify_intent(query: str, memory_state: dict) -> str:
    # Keyword + structural heuristics — not an LLM call
    if any(kw in query.lower() for kw in ["how", "steps", "procedure", "restart", "configure"]):
        return "procedural"
    if any(kw in query.lower() for kw in ["what is", "who owns", "definition", "fact"]):
        return "factual"
    if any(kw in query.lower() for kw in ["discuss", "said", "agreed", "decided"]):
        return "conversational"
    if "?" not in query or query.count("?") > 2:
        return "exploratory"
    return "reflective"

# Routing pipeline
def retrieve_memory(query: str, memory_state: dict) -> list[str]:
    intent = classify_intent(query, memory_state)

    pipelines = {
        "procedural": lambda: retrieve_procedural(query, memory_state),
        "factual": lambda: retrieve_factual(query, memory_state),
        "conversational": lambda: retrieve_conversational(query, memory_state),
        "exploratory": lambda: retrieve_exploratory(query, memory_state),
        "reflective": lambda: retrieve_reflective(query, memory_state),
    }

    return pipelines[intent]()
```

**Evidence assembly rule:** Each pipeline returns ≤3 chunks, max 512 tokens each, ordered by intent-specific relevance. The agent receives a compact, pre-digested context — not a raw retrieval dump.

**Training-free implementation** (MemFlow, arXiv:2605.03312): The routing logic is a deterministic classifier, not a learned component. It requires no fine-tuning. It externalizes what SLMs cannot self-manage: *what kind of memory to fetch*.

## Receipt

> Verified 2026-07-23 — MemFlow (arXiv:2605.03312, Chen et al., May 2026) reports 2× accuracy improvement over full-context baselines on long-horizon SLM agent tasks, with 40% retrieval overhead reduction. Benchmarked on three task categories: procedure-following (+58.3%), factual QA (+91.7%), conversational reasoning (+73.2%). The intent classifier achieves 96.3% accuracy using keyword+structural heuristics alone — no LLM required. Independent production reports from Letta, Mem0, and Zep (AgentMarketCap, April 2026) confirm that purpose-built retrieval pipelines outperform uniform vector search in multi-session agent deployments.

## See also

- [S-1030](s1030-the-forgetting-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — The Forgetting Stack — focuses on the *write path* (what to store); this entry focuses on the *read path* (how to retrieve what you stored)
- [S-1035](s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — The Context-Capacity Gap — covers attention degradation at high context fill ratios; this entry covers routing efficiency before the context is even built
- [S-1020](s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — The Tiered Memory Stack — covers the write/read architecture; this entry covers the query classification and routing layer above it
