# S-1647 · The Memory Architecture Stack — When Your Agent Remembers Everything and Knows Nothing

Your agent stores every conversation. When you ask it something it discussed last week, it either retrieves the wrong fact or tells you it never happened. The problem isn't storage capacity — it's that your memory layer is an append-only log wearing a knowledge base costume.

## Forces

- **Context windows don't scale.** Every token competes for attention — models start deprioritizing critical information once context exceeds 60% capacity, even when the answer is in the window. A 200K-token conversation dump is not memory; it's noise the model has to navigate.
- **Retrieval without meaning is not recall.** Vector similarity search finds semantically related text, not epistemically correct facts. An agent can retrieve the wrong version of a fact with high confidence if that version appeared more often or more recently.
- **Memory staleness is invisible.** The agent retrieves what the system stored — not what is still true. Real-world facts change (prices, policies, relationships), but the stored memory doesn't know. The agent acts on outdated assumptions while confidently retrieving stale evidence.
- **Cross-session identity is unsolved.** Attributing facts to the right user across sessions, distinguishing ephemeral preferences from durable knowledge, and handling conflicting information from multiple sessions all require active reconciliation — not just storage.

## The Move

The 2026 production consensus is a three-tier architecture that separates storage by retrieval pattern and manages each tier differently:

- **Tier 1 — Working memory (ephemeral).** The current session's raw message buffer, tool calls, and active state. Zero infrastructure. Cleared on session end. This is RAM — fast, accurate, gone when you power off.
- **Tier 2 — Episodic memory (compressed).** Past sessions stored as summaries or extracted facts, not raw transcripts. Use LLM-based summarization or extraction to distill what matters from each session rather than storing full history. Searchable within and across sessions.
- **Tier 3 — Semantic memory (curated).** Persistent knowledge base, entity relationships, user preferences that don't change. This tier is edited, not just appended — the agent or a reconciliation process updates facts when new evidence contradicts old ones.

The critical move: **treat memory as an active process, not a passive store**. Someone or something must be accountable for epistemic correctness — reconciling conflicting facts, invalidating stale information, and deciding what warrants a tier-3 slot. The dominant `add(text)` / `search(query)` API leaves nobody responsible for this, creating append-only logs that grow indefinitely while degrading in quality.

- Give the agent write access to its own memory, with a schema that enforces structure (structured facts with timestamps and provenance, not raw text blobs).
- Implement temporal validity: tag memories with expiration conditions or re-validation triggers. When the agent stores a fact about "the current sprint deadline," that memory should carry a dependency on the sprint end date.
- For multi-agent systems, shared memory needs a single writer protocol — concurrent append without conflict resolution produces contradictory knowledge that agents retrieve with equal confidence.
- Prefer knowledge graph over flat vector store when retrieval requires multi-hop reasoning (A relates to B, B relates to C, what is A's relationship to C?). Pure vector similarity cannot traverse relationships.

## Evidence

- **Benchmarking study:** Mem0's 2026 benchmark report shows new memory algorithms scoring 92.5 on LoCoMo and 94.4 on LongMemEval at ~6,900 tokens/query, with +29.6 points on temporal reasoning and +23.1 on multi-hop — but the report explicitly flags cross-session identity, temporal abstraction at scale, and memory staleness as the hardest open problems still unsolved by current approaches.
  — *Mem0: AI Agent Memory 2026 Progress Report* — https://mem0.ai/blog/state-of-ai-agent-memory-2026

- **Architecture analysis:** Atlan's 2026 pattern analysis found full-context in-process memory achieves 72.9% accuracy at 17.12s p95 latency, while flat vector retrieval drops to 66.9% at 1.44s (91% speed gain). The accuracy vs. latency tradeoff is not linear — the sweet spot is selective retrieval with structured memory, reducing tokens from ~26,031 to ~1,764 per conversation (90% reduction) while maintaining or improving accuracy.
  — *Atlan: Agent Memory Architectures — 5 Patterns and Trade-offs* — https://atlan.com/know/agent-memory-architectures

- **Framework comparison:** Letta (formerly MemGPT) demonstrates self-editing memory — the agent can update its own personality and user knowledge at runtime — while Mem0 uses adaptive memory that edits existing memories rather than appending duplicates, maintaining user/session/agent-level scoping across a hybrid vector + graph + key-value store. Zep scores 63.8% vs Mem0's 49.0% on LongMemEval, a 15-point gap attributed to Zep's temporal knowledge graph approach over Mem0's adaptive retrieval.
  — *RockB: AI Agent Memory Architecture Guide 2026* — https://baeseokjae.github.io/posts/agent-memory-architecture-guide-2026/

## Gotchas

- **Append-only is the default failure mode.** Every `add()` call without a corresponding `revise()` or `invalidate()` creates a memory that grows but never gets cleaner. After six months, your agent has 47 versions of the user's name pronunciation with no way to know which is current.
- **Bigger context window is not a memory strategy.** A 1M-token context means the model can see more, not that it understands more. Models degrade in retrieval fidelity long before context is full — the "lost in the middle" problem means important facts in dense context get deprioritized regardless of window size.
- **Cross-session summarization drift.** If you summarize sessions to compress memory, the summarizer introduces its own biases and omissions. After 3-4 summarization passes, the distilled memory has lost details the agent will need — especially for long-horizon tasks where granular history matters.
- **Memory poisoning is real.** An attacker who can inject facts into your agent's memory can permanently alter its behavior. The agent retrieves poisoned facts with the same confidence as legitimate ones. Treat memory writes with the same access control as memory reads.
