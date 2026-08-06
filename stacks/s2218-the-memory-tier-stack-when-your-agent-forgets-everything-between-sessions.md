# S-2218 · The Memory Tier Stack

_When your agent works fine within a session but loses everything the moment it starts a new one — facts about the user, project state, tool outcomes, all gone._

## Forces

- **The context window is not memory.** It is a performance surface. What fits in-context stays; what doesn't disappears. Teams confuse "fits in context" with "persisted."
- **Every memory type has a different access pattern.** Checkpoint state (pause/resume) needs different storage and retrieval than cross-session user facts or tool-use history. Treating them as one bucket is the root cause of most memory failures.
- **Vector similarity is not knowledge.** Storing everything as embeddings in a vector DB and retrieving by cosine similarity is fuzzy, slow, and hallucination-prone for exact facts. Precision vs. recall tradeoffs that don't appear in demos show up in production.
- **The retrieval-then-reason gap.** Agents must first retrieve relevant memory, then reason over it, then act. These are separate pipeline stages that fail independently — and most teams only test the happy path.

## The Move

Layer memory by access pattern, not by technology. Four types, four storage strategies:

- **Working memory** — Everything currently in-flight. Stored in the context window (KV or structured state). Used for pause/resume checkpoints. If the agent crashes mid-task, this is what you reload.
- **Episodic memory** — A log of events, tool calls, and outcomes. Stored with dual indices: a time-series index (for "what happened recently?") and an embedding index (for "what was similar before?"). This is what lets an agent say "the last time I tried this tool, it timed out."
- **Semantic memory** — Consolidated facts about users, projects, and domain knowledge. Stored in a structured store (key-value, graph DB, or relational) with exact-match retrieval — NOT a vector store for facts that must be precise. This is what "remembering" actually means for entities with specific values.
- **Procedural memory** — System prompts, tool definitions, skill libraries, and agent configuration. Version-controlled in code. Updated through deployment, not runtime writes.

**On retrieval**: Build a two-stage pipeline. First stage is exact-match or filtered lookup (fast, precise). Second stage is vector similarity search (for broader context). Never route factual lookups through vector similarity alone.

**On the framework question**: Mem0 (semantic layer, token-efficient), Zep/Graphiti (episodic with temporal reasoning), Letta (stateful agentic runtime), and LangMem (LangChain integration) are not competitors — they solve different tiers. Mem0 is the most widely deployed for cross-session user memory. Teams routinely run two or three of these simultaneously for different layers.

## Evidence

- **Research paper:** Perea.ai's "Agent Memory in Production" (2026-05-07, CC BY 4.0) establishes the four-type taxonomy (working/episodic/semantic/procedural), maps four frameworks to tiers (Mem0, Zep/Graphiti, Letta, LangMem), and benchmarks vector DBs by use case — Qdrant as production default at 26-29ms p99, Weaviate for tool registries with 50+ agents, pgvector for under-10M records, Pinecone for managed simplicity. — [https://www.perea.ai/research/agent-memory-production](https://www.perea.ai/research/agent-memory-production)
- **Engineering blog:** Slava Dubrov's "AI Agent Memory Architecture in 2026" (2026-02-14) distills the hot/cold/document split with concrete storage backends: hot checkpoints as structured JSON, cold facts as key-value or vector store, documents as versioned files. Stresses starting with the failure mode, not the technology. — [https://slavadubrov.github.io/blog/2026/02/14/the-cortex--architecting-memory-for-ai-agents](https://slavadubrov.github.io/blog/2026/02/14/the-cortex--architecting-memory-for-ai-agents)
- **Comparison review:** AI Workflow Lab and CallSphere both independently confirm the framework differentiation — Mem0 wins on token efficiency and API simplicity, Zep wins on temporal reasoning ("how did this fact change over time?"), Letta wins as a stateful agent runtime rather than a memory layer. Multiple sources confirm Mem0 is the most deployed for cross-session user memory as of mid-2026. — [https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026), [https://callsphere.ai/blog/td30-fw-mem0-vs-zep-vs-letta-2026-honest-comparison-guide](https://callsphere.ai/blog/td30-fw-mem0-vs-zep-vs-letta-2026-honest-comparison-guide)
- **Show HN:** AgentKeeper (2026-03) surfaced HN community pain — agents losing memory when switching providers or across sessions — and proposed cognitive persistence as a dedicated layer. — [https://news.ycombinator.com/item?id=47217244](https://news.ycombinator.com/item?id=47217244)
- **GitHub:** The broader MCP ecosystem shows the tool tier is mature (MCP itself is the tool-access standard per perea.ai), but the memory tier is where production systems are actively building — Mem0 (21k+ GitHub stars), Agent-MCP (1.2k stars, multi-agent coordination via MCP), and specialized MCP memory tools (mcp-memory, HN-MCP for agentic news research) confirm active development. — [https://github.com/NirDiamant/agents-towards-production](https://github.com/NirDiamant/agents-towards-production)

## Gotchas

- **Don't use a vector store for exact facts.** Storing user names, IDs, prices, and dates in a vector DB and retrieving by similarity is a common mistake that produces confident wrong answers. Use key-value or relational for precision data; vector for context and similarity.
- **Episodic memory grows unbounded without a retention policy.** Every tool call, every reasoning step, every user message — all of it logged. Without a policy to summarize, compress, or expire old episodes, you get retrieval pollution (relevant facts buried under noise) and cost inflation.
- **The working memory checkpoint is often the missing piece.** Teams implement cross-session memory (semantic) but skip the per-session checkpoint, so mid-task crashes lose everything regardless of how good the long-term memory is.
- **Framework proliferation is a real risk.** Running Mem0 + Zep + Letta simultaneously means three memory systems with three APIs, three failure modes, and three sync consistency problems. Start with one framework for the dominant use case; add layers only when you have a clear gap.
