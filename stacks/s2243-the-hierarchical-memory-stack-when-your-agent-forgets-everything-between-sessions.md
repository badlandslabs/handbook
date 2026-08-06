# S-2243 · The Hierarchical Memory Stack — When Your Agent Forgets Everything Between Sessions

An AI agent without memory is an expensive chatbot. It reasons beautifully inside a single context window, then forgets everything when the session ends. The next interaction starts from zero. Nothing compounds. The agents that have broken out of pilot purgatory — the ones running autonomously for weeks, accumulating user context, and actually displacing headcount — share one architectural feature: a purpose-built memory layer sitting between the LLM and the rest of the stack.

## Forces

- **Context windows are finite but conversations are infinite.** Dumping full chat history into context is the naive solution; it hits token limits fast, inflates costs, and degrades retrieval quality. A memory layer that intelligently compresses, summarizes, and retrieves is not optional at scale.
- **Four memory types, three backends.** The field has converged on Working/Episodic/Semantic/Procedural as the canonical taxonomy, but each tier needs a different storage substrate — and the wrong substrate for a given tier creates a new failure mode rather than solving the old one.
- **Shared vs. per-agent memory is the load-bearing architectural choice.** Per-agent memory isolates context but prevents knowledge sharing. Shared memory compounds knowledge but introduces cross-context contamination. Teams make this choice late — after building something wrong first.
- **The memory-as-infrastructure shift.** Memory moved from "prompt engineering" to "third infrastructure layer" (after MCP and observability) in 2025-2026. This means it needs its own versioning, expiry, deletion path, and governance — not just a vector store.

## The Move

The memory system operates as a three-tier hierarchy:

**Tier 1 — Working Memory (in-context):** The active context window. Pure RAM. Contains the current conversation, recent tool calls, and the agent's running notes. Always session-local; never persists.

**Tier 2 — Episodic Memory (cross-session):** A log of what happened — raw transcripts of past interactions, tasks, decisions, and outcomes. Stored in a document or time-series store. The agent retrieves relevant episodes by semantic similarity or temporal proximity.

**Tier 3 — Semantic Memory (long-term knowledge):** Extracted facts, entities, user preferences, and organizational knowledge. The load-bearing layer. Stored in a vector database for recall, optionally augmented with a knowledge graph for relational reasoning.

**Memory compaction pipeline:** After each session, the agent runs a summarization step that extracts new facts from the conversation, resolves contradictions against existing memories (via LLM judge), and writes compressed summaries to the appropriate tier. This is what prevents unbounded context growth.

**Dual-store for complex agents:** High-value agents use a vector store (for semantic recall) plus a knowledge graph (for relationship reasoning) plus a KV store (for fast key-value state). The retrieval layer queries all three and merges results. Pure vector search fails at exact-match queries (error codes, product names, IDs); hybrid search handles both semantic and lexical recall.

**Context is versioned, not overwritten.** Every memory write is append-only with a version marker. This enables the agent (or a human reviewer) to trace when a belief changed, revert a bad compaction, and audit memory provenance — essential for compliance and debugging.

## Evidence

- **Mem0 GitHub README:** Mem0 raises $24M Series A (Y Combinator) and publishes benchmarks showing 26% accuracy improvement over strong RAG baseline with 90% token reduction vs. full chat history dumps. Handles contradictions via LLM judge that decides whether new facts update, replace, or add to existing memories. — [github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)

- **Letta (MemGPT) research post:** Letta rebuilds memory architecture around "Context Repositories" using git-based versioning. The core insight from the MemGPT paper (arXiv 2310.08560): treat the LLM context window like RAM in an operating system, and give the agent tools to manage its own memory hierarchy — including a tool to move summaries to archival storage and a tool to retrieve from it. Raises $30M Series A. — [letta.com](https://www.letta.com/), [arxiv.org/abs/2310.08560](https://arxiv.org/abs/2310.08560)

- **Perea.ai production survey:** The definitive practitioner survey of agent memory in production (2025-2026) consolidates findings across 50+ deployments: recommends Mem0 for token efficiency, Zep/Graphiti for temporal reasoning, Letta for stateful agent runtimes. Critical failure modes documented: memory poisoning (injection via historical context), drift/staleness (outdated facts remain retrieved), cross-context contamination (shared memory bleeds between users), and compaction errors (bad summarization destroys signal). — [perea.ai/research/agent-memory-production](https://www.perea.ai/research/agent-memory-production)

- **MemoryOS (EMNLP 2025 Oral):** Academic memory OS achieving SOTA on LoCoMo benchmark: +49.11% F1, +46.18% BLEU-1 over prior methods. Provides plug-and-play memory modules including storage engines, update strategies, and retrieval algorithms with MCP server integration. — [github.com/0xSojalSec/Ai-MemoryOS](https://github.com/0xSojalSec/Ai-MemoryOS)

## Gotchas

- **Compaction errors destroy signal irreversibly.** Bad summarization doesn't just waste tokens — it destroys information. Summaries must be validated against source transcripts, and catastrophic compaction events should trigger a restore from the last known-good episodic snapshot, not a retry.
- **Memory poisoning via injection is real and under-discussed.** Adversarial users can inject false facts into the episodic layer that survive compaction and contaminate future sessions. The Mem0 LLM-judge approach helps but is not bulletproof; input sanitization at write time is required in addition.
- **Choosing one vector DB for all memory tiers is the most common mistake.** Episodic memory (high-volume, time-ordered, needs range queries) has different access patterns than semantic memory (low-volume, needs semantic similarity search). Using pgvector for under-10M vectors and Qdrant for 2-49 agents covers most production needs, but the tier-to-backend mapping matters.
- **Cross-context contamination in shared memory silently degrades outputs.** When agent A's memory includes facts from agent B's sessions — a misconfigured shared namespace, a failed isolation boundary — outputs become unpredictable and attribution becomes impossible. Treat memory isolation as a security boundary, not a configuration option.
