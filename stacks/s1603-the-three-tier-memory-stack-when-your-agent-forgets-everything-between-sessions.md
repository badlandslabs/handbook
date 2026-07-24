# S-1603 · The Three-Tier Memory Stack — When Your Agent Forgets Everything Between Sessions

Your customer-support agent handled Tuesday's conversation perfectly. On Wednesday, the same customer called back about the same issue, provided the same account details, and your agent greeted them like a stranger. It asked for their account number. They hung up. This is the stack for giving your agent a real memory — one that persists across sessions, compounds over time, and knows what to forget.

## Forces

- **Context windows are not memory.** A 1M-token context window is fast and zero-latency — until the conversation ends, at which point it is gone. Teams that treat context size as a memory solution discover this the hard way.
- **Vector retrieval is not memory.** Storing everything as embeddings and doing nearest-neighbor search on every request solves retrieval. It does not solve deduplication, conflict resolution, prioritization, or decay. These are different engineering problems.
- **The three-way distinction is non-obvious.** Episodic (what happened), semantic (what is true), and procedural (how to act) memories have different storage backends, retrieval strategies, and decay characteristics. Treating them identically produces a system that works in demos and fails in production.
- **Memory without forgetting is debt.** Agents that store everything eventually drown in it. Without prioritization and pruning, retrieval noise degrades response quality and costs spiral.

## The Move

Production agents need three distinct memory layers, not one.

**Layer 1 — Episodic: store what happened.**
Chronological, event-oriented records of past interactions, tool traces, decisions made, errors encountered. Implemented as conversation logs or event stores with time-indexed retrieval. The question it answers: "what did this user say last time, and what did we do?" Storage: document store, structured log, or append-only buffer. Retrieval: time-range queries, session identifiers, or semantic search scoped by recency.

**Layer 2 — Semantic: store what is true.**
Declarative facts — user preferences, domain knowledge, entity relationships, accumulated generalizations. Implemented as a knowledge graph, structured key-value store, or entity-indexed vector store. The question it answers: "what do I know about this user or domain?" Storage: graph DB (Neo4j), structured KV (Postgres JSONB), or entity-chunked vectors. Retrieval: entity lookups, relationship traversal, or importance-weighted semantic search. Mem0 reports 26% better accuracy than naive approaches on the LOCOMO benchmark with 90% prompt token reduction — because semantic facts are dense vs. the raw conversation log they'd replace.

**Layer 3 — Procedural: store how to act.**
Learned workflows, behavioral heuristics, policy rules, and agent self-knowledge about its own capabilities. The question it answers: "how should I handle this class of situation?" Implementation: rule engines, policy documents, or tool-selection metadata. This is the most under-built layer in production — most agents have no procedural memory and repeat the same mistakes across sessions.

**On retrieval:** Before every agent turn, run a multi-signal query: semantic similarity (embedding match), temporal recency (episodic freshness), and importance weighting (how critical is this fact). Formative Memory (OpenClaw plugin) adds association expansion — once a memory is retrieved, related memories are pulled in, mimicking spreading activation in biological memory systems.

**On forgetting:** Implement importance decay. Formative Memory uses a strength score that decays each time a memory is NOT accessed and is incremented when it IS accessed. Low-strength memories are pruned during a nightly consolidation job. Without this, memory density grows without bound and retrieval degrades.

**On conflict resolution:** The most recent observation overrides older contradictory ones. Deduplicate on storage — if a similar fact already exists, update rather than append. Mem0 automates this pipeline, achieving 91% faster retrieval vs. naive full-context approaches.

## Evidence

- **Engineering blog (Tian Pan, Oct 2025):** "The gap between a memory system that stores things and one that reliably surfaces the *right* things at the *right* time is where most agent projects quietly fail. A 1M-token context window is not a memory system." — [tianpan.co](https://tianpan.co/blog/2025-10-21-memory-architectures-for-production-ai-agents)
- **Research survey (Zylos Research, Apr 2026):** "No single storage paradigm dominates. Production-grade agents increasingly rely on hybrid architectures that layer vector and graph stores, with an LLM-managed interface deciding what to store, when to retrieve, and when to forget. Letta's benchmarking suggests a simple filesystem is competitive with sophisticated memory frameworks for many agent workloads." — [zylos.ai](https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge/)
- **GitHub / Show HN (jarimustonen, 2026):** Formative Memory implements biological forgetting curves — memories strengthen through use, fade when unused, and consolidate overnight. "Before every response, relevant memories are injected via hybrid search (embedding similarity + BM25), ranked by strength. Association expansion pulls in related memories." — [github.com/jarimustonen/formative-memory](https://github.com/jarimustonen/formative-memory)
- **Benchmark (Mem0, 2025):** Mem0's memory system achieves 26% better accuracy than OpenAI's built-in memory on the LOCOMO benchmark, with 91% faster responses and up to 90% prompt token reduction through semantic fact extraction vs. raw conversation logging. — [mem0.ai](https://mem0.ai/research)
- **Enterprise survey (Cleanlab, 2025):** Only 5% of surveyed enterprises have AI agents in production at scale. Stack churn rate is 70% — regulated enterprises rebuild their AI stack every 3 months or faster. The top cited reason: memory and state management failures in multi-session interactions. — [cleanlab.ai](https://cleanlab.ai/ai-agents-in-production-2025)

## Gotchas

- **Don't store everything.** A 100-session conversation log is not memory — it is noise. Extract facts, decisions, and preferences at write time. Store those, not the raw transcript.
- **Don't skip the procedural layer.** Episodic and semantic memory cover what happened and what is true. Without procedural memory — rules, heuristics, self-knowledge — your agent will repeat the same failures session after session. Build at least a lightweight policy store.
- **Retrieval quality beats storage volume.** Adding more memory makes things worse if retrieval is noisy. Invest in retrieval ranking (multi-signal scoring, importance weighting) before adding more storage.
- **Test forgetting as much as testing remembering.** If you never prune, you will eventually have a memory system that is slower and less accurate than one with no memory at all. Add a decay mechanism and test with stale data.
