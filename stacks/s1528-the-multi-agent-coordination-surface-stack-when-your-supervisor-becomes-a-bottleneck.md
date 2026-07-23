# S-1528 · The Multi-Agent Coordination Surface Stack — When Your Supervisor Becomes a Bottleneck

Your single orchestrator routes every task, making every routing decision, and holding all context. It works fine with three agents. At twelve agents, it becomes a fragile god-object: one slow step stalls the whole system, one bad routing call corrupts the whole pipeline, and adding a new agent means editing the supervisor's prompt.

## Forces

- **The topology choice is irreversible at scale.** Switching from supervisor to swarm after you've built 8 agents means rewriting every handoff. Teams defer the decision until it has already locked them in.
- **Coordination overhead grows faster than capability.** A supervisor routing between N agents has N handoff points; a full mesh has N×(N-1); a blackboard has 1 shared state but N concurrent readers/writers. Each topology has a different failure mode — and you only discover which one matters when you're at production scale.
- **The framework is not the pattern.** LangGraph, CrewAI, AutoGen, and Swarm each implement coordination primitives — but they don't tell you *which topology* to use for *your* task shape. Teams adopt a framework and inherit its default topology, which may be wrong.
- **Most "agent failures" are handoff failures.** Research across enterprise deployments (AgileSoftLabs, March 2026) finds that the majority of multi-agent failures are not model capability failures — they are failures at the boundaries between agents: dropped context, wrong routing, stale shared state, or unhandled concurrent writes.

## The Move

Choose a coordination topology based on **agent count**, **task dynamism**, and **fault tolerance requirements**. Each pattern is a different shape of trust:

**1. Supervisor (Centralized Coordinator) — 3–8 agents, deterministic pipelines**
- One "manager" agent decides which worker gets each task. Routes by intent classification or tool selection.
- Workers report back to supervisor; supervisor aggregates and decides next step.
- *Best for:* Well-defined task categories, regulated industries (audit trails are linear), when you need one agent to have full visibility.
- *Stack:* LangGraph's `route` node pattern, or a plain `while` loop with a router function.
- *Source:* Databricks/BASF Coatings production deployment (Oct 2025) used a supervisor agent orchestrating both Genie (structured SQL) and vector-search agents through a unified Teams interface. — [Databricks Blog](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)

**2. Swarm (Peer-to-Peer Handoff) — 2–15 agents, dynamic/conversational flows**
- Agents hand off to the next agent directly, with optional context transfer. No central router.
- Each agent decides who to hand to based on its own output — handoff is part of the agent's reasoning.
- *Best for:* Open-ended tasks where the next step is task-dependent (e.g., customer support → refund → escalation → supervisor approval).
- *Stack:* OpenAI Swarm (lightweight, experimental), or LangGraph `StateGraph` with conditional edges.
- *Warning:* Distributed tracing is hard — every handoff is a potential blind spot. QubitTool (May 2026) calls this "observability debt." — [QubitTool](https://qubittool.com/blog/multi-agent-orchestration-patterns)

**3. Hierarchical (Multi-Level Management Tree) — 10–50+ agents, enterprise scale**
- A tree of supervisor agents, each managing a cluster of workers. Top-level supervisor knows the goal; mid-level supervisors know the domain; workers know the tools.
- Each level only sees a summarized view of the level below — prevents context overload at the top.
- *Best for:* Large organizations with domain-aligned teams, complex compliance scopes (finance vs. legal vs. engineering).
- *Stack:* CrewAI's role-based `Crew` with `Process.hierarchical`, or custom LangGraph with typed state between levels.
- *Source:* Microsoft ISE documented this evolution at a retail customer migrating from a modular monolith (single router) to microservices-style agent reuse across teams (June 2026). — [Microsoft ISE Blog](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

**4. Blackboard (Shared Workspace) — variable agents, parallel document/code analysis**
- All agents read from and write to a shared, queryable artifact store. No agent knows about any other directly — coordination is indirect through the shared state.
- Useful when agents work on the same artifact (a document, a codebase, a spec) and the useful order of contributions is unknown in advance.
- *Implementation:* Read what's on the board, contribute what you can, with conflict resolution for concurrent writes. The agent-patterns catalog (2025) describes it as "more flexible than a pipeline, more disciplined than free shared memory." — [Agent Patterns Catalog](https://agentpatternscatalog.github.io/patterns/patterns/blackboard.html)
- *Source:* `claudioed/agent-blackboard` (GitHub, Oct 2025) implements 9 specialized agents (Documentation, API Design, Backend Architecture, Java/Go Development, DDD, Observability) coordinating through a shared knowledge repository with MCP integration. — [GitHub](https://github.com/claudioed/agent-blackboard)

## Evidence

- **HN Ask — Production Orchestration (2026):** Practitioners report building custom orchestrators on LangGraph rather than using framework defaults. Agent-to-agent communication via MongoDB + JSON documents — each agent is an Express endpoint in a V8 isolate, reading from a shared DB layer. "There's absolute 0 framework out there that's good enough for serious work." — [Hacker News](https://news.ycombinator.com/item?id=47660705)
- **HN Ask — Personal Multi-Agent Setup (2026):** Users deploying Scion (Google Cloud Platform) for personal project orchestration — specialized agents for coding, design, testing, and supervision with human-in-the-loop gates. — [Hacker News](https://news.ycombinator.com/item?id=48680842)
- **Databricks/BASF (Oct 2025):** Production supervisor agent for BASF Coatings orchestrating structured Genie agents and unstructured vector-search agents through Microsoft Teams. Demonstrates supervisor pattern handling heterogeneous data domains with a unified user interface. — [Databricks Blog](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)
- **Redis.io Architecture Blog (May 2026):** Across all five agentic patterns, backend requirements converge on shared infrastructure: memory, vector search, caching, and coordination. Tiered memory (short-term session state + long-term semantic retrieval) is the hard part — ranking relevance, expiring stale facts, and keeping consistency as context evolves. — [Redis.io](https://redis.io/blog/agentic-ai-architecture-examples/)
- **Presenc AI Framework Comparison (May 2026):** LangGraph has the largest enterprise production footprint. Framework choice is less consequential than model selection, observability, and error recovery design. CrewAI leads on demo-to-prototype ergonomics; AutoGen leads in research/academic adoption. — [Presenc AI](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026)
- **AgileSoftLabs Enterprise Guide (March 2026):** Multi-agent systems deliver 3× faster task completion and 60% better accuracy vs. single-agent. Gartner documented a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. Most "agent failures" are orchestration and context-transfer issues at handoff points. — [AgileSoftLabs](https://www.agilesoftlabs.com/blog/2026/03/multi-agent-ai-systems-enterprise-guide)

## Gotchas

- **Adding a new agent to a supervisor means editing the supervisor's routing logic.** The supervisor must know every agent to route to it. At ~8 agents, prompts bloat and routing accuracy degrades. Migrate to hierarchical before this happens.
- **Swarm handoffs are invisible to your observability stack.** Unless you explicitly log the handoff event (which agent → which agent, with what context), you cannot reconstruct execution traces. Build handoff logging as a first-class concern, not an afterthought.
- **Blackboard concurrent writes need explicit conflict resolution.** Without it, two agents writing to the same section of a shared document produces garbage. The pattern catalog recommends "contribution contracts" — agents declare what section they will work on before writing.
- **Context summarization at hierarchy levels is lossy.** Mid-level supervisors summarizing worker outputs for the top level will drop edge cases. Build validation loops where the top level can ask the mid-level to expand a summary, or accept that certain failure modes only surface at the worker level.
