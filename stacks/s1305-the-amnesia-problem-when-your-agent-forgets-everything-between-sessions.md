# S-1305 · The Amnesia Problem — When Your Agent Forgets Everything Between Sessions

Your agent works perfectly in the demo. The tenth conversation, it asks the user to repeat information already provided last week. The hundredth, it has no idea who this person is or what they care about. This is not a prompt problem. This is the absence of a memory system — and it is the most common reason production agents fail to retain value.

## Forces

- LLMs are stateless by design — every API call starts from a blank slate — but agents that reset to zero between sessions waste tokens re-deriving context and break user trust
- A large context window (1M tokens) is not a memory system; it is a larger scratchpad — it does not retrieve relevant context, it just holds more of it
- Agents that store everything face memory bloat, token cost inflation, and LLM accuracy degradation as context grows; agents that store nothing face amnesia
- The four memory types (working, episodic, semantic, procedural) have fundamentally different storage and retrieval requirements — collapsing them into one layer is the most common architectural mistake
- Memory that never decays accumulates stale facts that outrank current reality, causing agents to confidently assert outdated preferences
- Cross-agent memory contamination and the absence of per-user quotas create production failures that are invisible until a user notices

## The Move

Build a tiered memory architecture that matches each memory type to its appropriate storage and retrieval mechanism. The key moves:

- **Separate episodic from semantic.** Episodic memory (conversation logs, events) should be retrievable by time and topic. Semantic memory (facts, preferences, learned knowledge) should be retrievable by meaning. Mixing them into one vector store produces retrieval that returns the wrong type at the wrong time.

- **Implement time-decay with importance weighting.** Every stored fact carries a decay score that degrades over time unless reinforced. Critical facts (identity, core preferences) decay with a half-life of 60–90 days or longer; ephemeral context (one-off clarifications) decays in hours. The formula: `score = importance × decay_factor(time_elapsed)`. A trivial "user said hello" should not survive at full strength alongside "user confirmed the production deployment window is Friday 2am UTC." Use exponential decay: `λ = ln(2) / t½` where t½ is the half-life in days.

- **Use multi-signal retrieval, not semantic-only.** Single vector similarity search misses keyword-diverse queries. Real production retrieval layers combine semantic similarity, BM25 keyword matching, and entity-level linking in parallel, then fuse scores. Mem0's new algorithm (April 2026) does this in a single-pass ADD operation with one LLM call — down from iterative update/delete loops that caused memory fragmentation.

- **Enforce per-user memory quotas.** Unbounded memory storage per user is a cost and compliance liability. Set hard limits (e.g., 50K tokens per user for semantic memory) with automatic consolidation policies. Quota exhaustion should trigger priority eviction, not silent failure.

- **Give agents tools to write memory, not just read it.** Letta's OS-inspired approach gives agents `edit_memory` and `recall` as first-class tools — the agent decides what to persist and what to discard, mirroring how humans consciously decide what to remember. Passive accumulation is a log; intentional memory is a system.

- **Add a memory poisoning guard.** Hallucinated facts stored in long-term memory compound over time. Before writing a semantic memory, verify the fact against a tool result or explicit user confirmation. Do not store agent-generated inferences as ground truth without validation.

## Evidence

- **GitHub README (mem0ai/mem0, 61K stars):** Mem0's April 2026 algorithm update introduced single-pass ADD-only extraction, agent-generated facts as first-class memories, entity linking across memories, and multi-signal retrieval (semantic + BM25 + entity matching). Their LoCoMo benchmark went from 71.4 to 92.5, LongMemEval from 67.8 to 94.4, with 6.7–7.0K tokens per query at sub-second latency. — [github.com/mem0ai/mem0](https://github.com/mem0ai/mem0)

- **Engineering blog (Tian Pan, tianpan.co, April 2026):** Documents the three-tier taxonomy (episodic: "log of what happened"; semantic: "structured knowledge graph"; procedural: "how to do things") and the decay principle: "a memory system that only accumulates is not a memory system — it's a log." Makes the case that stuffing conversation history into the prompt is prohibitively expensive past ~10 sessions and degrades LLM accuracy measurably as context grows. — [tianpan.co/blog/long-term-memory-types-ai-agents](https://tianpan.co/blog/long-term-memory-types-ai-agents)

- **GitHub discussion (microsoft/autogen #7794, June 2026):** Production multi-agent system describes four failure modes from absent memory architecture: memory bloat (agents accumulate until token limits), cross-contamination (Agent A pollutes Agent B's reasoning), temporal confusion (can't distinguish recent from stale), and memory poisoning (malicious or hallucinated data persists). Proposes per-agent memory isolation with a shared blackboard for intentional cross-agent context. — [github.com/microsoft/autogen/discussions/7794](https://github.com/microsoft/autogen/discussions/7794)

- **Benchmark comparison (Vectorize, March 2026):** Mem0 vs Zep/Graphiti comparison shows architectural split: Mem0 uses vector DB + optional knowledge graph (dual-store) with Pro-tier graph features at $249/mo; Zep/Graphiti is graph-native with temporal validity windows on all edges. LongMemEval: Mem0 49.0%, Zep 63.8% (GPT-4o). Mem0 reports 186M API calls in Q3 2025, exclusive memory provider for AWS Agent SDK. — [vectorize.io/articles/mem0-vs-zep](https://vectorize.io/articles/mem0-vs-zep)

- **HN Show HN (Mnemory, ~74 days ago):** Open-source memory layer separates durable facts, preferences, episodic/context memory, TTLs, importance, user/agent scoping, and artifact-backed long-form memory. Built to plug into OpenWebUI, OpenClaw, Hermes, and other runtimes via MCP interface. Author notes: "durable facts and short-lived context need different treatment, but many systems collapse everything into one retrieval bucket." — [news.ycombinator.com/item?id=47995527](https://news.ycombinator.com/item?id=47995527)

## Gotchas

- **Vector similarity alone is insufficient.** Users phrase things differently than how facts were stored. A preference stored as "user prefers concise responses" won't match a retrieval for "short answers only." Hybrid retrieval (semantic + keyword + entity) is not optional — it is the baseline for production-quality recall.

- **Storing everything is not memory architecture.** Raw conversation logs in a vector DB compete with structured facts during retrieval. Episodic and semantic memories need separate retrieval pipelines and scoring functions, not a shared bucket.

- **Importance is not binary.** If you assign importance scores at creation, you must also revisit them on retrieval — frequently accessed memories should have their importance reinforced (a recency-weighted boost on access). Otherwise, an important fact that hasn't been queried in 30 days decays below a trivial but frequently-referenced fact that happened yesterday.

- **Context window is not memory.** The mistake of treating a larger context window as a memory solution leads to: higher per-query costs, degraded LLM accuracy as context grows, and zero retrieval — the agent can only re-read, not recall. Both the cost and the accuracy data show this approach breaks past ~10 sessions.

- **Memory layer deprecation risk.** Zep killed its open-source Community Edition in late 2025, locking thousands of developers into credit-based pricing. When choosing a memory infrastructure layer, verify self-hosting availability and data egress terms before building production workflows on managed-only platforms.
