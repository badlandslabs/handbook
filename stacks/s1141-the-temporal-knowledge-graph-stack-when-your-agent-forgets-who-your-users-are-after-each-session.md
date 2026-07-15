# S-141 · The Temporal Knowledge Graph Stack — When Your Agent Forgets Who Your Users Are After Each Session

When an agent running for days forgets who the user is, hallucinates prior agreements, and repeats onboarding questions the customer answered twice already.

## Forces

- **Context rot vs. context starvation:** Stuffing everything into context degrades model focus; aggressively pruning risks losing needed information. Neither scales for multi-day sessions.
- **Token cost vs. recall quality:** Vector search hits comparable accuracy at 3–4× fewer tokens vs. raw long-context retrieval, but only if your chunking and metadata hygiene are right.
- **Staleness is the real enemy:** Agents acting on outdated facts cause worse failures than agents with no memory at all. Time must be a first-class dimension, not an afterthought.
- **Write latency is a hidden bottleneck:** Memory writes happen during the agent loop. 800ms graph extraction per turn is unusable; 80ms async writes are acceptable.

## The Move

Use a **temporal knowledge graph** backed by a three-tier memory architecture. Time is not metadata — it is the primary axis.

**Three-tier architecture:**

- **Hot memory (checkpoint store):** PostgreSQL or Redis for current session state. Enables pause/resume, human-in-the-loop workflows, and turn-level continuity. Sub-10ms reads.
- **Cold memory (temporal graph or vector store):** Cross-session knowledge with time-anchored facts. Facts get `valid_from` / `invalid_at` timestamps so the agent can query "what did the user believe in January?" not just "what does the user believe?"
- **Document memory (file-based):** Accumulated project knowledge, human-readable summaries. Enables the agent to read its own memory like a journal — critical for debugging and audit.

**For temporal knowledge graphs specifically (Zep / Graphiti):**

- Store facts as nodes, relationships as edges with timestamps
- Assign `invalid_at` dates instead of overwriting — trace fact history, never silently mutate
- Graph traversals for multi-hop reasoning: "what changed between the user's first call and their complaint last week?"
- Knowledge graphs outperform vectors on temporal reasoning (+29.6 points on LoCoMo temporal subtask) and multi-hop (+23.1 points)

**Framework choices with distinct philosophies:**

| Framework | Core abstraction | Write latency (p50) | Best for |
|-----------|------------------|--------------------|----------|
| **Mem0** | Extracted facts in vector store | ~80–200ms async | Personalization, chat history compression |
| **Zep** | Temporal knowledge graph (Graphiti) | ~300–800ms | Temporal facts, CRM-style support agents |
| **Letta** | Editable memory blocks + archival | ~150–400ms sync | Stateful long-running agents |
| **Mastra** | Three-tier: hot/cold/document | Varies by backend | TypeScript stacks, observational memory |
| **Cloudflare Agent Memory** | Profile-scoped key-value + semantic | ~50–150ms managed | Edge agents, Workers AI integration |

**Anti-patterns to avoid:**

- Storing raw conversation logs as memory — the agent cannot retrieve useful signal from a wall of chat
- Vector-only stores for temporal reasoning — cosine distances between adjacent entries at scale are 0.001 to 0.01, selection threshold and norm clipping eat most of the magnitude
- Over-indexing: "AI Search should index curated artifacts, not raw everything" — retrieval quality depends more on chunk policy and metadata hygiene than on vector algorithm choice

## Evidence

- **Engineering blog (Mastra):** Three-tier memory architecture described with hot (checkpoint/Postgres), cold (vector), and document tiers. Observational memory uses background agents to maintain dense observation logs that replace raw message history as it grows. — [mastra.ai/blog/agent-memory-guide](https://mastra.ai/blog/agent-memory-guide)
- **Product announcement (Cloudflare):** Agent Memory launched April 2026 as private beta. Profile-scoped memory store shared across sessions, agents, and users. Solves context rot — the problem where relevant information gets buried as context fills, even at 1M token windows. — [blog.cloudflare.com/introducing-agent-memory](https://blog.cloudflare.com/introducing-agent-memory/)
- **Benchmark report (Mem0):** LoCoMo benchmark shows temporal reasoning +29.6 points, multi-hop +23.1 points with optimized memory retrieval vs. raw context. 92.5 on LoCoMo, 94.4 on LongMemEval at ~6,900 tokens/query vs. much higher for raw long-context approaches. — [mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **Competitive analysis (AI Workflow Lab):** Framework comparison table with write latency benchmarks across Mem0, Letta, Zep. Zep outperforms on temporal reasoning due to graph-first architecture; Mem0 wins on write speed and simplicity. — [aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026)
- **Industry analysis (AgentMarketCap):** 80,000+ combined GitHub stars across 5 open-source memory repositories in Q1 2026. Memory staleness identified as the hardest open problem, alongside cross-session identity and temporal abstraction at scale. — [agentmarketcap.ai/blog/2026/04/13/ai-agent-memory-architecture-production-2026](https://agentmarketcap.ai/blog/2026/04/13/ai-agent-memory-architecture-production-2026)
- **Show HN:** Lore — cross-agent memory SDK for Python and TypeScript, enabling memory sharing across multiple agents in a system. — [github.com/amitpaz1/lore](https://github.com/amitpaz1/lore), [news.ycombinator.com/item?id=46988014](https://news.ycombinator.com/item?id=46988014)

## Gotchas

- **The LoCoMo benchmark has known flaws** (sequential vs. parallel search, non-standard reranking): treat SOTA claims from any single vendor as unverified until independently replicated. LongMemEval is preferred by the Zep team for more realistic evaluation.
- **Long-context windows are not a substitute for memory:** fact-based memory achieves comparable accuracy at 3–4× fewer tokens vs. raw retrieval. Pushing everything into context is expensive and degrades model focus.
- **Memory staleness causes worse failures than no memory:** an agent acting on outdated facts is more dangerous than one that simply does not remember. Build invalidation into your write path, not just retrieval.
- **Git-backed memory (Letta, late 2025):** version-controlling agent memory objects enables rollback and diffing — worth the added complexity for agents making consequential decisions.
- **Cost is a runtime concern, not a billing review:** token usage balloons via hidden retries, idle agents consume compute silently, long-running workflows keep memory hot. Monitor in production, not post-hoc.
