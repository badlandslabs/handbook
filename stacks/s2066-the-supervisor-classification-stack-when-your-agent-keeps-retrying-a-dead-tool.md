# S-2066 · The Supervisor Classification Stack — When Your Agent Keeps Retrying a Dead Tool

When an agent hits a degraded tool, loops for 27 LLM calls, and burns budget before a human notices. When every failure mode routes to the same generic retry. When a 10-step pipeline fails end-to-end because step 4 is silently broken and nobody recovers it.

## Forces

- **The retry-everything instinct is wrong.** Not all errors are equal — retrying a 500-internal-error is different from retrying a tool that returns bad JSON. The wrong retry strategy wastes tokens, masks root causes, and compounds failures.
- **Agents fail in ways traditional software doesn't.** A web service crashes and logs. An agent may silently loop for 35 minutes, spawn redundant subprocesses, or take an irreversible action before anyone intervenes.
- **The reliability cliff is steep.** A 10-step pipeline where each step has 85% reliability succeeds end-to-end only ~20% of the time — without fault tolerance, not 80%.
- **Who fixes this?** is the first and most important question — and almost nobody asks it explicitly.

## The Move

The core move: **classify every error by who can fix it, then route each class to the right handler.** No single strategy handles all failures. The supervisor pattern adds a monitoring layer above the agent that classifies errors and dispatches them appropriately.

### Error Classification Matrix

| Error Class | Who Fixes It | Handler | Example |
|---|---|---|---|
| **Transient** | System (automatic) | Retry with backoff | HTTP 429, timeout, DNS blip |
| **LLM-Recoverable** | The LLM itself | Error in state + loop back | Bad JSON, wrong tool chosen |
| **User-Fixable** | The human | `interrupt()` + handoff | Missing required field, ambiguous input |
| **Unexpected** | The developer | Let it bubble + alert | `TypeError`, schema mismatch, logic bug |

### Per-Step Implementation

1. **Transient errors → `RetryPolicy` with exponential backoff + jitter.** AWS research: exponential backoff with jitter reduces retry storms by 60–80% versus fixed-interval retries. Set `max_attempts`, initial interval, and max interval explicitly — don't leave them implicit.

2. **LLM-recoverable errors → store the error in agent state, then loop back.** The LLM sees the failure context and adjusts its approach on the next call. This is different from retrying the same prompt — the error message becomes part of the next reasoning cycle.

3. **Tool degradation → per-tool circuit breakers.** Track each external tool's failure rate independently. Once a tool crosses the failure threshold, block calls to it and return a graceful degradation response instead. This stops agents from burning tokens on retry loops against a degraded service.

4. **Long workflows → checkpoint-and-resume.** On interruption (human handoff, timeout, pod restart), save state at every node boundary. Resume from the last successful node, not from scratch. The checkpointer backend must match your deployment topology — `MemorySaver` for dev/tests only; production needs `PostgresSaver` or Redis.

5. **Supervisor agent monitors subtask agents.** A parent agent watches child agents for three danger signals: no progress after N steps, budget threshold exceeded, or looping (same tool called 3+ times in a row). On detection, it kills the subtask and escalates.

6. **Graceful degradation chains.** Define fallback sequences explicitly: primary tool → fallback model → simpler model → static response. A degraded answer is almost always better than a failure response.

## Evidence

- **Engineering blog:** The Operator Collective (March 2026) reports that 86% of agent failures are recoverable — but that recovery requires deliberate infrastructure, not luck. Found that most multi-agent failures "aren't caused by weak models, they're caused by weak reasoning architecture" (NJ Raman). — [theoperatorcollective.org/blog/ai-agent-error-handling-production-guide](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)

- **Engineering blog:** Zylos Research (May 2026) provides the reliability cliff calculation: a 10-step pipeline at 85% per-step reliability succeeds ~20% of the time end-to-end without fault tolerance. Also reports Galileo's 2025 analysis of multi-agent failures: 42% specification failures, 37% coordination breakdowns, 21% verification gaps. — [zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery/)

- **GitHub / Framework docs:** LangGraph's production error handling guide (Focused.io, 2025–2026) formalizes the error classification matrix and maps each class to specific LangGraph primitives (`RetryPolicy`, `Command`, `interrupt()`, `ToolNode`). Notes that Arize encountered an agent making 27 LLM calls in circles before adding state-based error visibility. — [focused.io/lab/langgraph-agent-error-handling-production](https://focused.io/lab/langgraph-agent-error-handling-production)

## Gotchas

- **`MemorySaver` in production.** The ActiveWizards checkpointing guide warns: teams ship to production on `MemorySaver`, their pod restarts, twenty in-flight agent threads die silently, then they spend the next sprint reverse-engineering a database schema. Pick the checkpointer backend before production, not after.
- **Errors that return HTTP 200.** LLM responses can hallucinate successful-looking output from a failed tool. Traditional try-catch doesn't catch these. You need semantic validation of tool responses — check the content, not just the status code.
- **Retry storms on shared infrastructure.** Without jitter, multiple agents retry at the same intervals and thunder together against a recovering service. Always add random jitter to retry delays.
- **Cascading failures across multi-agent pipelines.** When agent A feeds agent B, a failure in A compounds through B and beyond. Build isolation: each agent has its own circuit breakers, and a parent supervisor kills the pipeline before a cascading failure consumes your entire budget.
