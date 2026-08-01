# S-1944 · The Orchestration Premature Optimization Stack

*When your two-agent supervisor pattern breaks under load that a single agent with better tools would have handled cleanly.*

You have a research task. Your first instinct is to spin up a supervisor agent, three worker agents, a fan-out layer, and a results aggregator. Three days later you have a working demo. Six weeks later you have a system you cannot debug, cannot cost-control, and cannot explain to a new engineer in under an hour. Meanwhile, the team across the hall shipped the same capability with one agent, four tools, and a JSON output schema — in two days.

## Forces

- **Framework enthusiasm vs. production humility** — CrewAI gets you to a demo in an afternoon; LangGraph gets you a graph you can resume after a deploy on Thursday. But both are premature if your problem fits in a single agent's context window.
- **Orchestration complexity scales faster than the problem** — Every agent you add is a new communication channel, a new failure mode, a new observability gap, and a new token cost.
- **The "more agents = smarter system" illusion** — Specialized agents do outperform generalists on domain-specific tasks. But you can often get the same specialization with better tool scoping and prompt design on a single agent, without the coordination overhead.
- **Multi-agent pays off only past a threshold** — Anthropic, HN practitioners, and framework comparisons all converge on the same trigger: you need orchestration when your workflow has genuine branching, parallelism, or requires multi-turn state that outlasts a single context window.
- **The real bottleneck is often tool design, not architecture** — A poorly scoped tool that returns 10,000 tokens of irrelevant output is worse than 10 well-scoped tools with narrow schemas. Teams reach for more agents when they should be redesigning their tool interfaces.

## The Move

**Only reach for multi-agent orchestration when simpler patterns genuinely cannot.** The decision tree:

1. **Start with a single agent + 3–5 well-scoped tools + structured output.** If it works, ship it.
2. **Move to parallel tool aggregation** (one agent calling multiple tools simultaneously, results merged) when you have independent data sources.
3. **Move to sequential chaining** (Agent A → Agent B → Agent C) when output of one genuinely gates the next.
4. **Move to supervisor/worker** when a planner needs to dynamically decompose tasks and delegate.
5. **Only then consider fan-out/fan-in or hierarchical patterns** for 10+ agent deployments.

**When you do orchestrate, own the state machine explicitly:**
- LangGraph earns its keep for complex branching with state persistence and checkpointing — not for simple linear flows
- CrewAI earns its keep for rapid prototyping of role-based pipelines — but plan for the rewrite when requirements harden
- Custom solutions (MongoDB + JSON, Node.js isolates, AGNO) outperform frameworks at the upper end of complexity where debugging and control matter more than speed-to-demo

**Design your agent communication protocol from the start:**
- Pass structured JSON documents between agents, not raw text
- Include pipeline ID and task metadata for traceability
- Treat inter-agent communication as you would treat a service-to-service API contract

**Gate orchestration complexity with a simple test:**
- If your agent's next-step reasoning varies based on output classification → you need branching (LangGraph-style graph)
- If your independent subtasks can all run in parallel → fan-out pattern
- If you need a human to approve at a checkpoint → human-in-the-loop state machine
- If none of the above are true → one agent with better tools

## Evidence

- **Anthropic Engineering Blog:** After working with dozens of teams building LLM agents across industries, the most successful implementations used "simple, composable patterns rather than complex frameworks." Explicitly recommends starting with prompts + tool use, then adding multi-step orchestration only when evaluation shows the simpler approach failing. Defines workflows as "predefined code paths" vs. agents as "dynamically directing their own processes" — recommends workflows first. — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)

- **HN Ask Thread (47660705):** Real production practitioners discussing orchestration in the wild. Multiple engineers report rolling custom solutions ("Absolute 0 framework out there that's good enough for serious work"), using LangGraph as a base to build on, or AGNO for minimalistic isolation + control plane. Key pain points surfaced: agent-to-agent data passing (MongoDB + JSON, shared document stores), state management, and observability. One team uses Express endpoints in V8 isolates for agent isolation. — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)

- **Agent Nexus framework comparison:** LangGraph (~10K monthly PyPI downloads) and CrewAI (~47K GitHub stars, $18M Series A) represent two dominant paradigms in 2025. LangGraph: graph-based state machine, explicit topology, checkpointing. CrewAI: role-based teams, fast to prototype. Key finding: orchestration framework choice matters far less than task-architecture alignment — picking the wrong paradigm for your problem class is the real cost, not which framework you use within that paradigm. — [https://agent.nexus/blog/langgraph-vs-crewai](https://agent.nexus/blog/langgraph-vs-crewai)

## Gotchas

- **You will reach for orchestration too early.** The framework tutorials demo multi-agent setups because they look impressive. The 80% case is a single agent with better tools.
- **Token cost compounds non-linearly.** A supervisor agent that routes to three workers, each calling a tool and reporting back, has already consumed 4× the context and 4× the inference cost of a single agent doing the same work in one pass.
- **Debugging N agents is N times harder than debugging 1.** When a workflow fails, you need to trace through which agent made which decision and why. Without explicit state machine semantics (LangGraph-style), this is archaeology.
- **Framework upgrades break production graphs.** LangGraph and CrewAI have both had breaking API changes in 2024–2025. If your entire system is a framework graph, you inherit that upgrade risk. Custom solutions have their own maintenance cost, but it is a known cost you control.
- **Agent role definitions drift under load.** In CrewAI-style role-based systems, agents interpret their role differently as context grows. Define tools as contracts, not prompts as specifications.
