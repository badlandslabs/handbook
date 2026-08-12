# S2513 · The Agent Memory Stack — When Your Agent Forgets It Already Forgot

When your agent accumulates memories across sessions but has no way to handle contradictions, corrections, or decay — so it starts acting on stale beliefs it doesn't know are wrong.

## Forces

- **Persistence vs. correctness** — once an agent writes something to memory, it trusts that memory forever, even if it was wrong when written or became wrong over time
- **Semantic search retrieves everything similar** — not everything relevant — so a "corrected" belief and its original error both surface as equally valid matches
- **The belief drift problem** — as memory grows, old corrections layer on top of old errors; the agent's worldview becomes a palimpsest no one can audit
- **Memory poisoning surface** — external data or adversarial prompts can write to agent memory, and the agent acts on those entries in future sessions with no new validation gate (OWASP ASI06, MINJA research: >95% injection success rate against production agents)
- **Memory is not chat history** — it requires intentional design around what to remember, when to surface it, and when to forget it

## The Move

Split memory into three tiers and add a curation layer between write and recall:

**Three-tier architecture:**
- **In-context (working memory)** — last N messages in RAM; refreshed every session, no persistence
- **Short-term (session memory)** — conversation summaries, key decisions, entities encountered; TTL-based decay
- **Long-term (cross-session)** — facts about the user/project, learned preferences, persistent beliefs; versioned, superseded entries are explicitly marked hidden

**Supersession chains over vector recall alone:**
- When an agent corrects a belief, the old entry stays in storage but is flagged `superseded: true` with a link to the new entry
- Default recall queries exclude superseded entries; the agent sees only current truth
- Full audit trail preserved for debugging (never delete, only hide)

**Draft isolation for untrusted writes:**
- New observations land in a `drafts/` namespace before promotion
- An LLM-based reviewer (or user) must approve before the thought enters shared memory
- Hallucinations, poisoning attempts, and transient errors stay contained in drafts
- This is the core of Fava Trails' approach: "working thoughts stay in drafts/; other agents only see promoted thoughts"

**Persist-then-rebuild over in-process state:**
- Write every event to storage immediately (not at session end)
- On every new execution, rebuild context from storage
- Agent process is stateless — no in-memory state that could corrupt on crash
- Cogency: "Events written to storage immediately, context rebuilt each execution. No state corruption, crash recovery."

## Evidence

- **HN Show HN (Fava Trails):** "If an agent hits a transient network error and writes 'this environment has no GPU' to its memory, and later realizes it actually does have a GPU and writes a correction... a standard vector search returns both. Your agent is now schizophrenic, holding contradictory beliefs." — [Show HN: Fava Trails](https://news.ycombinator.com/item?id=47197011) | [GitHub](https://github.com/MachineWisdomAI/fava-trails)
- **arXiv 2606.24775 (Jun 2026):** Systematic study of 12 agent memory systems across 5 workloads finds "no single architecture dominates all scenarios; effectiveness depends heavily on how well the memory structure aligns with the workload bottleneck." — [arXiv:2606.24775](https://arxiv.org/html/2606.24775v1)
- **Christian Schneider blog (Feb 2026):** Documents the OWASP ASI06 (Memory & Context Poisoning) risk — memory poisoning survives sessions unlike session-scoped prompt injection; MINJA research shows >95% injection success against production agents. — [Memory poisoning in AI agents](https://christian-schneider.net/blog/persistent-memory-poisoning-in-ai-agents)
- **Remery Blog (Aug 2025):** Three-tier memory architecture (working/short-term/long-term); key insight: "retrieval quality matters more than storage volume — 100 well-indexed memories outperform 10,000 poorly organised ones." — [Agent Memory Architecture](https://remery.ai/blog/agent-memory-architecture-persistent-context-systems)
- **Letta + Aurora PostgreSQL:** Production deployment using Aurora with pgvector for semantic search, six-way replication across three AZs, Aurora Serverless auto-scaling to 256 TB. — [AWS News Blog](https://aws-news.com/article/2025-11-26-how-letta-builds-production-ready-ai-agents-with-amazon-aurora-postgresql)

## Gotchas

- **Vector search alone creates belief drift** — semantic similarity ≠ relevance; embeddings retrieve both a correction and the error it corrected if they share vocabulary. You need structural metadata (supersession links, timestamps, trust scores) alongside embeddings.
- **Memory without eviction grows unbounded** — production systems need per-user quotas and TTL policies; set a budget (e.g., 500 memories per user) and a decay rule (unused facts expire after N days) before you ship.
- **Trust gates are a UX bottleneck** — requiring human review of every draft kills autonomy. Most teams implement an LLM-as-reviewer with human escalation for low-confidence or high-stakes entries.
- **Memory poisoning is silent** — unlike a crash or error message, a poisoned memory succeeds silently. You won't know until the agent acts on it days later. You need read-side scanning (audit what the agent would recall before it does) to catch this.
