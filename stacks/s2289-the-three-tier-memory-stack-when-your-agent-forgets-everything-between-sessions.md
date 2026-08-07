# S-2289 · The Three-Tier Memory Stack — When Your Agent Forgets Everything Between Sessions

Your agent handles a customer support ticket on Monday. The customer calls back on Thursday with a follow-up. The agent has no idea who they are, what was discussed, or what was promised. The customer starts over. This is the memory problem — and context-window stuffing is not the answer.

## Forces

- **Context stuffing hits a wall fast.** A 200k-token window stuffed with irrelevant history produces worse outputs than a 10k-token window with precisely the right information. As agent sessions compound, stuffing chat history becomes both expensive and counterproductive.
- **No single store does everything.** Vector databases excel at fuzzy semantic recall but are blind to temporal relationships and fact decay. Knowledge graphs handle entity relationships but demand ontology maintenance. Key-value stores are fast but offer no search. The production consensus in 2025–2026 is a hybrid approach, not a single tool.
- **The LLM should manage memory, not just read it.** Early systems treated memory as a static store. The shift in 2025–2026 is toward agentic memory — the LLM itself decides what to store, when to retrieve, and when to forget. A-Mem (Rutgers, arXiv 2502.12110, June 2025) formalized this as a write–manage–read loop tightly coupled with the agent's policy.
- **Memory has a right-to-be-forgotten problem.** In regulated industries, agents must be able to selectively erase facts — not just append. This is absent from most vector store implementations and is a production blocker for healthcare, finance, and legal deployments.

## The Move

Adopt a three-tier memory architecture that separates stores by access pattern and lifetime. Let the LLM manage what goes where, not just what gets read.

### Tier 1 — In-Context Working Memory (Hot)
The current session's raw message buffer, tool calls, and active state. Lives in RAM, injected directly into the prompt. Ephemeral — cleared on session end. Size-bounded by a sliding window (typically last 20–50 messages or ~10k tokens). This is not a database problem; it's a prompt engineering problem.

### Tier 2 — Semantic Memory (Warm)
Structured facts, domain knowledge, and learned preferences. Stored in a vector database (Pinecone, Chroma, pgvector) or hybrid vector-graph store. Retrieved on demand at the start of each session or when the agent detects a relevant query. Mem0 is the most widely deployed implementation — serving as the exclusive memory provider for AWS's Agent SDK as of 2026, with 186M API calls processed in Q3 2025.

### Tier 3 — Episodic / Cross-Session Memory (Cold)
Conversation histories, past task outcomes, and temporal facts. Keyed by user_id or session_id. LinkedIn's Cognitive Memory Agent uses a hybrid: vector store for semantic retrieval + graph store for entity relationships across sessions. Zep takes a graph-native approach with bi-temporal modeling — tracking both when events occurred and when they were ingested, so "student mastered product rule (March 2026)" supersedes the earlier "struggles with product rule (January 2026)."

### The Management Loop (A-Mem Pattern)
At each step t:
```
aₜ = πθ(xₜ, ℛ(Mₜ, xₜ), gₜ)        ← policy reads from memory
Mₜ₊₁ = 𝒰(Mₜ, xₜ, aₜ, oₜ, rₜ)     ← memory writes/updates itself
```
The LLM itself participates in memory writes (deciding what's worth storing) and retrieval decisions (deciding what to pull). This is the architectural shift from memory-as-store to memory-as-agentic-loop.

### Store Selection by Use Case
| Use Case | Recommended Stack | Why |
|----------|-----------------|-----|
| Customer support chatbot | In-context buffer (20 msgs) + Mem0 episodic keyed by user_id | Fast retrieval of past tickets and resolutions |
| Coding assistant | Semantic memory over codebase docs + episodic for library preferences | Graph storage unnecessary; search quality matters |
| Research agent | All three tiers | Needs session scratchpad, curated knowledge base, and episodic for dead ends |
| Personal productivity | Zep or Mem0 with entity extraction | Temporal fact tracking across sessions |

## Evidence

- **arXiv survey:** "Memory for Autonomous LLM Agents" (Du, March 2026, arXiv:2603.07670) formalizes the write–manage–read loop as the core memory architecture, examining five mechanism families and four evaluation benchmarks (LoCoMo, LongMemEval, BEAM, MemBench) covering 2022–early 2026. — [arxiv.org/html/2603.07670](https://arxiv.org/html/2603.07670)
- **HN Ask HN (2025):** Practitioner thread on multi-agent orchestration reveals the majority of production teams roll their own orchestration rather than use frameworks — one commenter: "there's absolute 0 framework out there that's good enough for serious work." Memory layer choice varies widely: custom MongoDB (shared state), SQLite (checkpoint stores), or purpose-built tools like Mem0. — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **GitHub / production data:** Mem0 reported 186M API calls processed in Q3 2025 and serves as the exclusive memory provider for AWS Agent SDK (AgenticWire, June 2026). Zep's Graphiti engine has 27,244 GitHub stars as an open-source temporal knowledge graph (self-reported). Hmem (Bumblebiber, HN Show HN) solves the tool/machine lock-in problem for coding agents — memory is stored in a local SQLite file and exposed via MCP, so switching from Claude Code to Cursor preserves session memory. — [github.com/Bumblebiber/hmem](https://github.com/Bumblebiber/hmem)
- **GitHub:** A-Mem (Rutgers + AIOS Foundation, arXiv 2502.12110, June 2025) — agentic memory system where the LLM dynamically organizes memories instead of relying on pre-defined storage structures. Shows superior reasoning on multi-hop and temporal reasoning tasks with lower computational overhead than static retrieval systems. — [arxiv.org/abs/2502.12110](https://arxiv.org/abs/2502.12110)
- **ACL 2025:** MemBench (Tan et al., Findings of ACL 2025) introduces multi-dimensional memory evaluation — effectiveness, efficiency, and capacity — across factual and reflective memory levels, with participation and observation scenarios. Addresses the gap that prior benchmarks only measured recall, not the ability to use memory for downstream reasoning. — [aclanthology.org/2025.findings-acl.989](https://aclanthology.org/2025.findings-acl.989)

## Gotchas

- **Vendor benchmarks are self-reported.** Mem0 claims 94.4% on LongMemEval; ByteRover (third-party) scores 92.2% on LoCoMo using the same evaluation methodology. Vendor scores should be treated as marketing until independently replicated on your workload. Run MemBench or LoCoMo against your actual use case.
- **Vector search misses relationships.** If your agent needs "who worked on this project before me" or "what did we promise this customer last quarter," pure vector retrieval will fail. Graph-native stores (Zep/Graphiti) or hybrid approaches (Mem0 with graph extension, Cognee) handle this. Start with vector; graduate to graph when queries expose the gap.
- **Context dilution in long sessions.** Long conversations get compressed and context silently disappears — agents forget decisions made 2 hours ago in the same session. Hmem's diagnosis: `CLAUDE.md` and rules files don't solve this; you need structured episodic capture with explicit retrieval, not implicit stuffing.
- **The forgetting problem is unsolved in most stacks.** Fact decay and contradiction are handled explicitly only by Zep (temporal knowledge graph with validity windows) and Letta (OS-inspired memory tiering with archival). Most vector-based systems store everything indefinitely, leading to stale facts polluting retrieval results.
- **Framework immaturity.** As one HN practitioner put it: "there's absolute 0 framework out there that's good enough for serious work." LangGraph, CrewAI, and AGNO provide primitives, but production memory layering — especially the write/manage/read loop — is still custom work for most teams.
