# S-1087 · The Supervisor Guardian Stack — When Your Agent Needs an External Brain to Stop It From Destroying Itself

Agents fail in ways that pure retry logic can't fix. A tool error that loops forever, a cascade where one bad output poisons the next, a runaway loop burning $200 before anyone notices. The fix is not a smarter model. It's a separate control layer — a supervisor guardian — that watches the agent from the outside and makes decisions the agent itself cannot make about its own state.

## Forces

- **Agents lack metacognition.** A reasoning agent has no awareness of how many steps it's taken, how much money it's spent, or whether it's repeating itself. These are externally observable properties.
- **Loops are structural, not strategic.** An agent stuck in a goal-ambiguity oscillation will not "think harder" and escape. It needs an external interrupt.
- **Cascades move faster than humans.** By the time someone notices an agent is misbehaving, the damage — a corrupted DB, a hammered API, a drained budget — is already done. The guardian must be in the hot path.
- **Graceful degradation is a design choice, not a model capability.** The agent doesn't know when to give up and route to a human. That decision belongs to the supervisor.

## The Move

Wrap every agent invocation in a supervisor guardian layer with four distinct responsibilities:

- **Watchdog loop enforcement.** Track iteration count, elapsed time, and cumulative cost externally. Hard stop at configurable limits. This is not a suggestion — it's code that executes regardless of what the model is doing. Log the `stopped_reason` so the next handler knows exactly which guard fired.

- **Circuit breaker per tool call.** For each tool the agent calls, wrap it with a circuit breaker: track failure count on that specific tool, trip after N failures, fall back to an alternative or abort with context. This prevents the "hammering a dead API" problem where the agent retries the same broken tool 50 times. — https://kangclaw.github.io/posts/circuit-breaker-pattern-ai-agents/

- **Fallback chain routing.** When a tool or model fails persistently, the supervisor routes to a predefined fallback: a cheaper model, a simpler deterministic script, or a human escalation queue. The fallback chain is defined declaratively at deployment time, not discovered at runtime. — https://agentbrisk.com/blog/ai-agent-error-recovery-2026

- **Structured stop reasons, not free-text.** When the guardian stops an agent (budget hit, loop detected, tool circuit open), it emits a structured `stopped_reason` enum — `LoopDetected`, `BudgetExceeded`, `CircuitOpen`, `PersistentFailure` — with attached metadata (which tool, how many iterations, last error). This lets downstream handlers make decisions without parsing model output.

## Evidence

- **Research synthesis:** Zylos Research (2026) analyzed production failure distributions across multi-agent systems: ~42% specification failures, ~37% coordination breakdowns, ~21% verification gaps. The synthesis argues fault tolerance for agents "is not optional engineering hygiene — it is the core engineering challenge of the agentic era, requiring deliberate, systemic design." — https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery

- **Enterprise RPA hybrid:** Browser Use's Workflow Use (HN, May 2025) took a different approach: for repeated enterprise workflows, they shifted from fully agentic (LLM decides each step) to deterministic-with-embedded-agents. The LLM runs only in AI steps within an otherwise scripted flow — the supervisor is the script, not the model. Reported 10x speed and ~90% cost reduction versus pure agentic execution. — https://news.ycombinator.com/item?id=44007065

- **Production error taxonomy:** Agentbrisk (March 2026) documented a five-type failure taxonomy for agents — transient (retry with backoff), persistent (fallback logic or user communication), bad input (modify request or route differently), partial (correction prompt), timeout (retry or simplify). Each type maps to a different guardian response. — https://agentbrisk.com/blog/ai-agent-error-recovery-2026

- **Guard patterns:** The OpenHelm n8n toolkit (open source) implements retry logic, fallback chains, output validation, and error isolation as explicit infrastructure components — not prompts. Treats guardrail trips as data points about agent design weaknesses rather than outages to route around. — https://www.openhelm.ai/blog/ai-agent-retry-strategies-exponential-backoff

## Gotchas

- **The guardian itself can block valid long tasks.** A max-iteration limit that's too tight causes false positives on complex tasks that legitimately need many steps. Calibrate against the 95th percentile task length, not the median.
- **Fallback chains rot.** When a fallback model or simpler path is defined at deployment and never revisited, it accumulates gap. Schedule quarterly reviews of fallback chain health — does the simpler path still exist? Does the fallback model still meet minimum quality bar?
- **Structured stop reasons only help if something reads them.** If the guardian emits rich metadata that gets dropped into a log no one reads, the structured output is wasted. The escalation queue or retry handler must actually consume the `stopped_reason`.
- **Circuit breakers per tool require instrumentation.** You can't trip a circuit on a tool you've never measured. Every tool call needs to report success/failure through the supervisor's tracking layer — not just let exceptions propagate.
