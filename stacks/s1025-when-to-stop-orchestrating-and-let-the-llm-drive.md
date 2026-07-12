# S-1025 · When to Stop Orchestrating and Let the LLM Drive

*You reach for a framework like LangGraph or CrewAI before you've confirmed the LLM actually needs to decide its own path. Teams add orchestration overhead before they have an orchestration problem.*

## Forces

- **The demo temptation** — frameworks like CrewAI get you a working demo in an afternoon, which creates organizational pressure to standardize on them before the production costs are known.
- **Autonomy vs. control** — more LLM autonomy means less predictable output, but more orchestration means more latency, cost, and maintenance surface.
- **The 80/20 trap** — LangChain's 2025 production survey found simple chains handle 80% of production use cases, yet teams consistently over-engineer their first implementations. Most tasks don't need a state machine.
- **The graph complexity cliff** — once you add branching, approvals, and resume capability to a LangGraph, the graph becomes its own maintenance burden. The cure can outweigh the disease.

## The move

**Match autonomy level to task predictability.** The right question is not "chains vs. agents" — it is "how much autonomy does the LLM need for this specific task?"

- **Zero autonomy (simple chain):** Fixed sequence of LLM calls. Use when steps are known and order never varies. Latency and cost are minimal. Best for summarization, translation, structured extraction.
- **Some autonomy (router pattern):** LLM classifies input type, then dispatches to a fixed handler. Use when task type varies but handling is deterministic. Keeps control in the routing layer.
- **Full autonomy (agent loop):** LLM decides next action, picks tools, loops until done. Use when the problem path is genuinely unknown at design time. Cost and latency scale with task complexity.
- **Specialist teams (supervisor/swarm):** Multiple agents with defined roles coordinate. Use when sub-problems are independent enough to parallelize but require synthesis. The "generalist LLM" anti-pattern lives here.
- **State machine (LangGraph):** Explicit graph of states with conditional edges. Use when you need crash-safe resume, human approval gates, or audit trails. If you don't need those, you're paying for complexity you won't use.

The heuristic from r/LocalLLaMA production users: if a task can be expressed as 3–5 tool calls in a fixed order, a single agent with scoped tools beats a multi-node graph every time. The overhead of routing, serialization, and context-passing between agents usually costs more than it saves.

The pragmatic test: **start with a simple chain, add orchestration only when the LLM's output forces you to.**

## Evidence

- **HN discussion (Anthropic article + comments):** The building-effective-agents thread (543 points, June 2025) crystallized the industry consensus: "Start with the simplest solution. Often, optimizing single LLM calls with retrieval and in-context examples is sufficient." HN commenter Zaylan: "A few clearly defined LLM calls with some light glue logic usually lead to something more stable, easier to debug, and much cheaper to run." — [news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)
- **Agentika production data:** Found that 73% of production systems use chains; only 12% use full agents. The majority of teams that reached for full agents reported regretting it once they hit debugging and cost. — [agentika.uk/blog/llm-orchestration-patterns](https://agentika.uk/blog/llm-orchestration-patterns)
- **Reddit r/LocalLLaMA:** A production developer wrestling with multi-step tool chains (scrape → extract → transform → save) reported: "Starting to wonder if the whole 'let the LLM orchestrate everything' model is wrong for this type of task. Like maybe the agent should decide what to do but hand off the actual execution to something more deterministic?" — [reddit.com/r/LocalLLaMA/comments/1qh8xj6](https://www.reddit.com/r/LocalLLaMA/comments/1qh8xj6/those_of_you_running_agents_in_productionhow_do/)

## Gotchas

- **Framework lock-in before you understand the problem.** CrewAI's role-based team model feels natural in a demo, but forces you into its abstractions when you need custom control flow. The migration cost from CrewAI to LangGraph mid-production is non-trivial.
- **Token bloat from intermediate reasoning.** Every LLM handoff in an orchestrated system adds reasoning tokens. A task that should cost 500 tokens can balloon to 3–4k when the LLM "thinks" between each step. This compounds with agent count.
- **The supervisor becomes a bottleneck.** In supervisor + specialist patterns, the supervisor agent often becomes the throughput ceiling. If it has to approve, review, or synthesize every output, you've created a single point of failure in your parallelism.
