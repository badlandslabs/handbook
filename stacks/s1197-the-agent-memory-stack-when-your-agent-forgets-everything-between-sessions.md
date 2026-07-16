# S-1197 · The Agent Memory Stack — When Your Agent Forgets Everything Between Sessions

A stateless LLM is fancy autocomplete. It takes a request, returns a response, forgets everything. That works for single-turn Q&A. It breaks the moment you need pause-and-resume (user comes back tomorrow), multi-turn coherence (agent needs to remember what tools it called three steps ago), personalization (returning user expects the agent to know their preferences), or human-in-the-loop (agent drafts a report and waits for approval — the waiting state has to survive process restarts). Agent memory is not a feature you bolt on; it is an architecture you design from the ground up.

## Forces

- **Context windows are not memory.** Models start deprioritizing critical information once context exceeds 60% capacity — even when the answer is literally in the window. A 2026 study found models hit this threshold in 15–20 turns of typical conversation. Stuffing more tokens produces more expensive forgetting, not better recall.
- **Token cost grows super-linearly with context length.** Full-context memory costs ~$15 per 1M-token inference call. At 1,000 customer support conversations per day, that is $15,000/day. Targeted retrieval at 90% less context can match or exceed full-context accuracy.
- **Three distinct memory types compete for your architecture budget.** Episodic (what happened), semantic (what you know), and procedural (how you do things) each need different storage backends and retrieval patterns. Most teams build one tier and wonder why the agent still fails.
- **Framework checkpointing ≠ agent memory.** LangGraph checkpoints save graph execution state (enabling resume from crash); they do not give the agent searchable long-term knowledge. These are different problems requiring different solutions.

## The Move

Build a three-tier memory architecture that mirrors cognitive science — episodic, semantic, and procedural — each with an appropriate storage backend and retrieval strategy.

**Episodic memory** — store what happened (conversation events, task histories, interaction timelines):
- Use a vector database (Qdrant, pgvector, Pinecone) with time-weighted scoring so recent events surface first
- Store raw transcripts compressed; store LLM-extracted facts as structured records
- LangGraph's `MemorySaver` or `PostgresSaver` handles execution-state checkpoints (thread position, intermediate variables) — separate from semantic recall

**Semantic memory** — store what the agent knows (facts, preferences, domain knowledge):
- Use a graph store or hybrid vector+graph DB for entity relationships (Neo4j + Qdrant, or Mem0's built-in graph layer)
- Extract facts via LLM summarization after each session; store as `<subject, predicate, object>` triples
- Mem0 (50K+ GitHub stars, Apache 2.0) is the dominant open-source implementation: `memory.search(query)` retrieves relevant facts, `memory.add(conversation)` extracts and stores new facts — 26% higher accuracy vs OpenAI's memory system on LoCoMo benchmarks, 91% lower latency than full-context, 90% token cost savings

**Procedural memory** — store how the agent operates (prompts, tool definitions, learned workflows):
- Store as versioned configuration files or in a key-value store (Redis, etcd)
- Agent reads its own procedural memory at session start to reconstruct operating context
- Workflow definitions should be declarative and agent-readable, not buried in code

**Working memory** (the scratchpad during active reasoning):
- Keep in-memory as a structured dict — intermediate calculations, plan states, tool call tracking
- Serialize to episodic memory on each tool completion or step boundary, not only at session end
- LangGraph's state object is the natural home; checkpoint after each superstep

**Context management within sessions:**
- Sliding window: keep last N messages, discard oldest
- Summary-based truncation: LLM summarizes old conversation chunks, store the summary instead of raw text
- Semantic chunking: cluster messages by topic, retrieve whole clusters rather than individual messages
- Never let raw conversation history dominate the prompt — route through the memory layer first

## Evidence

- **Research survey:** The three-tier taxonomy (episodic, semantic, procedural) has become the production standard across 2025–2026, validated across multiple independent research reviews and framework implementations. — [Zylos Research, 2026-04-05](https://zylos.ai/research/2026-04-05-ai-agent-memory-architectures-persistent-knowledge)
- **Benchmark data:** Mem0 achieved 26% higher accuracy vs OpenAI's memory system on LoCoMo evaluation benchmarks, with 91% lower latency than full-context approaches and 90% token cost reduction by sending only relevant facts rather than full conversation history. — [Mem0 documentation / Azalio comparison](https://www.azalio.io/mem0-an-open-source-memory-layer-for-llm-applications-and-ai-agents)
- **Enterprise production pattern:** Redis-backed LangGraph checkpointing (sub-millisecond writes via `RedisSaver`) handles execution state persistence across crashes, enabling thread resume within 30 seconds of hard kill. PostgreSQL-backed `PostgresSaver` adds compliance auditability for regulated industries. — [Markaicode LangGraph + Redis guide](https://markaicode.com/integrate/langgraph-with-redis) and [LangGraph stateful agents production guide](https://www.scaled2c.com/blog/multiagent-systems-aiops/langgraph-stateful-agents-production-deployment-guide.html)
- **Primary source (HN):** "When we first started building with LLMs, the gap was obvious: they could reason well in the moment, but forgot everything as soon as the conversation moved on. You could tell an agent 'I don't like coffee,' and three steps later it would suggest espresso again." — [HN Show: SQL-based agent memory](https://news.ycombinator.com/item?id=45329322)

## Gotchas

- **Checkpointing ≠ memory.** LangGraph's `MemorySaver` persists execution state so an agent can resume after a crash — it does not give the agent searchable recall of past conversations. These are two separate systems you need to build or compose.
- **Context length is attention, not storage.** Even with a 200K-token context window, models start forgetting mid-window at 60% capacity. Do not assume a long context eliminates the need for a memory layer.
- **Fact staleness is a production hazard.** Preferences and facts change. Without a mechanism to update or expire stored memories, the agent confidently acts on outdated information. Build explicit memory update or TTL logic into your `memory.add()` flow.
- **Multi-agent memory sharing is unsolved for most teams.** When two agents serve the same user, each typically has its own memory store. Cross-agent memory consistency requires either a shared backing store or explicit memory synchronization — most production systems have neither.
- **Embedding drift.** As models and embedding models evolve, old embeddings may not align with new ones. Budget for periodic re-embedding of the memory store when you upgrade embedding models.
