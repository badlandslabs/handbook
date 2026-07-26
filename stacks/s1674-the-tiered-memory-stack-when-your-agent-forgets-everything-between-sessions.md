# S-1674 · The Tiered Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent works great in demos. Start a new conversation and it knows nothing. Ask it to remember your codebase structure, a decision you made two weeks ago, or your company's deployment workflow and it starts from zero every time. This is the memory problem — and unlike the tooling or orchestration problems, it has no clean framework solution. Six architectures each claim to solve it, and the benchmark that matters (real production recall) barely exists.

## Forces

- **"Just use the filesystem" and "build a proper memory system" are both defensible.** Letta's benchmarking post (Aug 2025) showed a plain filesystem scoring 74% on LOCOMO — beating Mem0's graph variant. The right answer depends on your retrieval needs, not the architecture's sophistication.
- **Three retrieval primitives exist and teams default to all three.** Vector similarity search, knowledge graphs, and entity extraction pipelines each solve different recall problems. Using all three at once adds latency and cost; using only one misses use cases.
- **Staleness is the failure mode nobody talks about.** A memory that's technically retrieved correctly can still be wrong — outdated, scoped wrong, or contradicting another retrieved fact. The system is confident; the answer is stale.
- **Memory is agent-specific by default, breaking multi-agent architectures.** hmem's Show HN launch (HN ID 47103237) identified vendor and machine lock-in as the core memory problem: switching from Claude Code to Cursor erases everything. Cross-agent memory sharing requires explicit architecture.

## The move

Layer memory by purpose, not by technology. Start simple and add complexity only when the simpler layer's failure mode actually hits you.

**The four-layer taxonomy (practitioner consensus, 2025-2026):**
- **Working memory** — context window + active state. Every turn, decide what enters and what gets compressed. Use recursive summarization or semantic compression, not FIFO.
- **Episodic memory** — captured session events with temporal metadata. Store raw at first; synthesize at session end (the "reflect" pattern). Don't store everything.
- **Semantic memory** — structured facts extracted and generalized across sessions. Query this, don't scroll it. Use hybrid search (embedding similarity + BM25 keyword) to cover both fuzzy recall and exact fact lookup.
- **Procedural memory** — agent-defined rules, habits, and skills. CLAUDE.md for coding agents; config files for domain agents. The agent writes and edits this itself.

**Start with filesystem as baseline.** Letta proved (Letta Blog, Aug 2025) that conversation-history-in-files on `gpt-4o-mini` scores 74.0% on LOCOMO — above Mem0 graph's 68.5%. Don't add a vector database until you have a retrieval failure the filesystem can't recover from.

**Capture hooks beat manual memory.** agentmemory (GitHub 25.7K stars) implements 12 auto-capture hooks — file edits, command outputs, decisions — eliminating the need to manually tell the agent to remember things. This is the right model.

**Use the reflect pattern at session end.** Synthesize key facts, decisions, and user preferences instead of storing raw transcripts. This compresses ~170K tokens/year vs 19.5M+ for full context paste (agentmemory benchmarks). Claude Diary, fsck.com episodic memory, and claude-mem all use this approach.

**For graph memory, start with entity extraction over relationship mapping.** Mem0 removed its graph layer in v3 open-source after production data showed entity extraction + vector search handles most co-retrieval needs without the graph overhead. Add graph only if you have explicit multi-hop reasoning requirements.

**Make memory portable.** Use SQLite or a local file format. Avoid proprietary formats tied to one agent implementation — the moment you switch tools, you lose everything.

## Evidence

- **Letta research post (Aug 2025):** Plain filesystem achieves 74.0% accuracy on LOCOMO multi-session recall benchmark, beating Mem0 graph variant (68.5%) scored on the same benchmark. Letta argues modern models' file-search capabilities make specialized retrieval redundant for many use cases. — [letta.com/blog/benchmarking-ai-agent-memory](https://www.letta.com/blog/benchmarking-ai-agent-memory)
- **Mem0 ECAI 2025 paper (arXiv 2504.19413):** Introduced Mem0 as entity-extraction + vector-search memory with optional graph layer (Mem0g). Evolving agentic memory further illustrates value of structured persistent memory for multi-session coherence. — [arxiv.org/abs/2504.19413](https://arxiv.org/abs/2504.19413)
- **AgentMarketCap analysis (Apr 2026):** Surveyed 5 major memory repos (80K+ combined stars) and found a 91% latency gap between memory architecture approaches in production. Agents with proper memory achieve 3-5x higher task completion rates and 70% cost reduction via semantic caching. — [agentmarketcap.ai/blog/2026/04/13/ai-agent-memory-architecture-production-2026](https://agentmarketcap.ai/blog/2026/04/13/ai-agent-memory-architecture-production-2026)
- **Show HN — hmem (HN ID 47103237):** Identified vendor lock-in and context dilution as the two core memory problems for coding agents. Built a portable SQLite-backed MCP server so memory survives tool and machine switches. — [news.ycombinator.com/item?id=47103237](https://news.ycombinator.com/item?id=47103237)
- **GitHub — agentmemory (25.7K stars, Feb 2026):** 100% top-5 hit rate on coding-agent-life-v1 benchmark with ~170K tokens/year vs 19.5M+ for full context paste. 12 auto-capture hooks eliminate manual memory management. — [github.com/rohitg00/agentmemory](https://github.com/rohitg00/agentmemory)
- **Show HN — formative-memory (HN ID 48048647):** Memories strengthen through use, fade when unused, and consolidate overnight. Implements Hebbian-style association where retrieved memories pull their neighbors via single-hop expansion. — [github.com/jarimustonen/formative-memory](https://github.com/jarimustonen/formative-memory)

## Gotchas

- **Staleness is not a retrieval failure.** A technically accurate retrieval can still be wrong — the policy changed, the file moved, the user corrected their preference. Add timestamps, staleness checks, and contradiction detection at retrieval time.
- **The filesystem baseline has a ceiling.** 74% on LOCOMO is impressive, but LOCOMO tests single-session and multi-session factual recall — not complex relational reasoning. If you need multi-hop queries (e.g., "who worked on the auth module last quarter, and what did they change?"), you'll need a graph or entity extraction layer eventually.
- **Token cost compounds silently at query time.** A retrieval pipeline (embed + rerank + LLM synthesis) costs $0.002-0.01/query at low volume. At scale (thousands of sessions), this is a meaningful line item. Budget for it before wiring it into every turn.
- **Memory decay must be intentional, not automatic.** Formative Memory's "forgetting" model (strength fades when unused) sounds right but can lose critical institutional knowledge. Default to explicit expiration or consolidation triggers, not automatic decay.
- **Sharing memory across agents requires a write contract.** If two agents update the same memory store, you need to decide who wins. Without an explicit policy, agents can overwrite each other's synthesized facts with conflicting raw observations.
