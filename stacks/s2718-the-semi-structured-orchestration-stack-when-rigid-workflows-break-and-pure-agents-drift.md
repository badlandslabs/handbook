# S-2718 · The Semi-Structured Orchestration Stack — When Rigid Workflows Break and Pure Agents Drift

You built a pipeline of LLM calls. It worked until the user asked an unexpected question. Now you've bolted on conditional branches, which made the logic brittle. So you switched to a fully autonomous agent — and it loops, drifts off-topic, and duplicates work. The real pattern that production teams are converging on sits between those extremes: define phase boundaries, let agents self-organize within them.

## Forces

- **Rigid pipelines break when reality diverges.** Predefined step sequences require anticipating every scenario. Real-world tasks surface unexpected sub-tasks, pivots, and discoveries. A pipeline that can't self-modify fails at the first surprise.
- **Fully autonomous agents drift.** Agents given broad goals wander, duplicate work, and lose coherence across long conversations. The "General Computation Unit" problem — agents that can do anything but specialize at nothing — produces unreliable production behavior.
- **The restart tax punishes long-running agents.** A 15-minute agent that crashes at 99% wastes $4.50 in compute. Without durable execution, retry loops compound cost and latency unpredictably.
- **Framework adoption is now the norm, not the exception.** By 2025, 68% of new agent projects used an orchestration framework rather than raw SDK calls. The question is no longer "build or buy" but "which topology for which problem."
- **Teams mix frameworks, not pick one.** The dominant pattern: LlamaIndex for retrieval pipelines + LangGraph/AutoGen for orchestration. Using one framework for everything is the exception, not the rule.

## The move

The semi-structured orchestration pattern defines phase types (analysis, building, validation, execution) as fixed structural boundaries, then lets agents spawn tasks, create sub-tasks, and route work dynamically within those boundaries.

**Core implementation:**

- **Phase-boundary scaffolding, not step-by-step scripts.** Define what *kinds* of work exist (e.g., planning, execution, review) rather than what sequence they run in. Agents decide the trajectory within that scaffold.
- **LLM-powered trajectory monitoring.** Rather than just checking "is the agent stuck?", analyze whether the accumulated trajectory is aligned with phase goals. Coherence scoring — evaluating whether agent actions collectively make sense — catches drift before it compounds.
- **Durable execution underneath.** Use Temporal or equivalent to guarantee workflow completion despite crashes. Separate deterministic orchestration code (replayable) from non-deterministic activity code (LLM calls, API calls). This eliminates the restart tax for long-running agents.
- **Supervisor + specialist topology.** A central coordinator (supervisor) dispatches tasks to specialized sub-agents. Each sub-agent has a narrow toolset and role. The supervisor handles routing; specialists handle execution. When specialists find unexpected sub-problems, they spawn tasks back through the supervisor.
- **Parallel sub-agent execution with compression.** Run independent sub-agents in parallel (map-reduce over documents, sources, or tasks), then compress their outputs into a unified context for the next phase. Anthropic's research system uses this: a lead planner spawns parallel searchers, compresses findings, then feeds a coherent synthesis.
- **Human-in-the-loop checkpoints.** For high-stakes phases (billing, approvals, external API mutations), insert explicit human checkpoints or structured confirmation gates. Not every phase needs this — low-stakes analysis can run autonomously.
- **Evaluator agent as separate role.** A dedicated critic or evaluator agent runs in parallel with or after the primary agent. It checks outputs against criteria, not just the agent's own self-assessment.

## Evidence

- **Hephaestus framework (HN Show HN, 107 points):** "Semi-Structured Agentic Framework" where agents define phase types (analysis, building, validation) and spawn tasks across any phase based on discovered sub-problems. When testing finds bugs, it spawns fix tasks; when validation spots optimizations, it spawns investigations. The Kanban board is built dynamically by the agents themselves — Backlog → Building → Testing → Done, with blocking relationships discovered at runtime. — [https://github.com/Ido-Levi/Hephaestus](https://github.com/Ido-Levi/Hephaestus), [https://ido-levi.github.io/Hephaestus/](https://ido-levi.github.io/Hephaestus/)

- **Anthropic multi-agent research system (Jun 2025):** Built a lead planner agent + parallel sub-agents architecture. Key lessons: (1) explicit phase boundaries prevent context pollution between unrelated sub-tasks, (2) compression between phases prevents context window overflow from parallel outputs, (3) evaluator agents catch failures that the primary agent's self-assessment misses. The journey from prototype to production surfaced that tool design and prompt engineering matter more than orchestration topology. — [https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Temporal ambient agents blog (Sep 2025):** Production crypto trading platform with three agents — Broker (user-facing coordinator), Execution (trading decisions), Judge (continuous performance evaluation that updates the Execution agent's system prompt). Built on Temporal for durable execution: workflows survive crashes, retries are deterministic, and state is reconstructed from event history rather than re-computed. Netflix runs 100K+ workflows/day on Temporal; Datadog runs millions/month. — [https://temporal.io/blog/orchestrating-ambient-agents-with-temporal](https://temporal.io/blog/orchestrating-ambient-agents-with-temporal)

- **Fordel Studios framework analysis (Apr 2026):** Surveying the 2026 landscape: LangGraph owns stateful workflow control, CrewAI owns accessible multi-agent team patterns, AutoGen owns conversational orchestration. 68% of new agent projects in 2025 used a framework. The dominant hybrid: LlamaIndex (retrieval layer) + LangGraph or AutoGen (orchestration). — [https://fordelstudios.com/research/state-of-ai-agent-frameworks-2026](https://fordelstudios.com/research/state-of-ai-agent-frameworks-2026)

- **Anthropic Applied AI enterprise lessons (2024-2025):** Teams that deploy agents successfully transition from optimizing individual prompts to systems engineering. The evolution: simple Q&A chatbots → RAG systems → chained LLM workflows → agentic architectures with tool loops. Enterprise customers in finance, healthcare, and legal require human-in-the-loop checkpoints and structured output validation. — [https://www.zenml.io/llmops-database/building-production-ai-agents-lessons-from-claude-code-and-enterprise-deployments](https://www.zenml.io/llmops-database/building-production-ai-agents-lessons-from-claude-code-and-enterprise-deployments)

- **Hive framework (HN Show HN, 107 points):** Built specifically to solve the "Toy App Ceiling" — agents that work in demos but fail in real business automation. Identified the "GCU Trap": General Computation Unit agents that can do anything specialize at nothing. Solution: goal-driven decomposition where agents generate their own task topology at runtime. — [https://github.com/adenhq/hive](https://github.com/adenhq/hive), [https://news.ycombinator.com/item?id=46979781](https://news.ycombinator.com/item?id=46979781)

## Gotchas

- **Semi-structured is not "let it run and see."** Phase boundaries must be enforced — not just suggested. Without explicit phase transitions, agents treat "flexibility" as license to ignore structure entirely.
- **Trajectory coherence checking is expensive.** Running an LLM to evaluate whether another LLM's trajectory is coherent doubles token cost per step. Budget for it or accept periodic drift as a cost of flexibility.
- **Framework mixing adds integration surface area.** LlamaIndex + LangGraph + Temporal + MCP servers means four integration points, each with its own failure modes. The "use the right tool" philosophy becomes "manage four tools."
- **Parallel sub-agents explode context windows.** Running 8 search agents in parallel and feeding all their outputs to the next phase requires explicit compression. Without it, you hit context limits and the parallelism advantage disappears.
- **Human-in-the-loop checkpoints are often placed in the wrong phases.** Teams put checkpoints on low-stakes analysis and skip them on high-stakes actions (API mutations, billing, external sends). Reverse this — automate analysis, gate actions.
