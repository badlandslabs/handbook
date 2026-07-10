# S-898 · The Memory Stratigraphy — When Your Agent Forgets Who It Spoke To Last Tuesday

Your agent aced the demo. Three weeks later it re-onboarded the same customer, hallucinated a prior commitment, and sent a contradictory email. The model didn't change. The memory system didn't exist. Agents are stateless by default — every new session is a fresh LLM call with no awareness of what happened in the last one. Memory is the day-2 differentiator that separates agents that do real work from chatbots that pretend to.

## Forces

- **Stateless by design, stateful by necessity.** LLMs are stateless. Users expect continuity. Every session boundary breaks the thread unless you build infrastructure to bridge it.
- **Naive vector search is a lying machine.** Semantic similarity doesn't distinguish between a fact and its correction. A transient error写入memory, then corrected, still retrieves both — the agent now holds contradictory beliefs simultaneously.
- **Memory is not free.** Every retrieval call adds latency and cost. Every stored fact adds to context. Unstructured accumulation eventually exceeds your context window and collapses the agent's reasoning.
- **Persistence without validation is a jailbreak surface.** An agent that writes unchecked conclusions to persistent memory can be manipulated by a user, a jailbroken persona, or a hallucination — permanently.

## The move

Treat memory as stratified geological layers, not a flat dump. Separate concerns across time horizons and retrieval triggers:

- **Working memory (context window):** Only what the agent needs for the current task. Trim aggressively. Cost and latency scale with token count.
- **Session memory:** What happened in this session. Summarize on session end, don't accumulate raw logs.
- **Long-term memory:** Cross-session facts, preferences, commitments. Store as structured entities, not raw conversation blobs.
- **Archive:** What was true historically but is no longer relevant. Zep's Graphiti calls these *validity windows* — facts have expiration dates. Query: "what did the user tell us about their budget last quarter?" requires knowing the current state differs from Q1 state.
- **Validate before persisting.** Fava Trails (Git-backed MCP memory) enforces a promotion gate — facts must pass a curation check before being committed to the permanent layer. Don't let unvalidated LLM conclusions write through to persistent storage.
- **Curate, don't accumulate.** Mem0's v3 changed the retrieval architecture from overwriting to *accumulation-with-scoring*: single-pass ADD-only extraction, entity linking across memories, multi-signal fusion (semantic + BM25 + entity matching) so the right fact surfaces without requiring the agent to re-learn it each session.
- **Typed state at the orchestration layer.** In LangGraph, every node passes typed state schemas (not raw JSON blobs) between agents. Without typing, a field silently renamed in one node produces silent failures at runtime — the graph continues but the data is wrong.

## Evidence

- **Benchmarking:** Zep's Graphiti scores **63.8%** on LongMemEval vs Mem0's **49.0%** — a 15-point gap attributable to Graphiti's temporal validity windows and structured entity graph retrieval. Mem0 v3 narrowed this gap significantly by adding entity linking and multi-signal retrieval, with the biggest gains on temporal queries (+29.6 pts) and multi-hop reasoning (+23.1 pts). — *[Particula Tech benchmark, June 2026](https://particula.tech/blog/agent-memory-frameworks-tested-mem0-zep-letta-cognee-2026)*
- **Industry pattern:** "Memory is becoming one of their key moats now that LLMs are getting commoditized." — Taranjeet Singh, Mem0 co-founder. Four vendors raised significant funding in 2025-2026 specifically for agent memory: **Letta** (MemGPT evolution, OS-tiered memory), **Zep** (Graphiti temporal graph), **Mem0** (48K+ GitHub stars, YC-backed), and **OpenMemory** (local/CaviraOSS). — *[AgenticWire, June 2026](https://www.agenticwire.news/article/mem0-zep-letta-agent-memory)*
- **Production failure mode:** Fava Trails HN post documents the memory poisoning case — a transient GPU error written to memory, then corrected, still retrieved by vector search as "true," leaving the agent schizophrenic. Also: jailbroken personas or user-manipulated state writing through to persistent sessions permanently. — *[Hacker News Show HN, ~Feb 2026](https://github.com/MachineWisdomAI/fava-trails)*

## Gotchas

- **Don't accumulate raw conversations.** Storing full message histories balloons context and buries signal. Extract atomic facts, not transcripts.
- **Don't use vector search alone for truth.** Semantic similarity ≠ factual correctness. If you only use embeddings for retrieval, contradictory facts will surface together. Layer BM25 keyword matching and entity graph traversal.
- **Don't skip typed state in LangGraph.** The tutorial code uses raw dicts for state. Production code needs `TypedDict` schemas with validation — otherwise silent field mismatches between nodes will produce wrong outputs with green logs.
- **Don't persist without a promotion gate.** Any memory layer that accepts LLM output without validation is a write surface for hallucinations and manipulation. Require human or automated verification before committing high-stakes facts.
