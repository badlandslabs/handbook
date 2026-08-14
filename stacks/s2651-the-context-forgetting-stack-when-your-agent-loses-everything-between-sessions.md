# S-2651 · The Context Forgetting Stack — When Your Agent Loses Everything Between Sessions

Your agent handled the support ticket flawlessly this morning. Then it crashed. Then it restarted. The customer called back four hours later and the agent greeted them like a stranger. Nobody noticed until the complaint came in.

This is the context forgetting problem: agents are fundamentally stateless between sessions. Context windows are not memory — they're a bigger Post-it note that still gets thrown away when the process ends.

## Forces

- **Context windows are ephemeral.** A context window survives a crash about as well as RAM does. Every process restart, redeployment, timeout, or server restart wipes the agent's entire working state. Context windows are a bigger notepad, not a persistent store.
- **Context drift kills before limits do.** ~65% of enterprise AI failures in 2025 were attributed to context drift or memory loss — not raw context exhaustion. The agent doesn't crash; it just quietly starts making decisions with incomplete information and no one notices until something breaks.
- **Memory quality compounds across sessions.** A support agent that doesn't remember your account tier, your past tickets, or your stated preference for email callbacks is not a persistent agent — it's a very articulate stranger. User satisfaction with agents drops sharply after the third time they have to re-explain themselves.
- **Three architectures, three incompatible bets.** The field has split into vector-first extraction (Mem0), graph-native temporal reasoning (Zep/Graphiti), and OS-tiered context management (Letta). Each solves a different memory problem; none solves all of them. Choosing wrong means paying the cost without the benefit.
- **Memory is attack surface.** Once an agent has memory, that memory can be manipulated. MemGhost-class attacks plant persistent, invisible instructions in the agent's memory that survive normal inspection — the agent "remembers" something that was never actually true.

## The move

Build memory as a first-class architectural layer, not as a prompt engineering trick. The concrete decisions:

1. **Segment memory by type.** Separate working memory (current session scratch), episodic memory (past interaction events), semantic memory (facts and knowledge), and procedural memory (how to do things). Mixing them is the root cause of retrieval noise.
2. **Choose the right persistence backend for the failure mode.** Vector-first (Mem0) works for personalization and chat history compression — fast retrieval, low latency, simple integration. Graph-native (Zep/Graphiti) wins when facts change over time and you need to know *when* something was true and track how beliefs evolved. OS-tiered (Letta) is for long-horizon agents that need the model itself to manage what lives in core, recall, and archival memory.
3. **Make memory writes async by default.** Blocking writes on the response pipeline adds latency the user feels. Async memory writes prevent UX degradation, but require a write-reconciliation strategy to avoid serving stale reads.
4. **Rank and rerank retrieval results.** Raw vector similarity returns the right candidates in the wrong order. A reranking pass (cross-encoder or late-interaction model) consistently improves effective recall without changing the underlying index.
5. **Add validity windows to temporal facts.** A graph-based memory that tracks when facts were true and when they changed is the only way to handle "the user changed their email last month but the agent still uses the old one." Plain vector retrieval has no concept of fact staleness.
6. **Close the loop on memory verification.** After any significant interaction, write a structured summary to persistent storage. Before any new session, load the three most relevant prior sessions as seed context. Treat memory ops like database writes — with versioning, rollback, and checksum validation.
7. **Audit memory for manipulation.** Memory writes from untrusted sources (user messages, external APIs) should be validated before insertion. Flag anomalous patterns: sudden preference changes, injected instructions, or facts that contradict established history.

## Evidence

- **Benchmark data:** Mem0's 2026 state report (based on LoCoMo and LongMemEval, 1,540 + 500 question sets) shows memory systems reaching 92.5 / 94.4 on recall benchmarks at ~6,900 tokens/query. Gains of +29.6 points on temporal reasoning and +23.1 on multi-hop reasoning over 18 months. Hardest open problems identified: cross-session identity resolution, temporal abstraction at scale, memory staleness detection. — [Mem0 AI Agent Memory 2026 Report](https://mem0.ai/blog/state-of-ai-agent-memory-2026)
- **Failure rate data:** Zylos Research found ~65% of enterprise AI failures in 2025 were attributed to context drift or memory loss — not model quality. Anchored iterative summarization (Factory's approach) outperformed naive compression on context drift reduction in their evaluation. ACON (failure-driven guideline optimization) emerged as a separate pattern for compressing "how to handle X" rules. — [Zylos Research: AI Agent Context Compression, Feb 2026](https://zylos.ai/research/2026-02-28-ai-agent-context-compression-strategies)
- **Architecture comparison:** Three production patterns now standard: Mem0 (vector-first, AWS Agent SDK integration, 186M API calls Q3 2025 per TechCrunch), Zep/Graphiti (temporal knowledge graph with validity windows, tracks fact evolution), Letta (OS-tiered memory management — core/recall/archival — model manages its own memory hierarchy). Mem0 raised $24M in Oct 2025. — [AgenticWire: Mem0 vs Zep vs Letta Comparison, Jun 2026](https://www.agenticwire.news/article/mem0-zep-letta-agent-memory); [AI Workflow Lab: Mem0 vs Letta vs Zep, May 2026](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026)
- **Security signal:** MemGhost-class attacks demonstrated that agent memory can be persistently manipulated through normal conversation — planted instructions survive session boundaries and normal inspection. Oracle developers blog notes: "Memory is attack surface, not just state." — [Oracle Developers Blog: Agent Memory, Feb 2026](https://blogs.oracle.com/developers/agent-memory-why-your-ai-has-amnesia-and-how-to-fix-it)

## Gotchas

- **Async writes + sync reads = stale reads.** If a write hasn't committed before the next read, the agent acts on outdated context. Add a write timestamp and TTL to every memory entry; invalidate reads that cross a freshness threshold.
- **Vector retrieval gives you the right facts in the wrong order.** Relying on raw cosine similarity for memory retrieval without reranking is the most common production footgun in memory-heavy agents. The top-k results are often top-5-relevant and top-1-wrong.
- **Cross-session identity is unsolved.** Knowing that the person who chatted on Tuesday is the same person who called on Friday — across different channels, devices, or API tokens — requires identity stitching that no current memory framework handles reliably out of the box.
- **Memory overhead compounds token cost.** Every retrieved memory entry adds to context. Unconstrained memory retrieval can double effective token use per call, turning a cheap agent into an expensive one.
- **Schema evolution breaks retrieval silently.** If your memory schema changes (field names, entity types), old entries stop being retrieved correctly. There is no standard migration path — you find out when the agent starts acting confused and no one knows why.
