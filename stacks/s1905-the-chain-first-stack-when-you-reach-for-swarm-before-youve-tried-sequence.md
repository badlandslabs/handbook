# S-1905 · The Chain-First Stack — When You Reach for Swarm Before You've Tried Sequence

You open a fresh project and scaffold three specialist agents, a message bus, and a shared scratchpad. You didn't start with a sequential chain because it felt too simple. Three months later you're debugging 47 distinct failure modes unique to multi-agent systems that wouldn't exist if you'd started with a for-loop. The chain-first failure is the opposite of the eval-first failure: you over-engineered before you had evidence the complexity was warranted.

## Forces

- **Multi-agent failure modes are emergent, not additive.** Single-agent failures are local (hallucination, loops, context limits). Multi-agent failures cascade across agent boundaries — deadlocks, redundant work, cost explosions from context re-sending on every handoff. Microsoft Research identified 47 failure modes unique to multi-agent orchestration that don't appear in single-agent deployments. You inherit all of them the moment you add a second agent.
- **The demo-to-production gap is widest for complexity.** Swarms and peer-to-peer architectures look stunning in demos. In production, they're nightmares to trace, cost 3-5x more in tokens (Anthropic's data), and have no canonical framework implementation. Teams ship the demo, hit the failure modes, and patch with retries until the token bill becomes the incident.
- **Framework bias pushes teams toward agentic from the start.** LangGraph, CrewAI, and AutoGen all center multi-agent patterns in their documentation and onboarding. The simplest viable implementation with these tools is already more complex than most production needs warrant. Meanwhile, LangChain's 2025 production survey found that simple chains handle 80% of actual production use cases — yet most teams don't start there.
- **Context window pressure pushes teams toward agents for the wrong reason.** When a single prompt gets long, the instinct is to split into multiple agents. The simpler fix is often summarization mid-chain, better tool design (one well-scoped tool replacing a separate agent), or parallel tool calls within a single LLM turn — none of which require a second agent.

## The Move

Start with the simplest orchestration that could work. Add complexity only when the simpler approach demonstrably fails — not when you anticipate it might.

**The ladder, in order:**

1. **Simple sequential chain** — fixed steps, output of step N becomes input of step N+1, no branching, no agents. For 80% of production use cases, this is the ceiling.
2. **Router pattern** — one LLM classifies the input type and dispatches to a fixed handler. No multi-agent coordination, just smart routing. Add this when you have genuinely distinct input types that need distinct handling logic.
3. **Supervisor + specialists** — one supervisor LLM decomposes tasks and routes to specialist agents. One level of hierarchy only. Add this when task decomposition genuinely benefits from a reasoning planner that can decide not just *what* but *in what order*.
4. **Fan-out / map-reduce** — parallel execution of identical agents over a list, then aggregation. Add this only for embarrassingly parallel workloads where independent workers produce independent outputs.
5. **Multi-level hierarchy or swarm** — supervisors of supervisors, peer coordination, shared blackboard. Add this only when the workflow genuinely requires it, and instrument observability before you ship.

**On every rung:** enforce token budgets per step, instrument every handoff with trace IDs, and log cost per trajectory from day one. Multi-agent cost is non-linear and teams routinely get surprised.

## Evidence

- **LangChain survey (n=1,340):** Simple chains handle 80% of production use cases. The same survey found that 57.3% of teams building AI agents have them in production (up from 51% year-over-year), but the complexity distribution skews far simpler than the ecosystem's marketing suggests. — [LangChain State of Agent Engineering 2026](https://www.paperclipped.de/en/blog/state-of-agent-engineering-2026)
- **MMC Ventures research:** Interviewed 30+ agentic AI startup founders and 40+ enterprise practitioners. 52% build agentic infrastructure fully in-house specifically citing "ecosystem nascence" — meaning off-the-shelf orchestration frameworks weren't trusted enough for production. Biggest production blockers were workflow integration (60%) and employee resistance (50%), not technical model capabilities. — [State of Agentic AI: Founder's Edition](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)
- **Microsoft ISE field note:** A retail customer's production chatbot evolved from a modular monolith (router pattern, one agent per query) to coordinator-based multi-agent architecture when the requirements shifted to cross-team agent reuse. The transition was non-trivial: required explicit handoff contracts, shared tool registries, and a coordination layer that didn't exist in the simpler architecture. Lesson: the multi-agent transition cost was real and justified only by the reuse requirement. — [Orchestration Patterns for Multi-Agent Systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **Production breakdown (2026 survey of deployed systems):** Most production agent systems settle on supervisor + specialists or sequential pipeline. A smaller cohort runs hierarchical (supervisors of supervisors) for genuinely complex workflows. Swarm and blackboard patterns appear primarily in research-and-summarise tasks where parallel exploration has clear payoff. — [Paiteq 2026 Production Guide](https://www.paiteq.com/blog/multi-agent-orchestration-patterns)

## Gotchas

- **Adding agents to reduce context load is usually wrong.** Summarize intermediate state instead. One agent with summarization handles most "context too long" problems more reliably than two agents with a handoff.
- **Framework defaults bias you toward more agents.** LangGraph's graph model, CrewAI's role-based crews, and AutoGen's conversational agents all make multi-agent the path of least resistance. Fight this by benchmarking the chain version before introducing agents.
- **The observability gap widens with every agent you add.** LangChain's survey found 89% of teams have observability but only 37% run online evaluations. For multi-agent systems, "what did agent B see when it made decision X?" is a question you'll need to answer at 2am. If you can't trace it now, you're already behind.
- **Cost in multi-agent is non-linear.** Every handoff re-sends context. Three "specialists" each re-receiving the full conversation is 3x the tokens of one agent. Set per-agent and per-trajectory token budgets. Monitor them in production, not just in testing.
- **CrewAI's abstraction makes early iteration fast but limits advanced topology later.** If there's any chance the system needs custom branching or parallelism beyond the role-based crew model, start with LangGraph's explicit state machine — the verbosity pays off at scale.
