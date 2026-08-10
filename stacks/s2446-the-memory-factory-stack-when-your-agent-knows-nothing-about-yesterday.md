# S-2446 · The Memory Factory Stack — When Your Agent Knows Nothing About Yesterday

A coding agent fixes a flaky test for you on Monday. On Thursday you ask it to fix a similar one, and it starts from zero — re-deriving the same diagnosis, asking the same questions, making the same wrong first guess. Nothing is broken. The model did exactly what it was built to do: it answered from the tokens in front of it, and on Thursday those tokens did not include Monday. The context window is not memory. It is a workbench that gets wiped clean between sessions.

This is the fundamental disconnect: users treat agents as collaborative partners who accumulate knowledge, while agents are stateless query engines that reset on every session.

## Forces

- **Context window is temporary, not persistent.** A million-token window is a larger desk, not a longer memory. Once the session ends, everything inside it is gone. The engineering instinct to increase context size does not solve the problem — it defers it.
- **Store-and-retrieve is not learning.** Dumping conversation history into a vector database and pulling top-k at query time gives you retrieval, not memory. Duplicates pile up ("User uses Salesforce CRM" appearing 40 times with slight phrasings), and ingested errors become sticky — recalled on every future query.
- **Three memory types fight for the same slot.** Episodic memory (what happened), semantic memory (what it means), and procedural memory (how to do it) require different storage, retrieval, and update mechanisms. Most systems conflate them and pay for it with retrieval noise and stale facts.
- **Consolidation costs money and latency.** Running periodic offline synthesis is expensive. The incentive is to skip it and just keep adding to the store. The debt compounds invisibly until retrieval becomes useless.

## The move

**The memory factory pattern** — a layered, consolidated memory architecture with explicit write policies and forgetting mechanisms. The core insight: memory is not storage, it is a process.

### Layer 1: Short-term / Working Memory
- The context window is a scratchpad, not a database. Load only what is needed for the current step.
- Claude Code's approach: fixed system prompt + conversation history + tool results, managed with truncation policies. MCP tool definitions are deferred and loaded on demand — only the tool name consumes context until the tool is invoked.
- **Rule:** If it won't be needed in the next 3 tool calls, it doesn't belong in context.

### Layer 2: Episodic Memory (What Happened)
- Store raw interaction events: completed tasks, user corrections, tool outputs, session outcomes.
- Schema: `{event_type, timestamp, summary, entities, outcome}` — not raw transcripts.
- Implementation: Vector store with time-filtered retrieval, or temporal knowledge graph (Zep, Graphiti).
- Graphiti's episodic-to-semantic pipeline: events are nodes, relationships between events form edges, and periodic processing extracts facts from event chains.

### Layer 3: Semantic Memory (What It Means)
- Synthesized facts distilled from episodic memory. "User prefers dark mode" is semantic; "User changed setting to dark mode on Tuesday" is episodic.
- This layer is the output of consolidation. It is queryable, updatable, and consistent — not a pile of raw embeddings.
- **Critical:** Semantic memory must be editable, not just append-only. Corrections overwrite stale facts.

### Layer 4: Procedural Memory (How to Do It)
- Stored instructions, not stored facts. CLAUDE.md files, slash commands, skill definitions.
- Claude Code's `memory_20250818` tool lets subagents write directly to project memory.
- This is the layer that compounds fastest and costs the least to maintain — one write, infinite reuse.

### The Consolidation Loop
```
Session ends → Extract events → Write to episodic store
                ↓
Periodic (offline): identify patterns across episodes
                ↓
Promote significant patterns → Semantic memory
                ↓
Decay low-relevance → Soft delete or archive
```
Mem0's production evaluation shows the stakes: on LoCoMo (1,540 questions, 4 categories), systems with consolidation scored 29.6 points higher on temporal reasoning and 23.1 points higher on multi-hop recall than raw store-and-retrieve baselines.

### Forgetting Is a Feature
- Without staleness management, every session adds to the store. Retrieval degrades as noise accumulates.
- Policies: recency-weighted decay, relevance threshold deletion, user-initiated correction propagation.
- The cognitive science analogy is real: human memory consolidates during sleep, strengthening important episodes and letting others fade. Agents need an equivalent.

## Evidence

- **Benchmark Report:** Mem0's State of AI Agent Memory 2026 reports 92.5 on LoCoMo and 94.4 on LongMemEval using consolidated episodic+semantic architecture. Hardest open problems: cross-session identity, temporal abstraction at scale, and memory staleness. — [mem0.ai/blog/state-of-ai-agent-memory-2026](https://mem0.ai/blog/state-of-ai-agent-memory-2026)

- **HN Discussion:** The Ask HN thread "Examples of agentic LLM systems in production?" (112 points, 73 comments, Dec 2024) surfaced production deployments and confirmed the "reset on every session" problem as the top complaint, with practitioners repeatedly reaching for layered memory as the solution. — [news.ycombinator.com/item?id=42431361](https://news.ycombinator.com/item?id=42431361)

- **Framework Comparison:** The agent-memory GitHub repo (NirDiamant/Agent_Memory_Techniques) catalogs 30 production memory techniques across 6 families, documenting Letta's self-editing inner/outer monologue architecture, Zep's temporal knowledge graphs, and Graphiti's episodic-to-semantic extraction as the dominant production patterns. — [github.com/NirDiamant/agent_memory_techniques](https://github.com/NirDiamant/agent_memory_techniques)

- **Claude Code Architecture:** Anthropic's Claude Code docs reveal a four-layer memory system: CLAUDE.md (human-authored, session-start), MEMORY.md (auto-learned, session-start, first 200 lines), ephemeral context (current session), and MCP-based external memory. The design principle is layered by access frequency, not by storage type. — [code.claude.com/docs/en/memory](https://code.claude.com/docs/en/memory)

- **Anthropic Engineering Guidance:** "Building Effective AI Agents" (June 2025, 543 HN points) recommends starting with LLM APIs directly and composable patterns before reaching for frameworks, which adds abstraction layers that obscure what's actually happening in memory and retrieval. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- **Append-only is a trap.** Every session that writes raw transcripts to a vector store without consolidation makes future retrieval worse. The fix is to never do raw transcript embedding for long-term memory — extract structured events instead.
- **Context window management is a first-class concern.** Deferred tool loading (only loading tool definitions on use), truncation policies, and session-start memory filtering are not optimizations — they are load-bearing infrastructure. Get them wrong and the memory factory produces nothing useful.
- **Cross-session identity is unsolved.** Most production systems lack a durable user/agent identity layer. Without it, semantic memory accumulates facts about "the user" with no mechanism to verify, update, or invalidate them when the user context changes.
