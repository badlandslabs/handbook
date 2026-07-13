# S-1030 · The Forgetting Stack: When Your Agent Remembers Everything and Knows Nothing

Your agent has 50,000 stored conversation chunks in a vector database. It retrieves 20 relevant ones before every response. And it still acts like it has no idea who you are. The problem is not retrieval — it is what you chose to write.

## Forces

- **Extraction noise drowns signal.** Most memory systems dump every fact from every conversation into storage. After a month of use, the agent's "memory" is a bloated, contradictory corpus where nothing is findable and everything is equally important.
- **Retrieval crowding defeats relevance.** When everything is stored, semantic similarity retrieval returns the most textually similar chunk, not the most useful one. Recent conversations get buried under old ones. The agent's memory becomes its worst enemy.
- **Context compaction destroys state.** Even without a crash, automatic context compaction (used by Codex, Claude, and most long-context models) silently drops "low-priority" content. Task progress can regress from 97% to 42% mid-session with no warning — a confirmed bug in OpenAI Codex as of 2026.
- **Storage vs. inference is a false trade-off.** Full conversation history is expensive to store and expensive to retrieve. Teams default to "store everything" and pay both costs without solving the actual problem.

## The move

The dominant production pattern is not "store more" — it is **selective write with tiered forgetting**. The architecture has four layers:

- **Tier 1 — Core memory (always in-context):** A small, curated set of facts, preferences, and current task state. Think 200–500 lines that always survive compaction. In Letta/MemGPT this is called "core memory." Practitioners build a `NOW.md` file that acts as a lifeline. This is the agent's working identity — what it is doing right now, who it is working with, what constraints apply.
- **Tier 2 — Episodic memory (vector-backed):** Stored episodes from past sessions. MemGPT pioneered treating these as a paginated "archival storage" that the agent decides to retrieve from. The key innovation: the agent itself decides when to read from archival and when to write to it, not the orchestrator. This requires giving the agent explicit memory management tools.
- **Tier 3 — Semantic memory (graph or structured store):** Extracted facts, preferences, and relationships. Zep (arXiv:2501.13956, 234 citations) uses a temporally-aware dynamic knowledge graph where facts have validity windows — "user prefers dark mode" was true from January to April, not before or after. This handles contradictory information that kills vector-only systems.
- **Tier 4 — Procedural memory:** The agent's own system prompt, learned heuristics, and tool definitions. Often just a versioned system prompt in a database. This is what prevents the agent from forgetting its own instructions during long sessions.

**The critical insight from memv (r/LocalLLaMA):** store only what the agent *failed to predict*. Before extracting knowledge from a new conversation, synthesize what the episode "should" contain from existing memory. Only the prediction errors — the genuinely new information — get stored. Importance emerges from surprise. This cuts write volume by 60–80% and eliminates the retrieval crowding problem.

**The compaction escape hatch:** Explicitly write critical task state (progress %, current goal, completed steps) to a structured file or database that the agent re-reads on startup. This is separate from conversation history — it is structured state, not narrative. The Codex context compaction bug (GitHub issue #25792) shows that compaction silently drops progress tracking unless it is structured and re-loaded.

## Evidence

- **Research paper:** Zep — "A Temporal Knowledge Graph Architecture for Agent Memory" (arXiv:2501.13956, Jan 2025, 234 citations) — introduces validity-window facts in episodic knowledge graphs; outperforms MemGPT on the Deep Memory Retrieval benchmark by maintaining temporal relationships between facts.
- **Community post:** memv on r/LocalLLaMA — predict-calibrate extraction pattern: "Before extracting knowledge from a new conversation, it predicts what the episode should contain given existing knowledge. Only facts that were unpredicted — the prediction errors — get stored." — [memv r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1r18v9c/memv_opensource_memory_for_ai_agents_that_only/)
- **Community post:** 24/7 assistant operator on r/LocalLLaMA — pragmatic three-file system: `NOW.md` (200-line always-in-context lifeline), `MEMORY.md` (agent-curated long-term facts), ChromaDB for full-text episodic search — [CMDRBottoms r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1qrbs69/memory_system_for_ai_agents_that_actually/)
- **Open-source:** AgentKV (Show HN, 2025) — SQLite with memory-mapped vector + graph hybrid storage for agent memory, emphasizing single-file portability and zero-infrastructure deployment — [AgentKV HN](https://github.com/DarkMatterCompiler/agentkv)
- **Open-source:** Hmem (Show HN, 2025) — MCP-based hierarchical memory for coding agents, with explicit tiers for session state vs. project knowledge — [Hmem HN](https://news.ycombinator.com/item?id=47103237)
- **Confirmed bug:** OpenAI Codex context compaction regression — task progress jumping 97% → 42% post-compaction; affects all long coding tasks — [GitHub Issue #25792](https://github.com/openai/codex/issues/25792)
- **Framework:** Letta (MemGPT) — OS-inspired virtual memory paging; agent calls `core_memory_replace`, `archival_memory_search`, `archival_memory_insert` as tool calls; manages its own memory like an OS managing RAM. 22,960 GitHub stars — [Letta GitHub](https://github.com/letta-ai/letta)

## Gotchas

- **"Store everything" is the default and the failure mode.** Teams that pour all conversation history into a vector store end up with a memory that is semantically crowded, contradictory, and computationally expensive. The 2026 production pattern is selective write, not comprehensive capture.
- **Structured state must survive compaction explicitly.** Plain conversation history is not reliable state. If task progress, active goals, or completion checklists exist only in the conversation context, compaction will silently destroy them. Write them to structured files/databases and re-load them on startup.
- **Temporal consistency breaks vector-only systems.** If a user's preference changed in April, a vector store will retrieve the old preference just as readily as the new one unless temporal metadata is explicitly tracked. Zep's validity-window approach is the canonical solution; a simpler version is to tag memories with effective date ranges.
- **The agent must own its memory management.** Architectures where the orchestrator decides when to read/write memory force the LLM to work with whatever the orchestrator decided to surface. Letta's approach — giving the agent explicit memory tools it calls when it deems appropriate — is architecturally cleaner and produces agents that self-manage context.
