# S-2072 · The Retrieval-Doesn't-Matter Stack — When Your Knowledge Graph Underperforms a Text File

[Your agent forgets what it learned last session. You spend two weeks wiring up a Neo4j knowledge graph with temporal edges, bitemporal slots, entity resolution, and relation extraction. You embed everything into a Pinecone index with cross-encoder reranking. Three months later, a new team member reports the agent still asks the same questions it was asking before the memory system existed. Meanwhile, a colleague with a Python dict and a SQLite file is getting better recall. This is not a hypothetical. Letta measured it: filesystem retrieval scored 74.0% on LoCoMo, beating Mem0's specialized graph variant at 68.5%. The retrieval mechanism is a second-order concern.]

## Forces

- **Complexity compounds silently.** A vector DB, graph DB, embedding pipeline, reranker, and MCP server each introduce failure modes. When the agent's capability to invoke the system is the bottleneck, adding more infrastructure just adds more ways to fail.
- **Agent tool-use ability is the real variable.** Letta's research shows the same model with a filesystem outperforms a specialized memory tool — because the agent generates better queries against a familiar interface than it does against a novel, complex API. LLMs have seen filesystems in training data; they haven't seen every custom memory SDK.
- **Two-tier architectures conflict on properties.** Checkpoint stores need write-heavy, low-latency, single-thread writes. Semantic memory needs query-heavy, high-recall, cross-session reads. Using one store for both is a design smell that causes both workloads to suffer.
- **Bitemporality is non-negotiable for production agents.** An agent corrects itself — "the user actually lives in Seattle, not Portland." A flat memory overwrites; a bitemporal memory archives the old fact with its record time and assertion time, preserving the history of the agent's evolving understanding.

## The Move

**Start simple. Prove the agent can use memory at all before adding retrieval sophistication.**

- **Use a two-tier architecture, not one.** Checkpoint store (SQLite/Postgres/Redis) for session continuity: thread-scoped, write-heavy, every agent step checkpoints. Semantic memory (filesystem, SQLite, or vector DB) for cross-session recall: query-heavy, survives restarts, populated by summary of completed sessions.
- **File-first as a baseline, not a limitation.** Store conversation histories in newline-delimited JSON or markdown files. Let the agent search them with grep, tree, and cat — tools it already knows. Add vector retrieval only when you can demonstrate a measurable recall gap.
- **Use bitemporal slots at minimum.** Every stored fact has two timestamps: `recorded_at` (wall clock) and `asserted_from` (which session's evidence). When a fact changes, archive the old entry rather than overwriting it. This turns memory revisions into a queryable history.
- **Scope-chain entity identities.** "Alice" is not one entity — she is `{person: Alice, role: lead_engineer, project: AcmeAPI}`. Scope chains let the same canonical entity carry different facts in different project contexts without merge conflicts.
- **Expose memory via MCP tools, not SDK calls.** MCP provides a standardized tool interface. An agent that knows MCP (from training data) will call memory tools correctly; a custom SDK requires the agent to learn a novel interface it has never seen before.
- **Auto-compress at session boundaries.** At session end, run a summarization pass: extract entities, decisions, user preferences, and unresolved tasks from the conversation into a structured memory entry. This replaces a raw conversation dump with a dense, retrievable artifact.

## Evidence

- **Research benchmark:** Letta agents running `gpt-4o-mini` achieve 74.0% on the LoCoMo memory benchmark by storing conversation histories in plain files — beating Mem0's specialized graph variant at 68.5%. The agents iteratively searched files using natural language queries, generating custom retrieval strategies rather than relying on single-hop semantic similarity. — [Letta Research Blog, August 2025](https://www.letta.com/blog/benchmarking-ai-agent-memory/)
- **GitHub repository:** Agent-recall was extracted from a live system at a digital agency managing 30+ concurrent agents across 15+ clients. Every feature (scope isolation, bitemporal slots, AI-generated briefings) was added because something broke in production. Key insight: "two agents wrote conflicting data to the same entity" — scope chains with inheritance solved this. — [GitHub — mnardit/agent-recall](https://github.com/mnardit/agent-recall)
- **Production guide:** LangGraph's SQLite checkpointer is the most mature open-source implementation of thread-scoped checkpointing. Checkpoint store and semantic memory have conflicting access patterns — write-heavy/low-latency vs. query-heavy/high-recall — and treating them as one store is the #1 production mistake. — [NiteAgent Production Guide](https://niteagent.com/blog/agent-memory-production-guide/)

## Gotchas

- **Adding vector retrieval before proving basic recall.** If the agent won't reliably call `save_memory`, it won't call `vector_search`. Build the habit with simple tools first, then add sophistication.
- **Overwriting instead of archiving.** When a fact changes, overwriting the old entry destroys the agent's ability to reason about its own evolving understanding. Always archive with timestamps; overwrite only at compaction time.
- **Flat entity namespacing.** A single key `"Alice"` for every fact about Alice across all projects and sessions causes merge conflicts in multi-agent environments. Use scope chains: `{entity_id}/project/projectname/role/lead_engineer`.
- **No session-boundary compaction.** Raw conversation history grows unbounded. Without a summarization step at session end, the memory store fills with noise (turn-level chatter) that degrades retrieval signal-to-noise ratio.
