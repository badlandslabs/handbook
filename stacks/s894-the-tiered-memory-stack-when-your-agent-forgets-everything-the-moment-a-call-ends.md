# S-894 · The Tiered Memory Stack — When Your Agent Forgets Everything the Moment a Call Ends

LLMs reset to blank slate on every API request. Your agent won't remember what happened five minutes ago — not because of a bug, but because context windows are per-call by design. The moment you close the loop, the agent is new again. Tiered memory is how production teams bridge that gap.

## Forces

- **Context amnesia is architectural, not accidental.** Frontier models have large context windows, but they reset per-call. Session persistence across days and weeks requires infrastructure, not prompting.
- **More memory is not better memory.** Injecting everything into context is expensive — processing 10M tokens at 2026 prices costs ~$5 per inference call. Retrieval that filters to the relevant slice is what makes memory economically viable.
- **Memory systems introduce new failure modes.** A retrieval-augmented memory layer that returns wrong facts is worse than no memory at all — the agent acts confidently on a plausible-sounding error. Retrieval quality compounds agent reliability in ways that are hard to test.

## The move

Build a tiered memory architecture where the agent actively manages what lives in context, what lives in a retrieval store, and what lives in long-term archival. Three concrete patterns in production:

- **Tiered self-management (Letta/MemGPT):** Three memory tiers — core (always in context, like RAM), archival (vector store / structured DB, like disk), recall (full conversation history). The agent decides what to page in and out via an inner monologue. Heartbeat mechanism lets the agent chain memory operations without waiting for user input. Core memory stays bounded; archival is searched selectively; recall provides temporal grounding. — [Letta GitHub](https://github.com/letta-ai/letta), [Adaptive Recall — Letta Memory Hierarchy](https://www.adaptiverecall.com/memory-architecture/letta-memory-hierarchy.php)

- **Git-backed structured memory (DiffMem):** Store memories as markdown files in a Git repo — each conversation is one commit. BM25 for search instead of embeddings. `git diff` shows how understanding evolves over time; `git blame` tracks provenance; `git checkout` to any point to see what the agent knew then. Sub-second retrieval; ~100MB for a year of conversations. Six months post-PoC, the author reports it running in production with real workloads. — [HN Show: DiffMem](https://news.ycombinator.com/item?id=44969622), [HN Follow-up: DiffMem in production](https://news.ycombinator.com/item?id=47228509), [DiffMem GitHub](https://github.com/Growth-Kinetics/DiffMem)

- **Retrieval-augmented memory with observability (Mem0 + agentmemory):** Mem0 (60k GitHub stars) provides a universal memory API — semantic search, user/agent/session memory scopes, configurable embedding providers. agentmemory benchmarks at 95.2% recall@5 on LongMemEval-S (ICLR 2025), with 100% top-5 hit rate on coding agent benchmarks, at 14ms latency. Supports MCP interface for Cursor, Claude Code, Codex CLI, Gemini CLI, Hermes, OpenClaw, and more. — [Mem0 GitHub](https://github.com/mem0ai/mem0), [agentmemory GitHub](https://github.com/rohitg00/agentmemory), [Reddit: Agent Memory tools for LLM systems](https://www.reddit.com/r/LocalLLaMA/comments/1gvhpjj/agent_memory/)

## Evidence

- **GitHub README:** Mem0 described as "intelligent memory layer for AI assistants and agents — remembers user preferences, adapts to individual needs, across sessions, users, and AI agents" — [https://github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)
- **HN Show (198 points):** DiffMem replaced vector databases with Git for AI memory storage; entire index for a year of conversations fits in ~100MB RAM with sub-second retrieval — [https://news.ycombinator.com/item?id=44969622](https://news.ycombinator.com/item?id=44969622)
- **PingCAP engineering blog:** mem9 on TiDB Cloud began as a customer request in March 2026 — shipping a prototype before writing a plan. Key lesson: "Agent memory is not a storage problem. It is an engineering problem at the intersection of ingestion, ranking, evaluation, and product judgment. A memory API alone is not a product." — [https://www.pingcap.com/blog/how-we-built-mem9-agent-memory-product/](https://www.pingcap.com/blog/how-we-built-mem9-agent-memory-product/)
- **Reddit r/SideProject:** Team gave agents ability to add, search, and delete their own memories without human intervention via a CLI the agent calls directly — [https://www.reddit.com/r/SideProject/comments/1sgq9xj/we_let_ai_agents_manage_their_own_memory_heres/](https://www.reddit.com/r/SideProject/comments/1sgq9xj/we_let_ai_agents_manage_their_own_memory_heres/)
- **GetUnblocked benchmark comparison:** Memory MCP server comparison testing Stash, MemPalace, Hindsight, and agentmemory; MemPalace loads 170 tokens at startup, Hindsight scales to 10M tokens (64.1% BEAM score), Stash runs 8-stage consolidation — [https://getunblocked.com/blog/memory-mcp-servers-compared](https://getunblocked.com/blog/memory-mcp-servers-compared)
- **GitHub: agentmemory benchmarks:** 95.2% R@5 on LongMemEval-S (ICLR 2025, 500 questions), 100% top-5 hit rate on coding agent life benchmarks, 14ms retrieval latency — [https://github.com/rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)

## Gotchas

- **Memory poisoning accumulates silently.** If an agent hits a transient error and writes a wrong fact, vector search returns it alongside the correction. The agent holds contradictory beliefs because both are semantically similar. Fava Trails addresses this with JJ-backed validation workflows and structured commit history. — [HN Show: Fava Trails](https://news.ycombinator.com/item?id=47197011)
- **Naive RAG fails at retrieval, not generation.** Redis's AI memory architecture guide (2026) notes that naive RAG pipelines fail ~40% of the time at retrieval for complex queries. Agentic RAG — where the agent decomposes queries, routes to multiple sources, and validates results — outperforms static retrieval on multi-hop reasoning tasks. — [Redis: AI Agent Memory](https://redis.io/blog/ai-agent-memory-stateful-systems)
- **Context window growth doesn't eliminate the need for memory.** Even with 200k+ token windows, session persistence across weeks and selective context injection (pull only relevant facts) still require architectural memory layers. Context windows solve scale within a session; memory solves continuity across sessions.
