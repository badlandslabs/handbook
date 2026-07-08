# S-828 · The Failure Recovery Stack — When Agents Break and Keep Breaking

Agents fail in ways traditional software does not. A web service crashes and logs a stack trace. An agent loops for 35 minutes, burns 250K API calls, and takes an irreversible action before a human can intervene. Recovery is not optional.

## Forces

- **Recovery logic can become the hazard.** The same mechanisms designed to keep agents running are the ones most likely to run them off a cliff — unbounded retry loops, unbounded context growth, unbounded cost.
- **Error visibility is a prerequisite for self-correction.** Agents that see only HTTP status codes, not response bodies, cannot self-diagnose and cannot self-heal.
- **Most failures (86%) are recoverable** — but only if the system gives them a path back. The other 14% need hard limits, not smarter prompts.
- **Traditional fault-tolerance patterns (circuit breakers, retries, fallbacks) apply to agents** but require agent-specific adaptations: they must be paired with semantic error classification, not just status codes.
- **Cascading failures** are the dominant production risk — one agent's failure taking down an entire multi-agent pipeline — because most frameworks default to crashing the whole session on a single API error.

## The Move

Build three nested layers of failure recovery. Each layer handles a different failure class:

**Layer 1 — Hard guards (no agent involvement):**
- Retry caps: hard limits (e.g., max 3 retries per step) on all recovery loops. This is the single highest-leverage change. The 250K API call incident from Claude Code happened because a retry cap was missing.
- Circuit breakers: stop calling a failing provider after N consecutive failures. Prevents thundering-herd behavior when an API recovers.
- Timeouts: per-step and per-task. LangGraph supports `idle_timeout` on individual `Send()` calls and node-level defaults. Never leave an agent waiting indefinitely.
- Cost guards: hard budget limits per session or per task. Catch runaway loops before they burn the quarter's API budget.

**Layer 2 — Structured error classification:**
- Classify every exception into: retryable (transient: timeout, 429, 503) vs. fatal (auth failure, 404, schema mismatch). The classification drives whether to retry at all.
- Return full error context to the agent — including HTTP response bodies, not just status codes. The fewsats case study showed that surfacing complete error details enabled agents to self-correct on API errors that a bare `raise_for_status()` would have masked.
- Log structured error metadata (error kind, model used, tool, step count, token count) for post-mortem analysis. Raw error messages are not enough.

**Layer 3 — Agent-aware recovery:**
- Self-correction loops: verify → revise → retry, where verification is a separate tool or check from execution. Not "retry the same call" but "retry with a corrected input."
- Fallback routing: chain multiple model providers (e.g., Claude → GPT-4o → Gemini) so a degraded provider doesn't halt the pipeline. Requires ordered failover logic with per-provider error thresholds.
- Checkpoint and resume: serialize agent state after each meaningful step. PostgreSQL checkpointing with LangGraph's `interrupt-and-resume` enables recovery from pod restarts without losing work. Critical for long-running multi-agent pipelines.
- Escalation paths: define explicit handoff conditions — after N recovery attempts, after a specific error class, or after a human-approval gate. Never let an agent infinitely escalate itself.

## Evidence

- **Real incident — Claude Code (GitHub #29484):** A missing retry cap let 1,279 sessions run 50+ consecutive compaction failures each, burning ~250,000 API calls in a single day. The agent was executing its recovery logic exactly as designed. The logic had no ceiling. — [GitHub anthropics/claude-code #29484](https://github.com/anthropics/claude-code/issues/29484)

- **Production case study — fewsats:** Their domain management AI agents repeatedly failed on API errors that were actually recoverable. Root cause: the HTTP SDK discarded response bodies on errors (`raise_for_status()` pattern). After surfacing complete error information including response bodies, agents could self-correct on errors they previously could not detect. — [ZenML LLMOps Database / Medium](https://www.zenml.io/llmops-database/improving-error-handling-for-ai-agents-in-production)

- **Engineering post — Odea Works (AgentAgent platform):** Early versions of their multi-agent coordination system crashed entire sessions when a single API call failed. Recovery pattern: isolate error handling per step, return partial results where possible, and define explicit fallback behavior per tool — not per session. — [Odea Works Blog](https://odeaworks.com/blog/2026-04-05-ai-agent-error-handling-best-practices/)

- **Market data — Zylos Research (2026):** 67% of AI system failures stem from improper error handling rather than algorithmic issues. Self-healing implementations average 60% reduction in system downtime. — [Zylos Research](https://zylos.ai/research/2026-02-17-ai-agent-self-healing-auto-recovery)

- **OSS framework — LangGraph:** Error handlers run after all retries are exhausted. Enables structured recovery (checkpoint restore, fallback routing, human escalation) rather than silent failure or crash. — [LangGraph JS Production Guide](https://langgraphjs.guide/production)

- **Enterprise architecture — gheWARE:** PostgreSQL checkpointing + Kubernetes StatefulSets for durable agent state. Interrupt-and-resume enables human-in-the-loop approval without blocking threads. Parallel subgraphs with fan-out/fan-in cut research agent latency 60–70%. — [gheWARE DevOps AI Blog](https://devops.gheware.com/blog/posts/langgraph-production-state-management-enterprise-2026.html)

- **Market data — The Operator Collective (2026):** 86% of agent failures are recoverable. 40%+ of agentic AI projects will be cancelled by 2027 — not because models failed, but because pipelines failed. — [The Operator Collective](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)

## Gotchas

- **Hard caps without classification creates new failure modes.** A retry cap of 3 on every error means the agent gives up on recoverable transient failures (timeouts that would succeed on retry 2). Classify first, then apply tiered retry budgets.
- **Agentic retry loops can consume more tokens than the original task.** A loop that fails 10 times at step 3 may burn more tokens than completing the task without an agent. Monitor token-per-task, not just success rate.
- **Checkpointing adds latency.** Serializing state to PostgreSQL after every step slows pipelines. Balance durability against responsiveness — checkpoint at meaningful boundaries (tool completion, subgraph exit), not every LLM call.
- **"Self-healing" in a monitoring tool ≠ self-healing in the agent.** Many tools use the term for automated runbook execution. The agent itself still needs structured recovery logic — don't conflate SRE automation with agent fault tolerance.
