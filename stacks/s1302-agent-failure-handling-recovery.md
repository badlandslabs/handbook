# S-1302 · Agent Failure Handling and Recovery

Your agent will not crash with a stack trace. It will silently loop for 35 minutes, spawn redundant subprocesses, and charge your API budget — producing output that looks like work right up until someone reads the invoice.

## Forces

- Agents fail differently than software — there is no exception, only confident nonsense or polite repetition
- A failed tool call with HTTP 200 still succeeds technically but semantically fails — traditional try-catch catches nothing
- The gap between "something is wrong" and "we know what to do" costs more in agentic systems than in any other layer of the stack
- Guardrails implemented as prompt instructions are advisory; enforcement in code is what actually stops runaway behavior
- Safety and capability are in tension: too tight and the agent is useless, too loose and it burns resources silently

## The Move

Build a layered failure-recovery architecture with deterministic enforcement at the infrastructure level and adaptive recovery at the agent level.

**Budget enforcement (always code, never prompts):**
- Hard iteration cap — stop the loop after N tool-call cycles regardless of model confidence
- Token budget ceiling — kill the run if cumulative token spend exceeds the threshold
- Wall-clock timeout — stop if elapsed time exceeds the task SLA
- All three enforced in the orchestration runtime, not in the system prompt

**Circuit breakers for tool calls:**
- Track failure counts per tool endpoint independently
- Open the breaker after N consecutive failures (e.g., 3–5) — stop calling that tool and return a degraded result
- Half-open state: probe once after a cool-down period; close if the probe succeeds
- This prevents a dead API from consuming the agent's entire reasoning budget

**Progress signal detection:**
- Agents that repeat the same tool with the same arguments across consecutive turns are in a no-progress loop
- Maintain a rolling window of recent tool calls; flag when the last K calls are identical
- Also flag when the observation from a tool call is identical to a prior observation in the same session

**Supervisor / watchdog pattern:**
- A meta-agent or deterministic check function evaluates each step before the next begins
- Supervisor checks: is progress being made? Are costs within budget? Is the next action safe?
- Escalation triggers: low model confidence, high-risk action types, repeated failures
- Escalation path: pause and surface to human, with full trajectory logged for review

**Checkpointing for state recovery:**
- Every N steps, serialize agent state (plan, memory, tool results so far, budget remaining)
- On failure or timeout, restart from the last checkpoint rather than from scratch
- This is especially critical for long-horizon tasks where 30 minutes of work cannot be re-run cheaply

**Graceful degradation:**
- If the primary tool is unavailable, the agent should degrade to a fallback — search unavailable, try the cached index
- Define degraded outputs explicitly: "unable to complete full analysis — partial results follow"
- Never let the agent continue into undefined behavior when a tool fails

## Evidence

- **GitHub README:** Agentic Reliability Framework (ARF) — production-grade OSS multi-agent system for infrastructure reliability, states 73% of AI agent projects fail due to unpredictability, lack of memory, and unsafe execution, with 40%+ of alerts ignored due to false positives — [github.com/petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)
- **Research synthesis:** Zylos Research (May 2026) — AI Agent Self-Healing taxonomy: 42% specification failures, 37% coordination breakdowns, 21% verification gaps. Documents agents silently looping for 35 minutes, spawning redundant subprocesses, and accumulating context until model halt — [zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery)
- **Show HN launch:** TensorPool Agent — autonomous recovery for distributed GPU training jobs. HN discussion surfaced the core tension: agents need enough authority to self-heal, but require smarter progress checks to avoid nursing zombie jobs silently — [news.ycombinator.com/item?id=46812909](https://news.ycombinator.com/item?id=46812909)
- **Reference pattern:** Agent Circuit Breaker — tracks consecutive tool failures per endpoint, opens circuit after N failures, prevents cascading token waste and latency amplification — [agentic-patterns.com/patterns/agent-circuit-breaker](https://www.agentic-patterns.com/patterns/agent-circuit-breaker)
- **Enterprise guardrails:** Gheware DevOps (May 2026) — four-layer safety architecture: permission boundaries, output validators, circuit breakers, human-in-the-loop checkpoints — [devops.gheware.com/blog/posts/ai-agent-guardrails-production-enterprise-2026.html](https://devops.gheware.com/blog/posts/ai-agent-guardrails-production-enterprise-2026.html)

## Gotchas

- Prompt-level guardrails ("stop after 5 retries") are advisory — the model can ignore them. Enforcement must live in the orchestration loop
- Endpoint-scoring (was the final answer right?) misses the failure mode: lucky recovery after wasteful wandering burns budget without anyone noticing
- Without checkpointing, recovery always starts from scratch — a 30-minute agent run with no checkpoints is a 30-minute re-run on failure
- Identical tool calls with identical arguments across consecutive turns are the most common no-progress signal and the easiest to miss
- Escalation without trajectory logging is useless — the human needs the full step history to decide what went wrong
