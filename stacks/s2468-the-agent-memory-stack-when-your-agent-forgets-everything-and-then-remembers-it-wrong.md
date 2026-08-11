# S-2468 · The Agent Memory Stack

Every new session, the agent starts from zero. Not because the model can't remember — because the infrastructure doesn't give it anywhere to store what it learned. Teams solve "start from zero" by bolting on a vector database, then discover a subtler problem: the agent remembers everything, including things that stopped being true. The question isn't how to store more — it's how to store memory that degrades gracefully, tracks what changed when, and lets the operator correct it without a database migration.

## Forces

- **CRUD semantics break state reasoning**: Vector databases and standard RAG pipelines treat memory as storage — create, read, update, delete. But agent memory correctness lives in the *state trajectory*, not individual records. Storing "user prefers Adidas" in January and "switched to Nike" in March as equal-weight embeddings produces confident contradictions
- **Append-only accumulation is the path of least resistance — and the path to noise**: The easiest memory implementation is an ever-growing conversation log. This creates the "last 20 sessions bleed into the current one" problem. The agent gets slower and noisier, not smarter
- **The memory layer and the agent loop have competing interests**: The agent loop wants maximum context. The memory layer needs to stay lean enough to be retrievable and affordable. These incentives pull in opposite directions
- **No single storage paradigm dominates**: Pure vector recall handles fuzzy semantic search well but misses relationships and temporal ordering. Knowledge graphs encode relationships but add schema overhead. The leading production architectures are hybrid — and the LLM itself increasingly decides what to store, where, and when to forget

## The move

The core pattern: **hybrid memory with temporal awareness and importance-weighted retrieval**, not a single vector store.

- **Layer 1 — Episodic buffer**: Raw conversation history for the current session. Short-term, high-fidelity, discarded at session end. This is the working context the agent actually operates in
- **Layer 2 — Semantic memory via vector store**: Facts extracted from conversations, embedded and stored. Query vector DB for relevant context before each major reasoning step. Mem0 is the leading open-source implementation (GitHub: mem0ai/mem0); it handles importance scoring, user/agent/-system memory partitioning, and multi-modal memory
- **Layer 3 — Temporal knowledge graph**: Explicit entity-relationship graphs with validity windows. When a fact changes, the old fact is marked with an end timestamp rather than deleted. Graphiti (Zep's open-source engine) and Letta (MemGPT's successor) both implement this. The graph preserves *history*, enabling the agent to reason about change, not just current state
- **LLM as the memory orchestrator**: The agent itself decides what to commit to memory, which layer to query, and when to mark something stale. This is the emerging production pattern — not hard-coded rules, but a memory-use policy managed by the model
- **Importance scoring and forgetting**: Every fact gets an importance score (0–10) at write time. Retrieval is gated: only facts above a threshold are included in context. Periodic consolidation compresses low-importance, redundant entries. The agent forgets things intentionally, not accidentally

## Evidence

- **arXiv paper (May 2026):** "Is Agent Memory a Database? Rethinking Data Foundations for Long-Term AI Agent Memory" formally identifies four failure modes of CRUD-based agent memory — unregulated growth, temporal blindness, missing relationships, and forgetting ungoverned — and proposes Governed Evolving Memory (GEM) with six correctness conditions. Published as arXiv:2605.26252 by Abdelghny Orogat and Essam Mansour, Concordia University — https://arxiv.org/html/2605.26252v1
- **Zylos Research (April 2026):** "AI Agent Memory Architectures: From Context Windows to Persistent Knowledge" surveys production patterns and finds Mem0, Zep/Graphiti, and Letta pulling ahead of competitors. Key finding: evaluation remains immature — LoCoMo and LongMemEval test conversational recall but neither captures procedural memory quality or cross-agent consistency — https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge
- **Paperclipped (February 2026):** "AI Agent Memory: From RAG to Knowledge Graphs" documents three failure modes of RAG-as-memory: temporal blindness (contradicting facts at equal vector distance), missing relationships (facts stored as isolated points), and the impossibility of provenance (no way to know where a recalled fact came from). Recommends knowledge graphs over flat vector stores for agent-grade memory — https://www.paperclipped.de/en/blog/ai-agent-memory-knowledge-graph
- **Hacker News (December 2024):** Ask HN thread "Examples of agentic LLM systems in production" (112 points, 73 comments) surfaced memory and state persistence as the top production pain point, ahead of orchestration complexity and tool reliability. Top comment: "The agentic part is figuring out what to do with a response; the memory part is figuring out what to do with a history" — https://news.ycombinator.com/item?id=42431361

## Gotchas

- **Vector similarity ≠ semantic correctness**: Two semantically opposite statements can have near-identical embeddings. A vector search that returns both "user is on Pro plan" and "user downgraded to Free" at equal distance is not a memory system — it's a flip-flop generator
- **Session isolation is a trap**: Teams implement per-session memory correctly but fail to transfer *learned procedures* (not just facts) to new sessions. The agent remembers your name but not how you like your PRs reviewed
- **Memory corruption is silent and cumulative**: A hallucinated fact stored with high confidence will be retrieved and re-confirmed by future interactions. Unlike database corruption, there's no checksum and no rollback. Operators need read/write access to the memory store directly, not just through the agent
- **The importance/score system is usually tuned once and never revisited**: Teams set importance thresholds at implementation time and then wonder why memory degrades over 6 months. Treat importance thresholds as runtime-configurable parameters, not constants
