# S-2507 · The Agent Loop Is Nine Lines of Code

When you spend three weeks building a multi-agent crew graph and a five-tool agent with a while loop would have solved it.

## Forces

- The agentic AI market grew from $5.4B (2024) to $7.6B (2025); by 2028 Gartner projects 70% of multi-LLM organizations will use orchestration platforms — but most of those projects use simple chains, not crews
- The core agent loop is trivially simple: nine lines of Python that every framework ultimately runs; the engineering lives in the harness (context assembly, tool execution, state persistence, error recovery), not in the LLM itself
- Multi-agent orchestration earns its keep only when you need branching, parallelism, human-in-the-loop checkpoints, or durable state across deploys — not because it sounds more sophisticated
- Three architectural schools compete: DAG-based (deterministic, explicit), event-driven (async, reactive), and actor-model (isolated state, message-passing supervision hierarchies)
- The gap between "it works in the demo" and "it survives production" is where deadlocks, state corruption, silent failures, and runaway costs live — and orchestration decisions made on day one are the root cause

## The move

**Start at the bottom of the complexity ladder. Climb only when the simpler pattern genuinely can't solve the problem.**

1. **Use a sequential chain** when the workflow is linear: extract → classify → route, or summarize → store. Latency compounds, errors cascade, but it's predictable and debuggable.

2. **Use a router/dispatcher** when you need to classify a task and send it to the right specialist — a lightweight LLM call decides the path. Fast, low-latency, avoids loading all tools for every call.

3. **Use an agent loop** (while-True with tool calls) when the problem is open-ended and the model needs to iterate: research, coding, multi-step reasoning. This is where most "AI agent" demos live.

4. **Use multi-agent orchestration** (LangGraph, CrewAI, or AutoGen) only when you need branching based on intermediate output, parallel agents running simultaneously, checkpoint/resume across deploys, or a human can pause the run before a sensitive action.

5. **Design the harness, not the agent.** The LLM does the reasoning; your code handles context assembly, tool execution, state management, truncation strategies, error recovery, and cost controls. Most agent engineering is harness engineering.

6. **Treat loops as recursive goals, not prompts.** Instead of "prompt → response → prompt → response," build a small system that finds work, hands it out, checks output, logs results, and decides the next action — then let it run.

## Evidence

- **HN discussion (447 points, 320 comments):** "The unreasonable effectiveness of an LLM agent loop with tool use" — confirms the core loop pattern is nine lines of code and 95% of the "magic" is in the LLM's tool-calling fine-tuning, not the framework — [Hacker News, May 2025](https://news.ycombinator.com/item?id=43998472)

- **Engineering blog / Anthropic:** Claude Code implements a "single-threaded master loop (nO)" with TODO-based planning, diff-based workflows, and controlled sub-agent spawning — prioritizing debuggability and transparency over multi-agent swarms — [ZenML LLMOps Database / Anthropic engineering, 2025](https://www.zenml.io/llmops-database/claude-code-agent-architecture-single-threaded-master-loop-for-autonomous-coding)

- **Framework comparison (2026):** LangGraph's native support for parallel node execution wins for production scenarios needing real concurrency; CrewAI delivers ~20% lower operational costs vs AutoGen on AI-driven projects; AutoGen entered maintenance mode October 2025 with successor Microsoft Agent Framework — [JetThoughts, 2025](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)

- **LangChain blog (Feb 2025):** LinkedIn built an AI recruiter using hierarchical agents on LangGraph for candidate sourcing/matching/messaging; AppFolio created a property management copilot saving 10+ hours/week with 2x decision accuracy; LangGraph reached 1.0 stable (Oct 2025) with 20+ enterprise production deployments including Uber, LinkedIn, Replit, Elastic — [LangChain Blog](https://www.langchain.com/blog/is-langgraph-used-in-production)

- **Community consensus (Reddit/X, 2026):** "Most teams reach for multi-agent orchestration too early. A single `create_agent` with 3–5 well-scoped tools beats a three-node graph."; "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday." — [Idea to MVP / LangGraph orchestration guide, 2026](https://ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026)

- **Production framework matrix:** LangGraph = high control, explicit state/checkpoints, excellent debugging; CrewAI = low boilerplate, fastest time-to-production, role-based task delegation; AutoGen = dynamic conversational collaboration, self-correction, code execution — [Imperialis Tech / Inductivee / Iterathon, 2026](https://imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production)

## Gotchas

- **Over-engineering on day one:** LangChain's 2025 production survey found simple chains handle 80% of production use cases, yet teams consistently build multi-agent crews for problems that don't need them
- **Implicit state bites you on deploy:** AutoGen and CrewAI have implicit state management that works in demos but breaks under production load or mid-run failures. LangGraph's explicit checkpointing is the antidote — but it requires more upfront graph design
- **Tool explosion:** Giving an agent 50 tools means 50 descriptions in every context window call. Router patterns (classify before dispatch) avoid this; unbounded tool lists cause cost overruns and degraded reasoning
- **Silent failures in loops:** An agent loop with no max-iterations guard and no output validation will run until it hits a rate limit or your API budget. Budget guards and trajectory-level evaluations (did the path succeed?) are non-optional in production
