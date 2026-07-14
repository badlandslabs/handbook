# S-1107 · The Supervisor or Message-Bus Stack — When Your Multi-Agent System Can't Decide Who Is in Charge

You built a team of specialized agents. The problem is not their individual capability — it is the invisible question of who decides what gets done next. In a supervisor pattern, one agent calls the shots and delegates. In a message-bus pattern, agents claim tasks themselves from a shared queue. The choice is not cosmetic. It determines whether your system is controllable or chaotic, and it is harder to change after you have committed to one direction.

## Forces

- **A supervisor becomes a bottleneck.** The orchestrator agent in a hierarchical pattern carries the entire workflow's state. When it fails or degrades, everything stops. But it also means you have a single point of control for debugging, retries, and human override.
- **Message buses distribute failure but create contention.** Agents pick their own tasks from a shared queue — no single point of failure, but agents can duplicate work, step on each other, or return conflicting results if the task ownership contract is weak.
- **Framework defaults push you toward one pattern before you understand the trade-off.** LangGraph defaults to graph-based orchestration (supervisor-like). AutoGen defaults to peer conversation. CrewAI defaults to role-based delegation. Each encodes a philosophy about who is in charge.
- **Hybrid is tempting but adds operational complexity.** Some teams layer a coordinator on top of a bus — the coordinator enqueues, agents pick from the bus. This combines benefits but doubles the coordination surface.

## The Move

**Choose your coordination topology explicitly, before you pick a framework.**

### Supervisor / Hierarchical Pattern

One agent (the supervisor/coordinator) holds the task graph and delegates to specialized agents:

```
Supervisor Agent
  ├── Researcher Agent → returns findings
  ├── Writer Agent → receives findings → produces draft
  └── Editor Agent → receives draft → produces final
```

- Best for: linear or branching pipelines where execution order matters, and where you need a single place to observe the full workflow.
- Implementation: LangGraph `invoke()` chains, Semantic Kernel with a Planner, or a custom Python orchestrator on Modal.com.
- Data passing: Supervisor packages context for each delegate. The delegate returns output; the supervisor decides the next step.
- From production: WAYR TODAY runs a 5-agent sequential pipeline on Modal.com with a custom Python orchestrator — Discovery → Classifier (Gemini 2.0) → Rewriter → Publisher → Social. Each stage's output feeds the next; the orchestrator owns sequencing.

### Message-Bus / Claim-Pattern

Agents subscribe to a shared queue; one agent claims each task exclusively:

```
Task Queue (MongoDB / Redis / etc.)
  ├── [task_1] → claimed by Agent A
  ├── [task_2] → claimed by Agent B
  └── [task_3] → unclaimed

Agent A ──reads──> [task_1] ──claims──> processes ──writes──> result
Agent B ──reads──> [task_2] ──claims──> processes ──writes──> result
```

- Best for: parallel workloads where agents are functionally independent and order does not matter, or where you want agents to scale independently.
- Implementation: MongoDB shared layer with pipeline IDs, Redis pub/sub, or lightweight packages like `kagehq/bus`.
- Data passing: Each agent reads/writes JSON documents linked by pipeline ID. The bus handles task routing, not a central orchestrator.
- From production: pablovarela on HN runs each agent as a separate Express endpoint in a V8 isolate, communicating through MongoDB with shared pipeline IDs. The coordinator endpoint chains agents but agents themselves are stateless.

### Recovery Differences

| Failure Mode | Supervisor | Message Bus |
|---|---|---|
| Orchestrator dies | Entire pipeline stops | Agents continue independently |
| One agent dies | Pipeline stage fails, can retry at supervisor | Task remains in queue, another agent can claim |
| Duplicate execution | Impossible (supervisor delegates) | Possible without claim-lock |
| Observability | Single call graph | Distributed, needs trace correlation |
| Human override | Kill/restart at supervisor | Requires queue intervention |

## Evidence

- **HN Ask HN (production orchestration survey):** Practitioners report a split between rolling their own with Node.js + MongoDB (pablovarela — each agent in a V8 isolate, shared MongoDB layer, coordinator endpoint chains them) and building on top of LangGraph/CrewAI for the graph structure. Session state scoped to "agent" (persists across runs) vs "swirl" (one run only) is a common abstraction. — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **WAYR TODAY autonomous newsroom:** 5-agent sequential pipeline on Modal.com. Custom Python orchestrator owns sequencing; agents are specialized (Discovery, Classifier, Rewriter, Publisher, Social). Gemini 2.0 for classification, custom models for other stages. Architecture validates that linear pipelines favor supervisor control for sequencing clarity. — [wayr.today/how-it-works](https://wayr.today/how-it-works/)
- **KageHQ Bus (HN Show HN):** Lightweight message bus for multi-agent systems. Explicitly solves the problem of agents duplicating work and stepping on each other's tasks by enforcing that only ONE agent handles each task. Represents the bus-pattern approach to agent coordination. — [github.com/kagehq/bus](https://github.com/kagehq/bus)
- **Iterathon framework comparison (2026):** LangGraph dominates for graph-based state machines (developer control, explicit flow). CrewAI for role-based teams (fast setup, less flexibility). AutoGen for multi-agent conversations (peer model, harder to control). Microsoft Semantic Kernel + AutoGen as a combined stack — Semantic Kernel builds individual agents, AutoGen orchestrates collaboration. — [iterathon.tech/blog/ai-agent-orchestration-frameworks-2026](https://iterathon.tech/blog/ai-agent-orchestration-frameworks-2026)
- **Microsoft Agent Framework:** Open-source (MIT, 12K+ stars, April 2025) framework supporting Python and .NET with consistent APIs. Supports declarative agent definitions, model-agnostic agent providers (Azure OpenAI, OpenAI, GitHub Models, Ollama), memory components, and built-in observability. Represents the framework-backed supervisor pattern. — [github.com/microsoft/agent-framework](https://github.com/microsoft/agent-framework)

## Gotchas

- **Picking a framework before choosing a topology.** LangGraph, CrewAI, AutoGen, and Semantic Kernel each encode a coordination philosophy. If you scaffold your agents in CrewAI's role-based structure and later need peer-to-peer coordination, you fight the framework.
- **Claim locks are not free.** Message-bus systems need atomic claim operations (Redis `SETNX`, MongoDB `findOneAndUpdate` with a filter). Without them, two agents can claim the same task and duplicate work.
- **Supervisor context grows with pipeline depth.** In a 5-stage pipeline, the supervisor agent holds all prior outputs in context. After stage 3, you are paying for all of stages 1–2 to be re-read on every call. Memory summarization or checkpointing becomes necessary.
- **The "supervisor agent" can itself become a bottleneck in capability.** If your orchestrator is a weak model trying to coordinate strong specialized agents, it under-performs both. Give the supervisor enough capacity to reason about the workflow, not just the domain.
- **Hybrid systems need explicit failure boundaries.** When a coordinator enqueues tasks and agents pick from a bus, you need to decide: does the coordinator retry failed tasks, or does the bus? Ambiguity here creates zombie tasks that never complete and are never retried.
