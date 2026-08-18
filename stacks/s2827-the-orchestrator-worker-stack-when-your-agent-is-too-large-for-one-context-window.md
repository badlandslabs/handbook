# S-2827 · The Orchestrator-Worker Stack — When Your Agent Is Too Large for One Context Window

You have a task that exceeds what a single agent can reliably complete in one shot: a multi-source research report, a codebase-wide refactor, a workflow spanning six distinct tools. The instinct is to give the agent more context. The evidence is that more context often makes it worse.

## Forces

- **More context, worse output.** Anthropic's internal evaluation of their multi-agent research system found that token usage alone explains 80% of performance variance across runs. Heavier agents don't just cost more — they reason worse.
- **Parallelism unlocks what serialism can't.** Google Agent Bake-Off data shows distributed multi-agent processing cutting research time from 1 hour to 10 minutes (6×). Serial single-agent pipelines can't reach that without exponential context growth.
- **The collaboration pattern fails in practice.** Dynamic peer-to-peer agent negotiation — agents debating, voting, or handoff-ing freely — consistently underperforms structured patterns in production. Teams discover this after months of debugging emergent loops.
- **Most multi-agent failures are orchestration failures, not model failures.** The HN Ask HN thread on production multi-agent workflows surfaced that 57% of AI projects fail due to orchestration issues, not agent capability limits.

## The Move

**The Supervisor + Specialists (Orchestrator-Worker) pattern.** One lead agent decomposes a task and routes subtasks to specialized agents that execute in parallel. The supervisor integrates their outputs. This is what most production "multi-agent" systems actually are — simple, debuggable, effective.

### When to reach for this

Split across agents when at least one of these is true:

- **Branching** — different inputs need different next steps (router behavior)
- **Parallelization** — independent subtasks that can run simultaneously
- **Specialization** — tasks that benefit from distinct tool access or system prompts
- **Human-in-the-loop** — approval gates between agent stages
- **Crash-resume** — you need to checkpoint progress and continue after failures

If none of these apply, add a second agent anyway and you will add latency, cost, and failure modes without a compensating benefit.

### How to implement it

1. **Start single-agent.** One agent with 3–5 well-scoped tools beats a three-node graph with extra hops. This is the most consistently-repeated lesson across HN production threads and practitioner blogs.
2. **Use an explicit state machine** (LangGraph, custom FSM) over chat-transcript-based orchestration. State machines are testable, debuggable, and crash-resumable. Chat-based agents hide state in context.
3. **Supervisor handles decomposition, not execution.** The supervisor's job is to plan, route, and integrate — not to do the work itself. If the supervisor is also the most capable model, you're paying Opus rates for routing logic.
4. **Specialists get minimal context.** Pass each specialist only what it needs. Leaky pipelines — forwarding the entire accumulated context to each agent — cause the very degradation you split to avoid.
5. **Session-bound execution.** Anthropic's Claude Research system runs subagents within bounded sessions, using a Memory mechanism to survive context truncation. Long-running agents need explicit memory strategies, not infinite context.
6. **Instrument every handoff.** Log what was passed, what each agent returned, and the latency. Multi-agent systems fail in non-obvious ways (wrong agent got the task, output format mismatch, partial failure silently swallowed).

### The three patterns ranked by production reliability

| Pattern | When to use | Production readiness |
|---------|-------------|----------------------|
| **Supervisor + Specialists** | Decomposable tasks, clear routing logic | High |
| **Pipeline (sequential)** | Fixed workflow, clear handoff contracts | High |
| **Fan-Out / Fan-In** | Embarrassingly parallel work | Medium |
| **Peer collaboration** | Agents negotiating a shared answer | Low (fails in production) |

## Evidence

- **Anthropic Engineering Blog:** Their production Claude Research system uses an orchestrator-worker pattern — a lead agent coordinates parallel subagents running OODA research loops, with session-bounded execution and Memory for truncation recovery. Internal eval: +90.2% over single-agent Opus 4 on research tasks. ~15× token cost vs standard chat, ~4× vs single agent. Token usage explains 80% of variance. — [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **HN Ask HN thread (2025):** Practitioners building production pipelines overwhelmingly prefer custom solutions over frameworks. Top reasons: observability gaps, lack of crash-resume, and inability to control handoff contracts. Common pattern: Node.js/Express + MongoDB shared state, agents as V8-isolated endpoints, coordinator endpoint for sequential/parallel chaining. — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **TURION.AI field notes (March 2026):** After a dozen production multi-agent deployments, the conclusion: "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count." Supervisor + Specialists and Pipeline consistently survive production. Dynamic peer collaboration consistently fails. — [turion.ai/blog/multi-agent-orchestration-infrastructure-production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Google Agent Bake-Off:** Distributed multi-agent architecture cut research pipeline from 1 hour to 10 minutes (6× throughput improvement) through parallelism alone. — cited in [macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)
- **macgpu 2026 guide:** AdaptOrch research (2026) found orchestration topology delivers 12–23% performance gains on SWE-bench — topology choice matters more than model swap. — [macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)

## Gotchas

- **Tool description bloat kills performance.** Fountain City Tech's production validation of Anthropic's blueprint found that fixing tool descriptions alone reduced task completion time by 40%. Subagents with poorly-scoped or redundant tools produce worse outputs than a single well-tooled agent.
- **Fan-out without fan-in timeout is a runaway budget.** Each parallel agent consumes full token budgets. Without explicit per-agent timeouts and a cost ceiling, a fan-out can accumulate costs far beyond what the task warrants.
- **Context truncation mid-session breaks stateful pipelines.** If a long-running subagent hits its context limit, it loses state unless you've implemented explicit Memory (Anthropic's approach) or checkpointing. Most frameworks handle this poorly.
- **Framework choice is not the hard problem.** The HN thread confirms: teams successfully using LangGraph, CrewAI, or custom stacks all report the same root causes of failure — not framework limitations, but missing handoff contracts, unobserved pipelines, and premature complexity.

## Receipt

Verified 2026-08-18 — Cross-referenced 5 primary sources: Anthropic's own engineering post (the canonical case study), two HN practitioner threads, two independent practitioner blogs with production deployment data. Core finding triangulated across all sources: Supervisor + Specialists is the dominant production pattern, peer collaboration fails in production, and orchestration topology choice matters more than framework choice.

## See also

- [S-2826 · The MCP Agent Production Evaluation Stack](s2826-the-mcp-agent-production-evaluation-stack-when-your-agent-passes-staging-and-fails-every-tool-call-in-production.md) — how to eval the tools your orchestrator calls
- [S-2825 · The Agent = Model + Harness Stack](s2825-the-agent-equals-model-plus-harness-stack-when-your-benchmark-score-is-a-lie-because-youre-testing-the-wrong-thing.md) — harness design affects orchestration quality
- [S-2823 · The Checkpoint and Rollback Engineering Stack](s2823-the-checkpoint-and-rollback-engineering-stack-when-your-agent-has-already-broken-production.md) — crash-resume is essential for orchestrator-worker pipelines
