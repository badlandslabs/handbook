# S-1775 · The Operational Memory Stack — When Your Agent Forgets What It Was Doing Halfway Through

Your agent starts a task — browse three pages, extract pricing, compare options, write a summary. It browses page one, returns, re-reads the task, browses page two, returns, re-reads the task again. By page three it has forgotten what pages one and two said and re-asks for the task description. This is not a context window problem. You have 128K tokens remaining. This is an **operational memory** problem: your agent has no place to put "I have extracted X from page 1 and Y from page 2 and now I need Z from page 3." It is running on re-reading and re-trusting, not on state.

## Forces

- **Three memory types get collapsed into one** — operational (what I'm doing now), episodic (what happened before), and semantic (what I know generally) are treated as a single context problem, producing agents that re-read their own work as if they'd never seen it
- **Tool call boundaries are state boundaries** — every tool call is a black box to the agent; it cannot incrementally accumulate findings across calls without an explicit state store
- **Working memory and operational memory are not the same thing** — the context window is working memory; operational memory is the structured overlay that tells the agent which findings are pending, which contradictions have been flagged, and what the task state is at each step
- **Operational memory is the hardest to retrofit** — you can add RAG for semantic memory or append-only logs for episodic memory, but operational memory requires write-read-write patterns that most frameworks don't support natively

## The move

Build operational memory as a first-class, writeable layer that the agent updates explicitly at each step — not as a side effect of tool calls, but as a deliberate read/write cycle.

**1. Define the operational memory schema explicitly.** Operational memory is not a transcript. It has fields: `{task: string, phase: enum, findings: Record<string, any>, contradictions: string[], pending_actions: string[], checkpoints: [{phase, summary, timestamp}]}`. The agent reads this at the start of every inference and writes it at the end.

**2. Instrument tool calls to produce structured output, not just return values.** Every tool call should return a typed result that the operational memory layer can parse and slot into `findings`. If your browser tool returns raw markdown, your operational memory layer needs a summarizer between it and the agent. Build that summarizer.

**3. Use the "reflect" pattern at natural boundaries.** After every 3-5 tool calls or at each phase transition, run a lightweight reflection step: "Summarize what you know so far, flag any contradictions, list what remains." Store the output in `checkpoints`. If the agent goes off-track, you can restore from the last checkpoint rather than re-running everything.

**4. Treat contradictions as first-class citizens.** When two findings disagree, write to `contradictions: ["page 1 says $X/page, page 2 says $Y/page — needs reconciliation"]`. The agent must explicitly resolve contradictions before proceeding. This prevents the "confidently wrong" failure mode where the agent picks one finding and forgets the other existed.

**5. Keep operational memory small and structured.** Unlike episodic memory (which can grow large with embeddings), operational memory is plain text or JSON. Budget ~2K-4K tokens for it. If it's growing past that, the task is too complex and needs decomposition, not a bigger memory store.

**6. Add a "stuck detection" guard.** If the agent's next action is the same as its last action (same tool, same arguments), and no new findings were added to operational memory, trigger a reflection checkpoint and a restart from the last checkpoint rather than continuing the loop. This prevents the "I already browsed that page, let me browse it again" pattern.

## Evidence

- **arXiv survey (2025):** First large-scale study of deployed agents (306 responses, 86 deployed agents, 26 domains) found that 73% of teams building agents cite "productivity gains" as primary motivation, but the 86% who reached production all had explicit operational state management — either custom implementations or via frameworks with checkpointing (LangGraph, Microsoft Agent Framework). Agents without structured state management had 3-4x higher task failure rates on multi-step workflows. — [Measuring Agents in Production (arXiv 2512.04123)](https://arxiv.org/html/2512.04123v1)
- **Anthropic beta `context-management-2025-06-27` tool:** Client-side tool where Claude creates/reads/updates/deletes files in a `/memories` directory via tool calls. Internal evaluations showed 39% improvement on agentic search tasks and 84% token reduction in 100-turn conversations — by replacing re-reading with structured read/write cycles. Demonstrates that operational memory is more efficient than "just use more context." — [GitHub spikelab gist citing Anthropic beta](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)
- **HN Ask HN discussion on operational memory (2025):** Practitioner varunrrai proposed a distinction between episodic memory (past events) and a reusable operational memory layer for active tasks, noting that current agent frameworks conflate the two and produce agents that "forget mid-sentence" — where the forgetting is not a capacity issue but a missing write/read contract. Multiple commenters validated the pattern with production examples. — [HN Ask HN: Is operational memory a missing layer?](https://news.ycombinator.com/item?id=47462910)
- **Letta benchmarks vs. plain filesystem:** Memory platform Letta's benchmarks showed a plain filesystem scoring 74% on memory tasks, beating specialized vector-store memory libraries. The finding suggests the architectural clarity of simple operational memory (plain text, structured) often outperforms complex semantic retrieval — complexity is the enemy. — [GitHub spikelab gist on memory taxonomy](https://gist.github.com/spikelab/7551c6368e23caa06a4056350f6b2db3)

## Gotchas

- **Don't use episodic memory as operational memory.** Storing every past interaction in a vector DB and doing similarity search to reconstruct "what was I doing" is slow, expensive, and imprecise. Operational state needs indexed, structured access, not retrieval.
- **The "reflect" pattern has token costs.** Running a reflection step after every 5 tool calls adds ~20-30% to token consumption. Budget for it or it won't get used. Some teams gate reflections on phase transitions rather than fixed counts.
- **Checkpoint restoration requires idempotent tool calls.** If your browser tool returns different content on the same URL (dynamic pages, ads, A/B), restoring from a checkpoint won't reproduce the same result. Store the raw finding, not just the checkpoint summary.
- **Operational memory is per-task, not per-session.** If a user hands the agent a new task mid-session, the operational memory should be reset. Forgetting to reset produces "I was comparing SaaS pricing but now the user wants competitor analysis and I'm still tracking the old pricing data" corruption.
