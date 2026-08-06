# S-2229 · The Agent Orchestration Stack: When You're Not Sure How Many Agents You Need

You built a prototype that works. Now you need it to handle 10x the load, work across 4 data sources, and not hallucinate answers on Fridays. The question isn't whether to use agents — it's how much autonomy the task actually needs. Most teams answer that question wrong and pay for it.

## Forces

- **Autonomy is not free.** Agent-based systems cost 3-5x more than chains in tokens and latency. Teams that reach for multi-agent orchestration because it sounds sophisticated end up with expensive loops and no observability.
- **Chains can't handle branching decisions.** A sequential pipeline that encounters an unexpected input dead-ends. But converting it to an agent loop means accepting retry behavior, non-deterministic output, and much harder debugging.
- **Framework choice locks you in early.** LangGraph's state machine model rewards planning upfront. CrewAI's role-based collaboration rewards fast iteration. Switching costs are non-trivial once your graph has 5+ nodes.
- **Multi-agent wins for complexity, bleeds on simplicity.** Anthropic's production data shows multi-agent systems outperform single agents by 90.2% on complex tasks requiring parallel independent paths — but consume 10-15x more tokens. The same pattern that makes a research agent powerful makes a FAQ bot prohibitively expensive.

## The Move

The core insight: **match autonomy to the task's actual openness.** Build a ladder of three patterns, and only escalate when evidence demands it.

**Step 1 — Start with an optimized single call (the augmented LLM).**
An augmented LLM is an LLM with tools, memory, and data attached. Most production use cases stop here. Add a circuit breaker, time-box tool calls, and log every tool invocation. If this covers the task, stop.

**Step 2 — Add a router for branching paths.**
Before you make an agent, make a classifier. A router inspects the input, picks a downstream handler (billing, search, escalation), and passes it down. This costs one extra LLM call instead of an unbounded loop. Router patterns cut costs by 60% compared to full agent loops by routing 80% of requests to simpler handlers.

```python
# Router pattern — from LangGraph docs
builder = StateGraph(OrchestrationState)
builder.add_node("router", router)
builder.add_node("researcher", researcher)
builder.add_edge(START, "router")
builder.add_conditional_edges("router", route_next)
builder.add_edge("researcher", "router")
graph = builder.compile(checkpointer=MemorySaver())
```

**Step 3 — Reserve agent loops for open-ended, multi-path problems.**
Use a loop only when: (a) the task can't be pre-mapped, (b) multiple independent paths must be explored simultaneously, and (c) the cost is justified by the outcome. Anthropic's three-question test: How much control do you need? How many domains does the problem span? What's your token budget?

**Step 4 — Use control theory instead of max_iterations for loop termination.**
The `max_iterations=N` approach fails in both directions — stops loops still improving or lets them spin after the best answer was found. LoopGain (open-source, Apache-2.0) replaces this with empirical loop gain measurement: calculate Aβ = current_error / previous_error on each iteration. Aβ < 1 means the loop is still improving. Aβ ≥ 1 means it has converged or stalled. This prevents premature termination and unnecessary token burn.

**Step 5 — Treat tool execution as untrusted code.**
Time-box every tool call. Wrap external API calls in circuit breakers. A hung file-read tool is the most common cascading failure in agent systems — it blocks the orchestrator, which blocks every in-flight request.

**Step 6 — Structure session memory as durable, clustered state.**
Conversational memory must survive orchestrator restarts and scale past single-node Redis. Use clustered Redis or equivalent for session persistence. Separate conversational memory from agentic state (the working context of what the agent is trying to accomplish).

## Evidence

- **Anthropic enterprise guide:** Multi-agent systems outperform single agents by 90.2% on complex tasks requiring simultaneous exploration of independent paths, but consume 10-15x more tokens. Coinbase, Intercom, and Thomson Reuters deployments all follow the "start simple, evolve gradually" principle. — [Anthropic: Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **LangGraph production community:** Router patterns reduce costs by ~60% by routing most requests to simple handlers. LangGraph earns its keep when branching, human-in-the-loop, or crash-safe resume are required — teams describe it as "harder to start, easier to debug." — [Idea to MVP: Agent Orchestration with LangGraph, 2026](https://ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026)
- **Reddit r/LangChain production patterns:** After a year of production deployments, the community consensus is 8 core patterns: tool calling, ReAct, chain-of-thought, sequential chains, parallel execution, router agents, hierarchical agents, and feedback loops. Each has explicit "when NOT to use" guidance. — [r/LangChain: Production AI Agent Patterns](https://www.reddit.com/r/LangChain/comments/1qr6mii/production_ai_agent_patterns/)
- **Intercom Fin AI Agent:** Three-layer architecture (App, AI, Model) achieves 50-70% autonomous resolution across chat, email, and multiple languages. Anthropic uses Fin internally with 96% conversation participation rate. — [Faye Digital: Intercom Fin AI Agent Case Studies](https://fayedigital.com/blog/fin-ai-agent/)

## Gotchas

- **Over-engineering with agents when a chain would do.** LangChain's 2025 production survey found simple chains handle 80% of production use cases. The cognitive overhead of maintaining an agent graph rarely pays back for linear tasks.
- **Replacing `max_iterations` with "feel" is not a fix.** Teams that manually tune iteration counts end up either clipping improving loops or letting stale ones burn tokens. Use empirical loop gain measurement (Aβ) instead.
- **Framework lock-in is real — pick for the long game.** CrewAI wins for rapid prototyping and non-engineer-readable agents (role-based collaboration model). LangGraph wins for production reliability, observability, and complex state management. Switching from CrewAI to LangGraph mid-production is a painful migration.
- **Tool call failures cascade silently.** A tool that returns an unexpected schema, times out, or throws a non-200 response doesn't crash the agent — it feeds garbage into the next reasoning step. Every tool call needs schema validation on the response side.
