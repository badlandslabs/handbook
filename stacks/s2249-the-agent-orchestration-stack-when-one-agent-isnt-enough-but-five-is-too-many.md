# S-2249 · The Agent Orchestration Stack — When One Agent Isn't Enough But Five Is Too Many

When a single agent hits the ceiling of what it can reasonably do in one context window, but you're not sure whether to chain, route, parallelize, or just split into specialists.

## Forces

- A monolithic agent with one massive system prompt and fifteen tools becomes unreliable at tool selection — the more tools, the more the agent second-guesses itself
- Adding more agents compounds coordination overhead faster than it adds capability — two agents are 2× the work, five agents are 10×
- Workflows (predefined code paths) are predictable and cheap but rigid; Agents (dynamic self-direction) are flexible and powerful but expensive and opaque
- Every framework (LangGraph, CrewAI, custom) makes a different tradeoff between expressibility and control — none is universally right
- The "multi-agent" label hides two fundamentally different things: splitting a task across time (pipeline) vs. splitting it across capability (specialists)

## The Move

The core insight from production deployments: most successful multi-agent systems are simpler than they look. Start with the minimum viable structure.

**The canonical production pattern: Supervisor + Specialists.**
One agent decomposes the incoming task, routes subtasks to one or more specialist agents, and synthesizes their outputs. Think of it as a router with a brain, not a committee. LangGraph's supervisor node, CrewAI's hierarchical mode, and most "multi-agent" systems in production are this pattern underneath.

**Tool use as the atomic unit, not agents.** Anthropic's November 2025 advanced tool use release shows that 58 MCP tools can consume ~55K tokens before the conversation starts. The move is to let the agent discover tools on-demand rather than loading all definitions upfront. Tool Search Tool reduced token overhead by 85% in their benchmarks; Programmatic Tool Calling cut tokens by 37% and reduced inference passes.

**Treat inter-agent communication like API contracts.** Define what each agent expects as input and produces as output with schemas (Pydantic models, JSON Schema). Schema violations caught at the boundary — not three agents downstream. One HN practitioner uses Express endpoints in V8 isolates for each agent, with a coordinator endpoint for chaining.

**Choose orchestration based on the problem shape:**

| Problem | Pattern | Why |
|---------|---------|-----|
| Fixed sequence (A→B→C) | Pipeline | Predictable cost, easy to eval each step |
| Task needs routing logic | Supervisor + Specialists | Single decision-maker keeps it coherent |
| Many independent sub-tasks | Fan-out / Fan-in | Parallelism pays off when subs are slow |
| Asynchronous, multi-day | Asynchronous handoff | State must survive session boundaries |

**Long-running agents need a harness.** Anthropic (Nov 2025) documents two failure patterns: one-shotting (agent attempts too much at once, exhausts context mid-task) and premature completion (later agent sees partial progress and declares done). The fix is structured task decomposition with explicit checkpoints — not prompting the agent to "remember everything."

**Harness principle: keep decision logic in the harness, procedural knowledge in skills.** Validate each step before chaining to the next. A harness that validates intermediate outputs catches failures early; one that passes them through silently lets errors compound.

## Evidence

- **Anthropic Engineering (Dec 2024):** After working with dozens of teams building agents, "consistently the most successful implementations use simple, composable patterns rather than complex frameworks." Recommends defaulting to workflows and only moving to agents when the task genuinely requires dynamic self-direction. — [URL](https://www.anthropic.com/engineering/building-effective-agents)

- **Anthropic Engineering (Nov 2025):** Advanced tool use beta — MCP servers with 58 tools consumed ~55K tokens. Tool Search Tool reduced token overhead by 85%, Programmatic Tool Calling by 37%, and Tool Use Examples improved accuracy from 72% to 90%. — [URL](https://www.anthropic.com/engineering/advanced-tool-use)

- **TURION.AI Field Note (March 2026):** "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count." Field notes from production deployments: Supervisor + Specialists is the most common pattern that actually ships; most multi-agent frameworks don't survive contact with real async workflows. — [URL](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production/)

- **Hacker News Ask (Jan 2026):** "How are you orchestrating multi-agent AI workflows in production?" — practitioners report rolling their own rather than using existing frameworks ("absolute 0 framework out there that's good enough for serious work"), with agents running as parallel workers in separate git worktrees. — [URL](https://news.ycombinator.com/item?id=47660705)

- **GitHub aden-hq/hive (OpenHive):** Multi-agent harness with role-based memory, graph-based DAG execution, and self-healing capabilities. 10,876 stars. Emerged from construction ERP automation (PO/invoice reconciliation) — a real async, multi-day business process. — [URL](https://github.com/adenhq/hive)

## Gotchas

- **"We'll add more agents later"** — don't. Agents added post-hoc without clear handoff contracts create debugging nightmares. Design the boundary contracts first.
- **Confusing pipeline (splitting work over time) with parallel (splitting work over capability)** — they need different infrastructure. Pipeline needs checkpointing; parallel needs fan-out/fan-in coordination.
- **Loading all tools at startup** — token costs and latency spike. Load tools on-demand or use tool discovery patterns.
- **Multi-agent frameworks in demos vs. production** — frameworks that look elegant in demos (e.g., fully autonomous agent networks) often fail in production because they assume synchronous sessions. Real async business processes need state that survives session boundaries.
- **Premature specialization** — giving an agent a narrow role ("you are the SQL writer") works until the task needs cross-domain reasoning. Roles should be coarse-grained enough to handle edge cases within their domain.
