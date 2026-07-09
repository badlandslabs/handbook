# S-866 · The Memory Contradiction Stack — When Your Agent Remembers Everything and Knows Nothing

You shipped a persistent agent. Users love it for a week, then start catching it confidently citing outdated facts, repeating decisions that were superseded, and mixing up preferences from months ago. The agent has memory — it just has no idea what's true, what's current, or what it should have forgotten. The problem is not storage. It's that your memory layer treats every stored fact as equally valid forever.

## Forces

- **The vector store has no truth maintenance.** Cosine similarity retrieves whatever semantically matches the query — regardless of whether that fact was established last Tuesday or last quarter. Contradictions accumulate silently. The agent recalls them with equal confidence. — [widemem.ai: The Contradiction Problem in AI Memory](https://widemem.ai/blog/contradictions)
- **Context rot compounds memory failures.** Stale retrieval results, over-accumulated session history, and contradictory context lead to context poisoning, context confusion, and context clash simultaneously — agents get worse at the exact moments they need to be most reliable. — [Redis: AI Agent Memory vs Retrieval](https://redis.io/blog/ai-agent-memory-vs-retrieval)
- **Consolidation is an afterthought in most stacks.** Without a periodic compression step, episodic interaction history grows linearly with every session. At scale, this makes context windows prohibitively expensive and retrieval results noisy. The standard fix — stuffing prior context into the context window — fails on cost, latency, and the "lost in the middle" effect where models ignore facts far from prompt edges. — [Redis: AI Agent Memory vs Retrieval](https://redis.io/blog/ai-agent-memory-vs-retrieval)
- **Memory systems lack provenance metadata.** Most implementations store plain text with embeddings. They can't answer: when was this fact established, by whose input, how certain is the source, was it later contradicted? Without this, retrieval ranking is always partial. — [YantrikDB: Cognitive Memory Database for AI Agents](https://github.com/yantrikos/yantrikdb-server)
- **Multi-signal recall beats pure similarity.** The dominant failure mode — agent coherence degrading over long sessions — correlates with retrieval that weights recency, importance, and certainty equally with semantic match. A fact recalled twice gets the same score as one recalled twenty times. — [HN: silentsvn on persistent agent memory quality](https://news.ycombinator.com/item?id=47328951)

## The move

Design memory as a typed, scored, maintained system — not a dump-and-retrieve layer.

**1. Type memories by Tulving's taxonomy — don't mix them.**
- **Episodic:** events with temporal and contextual markers ("user ran `npm build` and it failed on March 3rd")
- **Semantic:** stable facts, preferences, ground truth ("user prefers TypeScript over Python")
- **Procedural:** strategies, patterns, what worked ("deploy with blue-green, not rolling update")
- Store each with importance, valence, source, certainty, and timestamps. These fields drive retrieval ranking, not just embeddings alone. — [YantrikDB: Tulving's Taxonomy in agent memory](https://github.com/yantrikos/yantrikdb-server)

**2. Gate storage with a certainty scoring layer before the write.**
- New facts pass through a scoring function that checks against existing knowledge.
- Contradictions get flagged rather than silently stacked. The agent surfaces the conflict to the user, marks the old fact as superseded, or demotes confidence — it doesn't just add another vector that will later be retrieved at equal ranking. — [HN: silentsvn on certainty scoring before storage](https://news.ycombinator.com/item?id=47328951)
- This is the single highest-leverage change for long-session coherence. — [widemem.ai: The Contradiction Problem](https://widemem.ai/blog/contradictions)

**3. Consolidate episodics into semantics on a schedule.**
- Periodic background job: compress recent episodic memories into semantic summaries. Delete or archive the raw events.
- This prevents unbounded storage growth and keeps retrieval relevant rather than noisy. — [Inductivee: AI Agent Memory Architecture (Oct 2025)](https://inductivee.com/blog/ai-agent-memory-persistence-architecture)

**4. Apply time-decay and recall-frequency scoring to retrieval.**
- Memories recalled frequently get promoted; those never referenced over a decay window fade.
- Retrieval ranking = semantic similarity × recency weight × importance score × certainty score. — [HN: silentsvn on recall-frequency promotion](https://news.ycombinator.com/item?id=47328951)

**5. Prefer SQLite with FTS5 over a dedicated vector database for agent-native memory.**
- Binary vector indexes are opaque: no git diff, no audit trail, no rollbacks, no manual edits.
- SQLite + FTS5 + an embedding column gives you semantic search with full auditability.
- For local agents (Claude Code, Cursor, Hermes), this is increasingly the preferred stack. — [Towards Data Science: memweave — SQLite + Markdown, No Vector DB Required](https://towardsdatascience.com/memweave-zero-infra-ai-agent-memory-with-markdown-and-sqlite-no-vector-database-required)
- ClawMem uses SQLite with FTS5 + sqlite-vec for hybrid retrieval, shared across Claude Code, Hermes, and OpenClaw via a single local vault. No API keys, no cloud. — [GitHub: yoloshii/ClawMem](https://github.com/yoloshii/ClawMem)

**6. Expose user controls for memory management.**
- Let users see, tag, correct, or delete stored memories.
- Make memory retention time-bound with expiration policies.
- Consent-based memory (mark inputs as "important to remember") outperforms blind accumulation. — [freeCodeCamp: Vector Stores in LLM Memory](https://www.freecodecamp.org/news/how-ai-agents-remember-things-vector-stores-in-llm-memory)

## Evidence

- **HN Comment (primary):** A practitioner building persistent agents described the architecture that landed: ingest goes through a certainty scoring layer before storage. Contradictions get flagged rather than silently stacked. Frequently recalled memories get promoted; stale ones fade. "The difference in agent coherence over long sessions is noticeable." — [HN: silentsvn on agent memory quality](https://news.ycombinator.com/item?id=47328951)
- **Blog post (primary):** widemem.ai analyzed the contradiction problem as "the single biggest reliability issue in AI memory today" — mundane, frequent, and invisible until it produces a wrong answer someone notices. Demonstrated with a concrete example: user said they live in SF, then mentioned relocating to Boston; both facts retrieved with equal confidence. — [widemem.ai: The Contradiction Problem in AI Memory](https://widemem.ai/blog/contradictions)
- **GitHub repo (primary):** ClawMem — on-device memory layer for Claude Code, Hermes, OpenClaw. SQLite with FTS5 + sqlite-vec for hybrid RAG. No cloud dependencies. Contradiction detection at ingest. Recall-frequency feedback loop. — [GitHub: yoloshii/ClawMem](https://github.com/yoloshii/ClawMem)
- **GitHub repo + benchmark (primary):** LangMem (langchain-ai, 1.5k stars) provides a standardized API over episodic, semantic, and procedural memory with native LangGraph store integration. Covers three-layer taxonomy with consolidation primitives. — [GitHub: langchain-ai/langmem](https://github.com/langchain-ai/langmem)
- **Benchmark comparison (primary):** Mem0 (49.0% LongMemEval with GPT-4o) vs Zep (63.8%) on the temporal knowledge graph benchmark. The gap reflects Zep's Graphiti-based temporal architecture handling recency and entity-relationship reasoning better than Mem0's flat vector approach. — [RockB: Mem0 vs Zep in Production, May 2026](https://baeseokjae.github.io/posts/mem0-vs-zep-production-guide-2026/)

## Gotchas

- **Vector store is necessary but not sufficient.** Semantic similarity retrieval without truth maintenance, recency scoring, and contradiction detection degrades into "everything goes in, nothing gets resolved." — [HN: silentsvn](https://news.ycombinator.com/item?id=47328951)
- **More memory does not mean better memory.** Context distraction (too much history crowds fresh reasoning) and context confusion (irrelevant tools/documents push the model toward wrong behavior) are real failure modes. Memory needs curation, not accumulation. — [Redis: AI Agent Memory vs Retrieval](https://redis.io/blog/ai-agent-memory-vs-retrieval)
- **Overwriting on contradiction is a lossy strategy.** Replacing old facts with new ones silently loses the audit trail. If the new fact is itself wrong, you have no way to recover. Flag contradictions explicitly. — [widemem.ai: The Contradiction Problem](https://widemem.ai/blog/contradictions)
- **"Lost in the middle" affects stored history too.** A fact stored in a retrieval result list is not immune to the model ignoring it. Position in retrieved context matters — put high-certainty facts at retrieval edges, not buried in the middle of a long result set.
- **Memory sprawl in multi-agent systems is harder than single-agent.** Each agent may maintain its own memory store. Without a shared semantic layer, agents retrieve different answers to the same question. Coordinate memory schemas across agents. — [HN: Ask HN — Multi-agent orchestration](https://news.ycombinator.com/item?id=47660705)
