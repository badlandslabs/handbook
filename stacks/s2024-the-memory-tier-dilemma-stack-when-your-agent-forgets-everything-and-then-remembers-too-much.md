# S-2024 · The Memory Tier Dilemma Stack — When Your Agent Forgets Everything and Then Remembers Too Much

You shipped a support agent. It worked perfectly in week one. By week three, it had accumulated so much context from prior sessions that it started hallucinating facts — confidently recalling conversations that never happened, applying preferences from one customer to another, mixing up project states. You added a memory layer to solve the forgetting problem. Now you have a remembering problem. This is the memory tier dilemma: agents default to stateless, so you bolt on persistence, and the retrieval noise drowns the signal.

## Forces

- **Stateless defaults are safe but useless.** Every LLM call starts from scratch without an explicit memory layer. The cleanest architecture is also the most forgetful.
- **Retrieval quality matters more than storage volume.** A well-tuned vector query against 50 relevant memories beats a bloated store with noisy retrieval — confirmed across Letta benchmarks, Mem0's fact-extraction approach, and agentmemory's tiered fetching.
- **Three retrieval failure modes exist, not one.** Agents can: (1) forget entirely — stateless default; (2) retrieve too little — sparse memory, stale facts; (3) retrieve too much or the wrong thing — memory poisoning, cross-user contamination. Most teams only design for case 1.
- **Hallucinated memories are a real failure class.** The HaluMem paper (arXiv:2511.03506, Chen et al., 2025) formally identifies hallucinated memory as a distinct failure mode where agents confidently assert facts from corrupted or fabricated memory entries. The standard retrieval pipeline doesn't catch this — you need validity windows or provenance tracking.
- **The three-tier taxonomy is the production consensus.** Episodic (what happened), semantic (what it means), procedural (how to do it) — mirrors cognitive science but is now embedded in Mem0, Letta, Zep/Graphiti, and MemGPT's OS-style memory management.

## The move

Build a tiered memory architecture with explicit retrieval logic — not a flat vector store appended to every call.

**1. Episodic tier: raw events, timestamped, append-only.**
Store conversation turns, tool-call traces, and interaction outcomes as structured JSONL records. Each entry gets a timestamp, session ID, and outcome tag (success/failure/partial). This is the source of truth — never edited, only queried or consolidated. agentmemory uses this with per-project isolation. Mem0 extracts facts automatically from this tier.

**2. Semantic tier: extracted facts, deduplicated, scored by reuse.**
A consolidation process (LLM-driven summarization or rule-based promotion) extracts high-value facts from episodic records and promotes them to semantic memory. Each fact carries provenance (which episodic record it came from) and a validity window. Zep's Graphiti engine does this with temporal awareness — it tracks when facts were true and when they stopped being true, preventing stale preference bleed. This tier is where cross-session context lives.

**3. Procedural tier: agent-defined skills and behaviors.**
The agent writes or updates `SKILL.md` files or equivalent declarative instructions. This is distinct from semantic memory — it encodes *how*, not *what*. The Agent Skills standard (agentskills.io) formalizes this as YAML frontmatter + Markdown body. Hermes Agent uses a hard 2,200-char cap on MEMORY.md and 1,375-char cap on USER.md — deliberately small to force curation.

**4. Retrieval: weighted multi-signal query, not raw similarity.**
Top retrieval systems (agentmemory, Zep, MEMTIER from Sidik & Rokach 2026) weight five signals: relevance, recency, outcome quality, access frequency, and structural compatibility. Hermes-style hard caps on memory size force the agent to self-curate. BetterClaw's fix guide recommends sliding-window summarization for episodic history — compress older messages rather than appending indefinitely.

**5. Validity windows and provenance for hallucination resistance.**
Zep's Graphiti tracks when facts are active. MemGPT uses OS-style memory hierarchy (main context vs. archival) with explicit `core_memory_append` calls the LLM invokes. Without validity tracking, a user's changed preference looks identical to a confirmed one in a flat vector store.

## Evidence

- **Research synthesis:** The three-tier episodic/semantic/procedural taxonomy is independently confirmed by Zylos Research (Apr 2026), Appscale Blog (May 2026), Redis agent-memory documentation (2025), and the academic MemGPT/Generative Agents lineage (Packer et al.; Park et al.) — 45+ sources consulted in spikelab's comprehensive review (Dec 2025–Feb 2026). — [https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)

- **Production framework comparison:** Letta's own benchmarks show filesystem/markdown scored 74% on memory tasks — beating specialized vector-store libraries. Mem0 ($19–249/mo managed) excels at extracted-fact personalization via LLM-based extraction policies. Zep ($25/mo managed, self-hosted available) leads on temporal reasoning via Graphiti's validity-window tracking. Letta ships its own agent runtime — the only one of the three that does. — [https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026](https://aiworkflowlab.dev/article/agent-memory-mem0-vs-letta-vs-zep-2026), [https://aicraftguide.com/article/mem0-vs-letta-vs-zep-ai-agent-memory-production-2026](https://aicraftguide.com/article/mem0-vs-letta-vs-zep-ai-agent-memory-production-2026)

- **Hallucinated memory failure:** HaluMem (arXiv:2511.03506, Chen et al., Nov 2025) formally identifies and evaluates memory hallucination as a distinct failure class in agent memory systems. Redis's own documentation acknowledges that "Configurable LLM-based extraction policies" introduce hallucination risk — the extraction step itself can corrupt facts before they enter storage. — [https://arxiv.org/abs/2511.03506](https://arxiv.org/abs/2511.03506), [https://redis.io/agent-memory/](https://redis.io/agent-memory/)

## Gotchas

- **Flat vector stores are not memory architectures.** Storing conversation embeddings and returning top-k by cosine similarity is the 2023 approach. It produces memory bloat, no deduplication, no validity tracking, and no way to distinguish "user prefers dark mode" (persistent) from "user asked about pricing" (one-off). The three-tier model exists because flat stores fail at scale.
- **LLM-based extraction can hallucinate before storage.** Redis, Mem0, and Letta all use LLMs to extract structured facts from raw conversations. If the extraction step produces a fabricated fact, it propagates cleanly into semantic memory — where it is now treated as a verified persistent truth. HaluMem proves this happens in practice. You need provenance and validity windows downstream of extraction, not just during retrieval.
- **Cross-user contamination is silent.** agentmemory enforces per-project isolation (workspaces, team collaboration), but many open-source setups share a vector store across users. A semantic-memory fact from user A can surface in a retrieval query for user B if deduplication isn't user-scoped. This is the "remembers too much" failure mode that produces wrong answers that look confident.
- **Hard size caps force curation; unbounded memory enables drift.** Hermes Agent's 2,200-char MEMORY.md cap is a deliberate engineering choice — it forces the agent to decide what matters. Unbounded semantic memory grows until retrieval noise exceeds signal. Budget your context window for memory injection and treat the budget as a production constraint, not a feature.
