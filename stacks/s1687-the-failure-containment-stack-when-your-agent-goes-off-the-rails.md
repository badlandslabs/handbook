# S-1687 · The Failure Containment Stack — When Your Agent Goes Off the Rails

Your agent worked perfectly in staging. In production, it hit an edge case, entered a retry spiral, and burned $47,200 over 11 days before anyone noticed. No crash. No exception. No alert. This is not a model problem. It is a failure containment problem — and it is the single most expensive gap in production agent deployments.

The field has converged on a layered resilience model: circuit breakers, loop detection, checkpoint/rollback, and graceful degradation. Together they form the containment stack that determines whether a failure is a $10 incident or a $47,000 one.

## Forces

- **Agents don't know they're looping.** LLMs retry with apparent confidence because they don't have visibility into the retry count. A loop that a human would recognize as broken looks like productive work to the model.
- **Agents produce plausible failures, not errors.** Unlike traditional software, agents don't throw exceptions when they go wrong — they produce wrong answers that sound right. Silent failures compound until someone notices.
- **Destructive actions compound the damage.** A retry loop that calls a write API repeatedly doesn't just waste tokens — it can corrupt state, trigger rate limits that lock out other systems, or execute side effects multiple times.
- **The gap between lab benchmarks and production is 37%.** Agents scoring 80–94% on SWE-bench and GAIA in evaluation hit exceptions requiring recovery in 30% of real-world production runs (Fast.io, 2026).
- **Agent production incidents tied to state management failures exceed 60%** (LangChain State of Agent Engineering, 2026).

## The Move

Build a layered containment stack. Treat each layer as a backstop for the one above it.

**Layer 1 — Loop detection and termination:** Count every step in the execution trace. Track repeated tool calls, repeated reasoning patterns, and token growth rate. Break on hard limits before cost or context damage accumulates.

**Layer 2 — Circuit breakers:** Wrap every external dependency (LLM API, tool API, database). A circuit breaker transitions through closed → open → half-open states and prevents cascading failures when a dependency is degraded. The key insight: retries are for transient hiccups; circuit breakers are for structural failures.

**Layer 3 — Checkpoint and rollback:** Serialize agent state — transcript, plan, memory, tool outputs — at defined boundaries. On failure or human review, restore to the last known-good checkpoint instead of restarting from scratch.

**Layer 4 — Human handoff and escalation:** When all containment layers fail, escalate to a human with the full execution trace. The agent should not be able to silently proceed past a defined damage boundary (e.g., a write operation that exceeds a cost or impact threshold).

**Layer 5 — Graceful degradation:** Define a fallback chain (primary model → fallback model → fallback provider → static response). When a dependency fails, degrade to the next tier rather than failing completely.

## Evidence

- **HN post-mortem (2025):** A team running multi-agent production workloads hit a retry spiral that burned $47,200 in 11 days before detection. The four controls that would have stopped it at $10: cost-per-run caps, step-count limits, circuit breakers on API calls, and execution trace logging. The agent looped because an A2A communication failure caused agents to re-attempt the same task without knowing prior attempts had failed. — [We spent 47k running AI agents in production | Hacker News](https://news.ycombinator.com/item?id=45802430)
- **Reddit production post-mortem (2025):** A team lost a production database to an agent retry loop. Key lessons shared: "streak breaker" policy (3 consecutive non-200 responses trigger hard stop and human escalation), idempotency keys per intent ID for state-changing operations, and logging the agent's internal reasoning trace alongside API logs to understand why retrying seemed valid to the model. — [r/AI_Agents: Our AI agent got stuck in a loop and brought down production](https://www.reddit.com/r/AI_Agents/comments/1r9cj81/our_ai_agent_got_stuck_in_a_loop_and_brought_down/)
- **Open-source tooling (2026):** LoopGuard — a zero-dependency Python library for semantic and structural loop detection in AI agents supporting LangChain, LangGraph, CrewAI, and AutoGen. Distinguishes between context spirals (token growth accelerating beyond baseline), retry storms (low-variance repeated calls), policy drift (reasoning going off-topic), early explosions (token spike in first turns), and budget exhaustion. — [Charbelto/loopguard | GitHub](https://github.com/Charbelto/loopguard)
- **Engineering post (2025):** A production lead-enrichment agent ghosted silently under load — no crash logs, no exceptions. Root cause: tool timeouts and API rate limits cascading silently. Fix: three-layer resilience pattern combining exponential backoff retry logic, circuit breakers on external API calls, and a fallback chain that degrades gracefully. — [When Your Agent Fails Silently | Supergood Solutions](https://supergood.solutions/blog/when-your-agent-fails-silently)
- **Vectara failure catalog (2025–2026):** Community-curated repository of AI agent failure modes with real-world case studies. Key documented classes: tool hallucination (tool output incorrect), silent tool failure (tool returns 200 but wrong data), loop/retry storms, schema drift, and context poisoning. — [vectara/awesome-agent-failures | GitHub](https://github.com/vectara/awesome-agent-failures)
- **OpenClaw GitHub issue (2026):** Real incident: Claude Opus agent tried calling `WebSearch` tool that was not configured — only `web_search`/`tavily_search` existed. Each call returned "Tool WebSearch not found." Agent retried 23 times before circuit breaker triggered, accumulating context and burning tokens. Resolution: per-tool circuit breaker with failure-type counting and automatic tool catalog validation. — [Circuit breaker for repeated tool failures | GitHub Issue #67399](https://github.com/openclaw/openclaw/issues/67399)

## Gotchas

- **Counting error types instead of iterations is a trap.** A loop detection system that tracks distinct error types rather than total iterations will not catch a loop where the same error repeats 47,000 times. Count steps, not error types.
- **Circuit breakers must be per-dependency, not global.** A global circuit breaker that opens when one tool fails cuts off all other tools. Wrap each external dependency independently and set thresholds based on the criticality of that tool.
- **Fallback chains that skip providers are not resilient.** A fallback from Claude Opus to Claude Haiku does not help if Anthropic's entire API is down. Cross-provider fallbacks (Anthropic → OpenAI → Cohere) are the only pattern that survives provider-wide outages.
- **Degradation paths must be tested before deployment.** A customer support agent that drops to a mid-tier model during an outage still resolves 70% of queries — but only if the fallback was tested. Untested fallback paths fail at the worst moment.
- **Human handoff requires a handoff, not just a flag.** Setting a "human escalation needed" flag and letting the agent continue is not a handoff. Freeze the execution state, serialize the full trace, and require an explicit human acknowledgment before the agent can resume.
