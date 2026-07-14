# S-1078 · The Multi-Agent Orchestration Stack — When One Agent Isn't Enough But Twenty Is Chaos

Your task is too complex for a single agent — it times out, loses track of sub-problems, and produces shallow results on everything instead of deep results on something. You add more agents. Now you have coordination overhead, duplicate work, context conflicts, and a 15x token bill with no clarity on whether it was worth it. The question isn't whether to use multiple agents. It's how to orchestrate them so the compounding cost actually pays off.

## Forces

- **Token compounding kills budgets.** Anthropic reports ~15x token cost for multi-agent vs. single-agent on the same task. On a 10-step pipeline, even 95% step reliability yields ~60% end-to-end success. Each agent you add multiplies both the capability ceiling and the cost floor.
- **Context window sharing is the bottleneck.** A single shared context forces agents to compete for tokens. The fix isn't bigger windows — it's partitioning so each agent operates in its own context while sharing only what matters.
- **Architecture determines whether more agents help or hurt.** Adding agents to a flat hierarchy (all talk to all) creates n² communication overhead. Adding them to a structured hierarchy (orchestrator + workers) scales linearly but requires explicit coordination logic.
- **Tool description quality is as important as tool design.** Anthropic found ~40% reduction in task completion time just from improving how tools are described to agents — not the tools themselves.
- **The pattern you choose constrains everything downstream.** A graph-based system (LangGraph) is deterministic and inspectable but requires upfront state schema design. A role-based system (CrewAI) is fluid and natural but harder to trace and reproduce.

## The Move

Split work across a **lead orchestrator + specialized sub-agents** pattern. The lead decomposes the problem, delegates to agents with isolated context windows, and synthesizes results. Key rules:

- **One lead, N workers.** The lead handles planning and synthesis. Workers handle domain-specific execution in parallel. Don't let workers talk to each other directly — route everything through the lead.
- **Isolate context per agent.** Each sub-agent operates in its own context window. Only the lead sees the full state. This is what enables the >90% performance improvement Anthropic measured — independent reasoning without context dilution.
- **Persist critical context explicitly.** Don't rely on the model's context window to hold shared state. Use a structured state object (typed schema in LangGraph, shared store in CrewAI) that the lead writes and workers read.
- **Use effort-to-complexity heuristics in the prompt.** Tell the lead agent to scale reasoning effort to task difficulty — don't use maximum effort on simple tasks.
- **Design for interleaved planning.** Let the lead re-plan mid-execution as results come back. Static pipelines break when the first agent returns something unexpected.
- **Write tool descriptions like user documentation**, not API specs. Anthropic found ~40% task completion improvement from this alone.

## Evidence

- **Engineering blog:** Anthropic's multi-agent research system (Claude.ai Research feature, launched April 2025) uses Opus 4 as lead agent + Sonnet 4 as supporting sub-agents in parallel. Internal evals showed >90% performance improvement over single-agent. ~15x token cost vs. standard chat. ~90% reduction in research time. ~40% task completion improvement from tool description optimization alone. — [Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Show HN / GitHub:** PRISM-INSIGHT — 13 specialized AI agents across 4 teams (Macro, Analysis, Report, Trading) collaborating on Korean/US stock analysis. Live since March 2025. ~450 users. Lead analysis agent coordinates specialized agents for technical analysis, trading flows, financials, news, market conditions. Architecture: each team has a manager that delegates to specialists, results synthesize up. — [GitHub dragon1086/prism-insight](https://github.com/dragon1086/prism-insight)
- **Engineering blog / comparative analysis:** LangGraph (~10.2K stars) uses directed graphs with typed state schema — deterministic, inspectable, composable sub-graphs. CrewAI (~47K stars) uses role-based crews with event-driven Flows — more natural for natural-language task descriptions, harder to trace. Both require engineering teams to own the full production stack; neither provides enterprise governance out of the box. — [Nexus agent.nexus](https://agent.nexus/blog/langgraph-vs-crewai)
- **HN discussion:** A developer using LangGraph for an AI ecommerce analyst with BullMQ queuing reported: "keep the graph small, the prompts concise, the nodes and tools atomic in function." The key lesson: don't add agents to avoid complexity — add structure to reduce it. — [Hacker News](https://news.ycombinator.com/item?id=44909029)

## Gotchas

- **Adding agents to a poorly decomposed problem makes it worse.** A team of agents all working on the wrong framing will produce a confident, coherent wrong answer faster. Invest in the lead agent's task decomposition before adding workers.
- **Parallelism is only valuable when tasks are actually independent.** If two agents keep waiting on each other's output, you've paid the token cost of two agents for the speed of one.
- **Token budgets compound invisibly.** Track cost per task class, not just accuracy. A 15x token multiplier is acceptable for complex research but catastrophic for high-frequency simple tasks.
- **Role-based framing (CrewAI) is easier to explain; graph-based (LangGraph) is easier to debug.** For prototypes where you need to iterate fast, CrewAI's natural-language role definitions accelerate initial development. For production systems where you need to trace failures, LangGraph's explicit state transitions win.
