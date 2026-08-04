# S-2109 · The Memory Tier Stack

When your agent completes a task beautifully on Monday, greets you on Tuesday as a complete stranger, and by Thursday has forgotten it even has a user. Statelessness is the default. Forgetting is free. The moment you want continuity — a partner that remembers your preferences, your projects, your corrections — you enter the memory architecture problem.

## Forces

- **Two tiers want to be one system.** Checkpoint stores (conversation continuity, resumability) are write-heavy and low-latency. Semantic memory (user preferences, learned facts) is query-heavy and cross-session. Treating them as the same store is the #1 production mistake.
- **Retrieval is not the same as performance.** Most memory benchmarks measure whether you can fetch a stored fact. Nobody measures whether having that fact makes the agent do anything differently. A 0.89 recall score means the right memory was retrieved — not that the agent used it correctly.
- **Agent-managed vs. infrastructure-managed is a fundamental fork.** Letta/MemGPT gives the agent itself the controls: the LLM calls `search_memory()` and `insert_memory()`. Mem0 and Zep manage retrieval outside the agent — infrastructure decides what surfaces, the agent receives it. Both work. They have different debugging profiles.
- **Simple beats sophisticated on cost.** Letta's own benchmarks show a plain filesystem scoring 74% on memory tasks, beating specialized vector-store libraries. GPU-backed embedders add $0.002–0.01/query at low volume, scaling to thousands per query at production scale. The memory system you can't afford to run is worse than the one you didn't build.

## The Move

Tier your memory by access pattern and lifecycle, not by how clever the retrieval is.

**1. Separate checkpoint store from semantic memory from the start.**
Checkpoint store: SQLite, Postgres, or Redis — write every agent step, support time-travel and resumability. Semantic memory: Mem0, Zep, or a vector store — write once per meaningful event, retrieve many times. These are fundamentally different workloads. A single Postgres table serving both will瘫 on you.

**2. Choose your memory governance model.**
- *Agent-managed (Letta/MemGPT)*: The LLM itself decides what to page in and out of its context window, treating the context as RAM and a database as disk. Good for agents that need behavioral continuity and can be given tool-level control over their own memory. More complex to debug — when the agent forgets something, was it the agent's choice or a bug?
- *Infrastructure-managed (Mem0, Zep, custom)*: Infrastructure handles retrieval; the agent receives memory in its context. Good when you want deterministic retrieval logic, enterprise compliance, or the ability to audit exactly what the agent has access to.

**3. Handle context window pressure with compaction, not infinite context.**
Every LLM call that includes full conversation history hits token limits, cost, and the "lost in the middle" effect (models ignore facts placed far from prompt edges). Microsoft Agent Framework calls this **compaction**: selectively summarizing, collapsing, or truncating older conversation portions before each run. Mechanical compaction (clearing thinking blocks and stale tool results) before heavier summarization saves tokens at zero LLM cost.

**4. Structure memory by cognitive type, not by storage backend.**
| Type | Content | Lifecycle |
|------|---------|----------|
| **Episodic** | What happened when | Short-to-medium, event-driven writes |
| **Semantic** | Facts, preferences, learned knowledge | Long-term, query-driven reads |
| **Procedural** | How to do X, workflow patterns | Stable, reusable across sessions |

Elasticsearch Labs' production implementation uses three separate indices — one per type — with hybrid retrieval (BM25 + dense vectors + cross-encoder reranker) per index. This is overengineered for most use cases, but the separation principle holds at any scale.

**5. Validate that retrieval improves outcomes, not just recall.**
Most memory benchmarks are retrieval tests: fetch a name from 50 turns ago. That proves the pipe works. What you actually need is evidence that the agent *behaves differently* when it has the memory. Build a task-level eval: run the agent with memory, run it without, compare task success rates. If retrieval doesn't move the needle, the memory is theater.

## Evidence

- **arXiv study (June 2026):** Zhou et al. from Shanghai Jiao Tong and Tsinghua evaluated 12 memory systems across 5 benchmark workloads. Key finding: no single memory architecture dominates all scenarios — effectiveness depends on how well the memory structure aligns with the workload bottleneck. Paper proposes a four-module framework: Representation, Storage, Query, Update.
  — https://arxiv.org/html/2606.24775v1

- **Elasticsearch Labs production implementation:** Built a persistent, multi-tenant agent memory layer on Elasticsearch achieving **R@10 = 0.89** across 168 questions with zero cross-tenant leaks. Used three indices (one per memory type) with hybrid BM25 + Jina v5 dense retrieval and cross-encoder reranking. Article explicitly frames context windows as short-term memory — they cannot scale across sessions, become expensive at volume, and suffer from "lost in the middle."
  — https://www.elastic.co/search-labs/blog/agent-memory-elasticsearch

- **Letta (formerly MemGPT) OS-inspired hierarchy:** Treats the LLM context window as RAM, a database as disk, and the agent as the OS that decides what to page in and out. Three tiers: core (in-context, actively used), recall (near-term, paged in on demand), archival (long-term, paged in selectively). Self-reported benchmarks show a plain filesystem scoring 74% on memory tasks — specialized vector stores do not automatically win.
  — https://www.adaptiverecall.com/memory-architecture/letta-memory-hierarchy.php

## Gotchas

- **"We use a vector store" is not a memory architecture.** It describes one component. You also need: what triggers a write, what triggers a retrieval, how you handle contradictions (the agent learned X in session 3 but now says Y in session 7), and how you evict stale memories.
- **Temporal validity is underused.** Zep's key differentiator is treating time as a first-class dimension — facts have validity windows. "User prefers dark mode" is true now but was false before their April 2025 complaint. Without validity windows, retrieval surfaces both and lets the agent sort it out.
- **Memory pollution is real.** The Letta whitepaper on stateful multi-agent systems for video production documents a critical discovery: background agents accumulated behavioral patterns from message history that *overrode explicit system prompt instructions*. The agent's learned behavior can contradict its instructions, with no obvious debugging path.
- **Memory benchmarks measure the pipe, not the outcome.** Mem0's LongMemEval score (49.0%) and Zep's scores tell you retrieval quality. They don't tell you whether having that memory makes your agent complete tasks faster, more accurately, or with fewer corrections. The benchmark you actually need is an A/B eval on your specific task.
