# S-1889 · The Agent Failure Handling Stack — When Your Agent Crashes, Fails Wrong, and Goes Silent All at Once

Your agent returns HTTP 200. Every tool call succeeded. The trace shows a clean path through your orchestration graph. The user reports it sent a customer a 50% discount nobody authorized. Your agent didn't crash — it succeeded at the wrong thing. This is the failure mode that 86% of agentic deployments face and most aren't built to handle: the confident wrong answer that looks like success.

## Forces

- **Confidence failures masquerade as success.** Unlike traditional software that crashes with an error code, agents return HTTP 200 with semantically wrong output. There's no exception to catch — only a wrong answer that looks right.
- **Failures are probabilistic, not deterministic.** The same prompt that works once fails the next time due to model drift, token limit proximity, or a slightly different tool response format. You can't exhaustively test your way out.
- **Every agent action is a potential cascade point.** A wrong tool call in step 3 of a multi-step workflow throws an uncaught exception and leaves your system in an undefined state. No checkpoint. No retry. No fallback. Just silence and a broken pipeline you restart by hand.
- **Retrofitting resilience is 10x harder than designing it.** Teams build agents to work, then discover failure handling is the hard problem. By then the architecture is set.
- **The scariest failures aren't crashes — they're convictions.** The agent plows ahead doing the wrong thing with absolute confidence, and you only find out when damage is done.

## The move

Build layered failure handling into your agent architecture from day one. The pattern that production teams converge on: classify failures by type, then route each type to its appropriate recovery mechanism. The five categories, mapped to their recovery paths:

### 1. Classify before you act

| Failure Type | Example | Recovery |
|---|---|---|
| **Transient** | Rate limit (429), timeout, 503, DNS hiccup | Retry — same request succeeds after waiting |
| **Semantic** | Malformed JSON, wrong tool name, schema violation | Re-prompt with corrective context appended |
| **Resource** | Token budget exceeded, context overflow, spending cap | Reduce payload — summarize history, switch to cheaper model |
| **Capability** | Agent requests unavailable tool | Escalate to parent agent or route differently |
| **Fatal** | Auth failure, revoked API key, policy violation | Abort immediately, log, alert, return partial results |

Source: Neel Mishra, "Agent Error Handling: Retries and Fallbacks" — production battle-tested at miaoquai.com

### 2. Retry with exponential backoff + jitter

For transient failures, the standard range is 1s → 2s → 4s → 8s with a max of 3 retries. Add 30% jitter (`random.uniform(0, 1)`) to prevent thundering herd when multiple agents retry simultaneously after a shared outage. Different error types get different backoff curves — rate limits get longer waits than server errors.

Source: GitHub Discussion anthropics/anthropic-sdk-python#1341

### 3. Circuit breakers at every agent boundary

Set threshold at 5 consecutive failures OR >30% error rate in a 10-minute window. Three states: **Closed** (normal flow) → **Open** (fail fast, return degraded signal) → **Half-open** (probe with limited requests). The critical insight: if Agent A fails, Agent B must receive a "degraded mode" signal, not garbage input. Circuit breakers prevent cascading failures from propagating through multi-agent systems.

Source: jingchang0623-crypto on anthropics/anthropic-sdk-python#1341

### 4. Guard against confidence failures with output validation

Wrap every LLM output in a Pydantic schema or JSON validator before it touches downstream systems. This catches semantic errors (valid JSON, wrong content) that return HTTP 200. When validation fails: retry with explicit format correction in the next turn's system prompt — append the parse error and ask the model to correct it.

Source: The Operator Collective, "AI Agent Error Handling: When Your Bot Breaks Production" (March 2026)

### 5. Checkpoint-and-resume for long workflows

Save agent state (conversation history, tool call results, intermediate outputs) to a durable store (Postgres, DynamoDB, Temporal workflow) at every decision boundary. When a task fails mid-way, resume from the last checkpoint instead of restarting from scratch. This is the difference between a 2-minute recovery and a 2-hour restart.

Source: Neel Mishra, production-tested with Anthropic SDK

### 6. Model fallback chain

Chain models with a priority order: primary → secondary → tertiary. Example from production:

```
MODEL_CHAIN = [
  {"model": "claude-sonnet-4-20250514", "provider": "anthropic"},
  {"model": "gpt-4o", "provider": "openai"},
  {"model": "gpt-4o-mini", "provider": "openai"},
]
```

If the primary model fails (outage, timeout, content policy), fall back through the chain. Each fallback can reduce the prompt complexity — smaller models may not handle the full original task, so simplify on fallback.

Source: aimadetools.com "AI Agent Error Handling: Retries, Fallbacks, and Circuit Breakers" (2026)

### 7. Economic circuit breakers for cost control

Set a cost ceiling per task and per session. When the ceiling is hit: pause the task, notify the orchestrator, await budget top-up. This prevents runaway agents from burning through quotas on infinite loops or repeated retry storms. Track cumulative cost per conversation_id and halt before the next LLM call if the budget is exceeded.

Source: GitHub Discussion anthropics/anthropic-sdk-python#1341

### 8. Infinite loop prevention

Set `max_iterations=N` and `early_stopping_method='generate'`. For LangChain agents, the most common loop root cause is an ambiguous tool description or a missing stop condition. A single misdescribed tool can cause the agent to loop until it hits the iteration limit, burning through tokens with zero progress. Review tool descriptions for disambiguation and add explicit stopping conditions.

Source: Markaicode, "Fix LangChain Agent Infinite Loop" (May 2026)

### 9. Human-in-the-loop escalation

When all automated recovery paths are exhausted — retries failed, circuit breakers open, fallbacks degraded — escalate to a human operator. This is non-negotiable for compliance-critical operations in finance, healthcare, and legal. Design the escalation queue before you need it. The escalation path should include: the full task context, the error history, the partial results, and a human-readable summary of what the agent was attempting.

Source: Preporato, "Error Handling in AI Agents: Circuit Breakers, Retry & Recovery"

## Evidence

- **GitHub Discussion:** "What patterns do you use for AI agent error recovery?" — production contributors including miaoquai.com sharing tiered retry, circuit breaker, and economic circuit-breaker approaches — https://github.com/anthropics/anthropic-sdk-python/discussions/1341

- **Research Report:** Zylos AI "AI Agent Self-Healing and Failure Recovery" (May 2026) — taxonomy of multi-agent failures: ~42% specification failures, ~37% coordination breakdowns, ~21% verification gaps — https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery/

- **Engineering Blog:** The Operator Collective "AI Agent Error Handling: When Your Bot Breaks Production" (March 2026) — 86% of agent failures are recoverable; 40%+ of agentic projects cancelled by 2027 due to weak failure handling — https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide

- **Technical Guide:** aimadetools.com "AI Agent Error Handling: Retries, Fallbacks, and Circuit Breakers" (2026) — layered defense pattern with concrete Python implementations — https://www.aimadetools.com/blog/ai-agent-error-handling/

- **HN Launch:** Sentrial (YC W26) — YC-backed startup specifically for agentic failure detection, founded by engineers who experienced the problem at SenseHQ and Accenture — https://news.ycombinator.com/item?id=47337659

- **Developer Blog:** Neel Mishra "Agent Error Handling: Retries and Fallbacks" — four-category failure taxonomy with Anthropic SDK implementations — https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html

## Gotchas

- **HTTP 200 is not success.** If your observability stack only alerts on non-200 responses, you're blind to the most expensive class of failures — semantic errors where the output is valid but wrong. Instrument output validation, not just HTTP status.
- **Idempotency is not automatic.** Tool calls that create side effects (post to Slack, send an email, write to a DB) must carry idempotency keys. Without them, a retry after failure can double-execute the operation. The GitHub discussion contributors call this the "already posted" guard pattern.
- **Circuit breakers can flip-flop.** A half-open probe that succeeds doesn't mean the dependency is healthy — it means one request succeeded. Require 2-3 consecutive successes in half-open state before closing the circuit, or you'll get oscillation.
- **Backoff without jitter creates thundering herds.** When a shared dependency recovers, every waiting agent fires at once. Jitter (even small — 30% of the delay window) distributes the load and prevents a recovery event from becoming a second outage.
- **Retrofitting is 10x harder.** If you're building failure handling after the agent is deployed, you're changing the architecture under load. Plan for it in the initial design.
