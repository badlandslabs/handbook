# S-1989 · The Memory Signal Stack — When Your Agent Remembers Everything and Finds Nothing

[Your agent has a 500K-token conversation history. Every session the user says "you already solved this last month" and the agent draws a blank. You added memory — a vector store, full-text index, the works. The agent stores everything. It retrieves nothing useful. The gap between hoarding and knowing is where most agent memory projects quietly die.]

## Forces

- **Storage is cheap; retrieval is expensive.** The hard problem is not remembering — it is surfacing the right memory at the right time without flooding context with noise. Most teams solve storage and declare victory.
- **Storing everything makes retrieval harder.** A vector index over 10,000 entries with no curation beats no memory on paper and loses to a curated 50-entry index in practice. Signal-to-noise ratio in retrieval is the actual bottleneck.
- **The three memory tiers have different retrieval semantics.** Episodic memory (events) needs temporal search. Semantic memory (facts) needs graph traversal and validity tracking. Procedural memory (skills) needs few-shot examples and prompt fragments. A single vector index cannot serve all three well.
- **Facts become stale; naive retrieval doesn't know it.** A semantic memory from six months ago may be factually superseded. Without validity tracking, the agent acts on outdated ground truth.
- **The framework doesn't own retrieval; the agent does.** The agent decides what to query, when to query it, and whether the retrieved result actually helps. Memory infrastructure is only half the problem.

## The move

The three-tier taxonomy from cognitive science maps directly onto agent architecture. Build three distinct stores with different retrieval semantics, and gate writes through an extraction + validation layer.

**Tier 1 — Working memory (in-context, zero retrieval latency)**
- The agent's current context window: task description, recent tool outputs, active subtask state
- Nothing here is persisted — it lives and dies with the session
- Loaded from tiers 2–4 at session start via a relevance router

**Tier 2 — Episodic memory (events, temporal search)**
- Store each agent interaction as an event with: timestamp, participants, action taken, outcome, and a one-line summary
- Retrieve via time-bounded queries ("what did I do in the last 3 sessions about auth?") and semantic similarity
- Real-world implementations: Graphiti's temporal knowledge graph (Zep AI) tracks event validity windows — facts have `t_valid` and `t_transaction` timestamps so superseded relationships are never retrieved
- YourMemory (GitHub: sachitrafa/YourMemory) applies a biological forgetting curve to scored memories: recency is a retrieval signal, not a hard filter

**Tier 3 — Semantic memory (facts, graph traversal)**
- Extract durable facts from episodic events: preferences, decisions, commitments, entity properties
- Store as typed nodes in a knowledge graph, not flat vectors — enables "user prefers X over Y" queries that semantic search can't answer reliably
- Validity tracking is non-optional: facts have expiry conditions or last-verified timestamps. Graphiti's bi-temporal model handles this natively; Mem0 requires explicit invalidation calls
- Cognee's "cognify" pipeline builds a typed ontology from raw data (30+ connectors: PDFs, Slack, Notion, audio). The ontology is the schema — facts are extracted into typed nodes, not raw text chunks

**Tier 4 — Procedural memory (skills, how-to)**
- Store as prompt fragments, tool definitions, and few-shot examples — not natural language descriptions
- The agent reads these at session start, not at retrieval time: procedural knowledge needs to be in-context to be used
- Anthropic's production pattern: store skills as versioned files in the repo (`.claude/skills/`) alongside their git commit hashes. When the agent loads a skill, it loads the version that was tested, not the latest

**The extraction gate (write-side filtering)**
- Every tier-2/3 write goes through an LLM extraction step: given a raw event, what durable knowledge does this create?
- Deduplicate before writing: extract → compare against existing facts → only write net-new information
- This is the predict-calibrate pattern from Memv: predict what the new session should add to existing knowledge, then extract only the delta. Dramatically reduces storage bloat

**The relevance router (read-side filtering)**
- At session start, the agent describes its current task. A lightweight LLM call routes to the appropriate tier(s) with a query
- Multi-signal retrieval: semantic similarity + BM25 keyword match + entity boost (facts about entities in the current query get weighted higher)
- YourMemory combines semantic search with recency scoring and a time-decay forgetting curve: $R(m_i,t) = \exp(-\lambda(t-t_i))$ — exponential decay on old memories, weighted fresher

**Consolidation job (periodic background process)**
- Nightly or post-session: merge related episodic entries into a single summary fact (tier 3)
- Invalidate superseded semantic memories — flag or delete facts with expired validity
- Prune episodic entries older than a retention window unless tagged as permanent
- This is what separates a memory system that gets smarter over time from one that just gets bigger

## Evidence

- **Anthropic engineering post:** Their long-running agent harness uses a flat `progress.txt` + git history for decision tracking, with explicit versioning of all memory updates. "Versioning stores all versions of memories, enabling rollback if updates prove ineffective." — ZenML LLMOps Database covering Anthropic's context management guidance. https://www.zenml.io/llmops-database/context-engineering-and-memory-management-for-production-agent-systems
- **Zep/Graphiti production pattern:** Graphiti's bi-temporal knowledge graph tracks `t_valid` (when a fact was true in the world) and `t_transaction` (when the agent learned it). "Every graph edge includes explicit validity intervals so superseded relationships are never retrieved." — Neo4j Developer Blog, Daniel Chalef (Zep AI founder). https://neo4j.com/blog/developer/graphiti-knowledge-graph-memory/
- **Cognee vs. Zep comparison:** Cognee builds typed ontologies from raw data via its "cognify" pipeline — extraction into typed graph nodes, not raw chunks. Zep scores 63.8% on LongMemEval (GPT-4o) using temporal graph traversal. Cognee has no published benchmark. — Vectorize.io benchmark comparison, April 2026. https://vectorize.io/articles/zep-vs-cognee
- **HN discussion:** Three-layer architecture separating "model actualization" (semantic), "structured task storage" (episodic + Jira-like), and "git" (procedural/decision rationale) for long-running agents. Each layer has distinct retrieval semantics — querying a flat progress file for "what decision led to this?" fails. https://news.ycombinator.com/item?id=46097759

## Gotchas

- **Episodic-only is not memory — it is a longer chat log.** Storing conversation history and calling it memory is the dominant failure mode. Agents can quote the past but cannot generalize from it. You need extraction + consolidation, not just storage.
- **Vector retrieval degrades with scale.** A flat vector index over 50K+ entries has poor precision for factual queries. Graph traversal and typed entity lookup outperform pure embedding similarity for relational questions.
- **Stale facts are active liabilities.** Without validity tracking, the agent will confidently act on contradicted ground truth. The retrieval layer must expose fact age and source, and the agent must prefer fresher information.
- **Your retrieval budget is finite.** Every memory query costs tokens and latency. Tier 4 (procedural) goes in-context at session start. Tiers 2–3 are queried on-demand. Over-querying memory defeats the purpose — start with the smallest retrievable set that improves task quality, not the largest set that fits.
- **Memory corruption propagates silently.** A bad extraction write contaminates future sessions. Anthropic's versioning + rollback pattern is not optional for production systems: track what each update contained, who triggered it, and make it revertable.
