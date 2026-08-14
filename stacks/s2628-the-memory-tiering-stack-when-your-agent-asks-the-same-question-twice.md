# [S-2628] · The Memory Tiering Stack

[When your agent starts every session cold — asking for context it should already have, repeating the same onboarding dance, and making the same mistake it made three sessions ago because it can't learn from experience.]

## Forces

- LLMs are stateless by default — every session starts with a blank context window, and the context window itself is a finite, expensive resource
- Naive vector RAG creates recall pollution: the more you store, the more irrelevant hits drown out the relevant ones, and contradicting facts from different sessions both get retrieved
- Memory as a database (append-only logs, chunked conversations, embedding everything) is the most common mistake teams make — it optimizes for storage volume, not decision quality
- But over-engineering a four-tier memory system for a simple task is equally wrong — the right architecture depends on what failure you're actually trying to fix
- The value of failures: "knowing the mistakes is critical information" — agents that only remember successes are brittle (Armin Ronacher, Flask author)

## The move

**Three-tier memory architecture, matched to access patterns, not to a framework's marketing claims.**

**Hot memory — checkpoint state for pause/resume.** Store mid-task state as serializable snapshots (usually JSON or a lightweight store) so an agent can be interrupted and restarted without re-deriving its work. This is not an audit log. Redis, a JSON file, or an in-process dict — choose based on your availability needs, not your vector DB vendor. Latency target: single-digit milliseconds.

**Cold memory — cross-session facts in a retrieval system.** This is where Mem0, Zep, Letta, and Engram compete. The real choice is between:
- *Extracted-fact storage* (Mem0): the LLM summarizes facts from conversation, stored as structured records with user_id/entity references. Good recall precision. Contradiction handling requires explicit memory updates.
- *Temporal knowledge graph* (Zep/Graphiti, Engram): facts are nodes with timestamps. When a user moves from Berlin to Munich, the graph versions the change instead of appending a contradiction. Supports multi-hop traversal. More complex to operate.
- *Agentic retrieval* (Infini Memory, arXiv:2606.10677): the agent uses tool calls to iteratively search memory, expand context, and assemble evidence — not just top-k semantic match. Achieves 64.7% on MemoryAgentBench vs ~42% for naive retrieval.

**Procedural memory — what to do, not what happened.** Lives in system prompts, tool definitions, and policies. Not a retrieval problem. Not stored in a vector DB. The agent's "skill" is a set of instructions that ship with it. When the HN community says "memory is a skill, not a database," this is what they mean — facts about preferences belong in the cold store; procedures for executing tasks belong in the agent definition.

**The retrieval loop.** Every request follows: **read → reason → act → observe → write**. Memory is consulted before the first LLM call and updated after the last. Writes are selective — not every message, not every tool call. Mem9 (PingCAP/TiDB) ships a prototype to a real customer before writing a roadmap, and finds that people want to *see, inspect, trust, and correct* what the agent remembers, not just rely on retrieval.

## Evidence

- **HN Ask: Thinking about memory for AI coding agents:** Developers keep re-explaining engineering principles to agents session after session. Prompts disappear after each task, static rules can't capture product constraints and past tradeoffs, and project-level rules are inappropriate for personal preferences. Solution: small, atomic memory entries that persist decisions and constraints, not conversations. — [HN ID 46742800](https://news.ycombinator.com/item?id=46742800)

- **Reddit/ClaudeCode: The mistake everyone makes with agent memory:** "Memory isn't storage — it's training data for decisions." Teams build append-only logs or vectors, spend 6 weeks tuning retrieval, then realize the agent still forgets the critical thing. What works: persistent memory for things the agent *decided* matter (not everything it saw), session memory that has a TTL, and treating failures as critical training data. — [r/ClaudeCode](https://www.reddit.com/r/ClaudeCode/comments/1q0i8mn/the_mistake_everyone_makes_with_agent_memory)

- **Redis blog — Long-Term Memory Architectures for AI Agents:** Maps CoALA's four memory types (working, episodic, semantic, procedural) to concrete storage. Procedural memory captures skills and routines encoded in prompts and agent code. Episodic memory gets consolidated into semantic memory over time. The read-before-reasoning, write-after-acting loop is the canonical agent architecture. Contradiction is the #1 failure mode in production. — [Redis.io](https://redis.io/blog/long-term-memory-architectures-ai-agents/)

## Gotchas

- **Appending everything makes retrieval worse.** A dense vector store with years of conversation chunks has worse recall precision than a sparse one with curated extracted facts. Size is not quality.
- **Fact contradiction is underappreciated.** Without temporal versioning, "user prefers dark mode" and "user prefers light mode" both get retrieved and the agent picks randomly. Graphiti-style temporal graphs address this explicitly.
- **Checkpoint state ≠ audit log.** Don't use your cold memory store as a history of everything. Keep checkpoints for resumability and audit logs in a separate append-only log.
- **Procedural memory is not a retrieval problem.** If your agent keeps skipping a validation step, the fix is a prompt or policy change — not a new memory entry.
- **The filesystem baseline is surprisingly strong.** Letta's benchmarks show plain filesystem scoring 74% on memory tasks, beating several specialized vector-store memory libraries. Start simple.
