# S-2129 · The Agent Failure Surface Stack — When Every Agent Is Safe Until a Surface-Dependent Glitch Unmasks It

Your agent passes every unit test. It reasons cleanly, calls the right tools, and produces correct outputs on your golden dataset. Then in production a rate limit hits mid-workflow, a tool returns malformed JSON, and the agent loops on the same failed call until it burns through your budget. The failure wasn't the agent's fault — it was yours, for not treating the tool interface as the actual failure surface.

## Forces

- **Failure is compound, not singular.** A 98% reliable agent × 5 sequential steps = 90% end-to-end reliability. This math ignores transient infrastructure failures (rate limits, network blips, API timeouts) that compound across every tool call. Silent failures at 3 AM are the ones that count.
- **Agents fail unpredictably but in predictable categories.** Tool hallucinations, loops, context overflows, permission escalations, and silent output corruption are all known failure modes with known mitigations. Teams treat each one as a surprise because they build agents defenseless by default.
- **The tool interface is where agents go to die.** Every tool is a potential failure point: wrong input format, error strings the agent wasn't trained to handle, malformed outputs that break downstream schema expectations, and network timeouts that return nothing.
- **Multiplication, not addition.** Three structural failure modes (binding without approval, operating beyond authorised permissions, economic case requiring service quality the agent can't guarantee) appear across Air Canada, DPD, Replit, Cursor, Klarna, and NYC MyCity — and the same seven OWASP ASI controls cover all of them.

## The Move

Build failure resistance into the agent's infrastructure, not into the agent itself. The agent should encounter failures as structured signals it can act on — not as crashes, loops, or silent corruption.

### The fallback stack

Structure every external dependency as a stack of alternatives, not a single call:

```
Level 1: Primary service (fastest, best quality)
Level 2: Backup service (slower but reliable)
Level 3: Cached data (stale but functional)
Level 4: Graceful error message (honest, actionable)
```

Each level is worse than the previous. That's the point — degrading gracefully is infinitely better than crashing.

### Retry with exponential backoff and jitter

Transient failures (network blips, brief rate limits, upstream timeouts) are resolved by retrying, but naive retry loops amplify the problem. The correct pattern:

- Exponential backoff: wait time doubles after each failure (1s, 2s, 4s, 8s...)
- Jitter: add random variance so concurrent failures don't thunder on the same endpoint
- Retry budget: cap total attempts (e.g., 4 max) so a degraded service doesn't burn resources indefinitely

### Circuit breakers

When a dependency is genuinely down (not just slow), retries are waste. A circuit breaker tracks failure rates and opens the circuit when a threshold is crossed, fast-failing subsequent calls and giving the service time to recover. This prevents cascade failures where one degraded service causes all dependent agents to pile up.

### Loop detection and kill switches

Tool call loops are the most common silent failure: agent calls a tool → tool returns error → agent retries → same error → repeat until token budget exhausted. Detection mechanisms include:

- Action history monitoring: flag when the same tool+input pair appears N times in a rolling window
- Semantic repetition: flag when agent output becomes self-similar across consecutive turns (n-gram or embedding similarity)
- Hard iteration cap: set a maximum step count per workflow, with a defined stop behavior

Kill switches must live at the infrastructure layer, not the software layer. A compromised agent can ignore a software-level flag; it cannot bypass a network-layer circuit break.

### Dead letter queues and escalation

Not every failure should be retried. Unrecoverable failures (permission denied, schema mismatch, tool permanently unavailable) should route to a dead letter queue for human review rather than looping. Define a taxonomy of failure types: retryable (transient), recoverable with modification (tool input needs fixing), unrecoverable (escalate), and terminal (stop and report).

### Idempotent agent actions

Safe retries require that repeating an action doesn't produce duplicate side effects. Tool calls that write, send, or mutate should carry idempotency keys or be wrapped so that a second execution is a no-op rather than a double-charge or double-write.

### Context overflow guard

Treat context as a scarce resource, not a buffer. Never let raw input touch the model unprocessed. Always run a preprocessing layer that chunks large documents, summarises content, or extracts relevant sections. A context window hit mid-reasoning returns garbage with no error signal.

## Evidence

- **Blog post:** "When Agents Fail: Retry Logic, Circuit Breakers, and Dead Letter Queues for AI Pipelines" — Supergood Solutions documents the compounding reliability math (98% × 5 = 90%) and provides four concrete patterns with implementation details — [supergood.solutions/blog/systems-sunday-agent-failure-recovery-2026](https://supergood.solutions/blog/systems-sunday-agent-failure-recovery-2026)
- **Engineering post:** "Multi-Agent System: 5 Lessons from Running One in Production" — Toucan Toco CTO David Nowinsky details failure taxonomy for multi-agent systems, including unpredictable model behavior, tooling complexity, and silent failure modes specific to LLM-agent systems — [toucantoco.com/en/blog/error-handling-observability-multi-agents-system](https://www.toucantoco.com/en/blog/error-handling-observability-multi-agents-system)
- **Engineering post:** "Building Reliable Agents: Lessons from Production" — Marcus Rivera (Agent Mag) identifies four primary failure categories (context overflow, tool loops, silent output corruption, permission escalation) with concrete fixes for each — [agentmag.dev/articles/building-reliable-agents-production-lessons](https://agentmag.dev/articles/building-reliable-agents-production-lessons)
- **GitHub repo:** "Awesome Agent Failures" — vectara/awesome-agent-failures (194 stars) is a community-curated catalog of known failure modes, real-world case studies, and mitigation techniques — [github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **GitHub issue:** crewAI loop detection middleware (Issue #4682, closed completed) — the crewAI team shipped a real-time loop detection middleware that monitors action history and breaks repetitive patterns before token budget exhaustion — [github.com/crewAIInc/crewAI/issues/4682](https://github.com/crewAIInc/crewAI/issues/4682)
- **Engineering post:** "Graceful Degradation — How AI Agents Handle Failing Services" — documents the fallback stack pattern with concrete examples across Brave Search → GLM Web Search → cached fetch → error message — [kangclaw.github.io/posts/graceful-degradation-ai-agents](https://kangclaw.github.io/posts/graceful-degradation-ai-agents)
- **Security analysis:** "Six Agentic AI Failure Cases" — agentmodeai.com clusters six documented failures (Air Canada, NYC MyCity, Replit, Cursor, Klarna, DPD) into three structural failure modes, each covered by OWASP ASI controls — [agentmodeai.com/agentic-ai-failure-case-studies](https://agentmodeai.com/agentic-ai-failure-case-studies)

## Gotchas

- **Don't build retry logic into the agent's prompt.** Retry decisions should be infrastructure-level, not model-level. The agent should receive structured failure signals it can reason about, not raw exceptions it has to interpret.
- **Don't skip the dead letter queue.** Without it, unrecoverable failures either loop (wasting resources) or vanish (losing work). Both are worse than a human-in-the-loop review.
- **Circuit breakers must be per-dependency.** A single global circuit breaker will cascade-open and take down every tool simultaneously. Each tool or API gets its own breaker with its own threshold tuned to that tool's expected failure profile.
- **Loop detection needs a semantic layer, not just counting.** Simple repeat-counting flags every agent that legitimately re-reads a file. Track tool+input+output similarity, not just the call count.
- **Don't place kill switches in software.** Infrastructure-layer kills (network ACLs, process memory limits, container cgroup limits) cannot be bypassed by a compromised or confused agent. Software flags can be ignored.
