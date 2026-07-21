# [S-1429] · The Supervisor / Orchestrator-Worker Stack

> When your single agent is degrading under tool overload and context bloat — but a full swarm feels like coordinating chaos for a task that mostly just needs a router.

The moment you give an agent more than 5–7 tools, or ask it to do more than one job, quality collapses. Splitting into multiple agents helps — but without a coordinator, you have a pile of workers and no foreman. The supervisor pattern (also called orchestrator-worker) threads that needle: one central agent that plans, routes, and assembles while specialist workers each do one thing well.

## Forces

- **Context window is finite and expensive** — a single agent handling research → analysis → write → review burns through tokens fast; later steps get degraded context.
- **Model cost is not uniform** — a capable model for routing decisions costs 10–40× what a task-specific worker model costs. Running everything on one model is waste.
- **Specialization beats generality** — one agent with ten tools ≠ ten agents with one tool. Tool selection accuracy degrades as scope grows.
- **Failure propagation** — without explicit handoff protocols, a worker failure can crash the whole pipeline or get silently swallowed.
- **Latency compounds** — sequential delegation is simple but slow; parallel delegation requires synchronization and partial-failure handling.

## The Move

The supervisor pattern runs a **central orchestrator agent** (capable model, high reasoning) that:
- Receives the top-level task
- Breaks it into subtasks based on capability requirements
- Routes each subtask to the right specialist worker agent
- Handles worker handoffs, error recovery, and result assembly
- Decides when to loop, escalate, or finish

Workers run **task-specific models** (cheaper, focused) with narrow tool sets. Handoff is explicit — the supervisor passes structured state, not just a prompt string.

**Concrete implementation in LangGraph** (the most mature open-source approach):

```python
# Supervisor decides which agent to call next
def supervisor_node(state: MultiAgentState) -> MultiAgentState:
    decision = llm.with_structured_output(SupervisorDecision).invoke(state["messages"])
    return {"next": decision.next_agent, "reasoning": decision.reasoning}

# Workers expose a handoff tool
handoff_to_researcher = create_handoff_tool(
    agent_name="researcher",
    description="Transfer to the research specialist for web searches and data gathering"
)

# Supervisor routes by calling the handoff tool
# Workers return results + call handoff_to_supervisor to return control
```

**CrewAI equivalent** uses `Crew` with `Task` definitions and agent `role`/`goal`/`backstory`:

```python
researcher = Agent(role="Research Analyst", goal="Find accurate data", backstory="...")
writer = Agent(role="Content Writer", goal="Write clear reports", backstory="...")

crew = Crew(agents=[researcher, writer], tasks=[research_task, write_task], process="hierarchical")
```

### Decision matrix

| Scenario | Pattern | Agent count |
|---|---|---|
| Sequential pipeline (clean → enrich → summarize) | Pipeline | 2–4 |
| Dynamic routing, one decision-maker | Supervisor | 3–8 |
| Peer handoff, no central authority | Swarm | 2–15 |
| Enterprise scale, 15+ agents, layered management | Hierarchical | 10–50+ |

### Cost optimization

- Run supervisor on capable model (e.g., GPT-4o, Claude Sonnet)
- Run workers on cheaper models (GPT-4o-mini, Haiku, Qwen) scoped to their task
- Reported cost reduction: **40–60%** vs. running all agents on the supervisor-tier model (beam.ai, 2026)

### State management

Supervisor maintains shared state across handoffs:
- `TaskStatus` enum per worker (pending / in_progress / done / failed)
- Accumulated results buffer
- Conversation history pruned to relevant window per worker
- Explicit handoff messages so each worker sees only what it needs

## Evidence

- **Databricks Blog / BASF Coatings (2025):** Production supervisor architecture using LangGraph to coordinate Databricks Genie agents (structured SQL + unstructured data) for the Marketmind platform. 1,000+ sales reps served globally via Microsoft Teams. Supervisor routes between domain-specific agents; workers handle function-calling within their data domain. — [URL](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)

- **Beam.ai / Fredrik Falk (July 2026):** 6-pattern production guide citing Gartner data: 1,445% surge in multi-agent inquiries (Q1 2024→Q2 2025), average 12 agents per org, **40% of pilots fail within 6 months** — not from agent quality but from wrong pattern selection or missing failure handling. Orchestrator-worker pattern recommended for cross-functional workflows with clear task decomposition. — [URL](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)

- **Tellius / ZenML LLMOps Database (2025):** Multi-agent analytics platform (text-to-insights) using deterministic planning layer + semantic governance + specialist agents for query compilation, execution, and result formatting. Key lesson: **~95% of AI pilot failures stem from product-level gaps** (ambiguity handling, observability, consistency) not model quality. Independent sub-queries run in parallel, capped concurrency to avoid warehouse thrashing. — [URL](https://www.zenml.io/llmops-database/building-production-grade-agentic-ai-analytics-lessons-from-real-world-deployment)

- **QubitTool / Tech Blog (May 2026):** Multi-agent orchestration comparison: supervisor (centralized routing, 3–8 agents), swarm (decentralized handoff, 2–15 agents), hierarchical (tree management, 10–50+). Notes production non-negotiables: timeouts, observability, graceful degradation. — [URL](https://qubittool.com/blog/multi-agent-orchestration-patterns)

- **MMC Ventures / State of Agentic AI (November 2025):** Survey of 30+ European agentic AI founders + 40+ enterprise practitioners. Finding: **technical challenges are not the primary barrier** — workflow integration, human-agent interface, and employee resistance dominate. Agents average 4.2 tools per deployment. — [URL](https://mmc.vc/research/state-of-agentic-ai-founders-edition/) (HN discussion: [https://news.ycombinator.com/item?id=45808308](https://news.ycombinator.com/item?id=45808308))

## Gotchas

- **Handoff loops** — without an explicit termination condition, a supervisor and worker can ping-pong indefinitely. Add a `max_iterations` cap and a final `finish` route.
- **Context leakage between workers** — each worker should see only the task brief + accumulated output, not the full conversation. Prune aggressively.
- **Supervisor becomes the bottleneck** — if the orchestrator model is slow or rate-limited, the whole pipeline waits. Profile your routing latency separately from worker latency.
- **Partial failure is the default** — when 3 of 4 parallel workers succeed, the supervisor must decide: retry failed ones, proceed with partial results, or abort. Handle this explicitly before going to production, not after.
- **Human escalation gates** — for irreversible actions (delete, send, spend, deploy), the supervisor should hand off to a human approval step, not route through an agent. The EU AI Act mandates explicit human oversight for high-risk agentic systems from August 2026.
