# S-1467 · The Context Rot Stack — When Your Agent Is Still Running but No Longer Thinking

Your agent is active. It responds. It takes actions. But somewhere around message 15 or after 35 minutes of operation, it stopped being correct. It contradicts earlier instructions. It repeats steps it already completed. It ignores constraints you set at the start. The context window hasn't hit its limit — the model has simply stopped paying attention to the middle of the conversation. Context rot doesn't crash your agent. It makes it confidently wrong.

## Forces

- **The model still works. The reasoning doesn't.** Context rot is not a crash or an error — it's silent degradation. The LLM generates fluent responses but pays diminishing attention to information in the middle of the context. Your agent appears functional while producing increasingly poor outputs.
- **Bigger context windows delay the problem, they don't solve it.** Claude 4 Opus has 1M tokens. Gemini 1.5 Pro handles 1M tokens. GPT-4o handles 128K. Yet context management remains the first serious technical wall teams hit in production. A 1M-token window just means you accumulate more garbage before the rot sets in.
- **The "lost in the middle" problem is a hard model behavior, not a fixable bug.** Stanford's landmark study found that with just 20 retrieved documents (~4,000 tokens), model accuracy drops from 70-75% at the beginning or end of context to **55-60% in the middle positions** — a 15-20 percentage point drop from position alone, with zero change in the actual content.
- **Context grows from three compounding sources.** Every turn of conversation adds a message pair. Every tool call adds verbose JSON output. Every document chunk from RAG adds retrieved text. In a 30-step workflow, these compound into 100K+ tokens — and the rot starts before you reach the hard limit.
- **65% of enterprise AI failures in 2025 trace to context degradation or drift**, not raw token exhaustion. Teams prepare for crashes and handle them. They don't prepare for silent reasoning collapse, so it ships undetected.

## The Move

The fix is layered: compress what stays in the window, preserve what gets evicted, and build in visibility so rot doesn't ship silently.

**1. Instrument before you compress.** Every LLM call goes through token-counting middleware that tracks window occupancy in real time. Set a trigger threshold at 70-75% of your history budget — not at 95%, where you're already in trouble. The Inductivee production configuration uses this two-stage approach: agent-side compaction fires at 50%, gateway safety net fires at 85% with deliberate offset to prevent gaps.

**2. Compress structurally, not narratively.** Generic summarization (turning conversation into a prose story) reduces token count but destroys the structured facts agents need — file names modified, constraints stated, steps already taken. The right target is **structured extraction**: preserve entities, actions taken, pending decisions, and hard constraints as labeled facts. Factory.ai tested three compression strategies on 36,611 real agent messages and found structured summarization retained more useful information than provider-native compaction or aggressive truncation. The right optimization target is not tokens per request — it's tokens per task.

**3. Offload tool results to external storage.** Verbose tool outputs (JSON dumps, document content, query results) are the fastest-growing context component. Deep Agents (LangChain's production reference architecture) implements filesystem-style offloading: large tool results are written to external storage and retrieved on demand, keeping only a reference and summary in the working context.

**4. Extract before compressing.** Before any compression or eviction happens, call `mem0.add()` (or equivalent) to write structured facts to persistent memory. This separates "what the model saw this session" from "what must survive across sessions." Compression manages the working window; external memory manages cross-session continuity. The write-before-compaction pattern ensures that when the context window compresses, the critical facts aren't lost — they're retrievable on the next turn.

**5. Prioritize recency with bounded history.** The rolling window approach keeps the N most recent turns and discards older ones. This is simple and predictable but risks evicting critical early-session constraints. A better approach: retain a persistent "anchor" of key facts (stated goals, hard constraints, completed steps) while applying rolling eviction only to conversational noise.

**6. Detect context drift, not just token limits.** Set up behavioral monitoring that tracks whether the agent is repeating actions, contradicting itself, or ignoring explicit constraints — independent of token count. Neura Market's analysis of 2,000 production agents found 15% degraded responses when context exceeds 75% of window occupancy. Track task-completion rate, not just latency or token usage.

## Evidence

- **Research study:** Stanford's "Lost in the Middle" paper (2023, arxiv:2307.03172) demonstrated that with 20 retrieved documents (~4,000 tokens), LLM accuracy drops 15-20 percentage points for information in middle positions versus beginning/end — despite all information being technically present. Redis.io analysis and citation — [https://redis.io/blog/context-rot/](https://redis.io/blog/context-rot/)

- **Production data:** AgentMarketCap (April 2026) analyzed real production agent sessions and found performance degrades meaningfully after ~35 minutes of autonomous operation. 65% of 2025 enterprise AI failures attributed to context drift rather than outright token exhaustion — [https://agentmarketcap.ai/blog/2026/04/09/agent-state-accumulation-degradation-context-window-memory-drift](https://agentmarketcap.ai/blog/2026/04/09/agent-state-accumulation-degradation-context-window-memory-drift)

- **Compression evaluation:** Factory.ai tested three compression strategies (Factory structured summarization, OpenAI, Anthropic) on 36,611 messages from real agent sessions spanning debugging, code review, and feature implementation. Structured summarization retained more task-relevant information than alternatives without sacrificing compression efficiency. Right optimization target is "tokens per task" not "tokens per request" — [https://factory.ai/news/evaluating-compression](https://factory.ai/news/evaluating-compression)

- **Pruning impact:** Neura Market (May 2026) analyzed 2,000 production AI agents and found agents without context pruning lose 30% accuracy after 50 interactions and cost 2× per run after 100 interactions. Age-based pruning (removing oldest turns first) is least effective — relevance-based pruning outperforms it significantly — [https://www.neura.market/blog/how-to-build-a-context-pruning-pipeline-for-long-running-ai-agents](https://www.neura.market/blog/how-to-build-a-context-pruning-pipeline-for-long-running-ai-agents)

- **Real-world deployment pattern:** Inductivee's production configuration combines token-counting middleware on every LLM call, incremental compression with domain-specific summary prompts, and a 70-75% threshold trigger. Their finding: a well-engineered compression prompt reduces context size by 80% while maintaining agent coherence — but a generic compression prompt that produces narrative summaries loses critical structured facts — [https://inductivee.com/blog/context-window-management-production](https://inductivee.com/blog/context-window-management-production)

## Gotchas

- **Providers' native context compaction is convenient but lossy.** Claude Code's Context Compaction API trades configurability for simplicity. It preserves narrative continuity but silently collapses exact-value preferences and hard constraints. Don't rely on it as your sole compression strategy.
- **Age-based eviction is the default but the worst strategy.** Removing the oldest turns first ignores whether those turns contain critical constraints or late-session decisions. Relevance scoring and explicit importance tagging significantly outperform FIFO eviction.
- **Context monitoring that only tracks token count misses the real problem.** Rot sets in well before the window is full. You need behavioral monitoring — tracking contradiction rate, action repetition, and constraint adherence — not just occupancy percentage.
- **The compression prompt is the most sensitive component of the entire system.** A bad compression prompt produces a concise context that looks fine but silently destroys the agent's ability to reason correctly. Treat compression prompt engineering as a first-class concern, not an afterthought.
