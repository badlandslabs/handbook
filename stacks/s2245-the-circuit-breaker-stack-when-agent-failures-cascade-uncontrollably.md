# S-2245 · The Circuit Breaker Stack — When Agent Failures Cascade Uncontrollably

When an agent failure in one step silently breaks every downstream step, or when a looping agent burns resources for 35 minutes with no alarm.

## Forces

- Agent failures are qualitatively different from service failures — they can loop silently, hallucinate plausible wrong outputs that pass schema validation, and take irreversible actions before a human notices
- Naive retry loops make rate-limit errors worse and can take down upstream services; teams discover this only in production
- A failure in one agent of a pipeline can cascade into every other agent, and traditional try/catch doesn't catch "the model chose the wrong tool" or "the agent is in a context accumulation spiral"
- Specifying what "success" means for a multi-step agent task is harder than the failure-handling code itself — evaluation and recovery are coupled problems
- Most teams write resilient demos in two weeks, then spend four months discovering failure modes they never planned for

## The move

Build fault tolerance as a first-class architectural layer, not an afterthought. The pattern that separates production-grade agents from demos combines four mechanisms:

**1. Classify failures by type before choosing a recovery strategy.** Transient errors (rate limits, timeouts, 503s) want retry with backoff. Persistent errors (model returning malformed JSON, safety filters, semantically wrong tool calls) want a try-different-model or try-different-tool path. Structural errors (agent deadlock, context overflow, infinite loops) want hard interruption and escalation. Guessing which one you're dealing with wastes time and can make things worse.

**2. Layer circuit breakers around agent nodes, not just tool calls.** A circuit breaker tracks the failure rate of an agent or tool over a sliding window. When failures exceed a threshold, the breaker opens: stop calling the failing component and route to a fallback (degraded mode, different model, human handoff). Monte Carlo validation on multi-agent systems shows circuit breakers reduce cascading failures by ~85% compared to unshielded pipelines.

**3. Enforce execution budgets — max steps, max time, max cost.** A step counter that hard-stops an agent after N actions prevents silent infinite loops. A time budget prevents context accumulation spirals. A cost budget prevents runaway token spend from a looping agent calling expensive tools repeatedly. These are not edge cases: agents looping for 35+ minutes have been documented in production systems.

**4. Build a dead-letter queue for graceful degradation.** When an agent fails after three retries and the circuit breaker opens, the task doesn't disappear — it goes to a DLQ with full trace context (what was attempted, where it failed, what the partial output was). A human or a recovery agent can inspect and retry. Without this, a failed multi-step task leaves no trace and no recovery path.

**5. Make evaluation the foundation of failure detection.** You can't recover from what you can't measure. Production teams instrument agents with trace-level observability (tool calls, intermediate reasoning steps, decision points) and run automated eval pipelines that score each agent run on task completion, tool-call accuracy, and safety. An agent that silently degrades across model versions will be caught only by a continuous eval run, not by watching logs.

## Evidence

- **Engineering blog — Zylos Research:** AI agent failures break down as ~42% specification failures (wrong task definition or tool schema), ~37% coordination failures (multi-agent deadlock or miscommunication), and ~21% verification failures (no check that the agent's output is actually correct) — sourced from Galileo's 2025 production incident analysis. — [zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)

- **Technical blog — NiteAgent:** A March 2026 incident where an agent posted technically incorrect guidance and retweeted it involved the agent returning a plausible-looking but wrong result that passed schema validation — illustrating that hallucinated outputs can clear type checks. Describes configurable per-agent timeouts, exponential backoff, circuit breakers, and dead letter queues as standard production patterns. — [niteagent.com/blog/multi-agent-pipeline-resiliency-patterns](https://niteagent.com/blog/multi-agent-pipeline-resiliency-patterns)

- **GitHub — hamley241/circuit-breaker-agents:** Monte Carlo validation study showing circuit breaker patterns reduce cascading failure rates in multi-agent LLM systems by ~85%. Repo includes empirical validation with reproducible results across multiple agent configurations. — [github.com/hamley241/circuit-breaker-agents](https://github.com/hamley241/circuit-breaker-agents)

## Gotchas

- Retrying without backoff on rate-limited endpoints amplifies the problem — the retries themselves become the load that keeps the rate limit active. Use exponential backoff (base 2, cap at 60s) with jitter, not linear retry loops.
- Schema validation catches malformed outputs but not semantically wrong ones — a circuit-breaker agent can return valid JSON that is the wrong answer. Pair structural checks with eval-based quality scoring.
- Hard step/time limits must be enforced at the orchestration layer, not the agent itself — a looping agent won't stop itself, because from inside the loop, continuing looks like the right next step.
- Most teams discover the need for DLQs only after losing a task mid-pipeline with no trace and no way to recover or audit what happened. Plan for this before you go to production.
