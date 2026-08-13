# S-2571 · The Circuit Breaker Stack — When Nothing Stops a Failing Agent

Your document-summarization agent degrades at 11 PM when the search API starts returning 503s. By 7 AM it has made 4,000 identical tool calls, all failing, all billing. No alert fired. No threshold tripped. You woke up to a $437 API bill. This is the Circuit Breaker Stack problem: agents that retry indefinitely on degraded tools, burning tokens until context exhaustion or bankruptcy.

## Forces

- **Retry logic handles transient failures but not sustained outages.** Exponential backoff delays waste — it doesn't prevent it. A tool that goes down for 10 minutes will generate hundreds of billable retry attempts if the agent has no circuit breaker.
- **Agents fail silently and confidently.** Unlike traditional software, a hallucinated tool argument returns HTTP 200. The agent thinks it succeeded. Without semantic validation, the next step compounds the error.
- **Tool degradation is invisible without per-tool tracking.** The agent's loop looks like normal execution — each call is cheap, each failure looks like one more try. Only aggregated cost and latency expose the pattern.
- **Kill switches require a human. Circuit breakers don't.** If the outage hits at 2 AM, a manual override is useless. The architecture must be able to halt itself autonomously.

## The move

Wrap external tool calls with per-tool circuit breaker state machines. Track failures at the tool level, not the agent level. Let the agent try alternatives or degrade gracefully instead of repeating calls that will fail.

**Implementation layers:**

- **Per-tool failure counters** — each external tool (API, search, code executor, database) gets its own state machine tracking consecutive failures, independent of other tools.
- **Three-state machine:** Closed (normal → count failures) → Open (block all calls immediately, return CircuitOpenError → agent attempts fallback) → Half-Open (probe with a limited number of calls → success returns to Closed, failure returns to Open).
- **Configurable thresholds:** failure_threshold (how many failures before Open), recovery_timeout (how long to wait before probing), success_threshold (how many Half-Open successes to confirm recovery).
- **Fallback chains:** when a tool's circuit opens, the agent routes to an alternative tool or degrades to a pre-defined safe response. Don't let the circuit open into a dead end.
- **Behavioral circuit breakers:** beyond tool-level, track cost velocity, iteration count, and scope violations. If cost_per_session exceeds $X or iterations exceeds N, terminate regardless of tool health.
- **Prometheus metrics export** for all circuit states — observability is required for production; you can't protect what you can't see.

## Evidence

- **$437 overnight bill post-mortem:** A document pipeline agent entered a retry loop at 11 PM when the search API returned 503s. No alert fired. By 7 AM it had run for 8 hours making thousands of identical tool calls. The fix (adding a circuit breaker with a $10 cost cap) took 20 minutes. — [Waxell AI Blog, May 2026](https://www.waxell.ai/blog/ai-agent-circuit-breaker-pattern)
- **Enterprise resilience library:** `agentarmor` (PyPI, MIT license) translates microservice reliability patterns (Hystrix, Resilience4j) into asyncio-native decorators for AI agents: circuit breakers, bulkheads, exponential backoff retries, fallback chains, and Prometheus metric export. Handles cascading failures from rate-limited LLMs (429s), third-party API instability, and hallucinatory parsing. — [github.com/Ismail-2001/agent-armor](https://github.com/Ismail-2001/agent-armor)
- **Agent circuit breaker library:** `AgentCircuit` wraps agent functions with circuit breaker protections as a Python decorator, specifically targeting the failure mode where agents loop on degraded tools. — [HN Show, github.com/simranmultani197/AgentCircuit](https://news.ycombinator.com/item?id=46899775)
- **Three error types in agentic AI:** Deterministic errors (rate limits, network failures — standard retry), semantic errors (tool succeeds technically but returns wrong data — verify against ground truth), and behavioral errors (agent enters harmful pattern — requires human override or automated kill switch). Only deterministic errors benefit from retry logic. — [Preporato NCP-AAI certification content](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)

## Gotchas

- **Backoff delays waste — it doesn't prevent it.** Exponential backoff with jitter is right for transient failures (a few seconds to minutes). It is the wrong tool for sustained outages. Configure backoff for transient recovery, circuit breakers for structural degradation.
- **Per-tool, not per-agent.** If your agent calls three tools and only one degrades, the circuit breaker for that tool should open while the other two continue normally. A single global circuit breaker for the entire agent session is too coarse-grained.
- **Circuit open is not failure — it's a signal.** When a circuit opens, the agent must have something to do: try a fallback tool, return a degraded response, or escalate. An open circuit with no fallback is a dead end, not a safe state.
- **Behavioral circuits need cost and iteration caps.** Tool-level circuit breakers handle external service failures. You also need bounds on the agent's own behavior: max cost per session, max iterations, max output tokens. These are separate safeguards against runaway loops.
- **Prometheus metrics are not optional.** Without observable circuit state, you can't distinguish "circuit open because tool is down" from "agent not calling tool for unknown reason." Instrument every state transition and make it queryable.
