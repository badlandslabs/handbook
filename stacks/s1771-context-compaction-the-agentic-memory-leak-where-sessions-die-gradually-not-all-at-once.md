# S-1771 · Context Compaction — The Agentic Memory Leak Where Sessions Die Gradually, Not All at Once

Long-running AI agents don't fail loudly. They fail silently — re-proposing rejected solutions, forgetting why approach A was chosen over approach B, losing track of running sub-agents, and accumulating "mini-amnesia" until the session becomes unusable. This is context rot: the silent degradation of agent reasoning that happens well before hard token limits are hit. The field calls it "compaction," and it is the production problem nobody talks about until their agent starts gaslighting itself.

## Forces

- **Context windows are finite but context rot is unbounded** — performance degrades before you hit the limit, so you can't just wait for the wall
- **Truncation destroys reasoning chains** — naive compaction destroys the "why" while preserving the "what," leaving agents confident but wrong
- **Compaction strategies vary wildly across frameworks** — some are surgical (preserve key decisions, distill reasoning), others are crude (sliding window, last-N tokens)
- **Cross-session memory is a separate problem** — in-session compaction doesn't solve the cold-start problem; agents still wake up fresh each session
- **Cost and latency compound** — every token in conversation history is re-processed and re-billed on every subsequent API call

## The move

Compaction is not truncation. It is the art of deciding *what survives* when context must be condensed — and the teams that get this right layer three things:

- **Compaction memory (in-session):** A production-tested method where agents maintain a "brain dump" — a persistent, cumulative instruction file that is prepended to every compaction cycle. The critical fix: instead of overwriting the previous compaction summary, *append* to it with explicit hierarchy. Preserve: (1) what was done and why, (2) current blocking issues, (3) running sub-agents and their status. The session survives 12+ compactions with full context versus losing everything after 2-3 without the fix.
- **Semantic memory (cross-session):** Persistent external storage the agent writes to and reads from between sessions. FAVA Trails (Git-native MCP) uses draft/promotion gates and supersession chains so old beliefs are hidden from recall when corrected. Mem0's 2026 report shows +26% accuracy gains with structured retrieval over naive vector similarity. This is distinct from in-session compaction — external memory persists when the context window resets.
- **Three-layer context budget:** Treat context as a finite resource with diminishing marginal returns. Set explicit breakpoints: at 50% capacity do lightweight tool clearing (drop re-fetchable intermediate results), at 70% do structured summarization (preserve decisions, discard scaffolding), at 85% do full compaction with external memory checkpoint. Never run compaction reactively — budget it proactively.
- **Tool clearing as a first-class primitive:** Not just compaction and memory. Claude's context engineering guide separates *clearing* (drop old, re-fetchable results while keeping the record that the call happened) from *compaction* (summarize and reinitiate) from *memory* (structured persistent note-taking). Each trades off differently. Use all three, not just one.
- **Compaction is a trust-gated write:** Don't let the agent auto-compact. Add an LLM-based reviewer step before committing a compaction summary to memory. A bad compaction is worse than no compaction — it introduces false beliefs that propagate confidently into every subsequent step.
- **Cold-start injection:** When an agent wakes fresh, explicitly retrieve the last 3 session summaries + active context from semantic memory before doing anything else. Without this, the agent is genuinely amnesiac — even if yesterday's session was perfect.

## Evidence

- **AWS Amazon Blog (Evaluating AI Agents, 2025):** Documents that "thousands of agents" have been built at Amazon since 2025, and that agent scaffolding (context management, memory, verification) is a primary determinant of production quality — separate from model choice. Emphasizes that traditional LLM evaluation (black-box, outcome-only) fails for agents; you must evaluate tool selection coherence, memory retrieval efficiency, and multi-step reasoning chains.
- **Zylos Research (Context Compression Strategies, Feb 2026):** Found that 65% of enterprise AI failures in 2025 were attributed to context drift before hitting hard token limits. Surveys three concrete techniques: anchored iterative summarization (preserve decision rationale), failure-driven guideline optimization (ACON, where compaction failures teach future compactions), and provider-native compaction APIs.
- **Claude Cookbook — Context Engineering (2026):** Documents three distinct primitives — compaction (summarize and reinitiate), clearing (drop re-fetchable results), memory (persistent external storage) — and shows that Claude Code uses all three in production, with server-side compaction APIs and the memory tool. Provides the API-level details for implementing each.
- **Redis Blog — Context Compaction Guide (2026):** Treats compaction as a distributed systems problem: the compaction mechanism and external memory are architecturally separate but operationally coupled. External memory only helps if the data inside it survives compaction of *that* memory store.
- **HN Discussion — How 30+ AI Agent Frameworks Handle Context Rot (2025):** A GitHub handbook (vasilyevdm/ai-agent-handbook, 111 stars) that read the actual source code of 30+ frameworks and documented their compaction logic, context rot handling, and system prompt assembly patterns. HN commenters noted that most "framework comparison" posts are surface-level feature matrices; actually reading source code reveals that compaction strategies "vary wildly — some are surgical, others are crude truncation."
- **DEV Community — "Memory Is the New Moat in Coding Agents" (July 2026):** Argues that with model quality plateauing at the frontier, the competitive war has shifted to harness components — memory systems, skill registries, and evaluation loops. Cites an ArXiv paper (April 2026) with empirical evidence that observability-driven harness improvements outperform model upgrades.

## Gotchas

- **Compaction is not truncation** — naive sliding-window or last-N compaction destroys reasoning chains and creates false confidence. The "what happened" survives; the "why it matters" does not.
- **Running compaction reactively is too late** — by the time you hit 90% context, the model is already degraded. Budget at 70%, trigger at 50% for summary, 80% for full compaction.
- **External memory that doesn't survive its own compaction is useless** — if your memory store itself gets compacted by a separate process, you've stored nothing. Treat memory compaction and agent compaction as separate processes with independent budgets.
- **Cross-session memory has a cold-start tax** — without explicit injection, the agent genuinely does not know what happened in the previous session. Write a session summary during every graceful exit, not just on errors.
