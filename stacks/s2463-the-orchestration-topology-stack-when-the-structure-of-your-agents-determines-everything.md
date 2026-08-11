# S-2463 · The Orchestration Topology Stack — When the Structure of Your Agents Determines Everything

The moment your agentic system grows beyond one tool call, you face a non-obvious structural decision: how do your agents relate to each other? Sequential pipeline? Parallel fan-out? Hierarchical supervisor? This decision — the orchestration topology — shapes cost, latency, failure surface, and debuggability more than which model you pick or which framework you use. Most teams choose topology by intuition, not by the properties of the problem.

## Forces

- **Most tasks don't need multi-agent.** A single agent with 3–5 well-scoped tools beats a three-node graph with extra latency and coordination overhead. Adding topology too early is the most common first mistake.
- **Topology and context are coupled.** Every topology decision is implicitly a context management decision — what each agent sees, when it sees it, and how much context it carries. Getting the topology wrong creates context explosion (flooding agents with irrelevant state) or context starvation (agents making decisions without enough information).
- **The "best" topology is problem-shaped, not preference-shaped.** Sequential works for linear dependencies. Parallel works for independent sub-tasks. Hierarchical supervisor works when a coordinator must decide who does what next. These are not equivalent — picking the wrong one multiplies latency and cost.
- **The real unit of orchestration is the handoff.** Every topology is ultimately about one question: who controls the handoff from one step to the next? That control point is where failures, cost, and latency live.

## The move

Start with a single agent. Add topology only when you hit a concrete wall.

**The four primary topologies, mapped to their triggers:**

1. **Sequential (Pipeline)** — Tasks form a strict chain: A → B → C. Each step completes before the next starts. Use when outputs are inputs to the next step, when order matters, or when you need a human checkpoint between stages. Latency is the sum of all steps. Failure is scoped to the current step.

2. **Parallel (Fan-Out / Fan-In)** — One agent spawns N independent sub-agents simultaneously, then aggregates results. Use when sub-tasks are independent and can run concurrently. Latency becomes max(sub-task times), not sum. The aggregation step is non-trivial — someone must synthesize N results without contradiction or loss.

3. **Hierarchical Supervisor** — A lead agent (typically a stronger model) orchestrates specialized sub-agents, decides routing, and synthesizes outputs. This is Anthropic's own architecture for Claude Research: Opus 4 as the supervisor, Sonnet 4 as sub-agents. Use when routing decisions require a bigger-picture view, when tasks require different tools/expertise, or when you need a single authority to control handoffs.

4. **Event-Driven / Mesh** — Agents react to shared state or events rather than being called by a central coordinator. The stigmergy pattern (from r/LocalLLaMA) uses a shared artifact store; agents write and read outputs without direct communication, reducing coupling and cutting token costs by ~80% in some deployments. Use when agents are loosely coupled, when you want fault isolation, or when a central coordinator becomes a bottleneck.

**The decision grid:**

| Trigger | Topology |
|---------|---------|
| Tasks are a strict chain | Sequential |
| Tasks are independent | Parallel |
| Routing needs judgment | Hierarchical Supervisor |
| Coupling causes problems | Event-Driven / Stigmergy |
| Most tasks | Single agent + tools |

**Context engineering is topology-agnostic but essential.** Google ADK's production research (December 2025) found that the biggest production failures in multi-agent systems come from context mismanagement — not topology mistakes. Whatever topology you choose, treat context as a first-class system: define what each agent receives, when it receives it, and when context is compressed or dropped.

## Evidence

- **Engineering blog (primary):** Anthropic's own multi-agent research system (June 2025) uses a hierarchical supervisor with Claude Opus 4 as lead and Claude Sonnet 4 as specialized sub-agents running in parallel. Internal evaluations showed **90.2% improvement over single-agent Opus 4** on research tasks. Key architectural lesson: "Subagents use centralized orchestration — a supervisor agent calls specialized subagents as tools, maintaining conversation context while subagents remain stateless." — [Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Engineering blog (primary):** Google ADK Tech Lead documented five orchestration architectures (Centralized Orchestrator, Parallel Workers, Hierarchical Supervisor, Event-Driven, Mesh) with production benchmarks showing that context management — not topology choice — is the primary determinant of production success. The article explicitly recommends: "Choose the lowest complexity that meets requirements — each level adds coordination overhead, latency, and cost." — [Google Developers Blog](https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production)

- **Community discussion (primary):** An Ask HN thread on production multi-agent orchestration (2026, ~20 replies) surfaced the state management challenge as the critical differentiator: production teams using LangGraph cited "crash-safe resume after deploy" as the key reason to use state-machine-based orchestration, while teams rolling custom cited fine-grained control. One practitioner noted: "For truly long-running conversations, we store context in agent memories with importance scoring, so the agent can recall relevant context days later without carrying the full history." — [Hacker News](https://news.ycombinator.com/item?id=47660705)

- **Engineering blog (primary):** Databricks documented a production supervisor agent deployment at BASF Coatings (October 2025) using a supervisor that routes to specialized agents for structured and unstructured enterprise data. The supervisor pattern enabled domain expertise preservation while providing unified conversational access across distributed data ownership. — [Databricks Blog](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)

- **Research paper (primary):** A practitioner on r/LocalLLaMA published the "stigmergy pattern" — indirect coordination via shared artifact stores instead of direct agent-to-agent communication — reporting **~80% token reduction** compared to direct messaging patterns. The pattern eliminates circular delegation deadlock and cascading context corruption by decoupling communication from coordination. — [Reddit r/LocalLLaMA](https://www.reddit.com/r/LocalLLaMA/comments/1qv3o3o/p_stigmergy_pattern_for_multiagent_llm/)

## Gotchas

- **Over-parallelization is the default failure.** Teams add multi-agent topology because it feels sophisticated. The Anthropic engineering team explicitly warns: "Most agentic tasks are best handled by a single agent with well-designed tools." The right trigger is a concrete problem, not a feeling.
- **The aggregation step is underestimated.** Parallel fan-out sounds free — everyone runs simultaneously. But someone must synthesize N results. This synthesis step is often harder than the sub-tasks themselves, and it's where cascading context corruption happens.
- **Context explosion is the production killer, not topology.** Google ADK's research found that the dominant production failure categories (semantic failures, cascading context corruption, circular delegation) all trace to context mismanagement, not wrong topology. Whatever you build, instrument context size at every handoff.
- **Supervisor agents are expensive.** A lead agent routing to sub-agents adds one model call per interaction. For high-frequency, low-complexity tasks, this overhead dominates. Use hierarchical supervisor when the routing decision itself requires significant reasoning, not as a default pattern.
- **Topology changes are expensive.** LangGraph's state machine approach makes topology changes tractable; CrewAI's role-based approach is faster to prototype but harder to modify once branching and approvals are added. Choose with migration cost in mind.
