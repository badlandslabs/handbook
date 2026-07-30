# S-1852 · The Graph-Native Memory Stack — When Your Agent Forgets What It Already Figured Out

Your agent works for five minutes. Then it re-answers questions it already resolved last session, loses track of entities across a conversation, and can't tell you what it concluded thirty seconds ago. Vector-store memory gives it raw retrieval — not structured recall. The graph-native memory stack gives it a shared model of entities, relationships, and session history that survives across turns and compounds value over time.

## Forces

- **Flat memory flattens reasoning.** Storing conversation logs in a vector store lets you retrieve similar past exchanges — but it can't tell you *which entity* a prior conclusion was about, or whether two mentions of "the deployment" refer to the same thing or different ones.
- **RAG without structure answers questions; graphs answer questions about relationships.** "What happened after the Q3 outage?" requires tracing a causal chain through events, systems, and outcomes. Vector chunks scatter that chain across unrelated documents. A graph connects it.
- **Context window is finite; entity graphs are not.** A conversation graph with 10,000 nodes still answers a single-hop query in one retrieval step. Ten thousand documents in a vector store answer a multi-hop query by luck.
- **Session isolation kills continuity.** Every new session starts from zero. A graph-backed memory layer means the agent picks up exactly where the last session ended — including what it decided, what it deferred, and what it learned.

## The move

Treat your knowledge graph as the agent's persistent working memory — not a retrieval backend, but an active context layer that mirrors how the agent actually reasons.

**Build a context graph for every agent session:**
- Extract entities (people, systems, decisions, errors) and edges (caused, depends-on, resolved-by) from every tool call, observation, and conclusion.
- Store each session node with a timestamp, outcome, and summary. Link it to prior sessions through shared entities.
- The agent queries the graph before acting: "What do I already know about this deployment?" — not "find relevant text."

**Use GraphRAG for multi-hop reasoning:**
- Instead of semantic similarity search, traverse the graph from the query entity outward N degrees.
- Microsoft's Agent Framework ships an [official Neo4j GraphRAG Context Provider](https://learn.microsoft.com/en-us/agent-framework/integrations/neo4j-graphrag) (April 2026) that implements this natively.
- Neo4j's neo4j-agent-memory library ([GitHub](https://github.com/neo4j-labs/agent-memory)) lets agents build and query context graphs directly from tool interactions.

**Separate short-term and long-term graph stores:**
- **Short-term (working memory):** recent session nodes, unresolved entities, pending decisions. Low-latency, high-frequency writes.
- **Long-term (knowledge base):** durable entity schema, canonical relationships, learned facts. Lower write frequency, supports complex traversal.

**Mirror the system prompt into the graph:**
- Store policy rules and constraints as typed nodes. Before a high-stakes tool call, the agent traverses the graph to confirm the action is policy-compliant — more reliable than checking a prose prompt under token pressure.

## Evidence

- **Microsoft Agent Framework + Neo4j integration:** The [official Microsoft GraphRAG Context Provider for Agent Framework](https://learn.microsoft.com/en-us/agent-framework/integrations/neo4j-graphrag) (April 2026) and [Neo4j Memory Provider](https://learn.microsoft.com/en-us/agent-framework/integrations/neo4j-memory) give agents persistent, graph-native memory as a first-class integration — not a plugin. William Lyon (Neo4j PM) documented the [reference architecture](https://neo4j.com/blog/developer/building-an-ai-agent-with-memory-microsoft-agent-framework-neo4j/) showing how session history, entity graphs, and GraphRAG queries replace flat conversation logs.
- **Neo4j production case studies:** Jesús Barrasa (AI Field CTO, Neo4j) documented [production agent failure modes](https://neo4j.com/blog/agentic-ai/ai-agent-useful-case-studies/) — specifically how agents that use structured knowledge graphs as the context layer avoid the "lost state" and "context becomes noise" problems that plague vector-store-backed agents. The case studies cover supply chain, financial services, and IT operations — domains where entity relationships are the primary unit of reasoning.
- **MMC Ventures founder survey (30+ startups, 40+ enterprise practitioners, Nov 2025):** Found that "incremental deployment beats ambition" — teams succeeding with agents in production focused on narrow, verifiable use cases with measurable ROI. The survey also found that over half of teams build their own agentic stacks rather than using off-the-shelf frameworks, suggesting the graph-memory layer is being adopted as a custom integration pattern. — [MMC Ventures State of Agentic AI: Founder's Edition](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)

## Gotchas

- **Graph schemas require upfront design — and they decay.** Entities and relationships that made sense at launch become wrong as the agent encounters new types of interactions. Build schema migration into your graph-memory lifecycle from day one.
- **Write latency is the bottleneck.** Every tool call that should update the context graph creates a write. If your graph store has high write latency, the memory layer falls behind the agent and becomes stale. Profile write paths, not just read paths.
- **Graph traversal depth is a tuning knob, not a constant.** A 2-hop query is fast. A 5-hop query that the agent needs to answer "what downstream effects did this incident have?" can time out. Set per-query depth limits and fall back to partial results with an explanation.
- **The graph doesn't self-populate.** You must explicitly write entity-extraction and relationship-binding prompts into the agent's tool call handlers. Without instrumentation, the graph stays empty and the agent keeps using flat memory.
