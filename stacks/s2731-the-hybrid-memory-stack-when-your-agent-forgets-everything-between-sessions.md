# S-2731 · The Hybrid Memory Stack — When Your Agent Forgets Everything Between Sessions

You shipped a customer-support agent. The first message goes great. The second message — the next day — starts cold. The agent doesn't know the user's name, their prior issue, or that they prefer JSON over markdown. Every session resets to zero. This is not a bug in the model. This is the default state: LLMs are stateless. Memory is infrastructure you have to build around them.

## Forces

- **Context windows give attention, not memory.** Models begin deprioritizing critical information at 60% context capacity, and filling a 1M-token window costs ~$15 per call — economically impractical for production retrieval.
- **Naive RAG over chat logs is noisy.** Storing raw conversation chunks and retrieving them by semantic similarity returns off-topic context alongside relevant facts. Extracted-fact and graph memory outperform this approach by 20–40 percentage points on the LOCOMO benchmark.
- **The three memory types have incompatible access patterns.** What works for episodic recall (recency, event identity) actively harms semantic retrieval (relevance, relationship traversal). A single storage mechanism — whether context window or vector store — cannot serve both well.
- **Complexity vs. simplicity.** Letta's own benchmarks show a plain filesystem scores 74% on memory tasks, beating some specialized vector-store libraries. The question is never "add memory" but "which memory tier, for what access pattern, at what cost?"

## The Move

Adopt a hybrid episodic-semantic memory architecture with three distinct tiers, each mapped to the cognitive science model that production teams converged on by 2025–2026:

**1. Working memory — the active scratchpad.** The current context window, holding system prompt, active conversation, tool definitions, and immediate state. Capacity is 3–5K curated tokens, not the full context length. Management technique: maintain a lightweight summary of the conversation, discard raw history beyond the last N turns.

**2. Episodic memory — what happened before.** A timestamped event log of past interactions and observations. Retrieved by recency and similarity. Stored in a vector database or structured log. This is your autobiographical record: "user X filed bug Y on date Z." Implement with Mem0 (fact extraction → vector store) or Zep/Graphiti (temporal knowledge graph).

**3. Semantic memory — what the agent knows.** Distilled facts extracted from episodic experience: "user prefers JSON over XML," "this codebase uses pytest, not unittest." Stored in key-value stores, knowledge graphs, or structured databases. Retrieved by relevance and relationship traversal. Zep's Graphiti tracks how facts change over time — when the user moves cities, the old fact is deprecated, not buried.

**4. Procedural memory — how the agent acts.** System prompts, tool definitions, agentic loop instructions. Always present. Never decays. Stored in the agent's prompt layer.

**The reflect pattern** closes the loop between episodic and semantic: at session end, run a lightweight LLM pass that extracts facts from the just-completed interaction and writes them to semantic memory. Claude Diary, fsck.com's episodic memory, Anthropic's "Dreams" (scheduled reflection that surfaces recurring mistakes and team-wide patterns), and claude-mem all implement this. It is the closest thing to a standard practice the field has.

**Framework choice is the second decision, not the first.** Pick your memory tier split before picking Mem0 vs. Letta vs. Zep:
- **Mem0** → extracted facts in a vector store. Fast, simple, LLM-required for every CRUD operation. Best when you want lightweight plug-in memory without graph infrastructure.
- **Letta (MemGPT)** → self-editing memory blocks with explicit core/archival tiering. Best for stateful agents that need to manage their own memory budget. Descended from UC Berkeley's MemGPT research.
- **Zep / Graphiti** → temporal knowledge graph on Neo4j. Best when facts change over time (user moves, product renames, team restructures) and you need the graph to track that change history. Tracks fact provenance and depreciation.
- **Plain filesystem** → surprisingly competitive. 74% on Letta's memory benchmarks, zero infrastructure, full developer control. Start here if your memory needs are simple.

## Evidence

- **Benchmark analysis:** Extracted-fact memory (Mem0) and graph memory (Zep) outperform naive RAG over chat logs by 20–40 percentage points on the LOCOMO benchmark (ACL 2024) — [aiworkflowlab.dev comparison](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026)
- **Platform implementation:** Anthropic's Claude Managed Agents uses filesystem-based memory with an Opus 4.7 model fine-tuned for memory tasks, plus a "Dreams" feature that runs scheduled reflection across sessions to surface recurring patterns and restructure memory stores — [claude.com blog](https://claude.com/blog/claude-managed-agents-memory)
- **Reflect pattern adoption:** The "reflect" pattern (session-end learning loops) is documented across Claude Diary, fsck.com's episodic memory, and claude-mem as the standard mechanism for converting episodic experience into durable semantic facts — [spikelab GitHub gist](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)
- **Memory cost arithmetic:** Full retrieval pipeline (embed + rerank + LLM) costs roughly $0.002–0.01 per query at low volume, scaling to thousands per month at enterprise volume. A plain filesystem eliminates this cost entirely — [spikelab GitHub gist](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)

## Gotchas

- **Don't conflate context window size with memory capacity.** The full context window is not your working memory — it's your retrieval target. Curate it to 3–5K tokens of high-signal, task-relevant content.
- **Naive RAG is not agent memory.** Stuffing raw conversation history into a vector index and retrieving by cosine similarity is the most common mistake. It retrieves off-topic chunks, creates massive storage costs, and has no mechanism for fact reconciliation when the same fact is asserted differently across sessions.
- **Fact decay is unsolved by default.** When a user updates a preference, vector-store retrieval will still surface the old fact unless the framework actively reconciles or depreciates it. Zep/Graphiti handles this structurally; Mem0 requires explicit update/delete operations.
- **Memory CRUD requires an LLM call in most frameworks.** Mem0 requires the LLM to extract and structure facts on every write. This is a latency and cost hit on every conversation turn. Budget for it.
