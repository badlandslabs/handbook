# S-1861 · The Memory Consolidation Pipeline Stack — When Your Agent Remembers Everything and Knows Nothing

Your agent stores every conversation, retrieves relevant past exchanges, and still fails to answer questions it has already solved. It has episodic memory — a log of what happened — but no semantic memory — understanding of what it means. The agent is a perfect tape recorder with no comprehension of its own recordings.

## Forces

- **Context windows are per-call buffers; continuity is a system property.** A context window is read fresh every time the model runs. No matter how large it grows, it does not give your agent awareness of what happened last week or last session. Agents fail on continuity, not on token limits.
- **"Store everything in a vector DB" is episodic memory dressed up as semantic memory.** The field distinguishes three tiers: episodic (raw conversation logs), semantic (extracted facts, entities, relationships), and procedural (learned agent behaviors). Most production implementations only have episodic. They call it RAG over chat history and are surprised when retrieval doesn't produce understanding.
- **The consolidation step is the hard part, and everyone skips it.** Converting "the user asked about PostgreSQL on March 3rd and we discussed connection pooling" into a retrievable fact requires a separate LLM pass — extraction, entity resolution, temporal tagging. This pipeline is where complexity lives, and it is where teams underinvest.
- **Sophistication doesn't pay as much as you'd expect.** Letta's benchmarks show a plain filesystem scores 74% on memory tasks, beating specialized vector-store libraries. The gap between "no memory" and "any memory" is enormous; the gap between "episodic RAG" and "graph-enhanced semantic memory" is often under 5%.

## The move

Build an explicit **three-tier memory architecture with a consolidation pipeline**, not a single flat store over conversation logs.

- **Tier 1 — Working memory (context window):** System prompt, conversation history, tool outputs, reasoning traces. Nothing persists beyond the current session. Budget for compaction: when you exceed ~70% of context, run a summarizer before adding more.
- **Tier 2 — Episodic memory (conversation store):** Full transcripts or structured summaries of past sessions. Use a vector store (PGvector, Qdrant, Pinecone) for semantic similarity search. Store metadata: session_id, timestamp, user_id, topic tags. This is what most people build first and stop at.
- **Tier 3 — Semantic memory (extraction + knowledge layer):** The consolidation step. On session end or async, run an extraction LLM pass over the episodic record to produce structured facts: entities (user preferences, project properties), relationships (user X used tool Y for Z), and temporal events (on 2025-03-14, found that Z in the database). Store in a knowledge graph (Neo4j, PostgreSQL with recursive CTEs) or structured document store. This is what enables "you solved this exact problem last month — here's the fix."
- **Tier 4 — Procedural memory (learned behaviors):** The agent's own system-prompt-fragment library. When the agent successfully handles a failure mode, extract the pattern as a behavioral directive (e.g., "When Postgres throws connection timeout, retry with exponential backoff up to 3 times"). Store alongside semantic memory, inject into system prompt on relevant task types. This is the rarest tier and the most valuable.
- **Consolidation pipeline (the missing step):** After each session, an async job extracts episodic → semantic. Use an LLM with structured output (JSON mode) to extract entity-fact pairs. Run deduplication against existing semantic store. For agents with high task repetition, batch consolidation after every N sessions or every 24 hours, not per-session (token cost vs. staleness tradeoff).
- **Retrieval routing:** Don't send everything everywhere. Route queries to the right tier — "what did we do last time?" → episodic (RAG over transcripts). "What do I know about this user?" → semantic (knowledge graph query). "How do I handle auth errors?" → procedural (behavioral directive retrieval).

## Evidence

- **Research paper:** Mem0 (arXiv 2504.19413, 2025) — introduces the extraction/update pipeline architecture for semantic memory. Mem0^g (graph extension) shows only ~2% improvement over dense natural-language extraction, but both dramatically outperform no-memory baselines. Key finding: "91% lower p95 latency than full-context approach" — selective retrieval beats stuffing everything into context.
  — [arXiv:2504.19413](https://arxiv.org/abs/2504.19413)
- **HN Ask thread:** "Anyone using knowledge graphs for LLM agent memory?" (HN, May 2025) — practitioners noting that naive implementations "store complete responses as entities and simply do RAG style similarity searches... not a knowledge graph by the standard definitions." Top comment: "actual entities and relationships defined like triples with some schema and appropriately resolved and linked can be useful" — but hard to get right. One respondent from an enterprise team using Zep reports success with temporal knowledge graphs for cross-session continuity.
  — [HN Ask: Knowledge graphs for LLM agent memory](https://news.ycombinator.com/item?id=43940654)
- **Framework analysis:** Letta/MemGPT (formerly) benchmarks — found that a plain filesystem with basic MEMORY.md files scores 74% on memory tasks. The insight: the existence of a consolidation pathway matters far more than the sophistication of the storage backend. MemGPT's core contribution is LLM self-editing of memory via tool calls — the agent itself decides what to store and when.
  — [Letta v1 Agent Architecture](https://www.letta.com/blog/letta-v1-agent/)
- **Enterprise production:** AWS selected Mem0 as the exclusive memory provider for their Agent SDK (announced 2025). Zep reported 94.8% accuracy on Deep Memory Retrieval benchmark vs. MemGPT's baseline, using temporal knowledge graph architecture with entity versioning.
  — [Zep: Temporal Knowledge Graph for Agent Memory (arXiv:2501.13956)](https://arxiv.org/abs/2501.13956)

## Gotchas

- **Async consolidation sounds good but silently fails.** If your extraction job errors out, you have no episodic→semantic pipeline and the gap goes undetected. Monitor extraction success rate, not just retrieval latency.
- **Context compaction and memory consolidation are different.** Compaction shrinks the working context (what fits in the current call). Consolidation moves knowledge from episodic to semantic (what you know across calls). Many teams build one and call it both.
- **Vector search over chat history is not semantic memory.** It returns "things like this" but has no concept of entities, relationships, or time. A user asking "what did I last ask about?" will get semantic similarity matches, not a chronological answer. You need structured metadata (timestamp, topic, outcome) to make episodic retrieval useful.
- **Procedural memory is the rarest and most fragile tier.** Storing "learned behaviors" requires a feedback signal — did this approach work? That signal is expensive to collect and easy to get wrong. Most teams never build it. Those who do often find behavioral drift: the agent slowly accumulates outdated procedural knowledge unless there's an active forgetting or versioning mechanism.
- **Multi-user memory isolation is an afterthought in most frameworks.** USER_ID scopesMem0's memories; Claude Code's auto-memory stores are per-project. If you serve multiple users, verify the memory backend enforces strict isolation at the storage layer, not just the retrieval query.
