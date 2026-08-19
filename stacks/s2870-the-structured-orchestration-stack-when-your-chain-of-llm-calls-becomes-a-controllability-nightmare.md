# S-2870 · The Structured Orchestration Stack — When Your Chain of LLM Calls Becomes a Controllability Nightmare

You've got a working prototype: a researcher agent, a drafter agent, and a reviewer agent chained together with prompt concatenation. It runs clean in demos. Then you ship it and discover that the reviewer sometimes blocks waiting for the drafter, the researcher sometimes loops on ambiguous queries, and adding a fourth agent requires rewriting every handoff. The gap between "works in a notebook" and "production-controllable multi-agent system" is the orchestration pattern you chose — or the absence of one. This stack gives you the three structural schools that survived 2025-2026 production use and the reasoning for picking each.

## Forces

- **Simple chaining hits a ceiling at 3-4 agents.** Beyond that, implicit dependencies become unmanageable: who calls whom, what state survives the handoff, and what happens when one link fails silently.
- **The framework you pick shapes your failure modes.** LangGraph's DAG model makes execution traceable but adds overhead. Event-driven gives you reactivity but buries causality. The Actor model isolates state cleanly but introduces supervision complexity.
- **Multi-agent workflows grew 327% between June and October 2025** (Databricks State of AI Agents report, per MHTECHIN). Technology companies build multi-agent systems at 4× the rate of other industries — they hit these problems first and hardest.
- **Teams confuse "orchestration pattern" with "framework."** Choosing LangChain vs CrewAI vs AutoGen is not the same as choosing DAG vs event-driven. The pattern determines controllability; the framework is an implementation detail.
- **Execution ordering vs. coordination semantics.** You need to know not just *what runs first* but *who decides* what runs next, and whether that decision survives failures.

## The Move

Pick a coordination model based on the failure properties you can tolerate, then implement it with a framework that matches. Three patterns have demonstrated staying power in production:

**1. DAG-Based Orchestration — deterministic, traceable, brittle on the edges**
- Define explicit dependency graphs where each node is an agent or tool step
- Execution order is baked in: the graph only runs where edges allow it
- LangGraph (built on LangChain) is the dominant implementation — treats agent interactions as state machines with defined transitions
- Best when: workflows are mostly fixed in structure, auditability matters, and failures must be traceable to a specific node
- The brittleness: adding a new agent often means re-wiring the graph; partial failures don't auto-retry unless explicitly coded as edges

**2. Event-Driven Orchestration — reactive, scalable, causality-blind**
- Agents publish events; other agents subscribe and react
- No central orchestrator dictating execution order — consumers drive the workflow
- Key benefit: natural horizontal scaling; agents consume events at their own pace
- Implementation options: Apache Kafka-based event buses, custom pub/sub with Temporal or Preflow, or lightweight message queues
- Best when: workflows are loosely coupled, agents work on independent timelines, and you need fault isolation between steps
- The gap: causality is implicit. If agent C needs output from agent A and B in a specific order, you need explicit sequencing logic or event schemas to enforce it

**3. Actor Model — isolated state, supervision hierarchies, heavyweight**
- Each agent is an "actor" with private state, communicating exclusively via message-passing
- Supervision hierarchies define what happens when an actor crashes — a parent restarts, escalates, or kills siblings
- Frameworks: Microsoft's AutoGen (multi-agent conversation as actors), Erlang-style supervision trees adapted for LLM agents
- Best when: agents must be truly independent processes, failures need hierarchical recovery, and you're building systems that run for days or weeks
- The gap: significant infrastructure overhead; not worth it for short-lived, tightly-coupled workflows

**4. The Supervisor/Coordinator Pattern — the practical hybrid**
- A single orchestrator (either a dedicated LLM or a deterministic router) decides which specialist agent handles each turn
- Specialists execute and report back; the supervisor aggregates and decides next steps
- This is the most common production pattern because it maps naturally to how teams think about division of labor
- Implementation: OpenAI's Agents SDK (handoff abstraction), Anthropic's Claude Agent SDK (invoke agents-as-tools), Google's ADK (hierarchical agent tree)
- Best when: task complexity requires specialization but workflow structure is relatively fixed

**The decision matrix:**

| Need | Pattern |
|------|---------|
| Auditability + fixed workflow | DAG (LangGraph) |
| Loose coupling + scaling | Event-driven |
| Long-running + fault isolation | Actor model |
| Practical production with specialization | Supervisor/Coordinator |

## Evidence

- **Research report:** *Agent Workflow Orchestration Patterns: DAG, Event-Driven, and Actor Models* — Zylos Research, April 2026. Documents the three-pattern convergence and notes that "by 2025 the naive chaining approach had collapsed under its own complexity: deadlocks, state corruption, silent failures, and runaway costs." Links the market growth (AI agents market $5.4B in 2024 → $7.63B in 2025) to the architectural maturity that forced teams beyond single-turn chains. — [https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/)

- **Industry guide:** *Orchestration Frameworks for Agentic AI: LangChain, AutoGen, CrewAI — The Complete 2026 Guide* — MHTECHIN Technologies, 2026. Reports multi-agent workflow growth of 327% (June–October 2025) from Databricks' State of AI Agents, with tech companies at 4× the deployment rate. Frames the framework landscape around orchestration philosophy: "Good frameworks encode best practices into the framework itself, reduce boilerplate code, make it easier to reach a higher level of quality." — [https://www.mhtechin.com/support/orchestration-frameworks-for-agentic-ai-langchain-autogen-crewai-the-complete-2026-guide](https://www.mhtechin.com/support/orchestration-frameworks-for-agentic-ai-langchain-autogen-crewai-the-complete-2026-guide)

- **Engineering post:** *Building Multi-Agent AI Systems: 2026 Guide* — AI Workflow Lab, 2026. Maps the supervisor/coordinator as "the workhorse for most production deployments," documents the sequential pipeline pattern (research → draft → edit → fact-check) with honest tradeoffs, and frames multi-agent divide-and-conquer as the answer to the single-agent ceiling on complex, multi-domain tasks. — [https://aiworkflowlab.dev/article/building-multi-agent-ai-systems-2026-architecture-patterns-mcp-production-orchestration](https://aiworkflowlab.dev/article/building-multi-agent-ai-systems-2026-architecture-patterns-mcp-production-orchestration)

## Gotchas

- **Picking a framework before a pattern.** LangGraph and CrewAI implement different orchestration philosophies — forcing a DAG pattern into CrewAI's role-based model (or vice versa) causes friction that shows up as code smell, not obvious errors. Decide the pattern first.
- **Event-driven systems lose trace causality.** When a workflow breaks in production, a pub/sub system makes it hard to reconstruct *why* agent B ran before agent C. Instrument your events with correlation IDs from day one — retrofitting trace context into an event bus is painful.
- **The supervisor becomes a single point of failure in the Coordinator pattern.** If your LLM-based router fails or drifts, the entire workflow halts. Treat the supervisor as a production-critical component with its own monitoring and fallback logic.
- **DAG graphs age badly.** A graph designed for a 3-step workflow will fight you when you add parallel branches or conditional edges. Build the graph with extensibility in mind from the start — prefer explicit state objects over implicit conversation passing.
