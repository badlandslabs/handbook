# S-1754 · The Context Surface Stack

When your agent degrades mid-conversation — repeating itself, losing the thread, ignoring facts that were stated three turns ago — the problem is not the model. It is that the context window is not a reliable storage medium: information in the middle gets ignored, older tokens get drowned, and what the agent "knows" shrinks as the session grows, even though nothing has been forgotten — only buried.

## Forces

- **Attention is not storage** — models attend differentially across context; information at the start and end sticks, middle information disappears. This is not a bug in your agent; it is a property of attention mechanisms.
- **Context rot before overflow** — most agents fail at ~130K tokens of actual usage, long before they hit model limits. Degradation is sudden, not gradual.
- **MECW vs. advertised context** — the Maximum Effective Context Window is almost always smaller than the marketed limit. A 200K model may perform reliably only to 100K.
- **Compression destroys signal** — naive summarization discards the very details that matter; importance-weighted compression requires knowing what will matter, which requires knowing the future.
- **Memory systems solve the wrong problem** — Mem0, Letta, and Zep persist across sessions, but context rot happens *within* a session, before any retrieval ever fires.

## The move

Treat the context window as a **tiered, actively-managed surface** — not a dump bin. The strategy: anchor critical information at the boundaries, compress the middle intelligently, and offload before the rot sets in.

- **Put the most important information at the start and end of context.** System instructions, current task, and the most recent user message sit in the positions models attend to best. Do not bury task-critical instructions in the middle of a long prompt.
- **Use hierarchical summarization, not truncation.** When context exceeds ~60–70% of MECW, compress older conversation segments into structured summaries rather than dropping tokens. Anchor summaries retain key facts, decisions, and unresolved threads; discard surface noise. An "anchored iterative" approach (per-event compaction with overlap) outperforms full-reconstruction summaries.
- **Implement a sliding window with an offloading trigger.** When the conversation exceeds a threshold (e.g., 80K tokens on a 128K-capable model), compress the oldest 20% into a retrievable summary and continue. Treat the window as a ring buffer, not a stack.
- **Separate tool definitions from active context.** MCP tool schemas alone can consume 70%+ of a 200K context window. Load them once per session and reference them by name, not by re-injecting definitions. Use tool registries, not tool re-description.
- **Use the LLM itself as a triage layer.** Before offloading, have the agent identify: what facts from this segment must survive? What can be reconstructed? What should be discarded? This is the Mem0/Letta insight applied *within* a session.
- **Track "unresolved threads" explicitly.** Maintain a short, pinned list of open questions, pending decisions, and known-facts-at-risk. Treat it like a task queue, not memory. It survives summarization and sits near the end of context where the model attends to it.

## Evidence

- **Research survey:** 65% of enterprise AI agent failures in 2025 were attributed to context drift or memory loss during multi-step reasoning — not model capability limits. 11 of 12 tested models dropped below 50% of short-context performance at 32,000 tokens. GPT-4 showed 15.4% degradation from 4K to 128K tokens. — [Zylos Research / AgentMarketCap, April 2026](https://agentmarketcap.ai/blog/2026/04/11/agent-context-engineering-sliding-windows-memory-2026)
- **HN discussion:** "Ask HN: Is operational memory a missing layer?" surfaced broad agreement that within-session degradation is distinct from cross-session memory — a category the author called "operational memory" distinct from episodic/persistent. — [Hacker News, ~Feb 2026](https://news.ycombinator.com/item?id=47462910)
- **Production implementation:** Google ADK exposes `TokenBasedContextCompactor` with configurable compaction intervals and overlap — evidence that framework vendors treat in-session compression as a first-class concern. — [Google Agent Development Kit](https://adk.dev/context/compaction/)

## Gotchas

- **Summarization introduces hallucination risk.** Compressed context can misrepresent what was actually said. Validate critical facts, not just summaries.
- **"Lost in the middle" survives summarization.** If you summarize but keep the summary in the middle of context, the same attention bias applies. Put summaries near the end of context.
- **MECW varies by model and task.** A single threshold will be wrong for some models. Calibrate your offloading trigger against actual performance on your task, not against the advertised context limit.
- **Tool redefinition is expensive.** The reflex to re-describe tools on every call is the single most wasteful context management pattern in production agentic systems. Fix it once with a registry.
