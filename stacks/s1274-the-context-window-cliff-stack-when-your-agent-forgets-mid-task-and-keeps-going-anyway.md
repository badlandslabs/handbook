# S-1274 · The Context Window Cliff Stack — When Your Agent Forgets Mid-Task and Keeps Going Anyway

[Your agent completes steps one through six flawlessly. Step seven contradicts step two. Step eight hallucinates a tool that doesn't exist. Step nine confidently submits garbage. Nothing crashed. No error was thrown. The agent simply forgot what it was doing — and kept going anyway.]

## Forces

- **The advertised context window is not your effective context window.** Models lose reliable reasoning well before their technical token limit. Your agent can technically accept 200K tokens but starts making confident mistakes at 80K.
- **Agents don't know when they're failing.** Context exhaustion doesn't throw an error — it produces a plausible but wrong answer that the agent believes and acts on. You find out at the output stage, not the failure stage.
- **More memory creates more failure surface.** Every extra tool result, API response, and retrieved document you prepend to context increases the chance of overflow. Memory tiering and compression are load-bearing architecture, not polish.
- **Checkpoint overhead vs. recovery cost.** Saving state at every step adds latency and complexity. But without checkpoints, a mid-task context overflow discards everything — you retry from scratch or accept degraded output.

## The move

Build a three-tier memory architecture with explicit context budgeting and checkpoint failure recovery:

- **Tier 1 — Working memory (context window):** Reserve 50-60% of your effective context window for reasoning space. Pre-pend system prompt, agent instructions, and the active task state. Everything else lives outside.
- **Tier 2 — Short-term memory (session store):** Raw buffer of recent turns using a two-buffer model — a raw buffer for the last K messages and a summary buffer for compressed history. When the raw buffer overflows, an LLM call compresses the oldest K turns into a structured summary. Use dated-observation format (not free text) so summaries are retrievable by time and topic.
- **Tier 3 — Long-term memory (vector store):** Persist across sessions using semantic search over structured memory records. Each memory entry has typed fields (user_id, entity, timestamp, topic, importance_score) enabling SQL joins and recency weighting alongside vector similarity. pgvector on PostgreSQL wins over dedicated vector DBs for agent memory because you get typed metadata, access frequency tracking, and SQL joins in one system. Pinecone or Qdrant win for pure retrieval at scale.
- **Context budgets per workflow phase:** Divide your effective context into explicit budgets per step. If your reliable window is 32K tokens and your workflow has eight steps, each step gets ~4K of net new context. Steps needing more must compress or externalize; steps needing less donate to later phases.
- **Instrument token consumption at every tool call.** Log token counts per step. Discover that one verbose API response or greedy file read accounts for half your context consumption. You can't budget what you don't measure.
- **Checkpoint before every cross-system call.** Before invoking an external API, tool, or another agent, write the current state (task goal, completed steps, pending steps, relevant entity facts) to Tier 2. On context overflow, the agent recovers from the checkpoint rather than retrying from scratch.
- **Classify errors before retrying.** Four error types need different recovery: transient (429, timeout — retry after wait), semantic (malformed JSON, invalid tool schema — re-prompt with corrective context), resource (token budget exceeded — summarize/drop/switch model), fatal (401, revoked key, policy violation — abort and alert). Retrying a fatal error amplifies damage.

## Evidence

- **Engineering post:** Anthropic's production multi-agent research system uses a LeadResearcher agent with a dedicated Memory component that checkpoints plan state whenever context approaches 200K tokens, enabling recovery across truncation boundaries without losing task continuity. — [ByteByteGo: How Anthropic Built a Multi-Agent Research System](https://blog.bytebytego.com/p/how-anthropic-built-a-multi-agent)
- **Engineering post:** Anthropic's internal evaluation found that a system with Claude Opus 4 as lead agent and Sonnet 4 as subagents outperformed single-agent setups by >90%, but consumed ~15x more tokens than standard chat. Subagents each operate in independent context windows, preventing any single agent's context from accumulating unboundedly. — [ByteByteGo: How Anthropic Built a Multi-Agent Research System](https://blog.bytebytego.com/p/how-anthropic-built-a-multi-agent)
- **Blog post:** Kronvex benchmarks agent-memory vector DB requirements vs. generic RAG retrieval and finds pgvector wins for agent memory specifically because it supports typed metadata, recency weighting, and SQL joins — features dedicated vector DBs either lack or require separate systems to provide. — [Kronvex: Vector Databases for AI Agents: pgvector vs Pinecone](https://kronvex.io/blog-vector-database-agents)
- **GitHub repo:** The agent_memory project (PostgreSQL + pgvector) implements seven memory types as a layered architecture: working memory, episodic memory, semantic memory, procedural memory, sensory memory, preference memory, and relational memory — each persisted with typed records and semantic retrieval. — [GitHub: srinivasraom/agent_memory](https://github.com/srinivasraom/agent_memory)
- **Research paper:** arXiv 2511.22729 formally categorizes context window overflow solutions — truncation (loses information), summarization (distorts specifics), retrieval-augmented compression (loses granularity), and selective context management (preserves important facts while discarding noise). — [arXiv: Solving Context Window Overflow in AI Agents](https://arxiv.org/abs/2511.22729)

## Gotchas

- **Don't confuse RAG retrieval with agent memory.** RAG retrieves document chunks for factual Q&A. Agent memory retrieves past experiences, preferences, and learned facts about specific entities with typed records, temporal weighting, and session scoping. The schema and query patterns are different.
- **The effective context window is smaller than advertised.** Build with a conservative estimate (30-50% of the model's stated limit) to account for degraded reasoning near the ceiling. Budget headroom for the model's own reasoning tokens, not just your input.
- **Summary compression loses specificity.** Rolling summarization discards exact details — exact dates, specific numbers, verbatim quotes. Use structured observation format with typed fields, not free-text summaries, so compressed memory remains queryable and precise.
- **Checkpoints add latency; no checkpoints add blast radius.** Every cross-boundary call needs a state snapshot. The overhead is worth it: a 4-hour agent pipeline that fails at step 8 without a checkpoint loses all prior work. With a checkpoint, it resumes from step 8.
