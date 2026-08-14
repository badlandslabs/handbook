# S-2621 · The Multi-Agent Handoff Stack — When Your Agent Knows Too Much and Does Too Little

Your single agent tries to be the expert, the planner, the researcher, and the reviewer — all at once. Its prompt is 3,000 words. It frequently drops context between steps, contradicts itself mid-task, and has no recovery path when it takes a wrong turn. The problem is not the model. It is the architecture: one agent with no decomposition, no handoff discipline, and no separation of concerns.

## Forces

- **Supervision overhead vs. delegation quality** — a supervisor that can't let go becomes a bottleneck; one that delegates too freely loses coherence. The line is hard to tune.
- **Context transfer is where agents die** — the handoff between agents is consistently where multi-agent systems fail. Not in the individual agent logic, but in what gets passed (or lost) at the boundary.
- **Adding agents multiplies failure surfaces** — every additional agent introduces a new coordination point. But it also introduces a new specialization vector. The tradeoff is real but manageable.
- **Debugging cross-agent failures is fundamentally different** — you can't just read one trace. You need observability across the handoff graph, not just within a single agent loop.
- **The orchestration pattern determines more than the model does** — Microsoft Azure's agent design guide explicitly states that orchestration is the highest-impact architectural decision in multi-agent systems, more than model choice or prompt tuning.

## The move

**Model your multi-agent system as a graph first, then assign agents to nodes.**

### Pattern 1: Supervisor with Short-Term Memory Scoping

A supervisor agent (usually a capable model) decides routing at each step. Specialists execute. The supervisor holds the **short-term memory of the current run only** — it does not need long-term memory unless the workflow genuinely requires it. Most teams over-build this layer.

```
Supervisor (routing + state) → Agent A (specialist) → Agent B (specialist) → Supervisor (aggregate + respond)
```

Key: keep supervisor prompts focused on **routing logic and result synthesis**, not domain knowledge. Offload domain expertise to specialists.

**Implementation in LangGraph:**
- Use `langgraph_supervisor` library (LangChain, 2025) or manual supervisor pattern with conditional edges
- Supervisor receives structured output from each specialist; no free-form conversation between agents
- Add a `max_hops` guard: if the supervisor routes more than N times without converging, escalate to human review

### Pattern 2: Structured Handoff with Shared Workspace Artifact

The agent handoff pattern (CrewAI's native model, Azure Agentic Lab's Magentic pattern) works when agents communicate through a **typed artifact** — a JSON document, a shared scratchpad, or a structured brief — rather than raw conversation. This is the key insight from Zach Wills's swarm operation: *"You manage a swarm through what survives the session: the ticket, the branch, the brief. Never the context window."*

```
Agent A writes structured_output { task, findings, blockers, confidence } → Agent B reads and responds
```

Rules for the artifact:
- **Schema-first**: define the artifact structure before the first agent runs
- **Append-only for audit**: agents append findings, never overwrite previous agents' outputs
- **Confidence field**: each agent rates its own confidence; downstream agents can decide whether to trust or re-verify
- **Blocker flag**: if any agent hits an unresolved blocker, the artifact carries it explicitly rather than silently failing

### Pattern 3: Parallel Fan-Out with Result Aggregation

For tasks where sub-problems are independent (data fetching, parallel analysis, multi-source review), spawn agents concurrently and aggregate. This pattern, documented in Azure's Concurrent Execution pattern, reduces wall-clock time dramatically for I/O-bound work.

```
Supervisor → [Agent A, Agent B, Agent C] (parallel) → Supervisor (aggregates results)
```

Critical: plan for **partial failure**. If 3 of 5 parallel agents succeed, the supervisor needs logic to decide: retry failures, proceed with 3, or abort. deepsense.ai's field data shows teams achieving 40–70% reduction in manual resolution time using this pattern with structured output.

### Pattern 4: Constrained Handoff Count

Zach Wills's revised rule (2026) replaces "A long-running agent is a bug" with: **"Every agent has a hard exit. If it hasn't finished in N steps, it writes its state to the artifact and hands off."** The swarm of 20 agents worked not because each agent was smart, but because each agent was **short-lived and replaceable**.

This is also the MAST taxonomy insight from glukhov.org: coordination breakdowns account for ~33% of multi-agent failures, and most are preventable with explicit handoff limits.

### The Emerging Standards: A2A and MCP

Two protocols are emerging as the interoperability layer for multi-agent systems in 2025–2026:

- **A2A (Agent-to-Agent)**: protocol for structured handoff between agents from different vendors/frameworks. Designed to solve the "agent A from CrewAI needs to hand off to agent B from LangGraph" problem.
- **MCP (Model Context Protocol)**: the tool-sharing layer. Lets agents use each other's tools without tight coupling. OpenAI, Anthropic, and the broader ecosystem are converging on this.

Teams building multi-agent systems today should design for A2A/MCP compatibility even if not immediately using cross-framework agents.

## Evidence

- **HN Discussion (263 points):** "LLM Agents Are Simply Graph" — the fundamental insight that all agentic frameworks (OpenAI Agents SDK, Pydantic AI, AutoGPT, Manus AI) are internally implemented as graphs with nodes = LLM calls/tool executions and edges = transitions. This reframes agent development from prompt engineering to graph engineering. — [https://news.ycombinator.com/item?id=43417511](https://news.ycombinator.com/item?id=43417511)

- **Azure Architecture Center (Microsoft, 2026):** Documents 5 canonical orchestration patterns — sequential, parallel, supervisor, handoff, and group chat — with explicit tradeoffs. Key insight: the orchestration pattern determines latency, fault tolerance, scalability ceiling, and debugging complexity more than any other architectural choice. — [https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

- **Zach Wills (zachwills.net, 2025/2026):** Operated a swarm of 20 AI agents for a week, producing ~800 commits and 100+ PRs. Revised rules after a year of daily practice: handoff discipline through artifacts (tickets, branches, briefs) beats context window management. Explicit max-step exits per agent prevent runaway loops. — [https://zachwills.net/i-managed-a-swarm-of-20-ai-agents-for-a-week-here-are-the-8-rules-i-learned/](https://zachwills.net/i-managed-a-swarm-of-20-ai-agents-for-a-week-here-are-the-8-rules-i-learned/)

- **deepsense.ai Field Report (2025):** Senior engineers from deepsense.ai (Anthropic + OpenAI service partners) report that structured multi-agent orchestration with memory layers cut manual resolution time by 40–70% and inference costs by up to 35% via caching and routing. — [https://deepsense.ai/resource/ai-agents-lessons-learned-in-the-field/](https://deepsense.ai/resource/ai-agents-lessons-learned-in-the-field/)

- **Glukhov Multi-Agent Orchestration Guide (2026):** Analysis of production multi-agent failures: MAST taxonomy finds ~33% specification ambiguity, ~33% coordination breakdowns, ~33% verification gaps. Coordination breakdowns are the most preventable with structured handoff limits and shared workspaces. — [https://www.glukhov.org/ai-systems/architecture/multi-agent-orchestration-patterns/](https://www.glukhov.org/ai-systems/architecture/multi-agent-orchestration-patterns/)

- **Azure/agent-innovator-lab (GitHub, MIT):** Production reference implementations of supervisor, plan-and-execute, and group chat patterns. Demonstrates structured handoff under a central controller with observability layers. — [https://github.com/Azure/agent-innovator-lab](https://github.com/Azure/agent-innovator-lab)

## Gotchas

- **No observability into handoffs means you can't debug failures.** Instrument every handoff with trace IDs and structured output. If you can't answer "which agent ran at step 3 and what did it output," you can't debug.
- **Over-engineering handoffs before you have real routing logic.** A simple shared workspace beats a full A2A implementation for teams with 2–3 agents. Protocol complexity must match coordination complexity.
- **Letting agents run too long before handoff.** The biggest coordination failure mode is an agent that tries to do too much before handing off — it accumulates context, introduces contradictions, and creates a larger recovery surface if it fails. Short-lived agents with explicit state artifacts are more maintainable.
- **Ignoring partial failure in parallel fan-out.** When 3 of 5 parallel agents succeed, the system doesn't fail loudly. It returns partial results that look plausible. Build explicit partial-failure logic into your aggregation supervisor.
- **The supervisor becomes a single point of failure.** If the supervisor prompt degrades or its routing logic has edge cases, the entire system degrades. Treat supervisor prompts as production code with tests, not configuration.
