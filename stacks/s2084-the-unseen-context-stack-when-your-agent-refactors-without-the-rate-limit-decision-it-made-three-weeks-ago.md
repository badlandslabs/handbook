# S-2084 · The Unseen-Context Stack · When Your Agent Refactors Without the Rate-Limit Decision It Made Three Weeks Ago

*When your agent completes a task that was already partially solved in a previous session — but it has no idea that prior context exists.*

## Forces

- **Context windows are finite; knowledge is unbounded.** Agents drop everything outside the current window, including decisions, constraints, and agreements made sessions ago.
- **RAG solves "you have it, find it" — not "you don't know you have it."** Standard retrieval requires you to query for what you need. The hard case is when you need something but don't know to ask for it.
- **Session isolation is the default, not the exception.** Switching models, providers, or even restarting a session resets the agent to a blank slate. Cross-session continuity is opt-in.
- **Memory is cheap; retrieval is expensive.** Storing everything is trivial. Knowing what to surface when — without a query, without a prompt — is the actual unsolved problem.
- **Compaction destroys signal.** When you compress context to fit a window, the first things to go are the "soft" decisions — the ones without a named file or explicit output — and those are often the most consequential.

## The Move

**Build a three-tier memory architecture that surfaces context proactively, not just on demand.**

The cognitive science analogy (episodic / semantic / procedural) maps directly to what production systems actually implement:

- **Working memory** (context window) — the current session's live state. Everything fits here by definition, but nothing survives a session boundary.
- **Short-term memory** (session-level) — what's learned within a session and needs to be summarized before the next one. Typically implemented as automatic session summaries or "last session recap" prompts.
- **Long-term memory** (cross-session persistence) — the accumulated knowledge base. This is where the real engineering challenge lives: what to store, how to index it, and critically, **how to surface it without a query**.

The core insight from production systems like Hipocampus (GitHub, 2025): the hardest memory problem isn't retrieval — it's **discovery**. The agent needs to know that relevant context exists even when nobody asked about it.

**Practical implementation tiers:**

- **Vector search with semantic indexing** — store conversation summaries, decisions, and extracted facts as embeddings. Query on session start to surface related prior context. Works for "I vaguely remember discussing X."
- **Proactive relevance surfacing** — instead of waiting for a query, run a background relevance check against long-term memory before each major tool call or task switch. Hipocampus calls this a "compaction tree" — a layered recall structure that surfaces context the agent doesn't know it needs.
- **Memory consolidation with intentional forgetting** — not everything should survive. Implement relevance scoring to decide what gets promoted from short-term to long-term. Trivial context (exact code reproductions, intermediate debugging steps) should decay. Architectural decisions, constraint agreements, and user preferences should persist.
- **Session bridge prompts** — on session start, inject a structured recap of the last N sessions' consequential decisions into the system prompt. Low-tech, high-signal. Works with any model, any provider.
- **Memory quotas per user or agent** — prevent unbounded storage growth by capping long-term memory at a fixed size and pruning by relevance + recency. The oldest entry isn't necessarily the least relevant.

## Evidence

- **GitHub repo (Hipocampus):** "Drop-in proactive memory harness for AI agents — 3-tier memory, compaction tree, hybrid search. Works with Claude Code and OpenClaw." The compaction tree approach directly addresses the unseen-context problem: layered recall that surfaces context without an explicit query. — [github.com/kevin-hs-sohn/hipocampus](https://github.com/kevin-hs-sohn/hipocampus)
- **HN Show Post (AgentKeeper):** "Agents lose memory when switching providers, restarting sessions, or changing models. We built a cognitive persistence layer to solve this." Explicitly targets the provider-switching and session-restart failure mode where memory loss is structural, not accidental. — [news.ycombinator.com/item?id=47217244](https://news.ycombinator.com/item?id=47217244)
- **Remery Blog (Aug 2025):** "Production systems need memory quotas per user to prevent unbounded storage growth." The three-tier taxonomy (working / short-term / long-term) maps observed production patterns to cognitive science frameworks. Key operational insight: semantic search with embeddings outperforms keyword matching when users phrase things differently across sessions. — [remery.ai/blog/agent-memory-architecture-persistent-context-systems](https://remery.ai/blog/agent-memory-architecture-persistent-context-systems)
- **Anthropic Engineering (Dec 2024):** "Optimize single LLM calls with retrieval and in-context examples first. Only increase complexity when needed." Positions memory as a retrieval problem first, an agentic problem second — consistent with the finding that simpler memory architectures outperform complex ones until complexity is genuinely required. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- **Long context windows are a trap, not a solution.** Packing everything into context doesn't scale, doesn't survive session boundaries, and buries signal under noise. Teams reach for 200K-token context as a memory substitute and end up paying for retrieval they don't use.
- **Vector search requires the right query to work.** If the user's current task is phrased differently from how the prior session was described, semantic similarity drops below retrieval threshold. The "payment flow ↔ rate limiting" example from Hipocampus illustrates this precisely: the concepts are related but lexically distant.
- **Memory compounding degrades quality.** Every summarization step loses nuance. By the third generation of session summaries, you get generic platitudes instead of specific decisions. Version your memory representations and prefer raw extracts for high-stakes content.
- **Provider switching destroys memory by default.** If your agent's memory lives in provider-specific context management, switching models or vendors wipes it. Portable memory layers (AgentKeeper's approach) decouple persistence from the inference provider.
