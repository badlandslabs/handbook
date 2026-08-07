# S-2271 · The Orchestration Layer Stack — When You Reach for Multi-Agent Before You Need It

You have a workflow that feels agentic. You sketch out three agents — a planner, an executor, a reviewer — and wire them together. Six months later, the graph has seventeen nodes, nobody can trace a failure to a specific agent, and your cost per task has grown 40% with no measurable quality improvement. The orchestration became the product. That is the trap.

## Forces

- **Simple chains handle ~80% of production use cases.** LangChain's 2025 production survey found teams consistently over-engineered their first implementations — reaching for agents when a three-step chain would have sufficed.
- **Multi-agent coordination adds latency at every hop.** Microsoft ISE documented teams discovering this only in production: even a two-agent supervisor pattern added 2–4× latency over a single-agent approach.
- **Framework abstractions obscure failure modes.** HN practitioners in a 2026 thread said it directly: "there's absolute zero framework out that's good enough for serious work" — preferring to build on LangGraph primitives rather than inside the framework's abstractions.
- **The real question is how much autonomy the LLM needs, not how many agents you can name.** Anthropic's year of production deployments concluded the best results came from simple composable patterns, not elaborate framework architectures.
- **LangGraph wins on durability, not on ease.** Community consensus: "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday."

## The move

Match orchestration complexity to the actual decision-space the LLM faces. Move up the stack only when a lower level genuinely cannot express the logic.

- **Level 1 — Direct model call:** Classification, summarization, translation. No tools, no state, no loop. One prompt in, one response out. If your task is this, stop.
- **Level 2 — Simple chain:** Sequential steps where each output feeds the next. Use when the workflow path is fixed but individual steps need LLM judgment (summarize → extract → classify). LangChain Chains, LlamaIndex pipelines, or raw API calls.
- **Level 3 — Router pattern:** One LLM call classifies the task type, then dispatches to a specialized handler. The router is the only decision point; handlers are stateless. Use when queries vary in type but not in path depth.
- **Level 4 — Agent loop:** Single agent with tools that decides iteration count at runtime. Use when the number of steps is genuinely unknown — research tasks, code exploration, multi-source synthesis. Set hard max iterations.
- **Level 5 — Multi-agent orchestration:** Multiple specialized agents with a supervisor, handoff protocol, or shared state. Only when tasks require genuinely different models, tool sets, or domain expertise that cannot be cleanly separated into a single prompt.

When you do go multi-agent, prefer a **supervisor pattern** (one coordinator dispatches to specialists and aggregates) over a **group chat pattern** (all agents talk freely) for production — the coordination overhead of group chat is rarely worth it.

## Evidence

- **Anthropic Engineering blog:** After working with dozens of teams deploying LLM agents across industries in 2024, they concluded "the most successful implementations use simple, composable patterns rather than complex frameworks." Their recommended hierarchy: workflows (predefined code paths) first; agents (dynamic self-direction) only when genuinely needed. — [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents)
- **HN Ask thread (2026):** Practitioners building multi-agent production systems reported mixed framework success. One said "there's absolute zero framework out there that's good enough for serious work" — many were building on LangGraph primitives rather than inside framework abstractions. Framework vs. custom was the top debate. — [Ask HN: Multi-Agent AI Workflow Orchestration in Production](https://news.ycombinator.com/item?id=47660705)
- **Microsoft ISE Developer Blog:** Documented evolving a retail customer's chatbot from a modular monolith (single router, one-agent-per-query) to a coordinator-based multi-agent microservices architecture. Found that coordinator-based patterns improved cross-team agent reuse but introduced 2–4× latency vs. the monolith — mitigated via prompt optimization, model selection per task type, and selective orchestration (simple queries bypass full routing). — [Orchestration Patterns for Multi-Agent Systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **Azure Architecture Center:** Defines a formal complexity spectrum from direct model call → single agent with tools → multiagent orchestration. Each level explicitly warns about coordination overhead, latency, and cost before recommending the next level up. — [AI Agent Orchestration Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

## Gotchas

- **Reaching for agent loops before proving a chain fails.** If the path is deterministic, a chain is faster, cheaper, and more traceable. Agent loops are for genuinely open-ended problems.
- **Treating framework features as requirements.** LangGraph, CrewAI, and AutoGen all underwent major rewrites in 2025. Building inside their abstractions creates upgrade risk. Build *on top of* their primitives instead.
- **Ignoring the latency tax of multi-agent.** Every agent hop is a network call + LLM inference + serialization roundtrip. Microsoft ISE's production case showed this adding seconds per task — noticeable in user-facing flows.
- **No checkpointing in agent loops.** Without explicit state persistence between iterations, a mid-loop crash restarts from scratch. LangGraph's checkpointing is its strongest production feature, not its graph syntax.
- **Supervisor prompts that try to be too clever.** A supervisor that also does work (not just coordination) conflates two roles and degrades both. Keep coordinators thin.
