# S-2855 · The Coordinator Pattern Stack — When One Agent Isn't Enough But Ten Is Too Many

Your single agent handles most requests well. Then you hit the edge cases: a task requiring domain expertise the agent wasn't trained on, a workflow where parallel execution would cut latency by 80%, a quality gate that catches hallucinations before they reach a user. You split into two agents. Then three. Then the communication overhead, the circular dependencies, and the "which agent owns this decision?" debate become your whole sprint. This is the multi-agent orchestration trap: splitting work helps when done for the right reasons, but most teams split for the wrong ones and end up with coordination costs that dwarf their parallelism gains.

## Forces

- **Coordination overhead scales superlinearly.** Adding agents doesn't just add capacity — it adds communication, shared state, and failure surfaces. Two agents talking to each other are manageable. Ten are a distributed systems problem.
- **The right split is about expertise and autonomy, not parallelization.** Splitting a task into concurrent subtasks only helps if subtasks are roughly independent. Most real tasks have sequential dependencies.
- **Framework choice shapes what coordination patterns are even possible.** LangGraph, CrewAI, and AutoGen implement fundamentally different mental models — switching costs are high, so pick based on where you're going, not where you are.
- **Real production systems reveal patterns demos hide.** Single-agent demos work fine. Multi-agent production reveals failure modes around inter-agent trust, output validation, and resource contention that no benchmark surfaces.

## The Move

**Phase 1 — Split only on real bottlenecks, not theoretical ones.**

Start with a single agent handling the full workflow end-to-end. Profile: where does it slow down? Where does quality degrade? Where does context overflow? Those are your split points. Valid split triggers:
- Different expertise domains (a research agent vs. a coding agent)
- Parallelizable subtasks with no shared state
- Quality control checkpoints where a reviewer catches what a worker misses

Avoid splitting for parallelism alone unless subtasks are genuinely independent.

**Phase 2 — Use a hierarchy, not a mesh.**

Adopt a **coordinator pattern** (top-down routing) over peer-to-peer agent meshes for most production workloads:

```
User → Coordinator Agent → Routing decision → Specialist Agent(s)
                              ↓
                        (sequential OR parallel)
```

The coordinator's job is intent classification and task delegation — it never does the work itself. Specialists are scoped to their domain and tools. This keeps communication paths O(n) instead of O(n²).

Microsoft ISE documented this pattern with a retail customer migrating from a modular monolith (all agents in one app, one orchestrator) to microservices-based domain agents with a coordinator — enabling agent reuse across teams and independent deployments.

**Phase 3 — Constrain tool access by agent role.**

Each specialist agent gets a **minimum viable toolset** — exactly what it needs for its domain, nothing more. LangGraph's state machine model enforces this structurally: you define which tools each node can access. A coding agent gets file I/O and git. A research agent gets web search. A reviewer gets read-only access to outputs. This limits blast radius when an agent takes a wrong turn.

CrewAI's role-based agents implement this more declaratively — agents have explicit roles, goals, and backstories that define scope. This is faster to set up but less fine-grained than LangGraph's state machine.

**Phase 4 — Layer in observability before you need it.**

LangSmith (from LangChain) processes traces from 400+ companies in production, with spans appearing in seconds. Arize Phoenix provides open-source tracing via OpenTelemetry but with noted dashboard latency. Braintrust optimizes for iteration speed — fast experiment scoring and real-time comparison views.

The minimum viable observability stack: trace every inter-agent call (sender, receiver, input, output, latency), log token counts per span, and alert on rate-limited or failed tool calls. Without this, you have no way to distinguish "agent completed the task" from "agent completed the wrong task."

**Phase 5 — Choose your framework based on where you're going, not convenience.**

| Need | Choice |
|------|--------|
| Fine-grained control, durable execution, production observability | LangGraph |
| Fast multi-agent prototypes with role-based agents | CrewAI |
| Human-in-the-loop workflows, Microsoft ecosystem | AutoGen (entering maintenance, successor is Microsoft Agent Framework) |

LangGraph's memory management is strongest — entity memory, vector store retrievers, and checkpointing that lets agents resume after failure. CrewAI uses structured, role-based memory with RAG support. AutoGen focuses on conversation-based memory within multi-turn dialogue.

## Evidence

- **Engineering blog:** Microsoft ISE documented a retail customer moving from a modular monolith chatbot (deterministic router, single orchestrator) to microservices domain agents with a coordinator pattern, enabling independent team deployments and agent reuse — [Orchestration Patterns for Multi-Agent Systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems) (June 2026)
- **Framework comparison:** JetThoughts benchmarked LangGraph, CrewAI, and AutoGen across performance, memory management, and production readiness — finding LangGraph dominates for production systems needing observability and durable execution, CrewAI leads on execution speed for straightforward orchestration — [LangGraph vs CrewAI vs AutoGen 2025](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)
- **Production lessons:** Data-Gate's field report from teams running multi-agent systems at scale in 2026 distilled the core lesson: start with one agent, add complexity only at genuine bottlenecks (domain boundaries, parallelizable independent subtasks, quality gates) — [Multi-Agent Systems in Production: Lessons from the Field](https://data-gate.ch/multi-agent-systems-production-lessons)
- **Enterprise survey:** Gartner projects 70% of organizations building multi-LLM applications will use orchestration platforms by 2028. Imperialis Tech's production guide notes that LangGraph is used at Klarna, Replit, and Elastic for production deployments. AutoGen entered maintenance mode October 2025 with Microsoft Agent Framework as its successor — [Multi-agent AI systems in production](https://imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production) (March 2026)

## Gotchas

- **Routing logic is a hidden LLM call.** Every coordinator decision costs tokens and latency. If your routing logic is itself an LLM call, you've just added an extra model invocation per request — profile before assuming coordination overhead is acceptable.
- **CrewAI's fast execution comes with less structural control.** Role-based agents are faster to set up but harder to debug when they operate outside their intended scope. For anything with financial, security, or compliance implications, LangGraph's explicit state machine is worth the added boilerplate.
- **Checkpointing is not optional in multi-agent systems.** If a specialist agent crashes mid-workflow and you have no checkpoint, the coordinator has no way to know what was already done. LangGraph's checkpointing handles this natively. CrewAI and AutoGen require explicit implementation.
- **AutoGen is entering maintenance.** Teams building new multi-agent systems on the Microsoft stack should evaluate Microsoft Agent Framework rather than AutoGen — existing AutoGen projects will need migration planning.
