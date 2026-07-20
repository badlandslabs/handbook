# S-1424 · The Agent Planning and Reasoning Stack — When Your Agent Gets Lost in a Long Task

When a simple task balloons to fifteen steps, your agent either burns through tokens chasing dead ends or silently produces wrong output. The failure isn't the model — it's the planning architecture.

## Forces

- **ReAct degrades with depth** — its tight think-act-observe loop is simple to implement but memory degrades around step 7–9 on complex tasks, per practitioner reports
- **Upfront planning costs more upfront** but saves on total LLM calls for long tasks — models in 2025–2026 can follow a plan from text alone without constant reminder
- **Exploration vs. exploitation** — agents need to try multiple reasoning paths on hard problems, but exploring everything is economically unviable at scale
- **Observability is orthogonal to planning** — you can't fix what you can't see; reasoning traces need to be structured and readable, not buried in token soup

## The Move

Match the planning pattern to task complexity. Three tiers dominate in production (2025–2026):

1. **Simple tasks (1–5 steps): ReAct** — tight loop interleaving Thought → Action → Observation. Zero upfront planning cost. Easy to implement, easy to debug. The dominant pattern in deployed LangChain/LangGraph agents through 2025. Hits a ceiling at medium complexity.

2. **Complex tasks (5+ steps): Plan-and-Execute** — separate Planner decomposes the goal upfront, Executor runs each step. Mirrors project management. Enables replanning on failure without context fragmentation. Production deployments report 40–60% lower total cost vs. ReAct on equivalent long tasks due to fewer wasted loops. Planners can use smaller/faster models than executors in some stacks.

3. **Hard multi-branch problems: LATS (Language Agent Tree Search)** — adapts Monte Carlo Tree Search from game-playing AI. LLM serves as agent, value function, and self-reflector simultaneously. UCT formula balances exploring alternative reasoning paths against exploiting known good ones. Backpropagation updates value estimates as exploration reveals new information — unlike ToT (which can't revise value estimates) or Reflexion (which retries whole trajectories instead of local backtracking). Production use remains niche due to computational overhead; strongest fit for domains with verifiable intermediate states (math proofs, code debugging, puzzle solving).

**Graduated approach** (from HN practitioner ruxudev): scale up planning complexity as tasks demand — simple instruction → plan-then-execute → plan written to file with subagent review → supervisor mode with handoff rollovers.

**Anti-pattern: building on frameworks.** The HN anti-framework consensus (June 2025, 543 points) is strong: most agent frameworks add abstraction layers that obscure prompts and responses. Most "production" AI agents that work are "mostly just well-engineered software with LLMs sprinkled in at key points" (humanlayer/12-factor-agents, 24k stars). Simple composable patterns outperform framework complexity for most teams.

## Evidence

- **HN Thread (543 pts, 2025):** Anthropic's "Building Effective Agents" post generates broad agreement that simple patterns (workflows with pre-defined paths) beat complex agent frameworks for most use cases. Commenter iLoveOncall: "It's insane that people use whole frameworks to send what is essentially an array of strings to an LLM." — https://news.ycombinator.com/item?id=44301809

- **HN Thread (142 pts, 2025):** Practitioner athrowaway3z describes graduating through planning complexity levels: "A year ago the models needed to be reminded. Today they can follow a plan from text alone." Documents diminishing returns from persistent plan files, todo lists, and sqlite tracking as models improved. — https://news.ycombinator.com/item?id=48461635

- **Blog post / production analysis (2026):** Laxaar engineering quantifies the ReAct vs. Plan-Execute tradeoff: ReAct averages 40–60% lower cost on short tasks but degrades on complex ones; Plan-Execute's upfront planning cost pays off for tasks exceeding 5–6 steps through reduced wasted loops. AgentMarketCap (April 2026) reports Plan-Execute agents using GPT-4-class models average 3,000–4,500 tokens and 5–8 API calls per complex enterprise task. — https://laxaar.com/blog/agent-planning-react-vs-plan-and-execute-1749470001700

## Gotchas

- **ReAct's memory horizon is a production surprise.** The "short-term memory problem" — degradation around step 7–9 — doesn't show up in demos of 3–5 steps. Teams discover it when users hand the agent a real multi-day task.
- **Plan-and-Execute doubles your LLM surface.** A separate planner means two system prompts, two model choices, and twice the failure modes. Only worth it when the task genuinely requires decomposition.
- **LATS is computationally expensive.** The MCTS-based exploration generates multiple reasoning paths per decision point. Production deployments need careful cost controls or must be scoped to domains where the extra exploration pays for itself.
- **Reasoning traces need structured output.** Raw thought strings are unreadable at scale. The EngineersOfAI analysis of ReAct notes: "the model never 'knows' it called a tool — it just sees more text." Without structured instrumentation, agent failures are anecdotal rather than systematic.
- **Models improved faster than planning tooling.** Practitioner reports that 2024-era planning scaffolding (persistent plan files, todo-tracking databases, explicit reminder prompts) became unnecessary by 2025–2026 as frontier models followed natural-language plans from text alone. Building persistent planning machinery into your stack may be premature over-engineering.
