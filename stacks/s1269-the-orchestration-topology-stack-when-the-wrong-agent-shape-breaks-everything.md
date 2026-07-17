# S-1269 · The Orchestration Topology Stack: When the Wrong Agent Shape Breaks Everything

The moment you move from "one model, one prompt" into multi-agent territory, the deciding factor is no longer model strength — it's topology: how agents are connected, who talks to whom, who decides, and who finishes. Anthropic's analysis of 200+ enterprise deployments found 57% of failed projects had root causes in orchestration design. The individual agents were fine. The shape of the system was wrong.

## Forces

- **Topology compounds failures** — a single-agent system with a bad tool call fails once. A five-agent system with bad handoff logic fails five times in sequence, with error messages that obscure the root cause.
- **Most teams default to peer mesh** — GroupChat-style flat topologies feel natural in prototyping (everyone talks to everyone) but degrade non-linearly as agent count grows. The 2024 "swarm = smarter" thesis failed in production precisely because of this.
- **The cost of wrong topology is paid in tokens** — multi-agent systems consume 15× more tokens than single-agent chat (Tran & Kiela, arXiv 2604.02460), and token usage explains 80% of performance variance. Choosing the wrong topology isn't just an engineering mistake — it's a budget catastrophe.
- **Topology determines auditability** — financial services firms overwhelmingly favor hierarchical supervisor patterns because regulators can trace a decision back to a named agent with a named human owner. Peer meshes make this structurally impossible.

## The move

Choose your orchestration topology by answering one question first: *does the task have a known decomposition, or must the agents discover it?*

**Known decomposition → use a Supervisor (hub-and-spoke) or Pipeline pattern.**
- A central orchestrator receives the task, breaks it into subtasks, routes each to the right specialist, and integrates results.
- Each specialist has a scoped context and a bounded toolset — they can't accidentally wander outside their lane.
- **Tooling:** LangGraph's `supervisor` pattern, CrewAI's `Process.sequential`, OpenAI Agents SDK handoffs with a manager agent.
- Production evidence: Microsoft ISE's retail customer migrated from a flat router (modular monolith) to a supervisor topology and achieved clear per-agent accountability for compliance auditing.

**Dynamic discovery → use a Bounded Network (controlled peer mesh) pattern.**
- Agents can recruit peers dynamically, but only within a declared topology — not open-ended swarm.
- Each agent has a declared handoff contract: what it accepts as input, what it returns, and what signals "I'm done with my piece."
- **Tooling:** LangGraph's `StateGraph` with conditional edges, Anthropic's Agent Teams (Teammates API), OpenAI's Agents-as-Tools pattern.
- The constraint that makes this work: per-handoff timeout, max recursion depth, and forbidden routes are declared upfront.

**Never use these without explicit justification:**
- **Flat peer mesh (GroupChat)** in production with >3 agents — coordination overhead and non-determinism grow faster than agent count.
- **Full swarm (open-ended recruitment)** — the 2024 pattern that ate 15× token budgets and produced incoherent outputs in enterprise settings.

**Practical checklist before committing to a topology:**
1. Can a human trace every decision to a named agent? If not, the topology is too opaque.
2. What is the max depth of the call chain? Beyond 3 hops, context drift compounds.
3. Is there a declared "done" signal per agent? Ambiguous completion causes loops.
4. Can a stuck agent be cancelled without killing the whole run? Timeout per handoff is non-negotiable.

## Evidence

- **Blog post (TURION.AI):** Multi-Agent Orchestration Infrastructure: Lessons from Production — supervisor + specialists emerged as the production standard over peer mesh; coordination cost and failure attribution drive the choice; LangGraph and CrewAI are the primary tooling paths — [URL](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Research (NiteAgent, 2026):** Five major vendors (Anthropic, OpenAI, AutoGen, Cognition, LangChain) converged on orchestrator+isolated-subagents; peer-collaboration GroupChat patterns lost ground; 15× token overhead of multi-agent vs chat confirmed — [URL](https://niteagent.com/blog/multi-agent-production-2026)
- **Microsoft ISE blog:** Coordinator Patterns for Multi-Agent Systems — router pattern as modular monolith evolved to supervisor hierarchy for clear accountability chains; financial services firms favor supervisor for regulatory auditability — [URL](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **Dev blog (Team 400):** OpenAI Agents SDK handoffs vs agents-as-tools — handoffs transfer control and context; agents-as-tools keep the manager in the loop; wrong choice creates permission loops and duplicate work; concrete decision framework provided — [URL](https://team400.ai/blog/2026-04-openai-agent-orchestration-handoffs-guide)

## Gotchas

- **Adding agents doesn't add intelligence** — the 2024 "more agents = smarter" thesis failed empirically. Token overhead explains 80% of variance; adding specialists without a routing logic upgrade just burns budget.
- **Context window management is topology management** — a supervisor pattern with 5 agents all holding full conversation history is worse than a single agent with the same context. Each agent in a supervisor topology should receive only its relevant slice of context.
- **Failure attribution requires explicit contracts** — without per-agent input/output schemas, a failed run produces a wall of interleaved agent outputs with no way to identify which agent made the bad call.
- **The topology you prototype with is not the topology you should ship with** — flat peer topologies are fast to prototype and terrible to operate. Convert to supervisor before production.
