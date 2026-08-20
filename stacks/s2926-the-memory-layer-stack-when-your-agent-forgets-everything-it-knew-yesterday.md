# S-2926 · The Memory Layer Stack — When Your Agent Forgets Everything It Knew Yesterday

Your agent aced the onboarding session. It knew the user's name, their project goals, their preferred stack, the decisions they made last week. Forty-eight hours later, it greets them like a stranger. Every session starts from zero. The agent is capable but amnesiac — and the user is tired of repeating themselves.

## Forces

- **Context windows are finite but sessions aren't.** Full-context stuffing works for a single session until it doesn't — day-7 context window limits hit continuously running agents, and multi-tenant architectures can't share a context across users.
- **Retrieval is harder than storage.** Embedding-based retrieval loses nuance, provenance, and temporal ordering. "The capital of France" is easy to store and retrieve; "the last time the user mentioned this project, they were frustrated about the deployment pipeline" is not.
- **Token economics punish statelessness.** Re-injecting the same context on every call burns tokens at scale. Selective external memory accepts a ~6pp accuracy gap vs. full-context in exchange for 90% fewer tokens consumed (ECAI 2025, per Mem0's benchmark data).
- **The four architectural camps haven't subsumed each other.** Vector-first extraction (Mem0), graph-native temporal reasoning (Zep, Graphiti), OS-inspired tiered context (Letta), and hybrid Redis + PostgreSQL each solve different memory failure modes. Picking the wrong pattern for your use case means spending complexity without fixing the actual problem.
- **Evaluation is still immature.** Fewer than 1 in 4 organizations have scaled agents to production as of early 2026, and memory architecture is consistently cited as the top technical bottleneck (AgentMarketCap, April 2026).

## The Move

Three-tier taxonomy mirrors cognitive science — but the engineering is the hard part:

- **Episodic memory** — past events, conversation logs. Implemented as structured conversation records with timestamps, linked to user/session IDs. Storage: PostgreSQL (permanent) + Redis (hot cache with TTL).
- **Semantic memory** — declarative facts, entity relationships. Implemented as either vector embeddings (semantic search) or knowledge graphs (temporal, relational). Storage: pgvector or dedicated graph DB.
- **Procedural memory** — workflows, behavioral heuristics, agent instructions. Implemented as system prompt templates, tool definitions, and agent configuration stored as versioned config.

**The extraction timing problem is the most consequential design choice.** Eager extraction (after every message) wastes tokens on noise. Lazy extraction (end of session) loses transient context needed to resolve pronouns and intent. The right approach: extract on conversation boundary transitions — when the topic shifts, the user explicitly changes subject, or a significant time gap occurs (brgsk.xyz, May 2026).

**The hybrid dual-layer pattern is production-proven for real-time agents.** Redis L1 (~1ms latency, 24h TTL) serves active conversation context; PostgreSQL L2 (~10ms, permanent) stores history and enables analytics. An async sync service bridges them without blocking user interactions (Propel AI Bootcamp, 2025).

**ByteRover inverts the external-service paradigm.** Instead of memory as an external service agents call into (creating semantic drift, lost coordination context, and recovery fragility), the same LLM that reasons also curates, structures, and retrieves knowledge into a hierarchical Context Tree — Domain → Topic → Subtopic → Entry, with explicit provenance per entry. Storage is local filesystem, no external databases (arXiv:2604.01599, April 2026).

**MemForge adds a neuroscience-inspired consolidation cycle.** Unlike passive stores, it actively improves knowledge over time through "sleep cycles" — LLM review of low-confidence memories that rewrites and strengthens them. Tracks revision stability, retrieval correlation, and contradiction rates. Single PostgreSQL database with pgvector and pg_trgm (salishforge/memforge, Show HN 2026).

## Evidence

- **Academic taxonomy:** The three-tier episodic/semantic/procedural model is now canonical across both academic research (arXiv:2603.07670, March 2026 — "Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers") and production frameworks. The field has converged; implementation divergence is where the real engineering happens.
- **Production benchmark data:** Mem0 scored 92.5 on LoCoMo and 94.4 on LongMemEval at ~6,900 tokens/query. Biggest gains: +29.6pp on temporal reasoning, +23.1pp on multi-hop reasoning. The three standard benchmarks (LoCoMo, LongMemEval, BEAM) now define memory architecture comparison (mem0.ai, August 2026).
- **Market signals:** Mem0 closed a $24.5M Series A in October 2025; Zep hit $1M ARR at 5 people. Enterprise apps with AI agents projected at 40% in 2026, up from <5% in 2025 — memory infrastructure is a first-class concern now (AgentMarketCap, April 2026).
- **Hacker News primary source:** The HN thread on agent memory (news.ycombinator.com/item?id=48287808, 40 points, May 2026) surfaced a key practitioner insight: the most consequential choice in extraction is *timing*, and most libraries get it wrong by choosing one extreme or the other instead of boundary-triggered extraction.
- **Letta benchmark infrastructure:** Letta published evaluation code on GitHub (github.com/cpacker/letta) integrating LoCoMo, MemBench, and LongMemEval — the first open-source framework to ship standardized memory benchmarks as part of its release, validating that memory evaluation needs to be reproducible and automated (Letta blog, 2026).

## Gotchas

- **Semantic drift is invisible until it's catastrophic.** When the memory service captures something different from what the agent understood, there is no error — just gradually incorrect behavior. ByteRover's agent-native design addresses this structurally, but most teams won't adopt it; the mitigation is provenance tracking on every stored fact.
- **Cross-session identity is unsolved.** When does a user become the "same user" vs. a new session? Most systems use a user_id, but user intent, context, and preferences can shift between accounts or devices. Temporal knowledge graphs (Zep, Graphiti) approach this with time-bucketed entity graphs — but cross-session reconciliation still requires explicit rules.
- **Memory staleness compounds silently.** A fact stored on day 1 may be wrong by day 3, but the agent has no signal to re-validate it. MemForge's active consolidation cycles are the most mature response; most production systems rely on TTLs or manual re-ingestion. This is the "static number fallacy" — agents copy a funding rate to memory and treat it as constant until someone notices (HN Ask: "What breaks when you run AI agents unsupervised," 2026).
- **Benchmark-architecture mismatch.** LongMemEval measures retrieval accuracy, but downstream agent performance depends on retrieval *timing*, storage *cost*, and forgetting *behavior* — none of which the benchmarks capture well yet. The evaluation gap is real: arXiv:2507.05257's MemoryAgentBench is a step toward holistic evaluation, but adoption is early.
