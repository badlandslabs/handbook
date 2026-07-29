# S-1829 · The Scope-Before-You-Graph Stack — When Your Multi-Agent System Is a Hammer Looking for a Nail

You have a workflow that *might* need multiple agents. You open LangGraph docs. Three hours later your architecture has five nodes, two cycles, and a state object that only you understand.

## Forces

- **The framework seduction** — LangGraph, CrewAI, and AutoGen all ship beautiful demo videos. The scaffolding is cheap. The operational cost (state explosion, debugging across graph boundaries, cost at scale) is invisible until you hit it.
- **The supervisor/specialist pattern is everywhere** — and it's overused. You do not need a classifier agent, a knowledge agent, a CRM agent, and a response agent for a simple FAQ pipeline. You need one agent with four good tools.
- **Context window exhaustion is real** — but the fix is often better tool design, not more agents. The "god agent" anti-pattern (one agent doing everything) is bad, but the "micro-agent sprawl" anti-pattern (ten agents for a three-step workflow) is worse.
- **Async coupling is the hidden CrewAI killer** — orchestration and execution in the same process means one slow agent blocks the queue. Teams discover this in production, not in demos.
- **Multi-agent earns its cost at specific triggers** — branching logic, durable execution, human-in-loop checkpoints, parallel independent sub-tasks, and different model providers per role.

## The Move

**Scope down before you graph. Reach for multi-agent only when a specific trigger is present.**

1. **Start with one agent + N tools.** If a single `create_agent` with 3–5 well-scoped tools solves your workflow, stop. You have not earned the complexity of a graph.

2. **Use LangGraph's state-machine model when you need durable execution.** LangGraph (38k GitHub stars, MIT license) treats agents as graph nodes with defined edges and checkpoints. Production users: Klarna, Uber, LinkedIn, Replit, Elastic. Best triggers:
   - Different branching paths based on classification
   - Human-in-loop pauses mid-execution
   - Need to resume after deployment crash
   - Multi-turn state that must survive context overflow

3. **Use CrewAI for fast multi-agent prototypes, then fix the async bottleneck.** CrewAI (47k GitHub stars, role-based agents) gets you to a working demo in an afternoon. Production teams hit a wall at concurrency > ~5 requests when orchestration and LLM inference share a synchronous process. Fix: decouple with an async task queue (Celery + Redis or SQS). One slow agent should not block the queue.

4. **Use the Supervisor + Specialists pattern sparingly.** One coordinator agent delegates to N specialist agents. This is the most common real-world multi-agent pattern — and it is often the right answer. But it requires: a well-scoped supervisor prompt, specialist agents that fail cleanly, and a shared state schema everyone agrees on.

5. **AutoGen is in maintenance mode.** Microsoft shipped AutoGen 0.4 in Oct 2025 and moved focus to the new Agent Framework. If you are starting fresh, evaluate Microsoft's Agent Framework over AutoGen for Microsoft ecosystem integration.

6. **MCP is the integration standard.** Model Context Protocol: 10K+ public servers, 97M+ monthly SDK downloads, adopted by Anthropic, Google, Microsoft, and OpenAI. If you are building tool integrations, build MCP servers. 41% of software organizations have at least limited MCP production usage (Stacklok 2026). The 78% figure widely cited was unsourced and retracted.

7. **Build context before planning, phase complexity.** DoorDash's Agentic Orchestrator (open source, Apache-2.0) models the key insight: for large/multi-step features, agents should build a per-repo knowledge base, run inquiry and design phases *before* planning. Complexity belongs in phased execution, not in agent count.

## Evidence

- **LangGraph production users:** Klarna, Uber, LinkedIn, Replit, Elastic publicly cited on the LangGraph README (github.com/langchain-ai/langgraph). LangGraph README also lists "reliable, observable, and controllable" as the core production triad that single-agent systems lack. — [LangChain Blog: "Is LangGraph Used In Production?"](https://www.langchain.com/blog/is-langgraph-used-in-production), Feb 2025
- **CrewAI async bottleneck:** "The most common failure in a CrewAI multi-agent system isn't bad agent logic — it's running orchestration and execution in the same process. Once you have more than a handful of concurrent requests, one slow or stuck agent blocks everything behind it." — [Markaicode: "CrewAI Production Architecture: Fixing the Async Bottleneck"](https://markaicode.com/architecture/agent-architecture-with-crewai/), Jul 2026
- **LangGraph vs. CrewAI choice:** "LangGraph is harder to start, easier to debug." / "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday." — [Idea to MVP: "LangGraph Agent Orchestration Patterns 2026"](https://ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026), Jun 2026
- **DoorDash orchestrator pattern:** Agentic Orchestrator phases execution as research → planning → implementation → code review → PR, running each phase concurrently. Context is "built, not hoped for." — [GitHub: doordash-oss/agentic-orchestrator](https://github.com/doordash-oss/agentic-orchestrator), Apache-2.0
- **MCP adoption data:** 10K+ active public servers, 97M+ monthly SDK downloads, 41% of surveyed software orgs in production (corrected from retracted 78% claim). — [Digital Applied: "MCP Adoption Statistics 2026"](https://www.digitalapplied.com/blog/mcp-adoption-statistics-2026-model-context-protocol), verified May 2026
- **Real-world deployment patterns:** 30+ startup founders and 40+ enterprise practitioners interviewed; main blockers are workflow integration, employee trust, and data privacy — not model performance. Incremental narrow deployment outperforms ambitious autonomy. — [MMC.vc State of Agentic AI Report, via HN](https://news.ycombinator.com/item?id=45808308)

## Gotchas

- **"God agent" anti-pattern is real** — one agent with 20 tools and a 40-page system prompt. The fix is not more agents; it is better tool boundaries. Break by function, not by model.
- **CrewAI parallel execution looks async but isn't always** — the `Process` mode (`crew.kickoff_async()`) is the production-safe path. Synchronous processes in CrewAI hide the bottleneck until load hits.
- **Graph complexity scales super-linearly** — a 5-node graph with 3 edges seems manageable. A 12-node graph with conditional edges, shared state, and human-in-loop nodes is a debugging nightmare. Treat graph complexity as a cost, not a feature.
- **MCP security gap** — 43% of MCP servers have command injection flaws; with 10 plugins, exploit probability exceeds 92%. Do not expose untrusted MCP servers to production without sandboxing. — [Deepak Gupta: "MCP Enterprise Guide 2025"](https://guptadeepak.com/research/mcp-enterprise-guide-2025)
- **Enterprise adoption ≠ autonomous** — most production agents in 2025-2026 still have strong human oversight. Fully autonomous agents in regulated industries (healthcare, finance) remain rare.
