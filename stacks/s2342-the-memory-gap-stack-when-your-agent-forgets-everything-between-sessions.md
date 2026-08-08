# S-2342 · The Memory Gap Stack — When Your Agent Forgets Everything Between Sessions

An agent that works beautifully in one session gives you a blank stare the next. Same user, same preferences, same project context — gone. Teams hit this when agents cross provider boundaries, restart with a new model, or simply run the next day.

## Forces

- **Context windows are finite; real relationships aren't.** Even 200K-token context windows degrade over weeks of multi-session interactions. After months, critical facts are buried under noise.
- **Vendor memory is stuck to the vendor.** Mem0, Claude memory, OpenAI Memory — they all work inside their own walls. Switch providers and you lose everything.
- **Retrieval is not the same as remembering.** Naive vector similarity search retrieves context but doesn't prioritize importance, recency, or relevance decay. The agent gets noise, not signal.
- **Memory infrastructure is everyone's second priority.** It's not the cool feature that ships. It accumulates as technical debt until agents need to work across real time horizons.

## The move

Treat memory as a separate infrastructure layer with its own API contract — not embedded in the agent, not locked to the provider.

**The retrieval-augmented memory pattern (Mem0 et al.):**
- Extract facts from each conversation turn automatically via LLM
- Store structured memories with user/session/agent scope
- Retrieve relevant memories at session start and inject as context
- Score and rank by recency, importance, and access frequency

**The biological decay scheduling (YourMemory):**
- Apply Ebbinghaus forgetting curve to memory reinforcement
- Schedule re-consolidation of memories that matter but haven't been accessed recently
- Compress memories (N→1) to stay within retrieval context limits

**The multi-agent shared memory (CtxVault pattern):**
- Centralized memory store accessible to multiple agents in a crew
- Each agent reads/writes to shared context pool
- Enables agent handoffs without repeating context

**The provider-portable memory contract:**
- Keep memory storage in your own infrastructure (SQLite, Postgres, vector DB)
- Provider agnostic — swap Claude for GPT without losing history
- Export/import formats so memory survives framework migrations

## Evidence

- **Research paper:** Mem0 published "Mem0: Building Production-Ready AI Agents with Scalable Long-Term Memory" (arXiv:2504.19413) — introduces the three-scope memory model (user, session, agent) and benchmarks showing LoCoMo scores of 92.5 (new algorithm, April 2026) vs 71.4 baseline. YC-backed, 62K+ GitHub stars, raised $24M Oct 2025.
  — https://arxiv.org/html/2504.19413v1

- **Show HN: AgentKeeper — cognitive persistence layer for AI agents** — built specifically to solve the provider-switching memory problem. Agents lose memory when: switching providers, restarting with a different model, or restarting with the same model but different session. AgentKeeper maintains a cognitive persistence layer that survives these transitions.
  — https://news.ycombinator.com/item?id=47217244

- **Show HN: CtxVault — Local memory control layer for multi-agent AI systems** — built for multi-agent systems where agents need to share context across handoffs. Each agent writes to a shared memory store; subsequent agents read the accumulated context rather than re-deriving it.
  — https://news.ycombinator.com/item?id=47136585

- **Production AI Agent Stack Guide (APIScout, 2026):** Memory layer is the fifth of six production layers, after model access, tools, MCP, browser automation. Recommendation: separate your memory storage from your agent logic and your provider, so each can evolve independently.
  — https://apiscout.dev/guides/production-ai-agent-api-stack-2026

- **Show HN: YourMemory — AI memory with biological decay (Ebbinghaus):** Claims +16 percentage points better recall than Mem0 on LoCoMo benchmarks by using forgetting-curve-based reinforcement scheduling rather than simple vector retrieval.
  — https://news.ycombinator.com/item?id=47914367

## Gotchas

- **Embedding drift.** As models change, the same query retrieves different memories. Your retrieval pipeline can silently degrade when you upgrade the embedding model without re-indexing.
- **Memory bloat.** Without active forgetting or compression, memories accumulate indefinitely until retrieval context is flooded. Your "relevant context" degrades to "everything."
- **Privacy leakage.** Cross-user memory is a data plane risk. A shared memory store for multi-agent crews can accidentally surface one user's context to another agent that shouldn't see it.
- **The cold-start gap.** A fresh session with no retrieved memories is indistinguishable from a session with empty memories. The agent may not know it has a memory system to consult, so it doesn't. Prompt explicitly: "Check your memory for prior context before responding."
