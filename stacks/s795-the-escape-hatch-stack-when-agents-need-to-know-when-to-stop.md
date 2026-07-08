# S-795 · The Escape Hatch Stack: When Agents Need to Know When to Stop

Your agent loops for 35 minutes, accumulates $200 in API costs, and produces nothing — then exits without an error. It never crashed. It simply didn't know when to quit. This is the failure mode most agent frameworks don't teach you to handle: not errors, but non-termination. The escape hatch stack is the layered set of mechanisms that force agents to stop, recover, degrade gracefully, or escalate before they cost you money, corrupt data, or leave users hanging.

## Forces

- **LLMs have no internal stop condition.** Unlike a function with a return statement, an agent decides its own continuation — and that decision is made under the same uncertainty that drives it to keep trying. The same property that makes agents useful (autonomy) is the one that makes them unsafe without constraints.
- **Silent failure is worse than loud failure.** A crash logs an exception. A loop silently burns tokens, spawns redundant subprocesses, and may take irreversible actions before anyone notices. The absence of an error message is not success.
- **Retry logic compounds the problem.** Exponential backoff on a misbehaving agent can turn a 5-minute incident into a 2-hour cost spiral. Retries help transient errors; they amplify planning loops.
- **Production incidents involve blast radius, not just failure.** A data cleanup agent corrupted 9,000 of 14,000 customer records over a weekend. The agent wasn't "down" — it was running. The failure was architectural: too much agency, no escalation path.
- **The 62–14% gap is partly a failure-handling gap.** Only 14% of enterprise AI pilots reach production (Deloitte), while 40% are cancelled by 2027 (Gartner). Many of those cancellations trace to a single runaway incident that made the business case for rollback.

## The move

The escape hatch stack is four concentric layers of termination logic, applied from innermost (cheapest check) to outermost (most expensive failure):

### Layer 1 — Mechanical circuit breakers (cheap, always-on)

Hard limits enforced outside the LLM's reasoning loop. These run on every step and cost nothing to check.

- **Max iterations:** Set `max_iterations=10` (not the default, which is often unbounded). In LangChain this is `AgentExecutor(max_iterations=10, early_stopping_method="generate")`. Markaicode measured a 92% reduction in token costs with this single setting on agents hitting the iteration limit.
- **Turn counter in multi-agent pings:** Never let the LLM decide "we're done" after N repeated failures. Inject a deterministic state variable incremented on each turn. If Generator→Reviewer cycles exceed a threshold, force-exit with a dead-letter result.
- **Token budget per run:** Enforce a cumulative token cap. Track with OpenTelemetry traces — GuardLoop (awesome-pro/guardloop) exposes budget caps as a first-class feature with trace integration. At 80,000 tokens per loop iteration, costs compound fast.
- **Execution timeouts:** `max_execution_time` as a secondary safety net. Set conservatively based on observed p95 run duration, not guesswork.

### Layer 2 — Semantic loop detection (moderately expensive)

Detects when the agent is stuck in a pattern even if it's technically making progress.

- **Output similarity scoring:** Compare the agent's last N outputs using embeddings or n-gram overlap. If similarity exceeds a threshold (TrackAI cites 0.75–0.95 as loop-adjacent ranges), flag for intervention. High similarity at low iteration count means the agent is repeating itself; high similarity at high iteration count means it's in a dead end.
- **Tool-call sequence fingerprinting:** Log the sequence of tool calls per run. A repeating 3-step sequence (A→B→A→B) is a loop even if each individual call succeeds. GuardLoop's circuit breaker monitors for this pattern.
- **Context window pressure:** Track token count against the model's context limit. A looping agent's context grows on every turn until it hits the ceiling — by then the bill is large and the output is degraded. Compact context proactively (summarize, drop oldest messages) before hitting 80% of the limit.

### Layer 3 — Fallback and graceful degradation (costs a call, preserves outcome)

When the primary path fails or terminates early, fall back rather than fail completely.

- **Fallback chain:** Route to a lower-cost or more reliable model when the primary model errors or loops. The chain is ordered: try Claude → try GPT-4o → try a local 7B. Each has a timeout. `llm-fallback-router` (PyPI) implements ordered multi-provider failover; `llm-circuit-breaker-py` stops hammering a failing provider.
- **Dead-letter queue with structured output:** When an agent terminates via circuit breaker, write a structured dead-letter record: what was attempted, where it failed, what partial output exists. This lets a human or a recovery agent resume from the failure point rather than restart from scratch.
- **Read-only degradation:** If an agent with write access starts looping, strip its write permissions and restart it in read-only mode. This is the minimum-viable version of the guardrail architecture described in OWASP LLM Top 10 v2.0: excessive agency is mitigated by least-privilege ephemeral identity.

### Layer 4 — Human escalation (expensive but necessary for high-stakes domains)

The last resort. Triggers when automated recovery cannot safely proceed.

- **Supervisor agent escalation:** In a supervisor-worker architecture, the supervisor monitors subagent output quality and can abort, reassign, or surface to human review. This is pattern #53 in saisrinivas-samoju/agentic_architectures: Guardrail Agent.
- **Approval gates before irreversible actions:** Any tool call tagged as destructive (DELETE, DROP, overwrite) should require confirmation — either from a human or from a policy engine that checks the action against the agent's allowed action set. The incident of 9,000 corrupted records had no such gate.
- **Async notification on escalation:** When a circuit breaker trips or an agent escalates, fire a notification (Slack, PagerDuty, webhook) with the run state. Don't wait for the user to notice.

## Evidence

- **GitHub: GuardLoop (awesome-pro/guardloop)** — Production runtime guardrails for AI agents: budget caps, circuit breakers, and OpenTelemetry traces. Implements all of Layer 1 as composable middleware. — [https://github.com/awesome-pro/guardloop](https://github.com/awesome-pro/guardloop)
- **Engineering blog: Pratik Pathak, "The Infinite Loop Trap"** — Multi-agent Generator→Reviewer system burned $200 overnight. The root cause: a stateful loop where Reviewer instructions were incompatible with Generator output. Each failed cycle accumulated ~80,000 tokens. Fix: max-turn counter + dead-letter queue. — [https://pratikpathak.com/the-infinite-loop-trap-how-my-multi-agent-system-burned-200-overnight-and-how-to-fix-it](https://pratikpathak.com/the-infinite-loop-trap-how-my-multi-agent-system-burned-200-overnight-and-how-to-fix-it)
- **Engineering blog: Markaicode, "Fix LangChain Agent Infinite Loop"** — Field-tested fix for LangChain agents that hit max_iterations without stopping. Setting `max_iterations=10` and `early_stopping_method="generate"` cut token costs by 92%. Root causes identified: ambiguous tool descriptions and missing stop conditions in the agent's own prompt. — [https://markaicode.com/errors/ai-agent-loop-fix](https://markaicode.com/errors/ai-agent-loop-fix)
- **Research: OWASP LLM Top 10 v2.0** — Explicitly names *Excessive Agency* as a top-10 production risk. The mitigation aligns with Layer 3 and Layer 4: least-privilege tool access, approval gates, and scope limitation. — [https://owasp.org/www-project-llm-top-10/](https://owasp.org/www-project-llm-top-10/)
- **Agentic architecture catalog: saisrinivas-samoju/agentic_architectures** — Documents Part XI as Safety & Resilience: Guardrail Agent (#53), Circuit Breaker (#54), Dead Letter / Escalation (#57). Patterns are explicitly catalogued as production-ready architectural components, not afterthoughts. — [https://saisrinivas-samoju.github.io/agentic_architectures/architectures/supervisor/](https://saisrinivas-samoju.github.io/agentic_architectures/architectures/supervisor/)
- **Industry data: The Operator Collective** — 40% of agentic AI projects will be cancelled by 2027 (Gartner); $1M+ lost per major failure (EY). The primary failure mode in production is not model quality — it's the absence of governance infrastructure (circuit breakers, approval gates, cost budgets). — [https://theoperatorcollective.org/blog/ai-agent-failures-lessons-learned](https://theoperatorcollective.org/blog/ai-agent-failures-lessons-learned)
- **Incident report: Q1 2025 SaaS data corruption** — An autonomous data cleanup agent with write access to a customer database corrupted 9,000 of 14,000 records over a weekend. Recovery took 31 engineering hours. Root cause: no guardrails on write actions and no escalation path when the agent produced corrupted output. — [https://logiciel.io/blog/guardrails-agentic-ai](https://logiciel.io/blog/guardrails-agentic-ai)

## Gotchas

- **Default limits in agent frameworks are designed for demos, not production.** LangChain's default `max_iterations` is unbounded. CrewAI's task timeouts are opt-in. The framework's getting-started experience works without constraints precisely because constraints make the first-run experience worse.
- **Retry logic makes loops faster, not safer.** Exponential backoff on a 429 (rate limit) is correct. Exponential backoff on a semantic failure (the agent is stuck in a reasoning loop) amplifies the cost without fixing the problem. Separate your transient-error retry from your loop-detection logic.
- **Context compaction is a loop-prevention tool, not a memory tool.** Teams add summarization to preserve long conversations, but the real benefit is that a looping agent with a compact context doesn't inflate its context window on every iteration — cost grows linearly rather than quadratically.
- **A circuit breaker that never trips is not a circuit breaker.** Set thresholds based on actual run data (p95 iterations, p95 token count), not defaults. A threshold that's never reached provides false confidence.
- **Escalation without structured dead-letter output is useless.** "The agent failed" is not actionable. "The agent failed on step 4 of 7 after calling tool B with params X; partial output Y was produced; human review needed for steps 5–7" is actionable.
