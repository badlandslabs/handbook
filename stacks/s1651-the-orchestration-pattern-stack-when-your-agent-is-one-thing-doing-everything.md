# S-1651 · The Orchestration Pattern Stack — When Your Agent Is One Thing Doing Everything

You built one agent to handle your entire workflow. It works — until it doesn't, and then it doesn't in ways that are hard to predict, hard to debug, and hard to fix without rewriting it from scratch.

## Forces

- **Autonomy vs. predictability** — agents are more capable when they decide their own path, but less predictable. Workflows are the opposite.
- **Coordination overhead vs. capability ceiling** — multi-agent systems unlock new capabilities but 37% of multi-agent failures trace to inter-agent coordination, not individual agent limitations (Swarm Signal, 2026).
- **The 80% rule** — LangChain's 2025 production data: 73% of production systems use chains, only 12% use full agents. Most teams over-engineer with agents when a chain would do.
- **The pattern-to-problem match** — Anthropic's research shows the same pattern that solves one class of problem creates new failure modes in another. Patterns are composable *and* cumulative: each layer adds failure modes the previous one didn't have.
- **Context is finite and expensive** — single-agent context windows fill up, dilute attention, and increase latency. The solution isn't a bigger context; it's multiple specialized agents with managed information flow.

## The Move

**Match the orchestration pattern to the minimum autonomy the task actually requires. Add pattern complexity only when the simpler version genuinely fails.**

The five production patterns, from least to most autonomy:

1. **Prompt chaining** — linear sequence, each LLM call's output feeds the next. No branching, no decisions. For pipelines where the steps are known and fixed: summarize → extract → format. Dead simple to debug — follow the thread.
2. **Routing** — a classifier (often a smaller/cheaper model) dispatches the input to the right handler. Anthropic routes easy questions to Haiku and hard ones to Sonnet. For systems with distinct task types that need different handling.
3. **Parallelization** — multiple agents or LLM calls work simultaneously, outputs merged at the end. Two variants: *sectioning* (independent subtasks, like parallel web searches) and *voting* (same task multiple times for diversity/confidence). Anthropic found large gains from carefully bounded parallelization using the same agents with different orchestration.
4. **Evaluator-optimizer** — one LLM generates, another evaluates, the first revises, repeat until the evaluator passes. Best for writing, code, and tasks where there's an objective quality signal.
5. **Orchestrator-worker** — a central LLM analyzes input, dynamically decides what subtasks are needed, delegates to workers, synthesizes results. No predetermined plan. For complex, multi-step tasks where the required steps can't be hardcoded.

Anthropic's Research system (June 2025) is a live orchestrator-worker: a lead agent analyzes queries, spawns specialized subagents for different search strategies, workers run in parallel, lead synthesizes and compresses findings before passing to the user.

## Evidence

- **Anthropic engineering blog:** Five composable patterns — prompt chaining, routing, parallelization, evaluator-optimizer, orchestrator-worker — listed from least to most autonomy, with guidance on when each earns its overhead. Their Research system uses orchestrator-worker in production. — https://www.anthropic.com/engineering/building-effective-agents

- **Anthropic multi-agent research system (June 2025):** Lead agent creates specialized subagents that explore different aspects simultaneously. Key benefits: separate context windows (information exceeds single context), parallel exploration, compression at each handoff. Weaknesses honestly noted: coding tasks have fewer parallelizable subtasks than research; LLM agents aren't yet great at real-time coordination. — https://www.anthropic.com/engineering/multi-agent-research-system

- **Coinbase production case study:** Tiger team shipped two production agents in six weeks using LangChain/LangGraph. Key architectural insight: shared observability (LangSmith) and evaluation standards were prerequisites for production, not afterthoughts. The orchestrator-worker pattern allowed different teams' agents to coordinate without a monolithic single-agent design. — https://focused.io/case-studies/bringing-agents-into-production-at-coinbase

- **Swarm Signal field guide (Feb 2026):** 37% of multi-agent failures trace to inter-agent coordination, not individual agent limitations. Six patterns catalogued with known failure modes and quantitative thresholds for when each pattern's coordination overhead is justified. Notes Anthropic's finding that parallelization with the *same* agents but different orchestration produces large gains. — https://swarmsignal.net/ai-agent-orchestration-patterns/

- **Claude Code worktree pattern (2025-2026):** Multiple Claude Code instances run in parallel using git worktrees for isolation. Three orchestration shapes: manager/worker, fan-out/gather, and pipeline. Each worktree gets its own branch so two agents editing files never overwrite each other. — https://neurals.ca/tech/claude/parallel-agents

- **Agentika production retrospective (Feb 2026):** "Start with the simplest orchestration that could work. Most teams over-engineer with agents when a chain would do." — Harrison Chase, LangChain CEO, cited in their analysis. LangChain 2025 usage data: 73% chains, 12% full agents in production. — https://agentika.uk/blog/llm-orchestration-patterns.html

- **heyuan110 orchestration breakdown (Feb 2026):** Detailed breakdown of orchestrator-worker pattern with Claude Code worktree as production example. Notes the three real bottlenecks that force multi-agent: memory bloat (latency climbs with context), context pollution (irrelevant history dilutes attention), and task complexity exceeding single-agent capability. — https://www.heyuan110.com/posts/ai/2026-02-26-multi-agent-orchestration

## Gotchas

- **Chains fail on open-ended tasks.** A chain assumes you know all the steps. When the task requires dynamic pivoting (following emergent leads, adapting to discoveries), a chain's rigidity becomes a liability. Use orchestrator-worker instead.
- **Orchestrator-worker is the most powerful and most fragile.** The orchestrator is a single point of failure. A buggy orchestrator plan produces worse output than no orchestration at all. It also has the highest token cost — orchestrator plus all workers.
- **Parallelization ceiling on coding tasks.** Anthropic explicitly notes: coding tasks involve fewer truly parallelizable subtasks than research. Running 10 agents in parallel on a task that only has 2 parallelizable steps wastes 8 agents' worth of compute. Measure actual speedup, not just agent count.
- **Multi-agent adds coordination failure modes.** Before going multi-agent, ask: could this be solved by adding tools to a single agent? Multi-agent earns its overhead when the agents have genuinely different tool sets, context windows, or specialties — not just different prompts.
- **The graph becomes unmaintainable.** LangGraph makes orchestration explicit as a state machine, which helps — but production teams consistently report the graph growing beyond comprehension. Start with LangChain's higher-level abstractions; drop to LangGraph only when you need cycles, branching, or crash-safe resume.
