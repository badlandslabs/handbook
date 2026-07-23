# S-1539 · The Memory Tier Stack — When Your Agent Remembers Everything and Knows What to Forget

You ship an agent. It works beautifully on day one — handles your request, calls the right tools, produces a clean result. On day twelve, it asks you to re-explain your project context like it's never heard of you. On day twenty, it makes the same mistake it made on day three. The agent isn't broken. It's stateless by default, and you never gave it a memory layer.

## Forces

- **The forgetting cliff.** LLMs reset on every API call. A 200K-token context window doesn't solve this — it just delays it. Real agents run for weeks; their users expect continuity across months.
- **Naive approaches explode.** Storing every message and stuffing it back into context works for a demo. It fails in production: context overflows, token costs spiral, retrieval gets dominated by recent noise.
- **What to keep vs. what to discard is non-obvious.** Not all history is equally useful. A one-off comment shouldn't harden into permanent identity. An error shouldn't recur indefinitely. The agent's own assessment of what matters should drive what persists.
- **Framework defaults set you up to fail.** LangChain's `ConversationBufferMemory` stores history in RAM — server restarts wipe it. The framework was designed for demos, not durable systems.

## The Move

Build a layered memory architecture. The insight from production systems (Letta/MemGPT, Mem0, Zep, Oracle Agent Memory, arxiv:2605.26252) is that memory isn't one thing — it's three to four distinct layers, each with different retrieval semantics and update rules.

### The four-layer stack

1. **Working memory** — The in-context window. Zero latency. Fully under your control. Holds the current conversation thread and active reasoning scratchpad. Does not persist across sessions. This is the cheapest layer and the one most developers over-rely on.

2. **Core memory** (aka pinned memory) — A small, always-injected layer that the agent can read *and write*. In Letta/MemGPT this is the `core_memory` block — a character-limited, agent-editable document that the LLM sees on every turn. Think of it as the agent's "identity card": who the user is, what their preferences are, what the current project is about. Size is intentionally bounded (8–32 KB typical) so it never causes context overflow.

3. **Episodic memory** — The log of what happened. Past conversations, completed tasks, prior decisions, tool outcomes. Stored as structured records with temporal edges, not raw message dumps. This is what lets an agent pick up a workflow where it left off, or not repeat a mistake it made three weeks ago. The critical design decision: episodic memory is not just "vector store of past messages." It's a fact-extracted, temporally-ordered record.

4. **Procedural memory** — How the agent knows how to do things. Learned skills, established workflows, approved patterns. In practice, this often lives as structured tool definitions, system prompt sections, or a dedicated "skills registry" that the agent can query. Mem0 calls this the "persona" layer. Oracle Agent Memory calls it "procedural memory derived from previous outcomes."

### Retrieval is temporal, not just semantic

The dominant failure of naive vector-based memory: similarity search returns semantically related but temporally stale results. "The user asked about billing last month" gets ranked alongside "the user asked about billing yesterday" because the embedding similarity is the same. Production systems (Zep, Oracle Agent Memory) fix this by storing temporal metadata on every fact and biasing retrieval toward recency — a weighted score of `f(semantic_similarity, recency, importance)`.

### Give the agent write access to its own memory

This is the MemGPT design principle and the one that separates toy implementations from production systems. The agent should be able to emit memory-write operations as tool calls — updating core memory blocks, flagging an episodic fact, recording an outcome. Don't make memory a passive store that only the developer writes to.

### Plan for eviction from the start

Memory grows unbounded unless you enforce eviction. The approaches that work in practice: recency-weighted retention (Zep), importance-ranked consolidation (Letta's archival memory), and fact-level TTLs (Mem0's automatic expiration). The approach that doesn't work: "we'll never hit the limit." You will.

## Evidence

- **Research paper:** Mem0 (arxiv:2504.19413) — extract→consolidate→retrieve pipeline for atomic facts across sessions. Reports 26% relative improvement over OpenAI baselines on LLM-as-Judge, 91% lower p95 latency vs. full-context. Validates that fact-extraction beats raw message storage. — https://arxiv.org/abs/2504.19413
- **Production benchmark:** Zep / Graphiti Temporal Knowledge Graph (arxiv:2501.13956) — three-tier episodic memory (episodes → semantic entities → community summaries) with temporal edges. Achieves 94.8% DMR accuracy vs. MemGPT's 93.4%, ~90% latency reduction (31.3s → 3.2s), 1.6k avg context tokens vs. 115k baseline. Cross-validated by AgentMarketCap benchmarking of Letta, Mem0, Zep in production 2026 setups. — https://arxiv.org/abs/2501.13956
- **Research paper:** "Is Agent Memory a Database?" (arxiv:2605.26252) — identifies four CRUD failures in naive memory systems and introduces GEM abstraction with four state-level operators and six correctness conditions. Argues memory correctness lives in the state trajectory, not individual records — critical distinction for systems that need to audit what the agent believed when. — https://arxiv.org/abs/2605.26252
- **Framework documentation:** Letta/MemGPT core memory architecture — core_memory blocks (persona + user + custom), archival memory tier, self-editing memory system. Agent can update its own personality and user knowledge over time. — https://github.com/letta-ai/ezra/blob/main/reference/2026-02/letta_memory_systems.md
- **Hacker News practitioner report:** "The agent is impressive in the moment, then it forgets. Or it remembers the wrong thing and hardens it into a permanent belief... That is not a model quality issue. It is a state management issue." — articulates the six memory management questions (what gets stored, compressed, promoted, decayed, deleted, what should never be durable). — https://news.ycombinator.com/item?id=46471524
- **Developer community:** DEV.to analysis of LangChain memory failures — session death (RAM-only storage), context overflow (every message re-added), framework lock-in, vector store complexity. — https://dev.to/joe_83920aecb4db91e002112/langchain-memory-is-broken-heres-what-to-use-instead-2k26
- **Open-source tooling:** agentmemory (rohitg00, 2025) — persistent memory for Claude Code, Cursor, Cline, Gemini CLI and other coding agents. Every major coding agent ships with sticky-note memory (MEMORY.md, notepads, memory bank); agentmemory is the searchable database behind those sticky notes. — https://github.com/rohitg00/agentmemory

## Gotchas

- **Don't store raw messages as memory.** Raw conversation logs bloat context and dilute signal. Extract facts, rank them by importance, store structured records with temporal metadata.
- **Context window overflow from memory is silent.** LangChain's `ConversationBufferMemory` fails gradually — tokens increase until the API errors out. Build hard limits into your memory injection logic and test the 50th and 100th interaction.
- **Semantic similarity is not the same as relevance.** Vector retrieval is necessary but not sufficient. Temporal decay, importance scoring, and source attribution are required for retrieval to be useful, not just voluminous.
- **Not everything should be durable.** Ephemeral signals (a user's off-hand comment, a failed tool call that was corrected) should not become permanent beliefs. Your memory architecture needs an explicit "never persist" category and an eviction policy.
- **Agent-editable memory needs guardrails.** If the agent can write to its own core memory, it can also write incorrect information, overwrite important context, or optimize for the wrong goal. Log all memory writes and treat them as first-class audit events.
