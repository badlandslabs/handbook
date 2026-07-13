# S-1036 · The Orchestration Gap: When Your Agent Demo Shines and Your Production System Dies

The agent runs perfectly in your dev notebook. It calls tools, chains reasoning, returns great results. Then you ship it and within a week it is looping, burning tokens, missing errors, and costing 10x what you budgeted. The problem is not the LLM — it is the architecture around it. The gap between a working demo and a production-ready agent is where 95% of projects die.

## Forces

- **Frameworks add a comforting abstraction and a dangerous one.** LangChain, CrewAI, and AutoGen make it easy to chain calls and call tools. They also hide the prompts and responses that are the primary debugging surface, making it harder to understand why something broke. Production teams keep hitting this wall.
- **Workflows and agents are not the same thing — and conflating them costs you.** Anthropic draws a clear line: predefined code paths are workflows; dynamic LLM-directed tool usage is an agent. Most teams build a workflow and call it an agent, then are surprised when it cannot handle edge cases. The reverse (an agent where a simple prompt chain would suffice) burns latency and money for no gain.
- **Multi-turn state is not free.** Every production agent eventually needs to remember something from last week. Sessions that start from zero are the default, but real workflows demand episodic memory, working-memory scratchpads, and the ability to resume after infrastructure restarts. Building this in retroactively is painful.
- **Trajectory-level failures are invisible to end-to-end tests.** If an agent calls the wrong tool at step 3, steps 4–20 may still produce plausible output. The output is wrong, it does not look wrong, and a test that only checks the final answer misses it entirely.

## The move

**Start with the direct API. Reach for a framework only when you can name what it buys you.**

- **Prefer predefined orchestration paths for linear, predictable tasks.** If the agent's behavior can be scripted, script it. Only introduce dynamic tool-use loops when the task genuinely requires the LLM to decide what to do next. This is not a lack of ambition — it is the recommendation from Anthropic after reviewing dozens of production deployments.
- **Use LangGraph when you need cycles, branching, and state persistence.** LangGraph's directed-graph model natively handles the multi-agent workflows that break linear chains: a supervisor agent dispatching to specialists, a research pipeline that loops until it has enough citations, an approval flow that waits for a human. Its checkpointing system lets agents resume after restarts without replaying the full conversation.
- **Instrument trajectories, not just outputs.** Log the full sequence of tool calls, inputs, and outputs at every step. A trace that shows "called search → got empty list → called search again → got same empty list → looped 14 times" tells you exactly where to fix. LangSmith, Arize Phoenix, and OpenTelemetry traces are the standard tooling here.
- **Implement circuit breakers for all external tool calls.** External APIs fail. A circuit breaker tracks failure rates and transitions from CLOSED (normal) to OPEN (blocking requests) to HALF_OPEN (testing recovery). Without this, a single API outage causes every agent run to fail with cascading retries.
- **Build checkpointing into the state graph from day one.** LangGraph's checkpointing serializes the agent's state at each step. On restart, the agent resumes from the last checkpoint rather than replaying the full conversation. This also enables human-in-the-loop: pause the graph, show a human the pending action, resume on approval.
- **Test the chain, not just the output.** Trajectory-level evaluation verifies that the right tool was called at the right step with the right input. SWE-bench and ProdCodeBench evaluate coding agents this way — against real GitHub issues and production codebases, not synthetic test suites.

## Evidence

- **Engineering blog post:** Anthropic's "Building Effective AI Agents" (Dec 2024) — after reviewing deployments at Coinbase, Intercom, and Thomson Reuters, the finding is that simple composable patterns outperform complex frameworks. The recommendation: start with direct LLM API calls, reach for orchestration tools only when the use case demands cycles and branching. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **HN thread:** "Building Effective AI Agents" discussion (HN #44301809, June 2025, 543 points) — top comments from production engineers: "It's insane that we use 15 abstraction layers to call an LLM," and "LLM-generated Python code that calls tools (smolagents pattern) beats JSON tool schemas for parallel tool calls." — [news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)
- **Industry guide:** Orchestrator.dev's "How to Build AI Agents in 2025" (Dec 2025) — "The gap between a working demo and a production-ready agent is where 95% of projects die." Notes Wells Fargo handling 245M interactions without human handovers, driven by rigorous orchestration design. — [orchestrator.dev/blog/2025-12-21-ai-agents-2025-guide](https://orchestrator.dev/blog/2025-12-21-ai-agents-2025-guide)
- **Technical guide:** Markaicode's "LangGraph Use Cases: Production Workflows That Actually Scale" (June 2026) — the three production patterns where LangGraph consistently outperforms alternatives: multi-agent orchestration with state persistence, human-in-the-loop approval flows, and error recovery with checkpointing. — [markaicode.com/usecases/langgraph-use-cases-production-workflows](https://markaicode.com/usecases/langgraph-use-cases-production-workflows)
- **r/LocalLLaMA discussion:** "One of the things with agents right now is that they fail in weird, inconsistent ways and you never really know if your last tweak actually fixed anything or just got lucky once. Running multiple trials and seeing a real pass rate feels way more honest." — [reddit.com/r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1qwvmlk/)

## Gotchas

- **Framework lock-in before you understand the problem.** A team adopting CrewAI for a simple FAQ pipeline ends up debugging an opinionated multi-agent system when a 20-line direct API script would have sufficed. Name the specific capability the framework provides before adopting it.
- **No observability until you add it retroactively.** Trajectories are only useful if you log them. Teams that skip structured logging during development spend days reproducing bugs that a trace would have caught in minutes. Add LangSmith or equivalent from the first demo.
- **Silent loops with no budget guard.** Without max-step limits or token budgets, a looping agent can consume your entire monthly API budget before anyone notices. Set these at the orchestration layer, not as an afterthought.
- **Checkpointing without state schema validation.** LangGraph checkpoints are powerful but if the state schema changes between versions, old checkpoints can fail to load. Pin your state schema and version it alongside your code.
