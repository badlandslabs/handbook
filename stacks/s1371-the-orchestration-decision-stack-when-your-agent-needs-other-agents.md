# S-1371 · The Orchestration Decision Stack — When Your Agent Needs Other Agents

The question isn't whether to use agents — it's whether a single agent, a workflow, or a multi-agent system solves your problem. Get this wrong and you either under-engineer (single agent burns out on a 65-company breadth-first query) or over-engineer (four agents in a pipeline for a task that needed two API calls). The orchestration decision is the first architectural call that compounds for everything downstream.

## Forces

- **Agents cost 15x tokens vs. a chat.** Anthropic's internal data: multi-agent research systems burn ~15x the tokens of a single chat interaction. Before adding orchestration, confirm the task value justifies the spend.
- **O(N²) communication is the silent killer.** When every agent can message every other agent, communication overhead scales quadratically. Confusion, lost context, and infinite loops follow. Hierarchy constrains this.
- **Frameworks add abstraction that hides debugging.** Anthropic's guidance: "These frameworks make it easy to get started... they often create extra layers of abstraction that can obscure the underlying prompts and responses, making them harder to debug." Start with LLM APIs directly.
- **Prompt engineering IS the architecture.** In Anthropic's multi-agent research system, early subagents made classic errors: spawning 50 subagents for simple queries, scouring endlessly for nonexistent sources, distracting each other with excessive updates. The fix was prompt engineering — each subagent's prompt defined objective, output format, tool guidance, and task boundaries.
- **Sequential isn't always right.** Research tasks are breadth-first by nature. Coding tasks often have deep dependencies. Forcing a sequential pipeline on a parallelizable problem wastes 80-90% of potential efficiency.

## The Move

Start at the simplest end of the spectrum. Move right only when evidence demands it.

**1. Single LLM call first.** Most tasks. HTTP request, response. If you need more, reach for a workflow before an agent.

**2. Prompt chaining for sequential refinement.** Chain multiple LLM calls where each step's output feeds the next. The code path is predetermined — you encode the logic. No agent loop, no dynamic routing. Use this for multi-step transforms: extract → classify → format → validate.

**3. Routing (supervisor pattern) when tasks diverge.** A supervisor agent — powered by an LLM — decides which worker handles the next task. Workers are specialized: a researcher, a writer, a critic. The supervisor routes and synthesizes, never workers talking to each other directly. This constrains communication to O(N) and keeps the supervisor as the single source of truth.

**4. Parallel fan-out for breadth-first tasks.** One agent decomposes a task (e.g., "research all 65 S&P 500 IT companies") into independent subtasks, spawns parallel subagents, collects results, synthesizes. Each subagent operates with its own context window — "search is compression." Use this when the subproblems are independent and the value of parallelization outweighs the ~15x token cost.

**5. Guard the handoffs.** Every agent boundary is a potential context loss. Define explicit output schemas for each agent. Anthropic's research team used a tool-testing agent to rewrite MCP tool descriptions — testing dozens of times to find the minimal description that prevented failures.

## Evidence

- **Anthropic Engineering Blog:** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Their multi-agent research system — lead orchestrator + parallel subagents — achieved 90.2% performance improvement over single-agent Claude Opus 4 on breadth-first research queries. Tokens were the primary lever: "Token spend alone explains 80% of performance variance." — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents) and [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **AccelateAI/multi-agent-orchestration (GitHub):** Production-grade Python patterns library implementing supervisor routing, sequential pipelines, and parallel fan-out with SQLite/Redis state persistence and explicit retry/error recovery. Design rationale: "Putting retry logic in the execution boundary means every agent gets it automatically with no boilerplate." — [github.com/AccelateAI/multi-agent-orchestration](https://github.com/AccelateAI/multi-agent-orchestration)
- **FromZero2AI Blog:** Detailed supervisor-worker architecture breakdown: "If every agent is allowed to talk to every other agent, communication overhead scales quadratically — leading to confusion, lost context, and infinite loops." The supervisor acts as project manager: receives tasks, assigns to specialized workers, monitors progress, synthesizes results. — [fromzero2ai.dev/blog/supervisor-worker-orchestration](https://www.fromzero2ai.dev/blog/supervisor-worker-orchestration)

## Gotchas

- **Reaching for multi-agent when prompt chaining suffices.** If your workflow is sequential and predetermined, a multi-agent system adds overhead with no benefit. The complexity cost is paid in debugging, token budget, and observability.
- **No defined termination condition.** Agents loop. Without explicit stop criteria — max iterations, output quality threshold, or human checkpoint — they'll continue until the context window fills. Set these before the first test run.
- **Context boundaries cause silent data loss at handoffs.** When one agent finishes and hands off to the next, the receiving agent has no inherited understanding. Anthropic solved this with explicit output schemas and structured handoff prompts. Don't assume context survives the boundary.
- **Subagent prompt drift over time.** In long-running multi-agent systems, subagents accumulate implicit assumptions. Anthropic's fix: a dedicated tool-testing agent that rewrites tool descriptions when failures occur. Build a feedback mechanism, not a one-time prompt.
- **Framework lock-in obscures cost.** LangGraph (33.4k GitHub stars, 34M monthly downloads), CrewAI, and AutoGen (58.5k stars but in maintenance mode as of 2026) all abstract token usage in ways that make cost prediction hard. If budget is a constraint, implement patterns with raw API calls first.
