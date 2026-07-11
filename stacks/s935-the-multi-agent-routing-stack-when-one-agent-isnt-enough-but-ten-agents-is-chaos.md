# S-935 · The Multi-Agent Routing Stack — When One Agent Isn't Enough But Ten Agents Is Chaos

You built an agent. It works. Then the use case grows: research, synthesis, fact-checking, formatting — each with different tool needs, latency profiles, and failure modes. You add all of it to one agent. Context window explodes. Tool list grows to 40. The agent starts calling Slack when it means to call the database. One agent can't hold the full workflow and stay reliable. But ten agents without a router is just ten failing independently.

This is the multi-agent routing problem: how do you decompose a workflow into specialized agents and reliably route tasks to the right one, at the right time, with coherent shared state?

## Forces

- **Task heterogeneity breaks single-agent reliability.** Research tasks want breadth (many parallel calls). Execution tasks want depth (sequential, stateful steps). A single agent handling both either over-parallelizes execution or over-sequentializes research.
- **Static routing is brittle; dynamic routing is complex.** Hard-coding "if X, then agent Y" works until X changes — then you're patching conditionals forever. Dynamic semantic routing solves flexibility but adds infrastructure.
- **Shared state across agents is where things quietly break.** Agent A writes to memory. Agent B reads it 3 steps later but the format changed. No error, no crash — just silently wrong output.
- **The number of agents grows faster than the routing logic.** Teams add agents for every new capability without a corresponding routing architecture, resulting in N×N communication complexity.
- **Token cost compounds non-linearly.** Anthropic's own Research feature costs 15× more tokens than a single agent but delivers 90.2% quality improvement. The math only works when task structure genuinely decomposes into parallel independent threads.

## The Move

Decompose on task structure, not capability boundaries. Route on semantics, not conditionals. Share state explicitly, not implicitly.

**Step 1 — Identify the orchestration pattern from your task's shape.**

| Task shape | Pattern | Frameworks |
|---|---|---|
| Sequential steps with branching (DAG) | **DAG/State Machine** | LangGraph, Temporal, Dagster |
| Many independent parallel threads feeding one synthesis | **Orchestrator-Worker** | Custom, Anthropic Research |
| Independent agents with message-passing | **Actor/Swarm** | AutoGen/MAF, Kafka+A2A+MCP |
| Async event-driven reactions | **Event-Driven** | Kafka-native, pub/sub stacks |

**Step 2 — Use a supervisor (router) agent to select, not a central orchestrator to control.** The supervisor pattern from Microsoft ISE's production work uses a lightweight routing agent that: (a) classifies the incoming intent, (b) selects the 1–3 specialized agents needed, (c) passes a constrained context window to each. The supervisor does not do the work — it decides who does.

**Step 3 — Establish an agent registry with capability descriptions, not just names.** Dynamic agent selection requires a registry mapping task-type → agent-capability. As Microsoft ISE documented: "Accurate Agent Selection" is the first core requirement of scalable multi-agent systems. Name-based routing (hard-coded if/else) does not scale past 5 agents.

**Step 4 — Route on semantic similarity, not keyword matching.** Use a lightweight embedding model or LLM-based classifier to match task descriptors to agent capability descriptions. This handles the "Slack vs database" confusion: when the agent's intent is "send a notification," semantic routing maps to the notification agent, not the nearest-named tool.

**Step 5 — Use explicit typed state channels for inter-agent communication.** Don't rely on shared memory or global context. Each agent-to-agent handoff should pass a typed message with schema. LangGraph's checkpointing is the production standard for this — Elastic, Replit, and Klarna all use it for durable state across agent handoffs.

**Step 6 — Set hard step budgets per agent, not per workflow.** Anthropic's internal eval used 3–5 subagents per research thread. Beyond that, token cost grows superlinearly and quality plateaus. Set a max steps per agent and escalate to supervisor on timeout.

## Evidence

- **Engineering blog (Microsoft ISE, Nov 2025):** Documented the supervisor pattern from a production e-commerce deployment with "Accurate Agent Selection," "Optimized LLM Usage," and "Efficient Orchestration" as the three core requirements. The case study showed dynamic agent routing reduced irrelevant agent invocations by routing on semantic task classification rather than static rules. — [https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale/](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale/)

- **Research analysis (Zylos Research, Apr 2026):** Systematic survey of three orchestration schools — DAG-based (LangGraph, Temporal, Dagster), Event-Driven (Kafka+A2A+MCP), and Actor Model (AutoGen/MAF) — with decision guides for when each applies. Notes: "Agent coordination deserves the same engineering discipline as distributed systems in general." — [https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)

- **Anthropic internal eval (The AI Engineer, May 2025):** Claude's Research feature is an orchestrator-worker system: a lead agent spawns 3–5 specialized subagents in parallel, each with its own context window, then synthesizes findings. Internal eval: 90.2% improvement over single-agent Opus 4 on breadth-first research tasks; 15× token cost. "Architecture follows task structure. Multi-agent only wins when the task decomposes into independent parallel threads." — [https://theaiengineer.substack.com/p/how-anthropic-built-multi-agent-deep](https://theaiengineer.substack.com/p/how-anthropic-built-multi-agent-deep)

## Gotchas

- **Adding agents because the diagram looks good.** Per Fountain City Tech's validation of Anthropic's blueprint: "The mistake to avoid is adding agents because the architecture diagram looks impressive; the goal is to remove jobs from human supervision, never to create more agents for a human to supervise." Every agent is a component to debug, monitor, and pay for.
- **N×N communication complexity.** Without a hub-and-spoke or supervisor pattern, N agents each talking to each other creates O(N²) connection points. Every new agent requires O(N) new integration tests. The supervisor pattern limits connections: each specialized agent only talks to the supervisor.
- **Context window pressure from aggregating agent outputs.** The supervisor's synthesis step must process all worker outputs. If you have 5 workers each returning 8K tokens, the supervisor needs 40K+ tokens just for aggregation before it can synthesize. Size your supervisor's context accordingly.
- **Failure propagation without circuit breakers.** If one subagent hangs or loops, the whole workflow stalls. Per Zylos Research's production guidance: use supervision hierarchies (actor model) with explicit retry budgets and escalation paths. A hung agent should trigger a timeout and escalate, not block the workflow.
