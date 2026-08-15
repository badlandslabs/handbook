# S-2695 · The Orchestration Pattern Selection Stack — When Your Framework Chooses You Before You Realize It

You picked LangGraph because it looked flexible. Or CrewAI because it shipped a working demo fast. Six months later you're deep in production and you realize the pattern baked into that framework is fighting you — your agent needs to react to events but your graph expects a deterministic path, or your workflow is fundamentally peer-to-peer but your supervisor agent is the bottleneck. The orchestration pattern isn't a detail you pick at the start and forget. It's the load-bearing structure that determines every failure mode, every debugging session, and every scaling decision that follows.

## Forces

- **Every framework ships with an implicit pattern.** LangGraph gives you DAGs. CrewAI gives you role-based crews with a supervisor. AutoGen gives you conversational agents. Semantic Kernel gives you five patterns but expects you to know which to reach for. Choosing a framework without understanding its canonical pattern means you inherit its constraints without choosing them.
- **The wrong pattern compounds failure.** A deterministic DAG running an event-driven workload either rejects legitimate branching or silently drops state. A pure swarm trying to run a linear pipeline wastes coordination overhead on steps that have no real dependency. 37% of multi-agent failures trace to inter-agent coordination, not individual agent behavior — and the orchestration pattern is what governs coordination.
- **PoC environments hide pattern mismatches.** In a demo, every pattern works because the inputs are curated and an engineer is watching. Real production traffic exposes the pattern: unbounded event streams, branching logic that can't be expressed as a DAG, or handoff chains that exceed the supervisor's context window.
- **Scaling multiplies pattern friction.** A supervisor pattern that works fine with 4 agents develops a single point of failure with 20. A swarm that handles 10 agents gracefully requires significant redesign at 50.

## The Move

Match the orchestration pattern to the **shape of the dependency graph in your actual workload**, not the shape of the framework's documentation:

- **Sequential (chain):** When steps must happen in order and each step depends on the output of the previous. Simple, predictable, easy to debug. Fails when steps could run in parallel or when late steps need early context. Used by: Cron jobs, single-user linear workflows, ETL agents.
- **Parallel/concurrent:** When independent tasks can execute simultaneously and results are collected. Massive latency wins when tasks are I/O-bound. Fails silently when hidden dependencies exist — step B might not declare it needs step A's output, and the race condition only appears in production.
- **Hierarchical (supervisor/manager):** When a central agent decomposes tasks and delegates to specialists, then synthesizes results. Natural for business workflows with a "planner" role. Single point of failure in the supervisor — if it misroutes or misinterprets, the whole workflow degrades. Used by: CrewAI's Hierarchical Process, Semantic Kernel's manager pattern.
- **Event-driven (pub/sub, actor model):** When agents react to shared state or signals rather than following a predetermined path. Scales well because agents are loosely coupled. Fails when events fire faster than consumers can process them, or when event schema drift breaks downstream handlers. Hive framework uses this model explicitly.
- **Swarm:** When 50+ agents collaborate without central coordination, emergent behavior solves complex optimization problems. Appropriate for robotics, research, and financial modeling. Requires careful design of termination conditions and emergence safeguards.

**State channels are the key structural choice in graph-based patterns.** LangGraph's typed state channels (messages, documents, intermediate_results) prevent race conditions by making data flow explicit. In frameworks without named state channels, implicit context carries hidden coupling that surfaces as bugs at scale.

**Memory architecture must be chosen alongside the pattern.** Sequential chains can use simple last-message memory. Concurrent and event-driven patterns need shared state stores. Hierarchical patterns need supervisor-accessible context windows. The memory tier and the orchestration pattern co-evolve.

## Evidence

- **Framework comparison (2026):** LangGraph (29,700 stars, MIT) — DAG-based, stateful checkpointing, best for deterministic workflows with branching. CrewAI (48,400 stars, 39M+ PyPI downloads, MIT) — role-based crews, supervisor/hierarchical patterns, fastest PoC-to-prototype. AutoGen/MAF 1.0 (GA April 2026) — conversational agents, Microsoft-backed, best for human-in-the-loop. Semantic Kernel — five patterns (sequential, parallel, hierarchical, group chat, handoff) in a single .NET/Python SDK, best for enterprise C# shops.
  — *AutomationSwitch comparison (April 2026)* — https://automationswitch.com/ai-workflows/langchain-vs-crewai-vs-autogen-vs-langgraph

- **LangGraph in production:** Uber, LinkedIn, and Replit use LangGraph. LinkedIn uses it for an AI-powered recruiter agent that handles candidate sourcing, matching, and outreach — freed recruiters to focus on strategy. AppFolio uses a LangGraph-powered property management copilot that saved property managers 10+ hours/week with 2x accuracy in decision-making. Klarna uses LangGraph for stateful agent workflows with checkpointing.
  — *LangChain Blog (February 2025)* — https://www.langchain.com/blog/is-langgraph-used-in-production

- **Hive framework self-evolving topology:** Hive treats exceptions as observations rather than terminal failures — a FileNotFoundError is caught, serialized, and fed back into the context window as a new prompt: "I tried to read the file and failed with this error. Why? And what is the alternative?" This moves the failure recovery decision into the LLM rather than pre-specifying recovery paths. HN discussion noted concerns about astroturfing in the post, but the architectural pattern of treating exceptions as state is a genuine design decision with precedent.
  — *Show HN (April 2026)* — https://news.ycombinator.com/item?id=46979781

- **Microsoft Semantic Kernel multi-agent orchestration:** The framework documents five distinct patterns with explicit use cases: sequential (linear workflows), parallel (fan-out/fan-in), hierarchical (manager delegates to specialists), group chat (collaborative with optional human), and handoff (specialist-to-specialist transfers). The Azure Architecture Center recommends starting with the lowest complexity pattern and escalating only when the workload's actual dependency graph requires it.
  — *Microsoft Dev Blogs (May 2025)* — https://devblogs.microsoft.com/semantic-kernel/semantic-kernel-multi-agent-orchestration/

- **Multi-agent failure analysis:** 37% of multi-agent failures trace to inter-agent coordination rather than individual agent limitations. The pattern chosen for connecting agents influences reliability, latency, cost, and debuggability as much as model selection or prompt engineering.
  — *Swarmsignal.net (February 2026)* — https://swarmsignal.net/ai-agent-orchestration-patterns

## Gotchas

- **AutoGen is in maintenance mode** as of October 2025, with Microsoft's Agent Framework (MAF 1.0, GA April 2026) as its successor. Don't start a new project on AutoGen unless you have an existing codebase — MAF unifies Semantic Kernel and AutoGen under one SDK.
- **CrewAI's Flows (event-driven)** were added in 0.36+ (mid-2025). Early adopters running pre-0.36 versions are missing the event-driven pattern and have no clean migration path — they end up bolting on external event systems.
- **Token budget overruns** are the top production failure mode for hierarchical patterns (CrewAI's top failure mode per Inductivee's 40+ deployment postmortems). The supervisor's context grows with each delegation round-trip. Set hard token limits on supervisor synthesis steps.
- **LangGraph checkpointing** is not free — it serializes full state on every step. For high-frequency agents (thousands of steps/minute), the checkpoint overhead can dominate. Consider checkpointing every N steps or only on boundary transitions.
- **Agent loops** (the agent calling itself repeatedly) are most common in parallel patterns where multiple agents see partial state and make conflicting decisions. Build explicit termination conditions and step-count guards into every agent definition.
