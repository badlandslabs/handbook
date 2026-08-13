# S-2576 · The Simple Memory Wins Stack — When Your Agent Remembers Better Than Your Vector Store

You spent three weeks building a temporal knowledge graph with weighted episodic recall and entity linking. Your colleague's agent stores conversations in a `.md` file. Their agent outperforms yours on recall tasks. This is the **simple-memory-wins problem**: the agent capability matters more than the retrieval mechanism, and most of the complexity you added was noise.

## Forces

- **Sophistication bias:** teams assume better tools = better memory, so they reach for vector stores and knowledge graphs before proving simpler approaches fail.
- **Benchmark blindness:** popular memory benchmarks (LoCoMo) don't meaningfully differentiate retrieval mechanisms — a flat file scores 74%, Mem0's graph scores 68.5%.
- **Token cost amnesia:** specialized retrieval introduces its own token overhead (query embedding, system prompts describing the retrieval API, result parsing) that can outweigh the retrieval benefit.
- **The AgentMarketCap finding:** 2026 production postmortems show the most common memory failure isn't *retrieval* — it's that agents can't recall what happened last week, can't synthesize across sessions, and lose coherent evolving context. The fix is usually structural (what you store, when you consolidate) not mechanical (how you index it).

## The move

Don't reach for a memory system until you've established what the agent needs to remember and why a flat store fails. Start at the bottom of the complexity ladder.

- **Layer 1 — Conversation file:** append sessions to `memory/sessions/{date}-{session_id}.md`. Truncate or summarize when it exceeds a token budget. This alone scores 74% on LoCoMo.
- **Layer 2 — Entity index:** a second flat file tracking key entities (user prefs, project facts, current objectives). Updated on session end via a "reflect" step — the agent reads its session, extracts what to carry forward.
- **Layer 3 — Selective retrieval:** only add semantic search (vector DB, BM25) when entity index growth makes linear scan too slow. Most agents never hit this threshold.
- **Reflect before storage:** run a session-end prompt ("what does the next agent need to know?") to convert raw conversation into structured notes. Raw logs bloat context; distilled notes don't.
- **Memory decay by design:** prune or archive sessions older than 30 days into an "archive" bucket. Don't keep everything — keep what's actionable.
- **Measure retrieval quality, not system complexity:** track what the agent *gets wrong* when it retrieves, not how fast or fancy the retrieval is.

## Evidence

- **Letta benchmark:** Letta agents using only filesystem storage (storing conversation histories in files, no specialized tools) scored **74.0% on the LoCoMo recall benchmark**, outperforming Mem0's graph-variant at 68.5% and most specialized memory systems. — [Letta Blog: Benchmarking AI Agent Memory](https://www.letta.com/blog/benchmarking-ai-agent-memory/), Aug 12, 2025
- **Anthropic production findings:** after working with dozens of teams deploying agents, Anthropic engineers found the most successful implementations use simple, composable patterns rather than complex frameworks. Memory is surfaced through structured session logs and deliberate reflection steps, not automated retrieval pipelines. — [Anthropic Engineering: Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents), Dec 19, 2024
- **AgentMarketCap architecture survey:** across 2026 enterprise deployments, the primary memory failure mode was structural — agents couldn't maintain coherent cross-session context — not mechanical. Teams that added explicit "what did we learn" reflection steps (without changing the storage backend) saw measurable quality improvements. — [AgentMarketCap: Agent Memory Architecture Benchmark 2026](https://agentmarketcap.ai/blog/2026/04/11/agent-memory-architecture-benchmark-2026), Apr 11, 2026

## Gotchas

- **You need a session-end trigger to consolidate memory.** Without one (a reflect step, a summary hook), memory stays raw and grows unboundedly. Most "memory systems" that fail are actually missing this step.
- **The 74% LoCoMo score doesn't mean flat files are always enough.** LoCoMo tests short-horizon episodic recall. Long-horizon tasks (weeks of project context) may benefit from structured entity tracking that flat files can't maintain efficiently.
- **Context window limits bite before retrieval fails.** Before optimizing your retrieval mechanism, audit what fraction of your context window is consumed by the memory retrieval itself. Purpose-built memory layers can cut token costs ~90% by retrieving only what's relevant — not because the retrieval is smarter, but because it returns less.
