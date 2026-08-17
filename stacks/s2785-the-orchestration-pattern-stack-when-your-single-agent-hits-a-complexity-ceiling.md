# S-2785 · The Orchestration Pattern Stack — When Your Single Agent Hits a Complexity Ceiling

Your agent works fine on simple tasks. Then you give it something real — multi-domain research, code review with testing, a workflow that branches based on partial results — and it starts dropping steps, losing context, or just doing the wrong thing confidently. You've heard multi-agent orchestration is the answer. It is, but it comes with its own class of failures that are harder to debug than a single broken chain.

## Forces

- **Context poisoning** — as tasks grow, the agent's context window fills with accumulated history; performance degrades via the lost-in-middle effect and attention dilution. Splitting across agents fixes this but introduces coordination overhead that can make things worse.
- **Parallelism vs. correctness** — you can run subagents in parallel for massive time savings, but unordered concurrent execution means you lose determinism and introduce race conditions in shared state.
- **The compound reliability problem** — every agent-to-agent handoff multiplies failure probability. At 90% per-step reliability across 5 steps: 59% success. At 10 steps: 35%. Add 4 agents and token costs are 3.5× higher than a single agent.
- **The anthropomorphic trap** — teams assign agents role labels ("Architect", "QA", "PM") thinking specialization is the point. The actual point is **context isolation**: sub-agents exist to keep each reasoning window clean, not to mimic org charts.
- **Orchestration is infrastructure** — unlike a simple chain, orchestration code is stateful, non-deterministic, and controls external side effects. It needs the same operational rigor as a distributed system.

## The Move

Choose an orchestration topology based on the failure mode you're trying to solve — not the framework's marketing.

**1. Supervisor (hierarchical router)** — One central agent inspects incoming state and dispatches to specialized workers. Workers return results; supervisor synthesizes. Best for: open-ended tasks where a lead needs to decide *who* does *what* based on partial information. LangGraph's `Supervisor` node routes to worker subgraphs via a durable checkpointer. At scale, swap in-process calls for an external message queue (Redis, SQS) — a crashed worker no longer kills the request.

**2. Parallel workers with merge** — One orchestrator fans out to N agents running concurrently, each operating in a clean context window, then their outputs are merged. Best for: research, data extraction, independent analysis tasks. Anthropic's internal eval showed **+90.2% performance gain** over single-agent for complex research tasks, with **up to 90% time reduction** via parallelization. Critical: give each worker a narrow, well-scoped toolset. Anthropic found that better tool descriptions alone delivered a **40% decrease in task completion time**.

**3. Sequential pipeline** — Output of agent A feeds directly into agent B. Best for: tasks where order is non-negotiable and each step's output must be correct before the next begins. The simplest pattern, lowest coordination overhead. Risk: a single failure cascades. Semantic Kernel's `SequentialOrchestrator` formalizes this.

**4. Handoff (round-robin)** — Agents explicitly transfer control to another agent with a structured message. Best for: complex customer support flows, multi-tool workflows where one agent exhausts its capabilities. Microsoft's AutoGen (now merging into Semantic Kernel) implements this as nested conversations — an agent can spin up a sub-conversation to resolve a subtask, then return the result to the parent.

**5. Group chat with consensus** — All agents participate in a shared conversation; a moderator or voting mechanism selects the final output. Best for: tasks where multiple perspectives are genuinely needed and no single agent has the right answer. Highest coordination cost; highest potential for deadlocks (36.9% of multi-agent failures are coordination breakdowns).

**The operational foundation** regardless of topology:
- **Durable checkpointing** — serialize state between steps so a crash doesn't restart from scratch
- **External message queues** for fault isolation when scaling beyond a single process
- **Bounded context per agent** — the narrower the toolset and prompt, the more reliable the agent
- **Structured output schemas** — use Pydantic or JSON Schema to constrain what agents can return at each handoff, reducing the surface area for interpretation errors
- **Token budgets per step** — track and cap how many tokens each subagent can spend, as 80% of performance variance in Anthropic's eval was explained by token usage alone

## Evidence

- **Engineering blog (Anthropic, Jun 2025):** Multi-agent research system using orchestrator-worker pattern with parallel subagents. **+90.2% performance gain** on internal research eval vs. single agent. Parallelization cut research time by **up to 90%**. Tool description improvements yielded **40% decrease** in task completion time. 80% of eval performance variance explained by token usage alone. — [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Enterprise engineering post (Databricks + BASF, Oct 2025):** Supervisor agent architecture deployed for BASF Coatings to orchestrate cross-team enterprise AI. Supervisor unifies modular, specialized agents under a single interface while preserving data ownership across teams. Key lesson: the supervisor pattern solved knowledge asymmetry and compliance requirements that no single agent could handle. — [databricks.com/blog/multi-agent-supervisor-architecture](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)

- **Industry analysis (Towards Data Science, 2026):** Multi-agent failure rates of **41%–86.7%** across surveyed deployments. **36.9% of failures** are coordination breakdowns. Unstructured multi-agent systems produce **17.2× worse error rates** than single-agent baselines. **40% of agentic AI projects** will be canceled by Gartner's 2027 horizon. Token cost multiplier for 4-agent systems: **3.5×**. — [towardsdatascience.com/the-multi-agent-trap](https://towardsdatascience.com/the-multi-agent-trap)

- **Framework documentation (Microsoft, May 2025):** Semantic Kernel ships 5 orchestration patterns — Sequential, Concurrent, Group Chat, Handoff, Hierarchical — formalizing what production teams actually need. AutoGen's nested conversation model (agent-initiated sub-conversations) enables recursive delegation. — [devblogs.microsoft.com/agent-framework/semantic-kernel-multi-agent-orchestration](https://devblogs.microsoft.com/agent-framework/semantic-kernel-multi-agent-orchestration)

- **HN discussion (real practitioners, 2025):** Thread on production multi-agent setups found consensus: agents work for narrow, well-bounded tasks; broad orchestration setups "burn tokens" without reliable results. Key pain: cross-agent state sharing is the missing piece. — [news.ycombinator.com/item?id=48559933](https://news.ycombinator.com/item?id=48559933)

- **GitHub repo (yx-fan/multi-agent-orchestration-framework):** Open-source LangGraph + FastAPI framework implementing modular orchestration with separate `orchestrator/`, `agents/`, `memory/`, `tools/` directories — a reference architecture for teams building this in production. — [github.com/yx-fan/multi-agent-orchestration-framework](https://github.com/yx-fan/multi-agent-orchestration-framework)

## Gotchas

- **Adding agents doesn't fix bad agents.** If your single agent is unreliable, multi-agent orchestration will amplify every failure. Fix the single-agent reliability first (structured outputs, bounded toolset, eval harness) before distributing.
- **Context isolation is the point, not role-playing.** Don't build an "Architect" agent because it sounds right. Build it because you have a specific context window that needs to be kept clean from another agent's output.
- **Token budgets collapse silently.** Multi-agent systems consume 3.5–15× more tokens than a single-agent equivalent. Without per-step budgets and monitoring, you'll hit cost overruns before you hit reliability problems.
- **Coordination failures are invisible until they aren't.** A 36.9% failure rate from coordination breakdowns means the system works fine 63% of the time — until a critical workflow deadlocks with no visible error.
- **Queue-based scaling adds latency.** Moving from in-process routing to an external message queue gives fault isolation, but adds 50–200ms of latency per hop. Profile the actual user impact before committing to the infrastructure complexity.
