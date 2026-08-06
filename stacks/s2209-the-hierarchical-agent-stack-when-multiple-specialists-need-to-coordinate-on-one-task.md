# S-2209 · The Hierarchical Agent Stack — When Multiple Specialists Need to Coordinate on One Task

A product research agent needs to crawl five competitor websites, synthesize findings, and draft a competitive analysis. Letting one agent do all of it means a mediocre generalist. Letting five agents do it independently means five siloed outputs. The right move: one supervisor decomposes, routes, and synthesizes — while specialist agents own their domains.

## Forces

- **More agents = more coordination overhead.** Multi-agent systems are harder to operate than single agents by roughly the order of their agent count. Adding a second agent doesn't halve your work — it adds state management, error propagation, and coordination logic.
- **Generalists are mediocre at everything.** Building a single capable agent that researches, writes, reviews, and publishes produces worse output than five agents that do one thing well. The technical challenge of building agents is largely solved; the unsolved challenge is management and coordination.
- **Fully autonomous systems ship low-quality work fast.** As one HN commenter put it: "Claude could already build a low quality version of our entire backlog in a week." The industry over-indexes on throughput at the expense of quality. Fewer, more deliberate agents often outperform swarms.
- **Predefined paths beat dynamic routing for predictable tasks.** Anthropic's engineering team found that the most successful implementations use simple, composable patterns — not complex frameworks. Workflows (predefined code paths) beat agents (dynamic LLM-directed processes) when task structure is known in advance.

## The Move

**The supervisor + specialists pattern:** A single coordinator agent decomposes incoming tasks, routes subtasks to domain-specific specialist agents, and synthesizes their outputs. Specialists are purpose-built for narrow scopes — not jack-of-all-trades prompts with long system instructions.

Key techniques that hold up in production:

- **Supervisor handles routing and synthesis only.** The coordinator never does the work itself — it decomposes, assigns, and merges. If a task can be done by one agent, use one agent.
- **Specialists are stateless and self-contained.** Each specialist receives only the context it needs for its subtask. No shared mutable state between agents — pass outputs through the supervisor.
- **Parallelize independent subtasks.** If five competitor analyses have no interdependencies, run them concurrently. The supervisor waits, then merges results. This is where multi-agent pays off — horizontal parallelism with vertical synthesis.
- **Use structured output or tool schemas over free-text delegation.** Pass task definitions as typed tool parameters, not LLM-generated natural language instructions between agents. Reduces hallucination in the coordination layer.
- **Human-in-the-loop gates on critical paths.** Route quality review through a human or a verified automated checker before outputs become irreversible (e.g., before a PR is opened or an email is sent).
- **Start with workflows, graduate to agents.** Anthropic's recommendation: if a task has predictable steps, encode them as a workflow. Only reach for dynamic agentic behavior when the path genuinely cannot be predefined. Each level of dynamism adds debugging cost.

## Evidence

- **Engineering Blog (Anthropic, Dec 2024):** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Their taxonomy — workflows (predefined code paths) vs. agents (LLM-directed dynamism) — maps supervisor+specialists as a hybrid: supervisors are agents that direct specialists through workflows. — [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **AI Infrastructure Blog (TURION.AI, Mar 2026):** "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count." Their production-proven pattern: supervisor agent decomposes tasks and routes to specialists, who return results for synthesis. Parallel execution for independent subtasks; sequential only where there are true dependencies. — [Multi-Agent Orchestration Infrastructure: Lessons from Production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Industry Engineering Post (Microsoft ISE, 2025):** Partnered with a large retail customer to migrate from a router-as-monolith (single agent per query) to a microservices model where domain agents are independent services that coordinators orchestrate together. Key insight: moving from one-agent-per-query to multi-agent-per-query required explicit state management and response synthesis — not just better routing. — [Orchestration Patterns for Multi-Agent Systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **HN Discussion (128 points, 32 comments, 2026):** "Few people seem to be focusing on building 'high quality' changes vs. maximising throughput of low quality work items." The top comment thread explores the "slipshod expert" problem — agents that produce plausible-sounding but wrong outputs — and the gap between agent capability demos and production reliability. — [Agent orchestration for the timid | HN](https://news.ycombinator.com/item?id=46746681)

## Gotchas

- **Don't add agents for their own sake.** The marginal agent adds coordination cost. Only split work when specialists genuinely outperform a generalist on their slice, or when parallel execution provides meaningful speedup.
- **State leaks between agents corrupt outputs.** If agent B inherits agent A's context as mutable state, failures compound. Treat inter-agent communication as immutable message passing, not shared memory.
- **Supervisor failures cascade silently.** A buggy supervisor doesn't just fail its own output — it misroutes work to the wrong specialist, synthesizes incomplete results, or loops indefinitely. Add supervisor-level observability, not just specialist-level.
- **Quality review is not optional.** Without a human or automated checker on the critical path, agents will ship plausible-sounding wrong outputs. The "slipshod expert" failure mode is the most dangerous in production — it passes initial review until it doesn't.
