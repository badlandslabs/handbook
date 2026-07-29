# S-1842 · The Tiered Memory Stack — When Your Agent Knows Nothing About Yesterday

Your agent spent three sessions learning that this user prefers markdown reports, never CCs finance, and asks clarifying questions before executing. Session four: it outputs a plain-text email CC'ing everyone, and has no memory of the previous three sessions. The agent was not broken — it had no persistent memory layer to break.

This is the cross-session amnesia problem: agents reason brilliantly within a context window and reset completely when it closes. The agents that have broken out of pilot purgatory — running autonomously for weeks, accumulating context, displacing workflow steps — share one architectural feature: a purpose-built, tiered memory layer between the LLM and the rest of the stack.

## Forces

- **Context window ≠ memory.** A 1M-token window is working memory (RAM), not long-term storage. Input cost, attention degradation ("lost in the middle"), and session-scale accumulation make dumping everything into context unworkable at production scale.
- **Not all memory is the same.** Episodic (what happened), semantic (what it means), procedural (how to do it), and state (current working context) have fundamentally different access patterns and storage requirements. Using one retrieval strategy for all four is a common architectural mistake.
- **Retrieval is not cosine similarity.** Vector search is the floor, not the ceiling. Production systems score memories by weighted recency + relevance + importance — which fixes failure modes pure similarity search produces, especially for temporal queries.
- **Compression is lossy.** Storing extracted facts (Mem0-style) or entity graphs (Zep/Graphiti-style) reduces storage cost and token overhead but sacrifices exact-match recall. A deterministic verbatim baseline scores 0.980 exact-match; extraction pipelines score 0.465 at best.
- **Reflection is load-bearing.** The consolidation step that turns raw events into compact, reusable knowledge is not cosmetic. Remove it and long-horizon agents degenerate into repetition within 10–20 sessions.

## The move

Build three distinct memory tiers, each with its own storage, retrieval strategy, and update policy:

- **Tier 1 — Core/Working memory (always in context).** A small, pinned summary: user identity, active goals, current task state. Updated on every session boundary. Size ceiling enforced by the model context limit. This is the agent's short-term memory — low latency, zero retrieval, fully deterministic.
- **Tier 2 — Episodic memory (semantic retrieval).** Timestamped logs of past sessions, tasks, and decisions. Retrieved via hybrid search: vector similarity + recency weighting + explicit importance signals. This is what lets the agent pick up where it left off. Implement reflection/consolidation at session end to compress raw logs into dense summaries before they accumulate beyond retrieval budget.
- **Tier 3 — Semantic/procedural memory (structured storage).** Extracted facts, entity relationships, learned preferences, and agent instructions. Stored as structured records (not raw text) so they can be updated, versioned, and queried relationally. A knowledge graph or temporal graph (e.g., Zep/Graphiti) outperforms flat vector stores when "what was true in Q1?" or "how has this relationship evolved?" are questions the agent needs to answer.
- **Retrieval is a scored blend, not a single pass.** Rank candidates by `(α × recency) + (β × semantic_relevance) + (γ × importance)`, where importance is either user-specified or LLM-judged at write time. Tune α/β/γ per domain — factual recall favors recency, creative tasks favor relevance.
- **Forgetting is explicit policy, not overflow.** Set a retention budget per tier (e.g., core: unbounded; episodic: last 50 sessions + last 10 compressed summaries; semantic: all confirmed facts, age-penalized on retrieval). The agent should know what it has forgotten so it can ask or re-derive, not silently hallucinate continuity.
- **Benchmark before choosing a framework.** The verbatim storage approach (Letta archival) scores 0.917+ exact-match; extraction pipelines (Mem0) score ~0.465; graph pipelines (Zep/Graphiti) score ~0.215. For compliance or contractual recall requirements, verbatim wins. For conversational personalization at scale, extraction wins on storage economics.

## Evidence

- **Benchmark (DecisionSynth, 2026):** Verbatim archival storage (Letta) achieved 0.917–0.922 overall exact-match on 543 held-out decision episodes; Mem0 extraction scored 0.465; Zep/Graphiti scored 0.215. Deterministic verbatim baseline: 0.980. — [WealthSchema comparison](https://www.wealthschema.com/resources/comparisons/mem0-vs-zep-vs-letta-decision-recall-benchmark)
- **Production lift (iterate.ai, citing MemGPT lineage):** Agents with structured memory — storing observations, generating reflective summaries, retrieving by relevance and recency — sustained coherent behavior over extended horizons that stateless agents could not. By 2024, memory architecture had become primary differentiation among enterprise agent platforms. — [iterate.ai Agent Memory Glossary](https://iterate.ai/ai-glossary/agent-memory)
- **Snowflake data agent (RockB blog, May 2026):** Adding a memory context layer to a Snowflake data agent produced **20% accuracy improvement** and **39% fewer tool calls** compared to the same agent without persistent memory. — [RockB Agent Memory Guide 2026](https://baeseokjae.github.io/posts/agent-memory-architecture-guide-2026/)

## Gotchas

- **Don't use a vector store as the only retrieval layer.** Pure semantic similarity misses temporal queries ("what did we do last Tuesday?"), importance signals, and recency. It also degrades as the corpus grows — retrieval noise compounds.
- **Don't skip reflection/consolidation.** Raw session logs accumulate beyond a retrievable scale within 20–30 sessions. Without a compression step at session boundaries, episodic memory becomes unqueryable and the agent either ignores it or retrieves irrelevant noise.
- **Don't assume compression is free.** Extracting facts into semantic memory (Mem0-style) reduces token overhead and storage cost significantly, but the lossy compression is measurable on exact-match benchmarks. For domains where precision matters (legal, financial, medical), the trade-off may not be worth it.
- **Don't treat all memory types the same.** Procedural memory (agent instructions, learned skills) needs versioning and diffing, not vector retrieval. Episodic memory needs temporal indexing. Semantic memory needs relational queries. Mixing these into one store creates retrieval conflicts.
