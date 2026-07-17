# S-1000 · The Context Exhaustion Stack — When Your Agent Silently Degrades as the Window Fills

Your agent completed the first 30 tasks flawlessly. By task 47, it was hallucinating function names, ignoring your instructions, and re-reading files it had already modified. No error. No crash. No log entry. The model didn't change. The context filled and the agent quietly lost the middle of what it knew.

This is not a memory problem. Memory systems — summaries, vector stores, scratchpads — live *outside* the context window. The context window is the live working memory: everything the model can actually attend to right now. When it fills, the model degrades before it fails, and the degradation looks like confusion, repetition, and hallucination — symptoms that are hard to attribute to their real cause.

## Forces

- **The model can't tell you it's full.** Token limits are hard ceilings. Before the model hits them, it degrades — and it does so confidently, without signaling the problem.
- **"More context = better answers" is obsolete thinking.** Research from Stanford, UC Berkeley, and Samaya AI (2023) shows that transformer attention has a natural U-shaped bias: information at the beginning and end of the context is attended to strongly; information in the middle drops to 76–82% accuracy versus 85–95% at the edges. Burying critical context in the middle of a long session is worse than not including it.
- **Context stuffing feels correct.** The instinct to dump everything in — all prior messages, all tool outputs, all retrieved documents — feels like thoroughness. In production, it directly causes the degradation you're trying to prevent.
- **Compression is lossy and invisible.** Auto-summarization discards details you may still need, and the agent has no signal that this happened. It continues working with a gap it can't perceive.
- **Context is not heap memory.** Treating the context window like a scratch buffer — append everything, let the model sort it out — ignores that its contents directly affect every computation. It is closer to a CPU register file: finite, expensive per unit, and its contents are the actual medium of reasoning.

## The move

**Manage context as a first-class resource with explicit eviction, not implicit truncation.**

- **Treat the context window as a budget, not a buffer.** Track token usage per turn and per session. Define hard thresholds — most teams trigger active eviction at 60–70% capacity, not when the window is full. Leave a safety margin.
- **Implement tiered compression in order of reversibility.** Tier 1: offload large tool responses (full files, API returns, search results) to disk, replace with a filesystem reference and 2–3 sentence summary. Tier 2: summarize prior conversation turns, keeping decisions and current state. Tier 3: re-rank and evict based on semantic relevance to the active task. Each tier is progressively more lossy — use the least destructive option first.
- **Keep critical state in the system prompt, not conversation history.** System-level constraints, guardrails, and task intent belong in the system prompt — the highest-attention zone. Conversation history is where context degradation is most likely. Externalize what must survive into the invariant header.
- **Give the agent surgical context tools, not bulk compaction.** The context-surgeon pattern (evict / replace / restore primitives) lets the agent itself decide what to keep, making the eviction decision explicit and reversible. This is better than auto-compaction because the agent has task-level awareness that a static threshold lacks.
- **Log pre/post eviction diffs.** Every eviction should produce a structured log entry: what was removed, why it was selected for removal, and what the context looked like after. This makes post-hoc auditing possible — you can't fix a failure mode you can't see.
- **Use positional resilience for critical information.** Put the most important items at the beginning *and* end of the context window — exploit the U-shaped curve, don't fight it. Put secondary information in the middle where the model's attention is naturally weakest.
- **Monitor context usage end-to-end.** Track token counts, eviction frequency, and compression ratios per session. A session that triggers eviction 3x in 20 turns is exhibiting a pattern worth investigating before it hits production.

## Evidence

- **HN discussion (Ask HN):** Production teams overwhelmingly report that stateless approaches break down fast when users say "as I mentioned before." The solution that works: treating the entire conversation thread as bounded context and managing it explicitly, not appending indefinitely. — [Hacker News, ID 47660705](https://news.ycombinator.com/item?id=47660705)
- **Engineering blog:** The context window is not heap memory — treating it like one causes silent degradation. Explicit eviction policies (semantic relevance scoring, cost-aware eviction, information density ranking) outperform both LRU and random eviction in agentic workloads. — [Tian Pan, tianpan.co (April 19, 2026)](https://tianpan.co/blog/2026-04-19-context-not-heap-eviction-policies-llm)
- **GitHub / engineering post:** context-surgeon gives agents three primitives — evict, replace, restore — for managing their own context window. Replaces crude auto-compaction with task-aware, surgical editing. Works with Codex CLI and Claude Code. — [jackfruitsandwich/context-surgeon, GitHub](https://github.com/jackfruitsandwich/context-surgeon)
- **Research + engineering synthesis:** Comet.com analysis of the "lost in the middle" problem in production: information buried in the middle of long contexts degrades model reasoning performance by up to 73%. The solution at the architectural level is distributed context management — compartmentalizing context so no single window exceeds the U-shaped curve's degradation threshold. — [Comet.com, Sharon Campbell-Crow (January 5, 2026)](https://www.comet.com/site/blog/multi-agent-systems)
- **Industry benchmark:** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025, with 57% of organizations already running agents in production. The #1 infrastructure bottleneck these teams report: routing, guardrails, and context management across agents — not model selection. — [RaftLabs / Gartner data (March 27, 2026)](https://www.raftlabs.com/blog/multi-agent-systems-guide)

## Gotchas

- **Auto-summarization doesn't signal itself.** The agent continues working after compression with no awareness that details were dropped. Pair every compression step with an explicit note to the agent: "Previous turns summarized — key decisions preserved: [list]. Re-read files as needed."
- **Summary fidelity is unverified by default.** A compressed summary can omit exactly the detail that becomes critical on the next turn. For high-stakes sessions, add a periodic spot-check: compare the live summary against the original content to catch silent fidelity loss before it cascades.
- **Context eviction in multi-agent systems multiplies the problem.** When one agent hands off to another, the receiving agent gets only what the sender included — not what was evicted. Handoff summaries must be treated as a distinct artifact with their own fidelity requirements, not a pass-through of the sender's compressed context.
