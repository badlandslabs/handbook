# S-748 · Multi-Agent Production — The Four Foundations That Actually Hold

The promise is compelling: specialized agents dividing complex work. The reality in 2025-2026 is a narrower set of patterns that have actually shipped, with failure modes now documented by practitioners across dozens of production deployments. The gap between demo and production multi-agent is almost entirely in four foundations — and teams that get any one of them wrong rewrite everything within 12 months.

## Forces

- **Starting multi-agent when you don't need it is the most expensive mistake.** Most "multi-agent" production systems are actually supervisor + specialists, which is one agent with tool-calling. Add agents only when a genuine boundary appears — conflicting concerns, different trust levels, or audience segmentation.
- **State management is where production systems die quietly.** Without typed, scoped shared state and checkpointing, failures in one agent cascade silently. Long-running workflows lose context mid-execution and nobody notices until the output is garbage.
- **Non-LLM costs are invisible until they're 27% of your bill.** LLM cost is what shows in the dashboard. Tool calls, external APIs, vector DB queries, retries, and observability overhead routinely add 15-40% on top. In heavy multi-turn workflows, non-LLM costs can exceed LLM costs entirely.
- **Agent boundaries drawn by workflow step are wrong.** Boundaries should be drawn by audience, timing, or trust — not by which step comes next in the pipeline.

## The Move

Four foundations, in order of what breaks first:

**1. Draw agent boundaries on concerns, not steps.**
- Split when: conflicting goals (helpful vs. impartial evaluator), different trust/data access levels, different update cadences, or different audiences. Not when "we need a researcher and a writer."
- Start with one agent. Add specialists only when the boundary is genuine and you can articulate the concern that makes them separate.

**2. Use typed, scoped shared state with checkpointing.**
- Define explicit schemas for inter-agent communication — not freeform tool outputs.
- Checkpoint state at every handoff so failed agents can resume, not restart.
- State in memory for short runs; persist to Postgres or Redis for anything user-facing or >5 minutes.

**3. Explicit error handling — retries, fallbacks, and hard timeouts on every agent.**
- Every LLM call needs a retry budget (typically 2-3x).
- Every tool call needs a fallback: what does the agent do if the vector DB is slow? If the search API fails?
- Hard timeout per agent: if an agent runs >60s, escalate or fail gracefully. "Runaway thinking" — agents looping on tool calls — is the #1 production incident type.

**4. Full-trace observability from day one.**
- Log input context, model reasoning, tool calls with results, and final output for every agent turn.
- Without traces, debugging multi-agent failures is like debugging with printf and no logs. Use LangSmith, Phoenix, or custom structured logging — but log everything, not just outputs.
- Token usage per agent is critical for cost attribution and identifying runaway loops.

**Production patterns that hold up:**

- **Supervisor + Specialists** — One supervisor decomposes and routes; specialists execute and return. Simple, debuggable, effective. Most production "multi-agent" systems are this.
- **Pipeline (sequential)** — Fixed sequence: researcher → writer → editor. Each agent has a clear contract. Predictable cost, easy to eval per step, low latency overhead.
- **Asynchronous fan-out** — Multiple agents work in parallel on independent subtasks, results merge at a synthesis step. Use when subtasks are truly independent and latency matters.

**Cost reality from production deployments:**

- Support ticket resolution: **$0.12–$0.50** per ticket (3-8 LLM calls + 2-5 tool calls)
- Complex multi-step task: **$0.05–$0.47**
- Multi-agent research + writing + review: **$0.03–$0.07** (40-60% cheaper than equivalent single-agent via specialization)
- Non-LLM costs add **15-27%** on top of what shows in LLM dashboards

## Evidence

- **Research report:** Multi-agent system architecture — four foundations (typed state, checkpointing, explicit error handling, full-trace observability) and agent boundary guidance — [FRE|Nxt Labs, April 2026](https://www.frenxt.com/research/multi-agent-architecture-guide)
- **Engineering blog:** Microsoft ISE patterns for scalable multi-agent — accurate agent selection, optimized LLM usage, efficient orchestration, and the router pattern as modular monolith before microservice split — [Microsoft ISE Developer Blog, November 2025](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale)
- **Industry survey:** 30+ startup founders + 40+ enterprise practitioners — main blockers are organizational (workflow integration, employee trust), not technical model performance; main lesson: start with one agent — [Hacker News discussion, 2025](https://news.ycombinator.com/item?id=45808308)
- **Cost benchmark:** 200 tasks across 4 providers, April 2026 — multi-agent workflows 40-60% cheaper for complex tasks; non-LLM costs add 27% in real-world support ticket flows — [Ivern AI, April 2026](https://ivern.ai/blog/ai-agent-cost-benchmark-report-2026)
- **Production breakdown:** Real cost anatomy of support ticket resolution ($1.10 total: $0.80 LLM, $0.17 tools, $0.13 external APIs) — [AgentMeter, March 2026](https://www.grislabs.com/blog/agentmeter/how-much-do-ai-agents-cost)
- **Field notes:** Multi-agent orchestration production lessons — Supervisor + Specialists is the most common production pattern; explicit error handling and cost per agent are non-negotiable — [TURION.AI, March 2026](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Decision framework:** Framework selection matrix — CrewAI for demos, LangGraph for production, AutoGen for complex reasoning, raw API for minimal complexity — [GitHub - ai-agent-framework-decision-guide, April 2026](https://github.com/benconally/ai-agent-framework-decision-guide)

## Gotchas

- **Multi-agent does not mean parallel agents.** Most production gains come from specialization, not parallelism. Fan-out parallelism requires genuinely independent subtasks — adding agents in series just adds latency.
- **The router pattern is the entry drug to complexity.** Starting with a single supervisor routing to specialists is fine. The mistake is treating the next architectural evolution as inevitable — "we'll need a meta-supervisor and a feedback loop" is almost always overengineering.
- **MCP is the tool integration standard now, not the exception.** LangGraph's MCP support treats MCP tools as first-class graph nodes with full streaming. If your framework doesn't support MCP natively, the integration cost compounds fast.
- **GraphRAG earns its cost only on cross-document questions.** For simple lookups, naive chunk retrieval + reranker (Cohere Rerank v3, typically) outperforms graph-based approaches. Add complexity proportional to query complexity.
