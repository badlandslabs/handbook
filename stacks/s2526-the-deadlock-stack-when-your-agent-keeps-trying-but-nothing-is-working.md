# S-2526 · The Deadlock Stack — When Your Agent Keeps Trying But Nothing Is Working

Your agent is running. No errors. No crashes. It just keeps calling tools, accumulating context, growing more confident — and producing nothing useful. The agent is not failed in any way a traditional exception handler would catch. It is stuck in a failure mode unique to autonomous agents: the deadlock of self-referential progress. The move is a layered recovery architecture that distinguishes failure types and routes each to the right response — retry, re-prompt, fallback, or human.

## Forces

- **Retries assume transience, but agent failures often aren't.** Standard retry logic works for network timeouts and 429s. It does not work when the agent chose the wrong tool, misread user intent, or acted on stale context. Retrying in these cases compounds cost while the agent grows more confident in the wrong direction.
- **Silent drift is more dangerous than crashes.** The most costly production failures are not exceptions — they are agents that continue running without erroring while producing stale, wrong, or increasingly degraded output. A crash is visible. Silent drift is not.
- **Failure taxonomy is a prerequisite for recovery.** You cannot build a recovery system that handles "errors" until you have classified what kinds of failures your agent actually produces. A rate limit requires different handling than a hallucinated tool call, which requires different handling than a context overflow, which requires different handling than an infinite reasoning loop.
- **Escalation policy is structural, not prompted.** Expecting the agent to decide when to hand off to a human is not a recovery strategy — it is a single point of trust in an unreliable system. Escalation must be codified in the execution layer, not left to the model's judgment.

## The move

Build a four-layer recovery architecture, each layer handling a distinct failure class. The layers are ordered: exhaust cheaper, faster fixes before escalating to slower, more expensive ones.

**Layer 1 — Retry with exponential backoff and jitter**
- Target: transient failures only (HTTP 429, 503, timeouts, DNS failures)
- Apply exponential backoff with jitter to avoid thundering herd
- Cap the maximum number of retries; do not retry indefinitely
- Exit with a semantic error code rather than a raw HTTP code — let the next layer decide

**Layer 2 — Semantic re-prompt with corrective context**
- Target: malformed tool calls, wrong tool selection, JSON formatting failures
- Re-inject the error, the original tool schema, and a corrective instruction into the next LLM call
- Do not retry the exact same prompt — the agent needs new context to self-correct
- Cap at one re-prompt attempt; if it fails, the problem is architectural, not transient

**Layer 3 — Fallback chain (provider-agnostic model routing)**
- Target: persistent failures from a specific provider or model
- Maintain a ranked fallback list (primary model → secondary model → rule-based fallback)
- Route on failure type: if the primary model produces semantic errors, try a model with different instruction-following behavior
- Preserve partial outputs — a degraded answer is better than no answer if the user expects one

**Layer 4 — Circuit breaker and human escalation**
- Target: cascading failures, infinite loops, or failures that survive all prior layers
- Track failure counts and rates per component (tool, model, API endpoint)
- Open the circuit when failure rate exceeds threshold; stop routing traffic to the failing component
- Escalate to human review with full context snapshot — do not ask the agent whether to escalate
- Include a hard maximum execution time that terminates regardless of internal state

**The degradation ladder (enforce in code, not prompts)**
1. Retry briefly if the failure looks transient
2. Switch to a compatible fallback if the contract can stay the same
3. Reduce capability on purpose if the backup is weaker (fewer tools, shorter context)
4. Escalate to human with the full state snapshot
5. Log and halt — do not allow silent continuation

## Evidence

- **Engineering blog — Operator Collective:** Documents that 86% of agent failures are recoverable, and that the gap between "experimenting" and "production-ready" is almost entirely an engineering problem. The AI model rarely causes catastrophic failures — it's the integrations that fail: APIs that time out, rate limits hit at 3 AM, context windows that overflow, tool calls that silently return nothing. — [theoperatorcollective.org](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)
- **Research synthesis — Zylos Research:** Synthesizes patterns from real-world post-mortems 2025–2026, finding that agents fail in ways conventional microservices do not: silently looping, spawning redundant subprocesses, accumulating context until the model halts, or taking irreversible actions before human intervention. Proposes circuit breaker and supervisor tree patterns borrowed from distributed systems. — [zylos.ai](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery/)
- **Engineering post — Meta data engineer (HackerNoon):** Argues that standard retry logic fails for agents because agent reasoning failures are not transient — a wrong tool choice, misread intent, or stale context doesn't reset between retries. Retrying compounds cost while the agent remains confident it's making progress. Circuit breakers and explicit escalation gates outperform retry-at-all-costs strategies. — [hackernoon.com](https://hackernoon.com/your-agent-doesnt-need-better-retries-it-needs-a-circuit-breaker)
- **HN Ask thread — AI agent testing before production (harperlabs):** Documents 7 core failure modes: hallucination under unexpected inputs, edge case collapse (null values, Unicode names), prompt injection, context limit surprises, infinite loops, silent context drift, and tool call hallucinations. Notes that 67% of AI system failures stem from improper error handling rather than algorithmic issues. — [news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)

## Gotchas

- **Do not retry reasoning failures as if they are transient.** An agent that chose the wrong tool doesn't have a connectivity problem. Re-prompt with corrective context instead, or escalate. Retrying the same reasoning with the same context produces the same result.
- **Hard-code the escalation policy in the execution layer.** If you rely on the agent to decide when to escalate, it will escalate either too late or too often — depending on how it was prompted. Escalation thresholds belong in infrastructure, not prompts.
- **Track failure rates, not just failure counts.** A single model that fails 3 times in 10 minutes is a circuit breaker candidate. A model that fails 3 times in 10,000 calls is within normal variance. Set rate-based thresholds, not absolute counts.
- **Preserve checkpoint state before risky operations.** If the agent takes an irreversible action and then fails, you need to know what state it had when it decided to act. Without checkpointing, recovery means starting over with no visibility into what went wrong.
