# S-2351 · The Failure Taxonomy Stack — When Your Agent Fails Four Different Ways and You Handle Them All the Same

When your agent hits a rate limit, a malformed JSON response, a context overflow, and an auth failure — do you retry them all the same way? You shouldn't. Agents fail in four structurally distinct ways, and treating them identically is how a $0.01 task becomes a $2 runaway loop.

## Forces

- **Agents retry at token cost, not just compute cost.** Every retry in an agentic system re-sends the full conversation context — not just the failing HTTP request. A single flaky API endpoint can multiply costs 200x via retry amplification. Traditional microservice retry math doesn't apply.
- **LLMs fail semantically, not just transport-wise.** A tool call returns HTTP 200 with hallucinated output. Your circuit breaker never trips. You keep burning tokens on bad responses.
- **"Catch-all" exception handling makes things worse.** A blanket `except Exception: retry` re-attempts fatal failures (revoked keys, policy violations) that will never succeed — compounding the damage.
- **Checkpoint state persists across retries.** When a tool call fails at step 4 of 7, the agent has accumulated context that affects every retry. Retrying without checkpoint-based recovery means re-processing all prior steps on each attempt.

## The move

Build an error classifier first, then route each failure type to its appropriate recovery:

1. **Classify before you retry.** Route failures into four buckets: Transient (rate limits, timeouts, 503s), Semantic (malformed output, wrong schema, tool hallucination), Resource (token overflow, spending cap), Fatal (auth failures, revoked keys, policy violations).

2. **Transient → retry with exponential backoff + circuit breaker.** Wait before re-attempting. Cap total retries. The circuit breaker prevents thundering-herd amplification when a downstream service is genuinely down.

3. **Semantic → re-prompt with corrective context.** The tool returned garbage; re-invoke with explicit schema constraints or a different tool selection. Do not mechanically retry the same call.

4. **Resource → reduce payload, don't retry blindly.** Summarize or truncate prior results, drop older conversation history, switch to a smaller/faster model. Retrying at the same token budget just hits the same wall.

5. **Fatal → abort immediately, log, alert.** A revoked API key will never succeed. Revoked tokens, removed endpoints, and policy violations are logged and escalated to a human. No retry.

6. **Pair circuit breakers with graceful degradation.** An open circuit with no fallback stalls the agent anyway. Route to a confirmation gate or a simpler fallback model so the agent can still make progress.

7. **Implement checkpoint-based recovery.** Persist intermediate state after each successful tool call. On failure, resume from the last checkpoint — do not restart the full workflow.

## Evidence

- **Technical guide (Agentbrisk):** Production failure taxonomy with four distinct error categories and recovery strategies — transient, semantic, resource, fatal. Notes that a blanket `except Exception: retry` is worse than no error handling. — [agentbrisk.com](https://agentbrisk.com/blog/ai-agent-error-recovery-2026/)

- **Engineering blog (Tian Pan):** The retry storm problem — each agent retry re-sends the full conversation context, not just the failing HTTP request. A single flaky endpoint can produce 200x token cost amplification relative to a single successful execution. — [tianpan.co](https://tianpan.co/blog/2026-04-10-retry-storm-problem-agentic-systems)

- **Engineering blog (AgentPatterns.ai):** LLM-backed tools routinely return HTTP 200 with hallucinated output, so circuit breakers keyed on transport errors never trip. Pairing the breaker with semantic failure detection and a confirmation gate is required for agents. — [agentpatterns.ai](https://www.agentpatterns.ai/agent-design/agent-circuit-breaker)

- **Technical guide (Logiciel.io):** Q1 2025 SaaS incident: autonomous data cleanup agent with write access corrupted 9,000 of 14,000 customer records over a weekend due to unanticipated edge case. Recovery took 31 hours. Root cause: missing guardrails. OWASP LLM Top 10 v2.0 lists excessive agency as a top production risk. — [logiciel.io](https://logiciel.io/blog/guardrails-agentic-ai)

- **HN thread:** "Ask HN: How are you testing AI agents before shipping to production?" surfaced six specific failure modes: hallucination under unexpected inputs, edge case collapse, prompt injection, context limit surprises, cascade failures, and data inconsistency. — [news.ycombinator.com](https://news.ycombinator.com/item?id=47325105)

## Gotchas

- **Don't retry at the same token budget when hitting Resource errors.** You'll hit the same limit. Reduce context first, then retry.
- **Semantic failures return HTTP 200.** If you're only tracking error codes, you'll never detect them. Add output schema validation as part of the tool result handler.
- **Agents without checkpoints restart from scratch on retry.** This means every failure triggers full context re-processing — the worst possible outcome for expensive multi-step workflows.
- **Graceful degradation requires a plan, not just a circuit.** When the circuit opens and there's no fallback path, the agent stalls anyway. Design the fallback before you need it.
