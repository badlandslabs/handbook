# S-964 · The Agent Failure Handling Stack — When Your Agent Won't Quit or Won't Start

An agent that fails silently returns 200 OK and calls it done. An agent that fails loudly burns tokens in a loop until the context window collapses. Both are failure modes — and traditional try-catch blocks handle neither. The gap between agent failure and agent recovery is where production agentic systems live or die.

## Forces

- **Agents fail non-deterministically.** A tool returns a 400, the LLM retries with the same bad params, and the loop continues until the token budget evaporates. No stack trace, no crash — just silence that costs money.
- **Completion ≠ recovery.** An agent can reach a final state (out of context, out of retries) and report it as success. "Agent stopped due to max iterations" is a failure that looks like a finish.
- **Failure modes are layered.** LLM API failures (429, 5xx), tool execution failures (bad params, timeouts), semantic failures (wrong answer, hallucinated action), and cascade failures (one agent's error poisons the next) all need different recovery strategies.
- **The harness must own recovery.** The LLM cannot be trusted to recover itself — it will often double down on a failing strategy rather than pivot. Recovery is an infrastructure responsibility.

## The Move

Build a layered failure handling system: detect failures early, recover deterministically where possible, and fail safely when recovery isn't viable.

### 1. Classify failures by recoverability

Not all errors are equal. Separate three classes before deciding what to do:

- **Transient** (429, 5xx, network timeout): retry with backoff
- **Semantic** (wrong params, hallucinated tool call, bad output): do not retry — self-correct or escalate
- **Terminal** (out of context, max retries hit, policy violation): halt and report

LambdaFlux identifies three loop patterns that indicate which class you're in: **tool hammering** (same tool + same params + same error), **logic shuffling** (alternating tools without refining), and **hallucinated parameters** (confidently wrong inputs). Each requires a different intervention.

### 2. Implement progress-aware termination, not just iteration limits

Current agent frameworks cap total steps — but an agent can exhaust all iterations without making progress. The fix is progress tracking: compare the current step's tool calls, arguments, and results against the previous N steps. If nothing has changed for K consecutive steps, terminate early and return a `no_progress_detected` signal. LangChain's GitHub issue #36139 (closed June 2026) proposes this as `ProgressGuardMiddleware` — tracking same-tool + same-args + same-error and same-action + same-output patterns. This is more efficient than iteration limits because it stops *early*, not just *eventually*.

### 3. Design tools for idempotency

When an agent re-runs after failure, it often has no memory of prior progress. The fix is designing operations so duplicate execution produces the same end state, not duplicate artifacts. Core techniques from agentpatterns.ai:

- **Check-before-act**: probe for existing state before creating. One read to avoid two writes.
- **Upsert over create**: update existing artifacts rather than failing on existence.
- **State labels as checkpoints**: encode pipeline state in issue labels (`idea → researching → drafted`). An agent that checks the current label before transitioning avoids re-processing completed work.
- **Unique identifiers as keys**: use issue numbers or task IDs as natural idempotency constraints.

### 4. Layer circuit breakers at the infrastructure level

Circuit breakers belong outside the agent, at the tool/API gateway layer. A circuit breaker tracks failure rates per dependency — if a tool or LLM provider exceeds a failure threshold (e.g., 50% error rate in the last 10 calls), the breaker opens and subsequent calls fail fast rather than queueing behind a degraded service. This prevents the "thundering herd" problem where a recovering service gets swamped with retry traffic. Mavik Labs recommends setting timeouts on *all* remote calls, configuring circuit breakers per dependency, and retrying only on truly transient errors (429, 5xx) — never on 400s or 404s.

### 5. Use stateful rollback for multi-step tasks

When an agent fails partway through a multi-step task, rollback is required — but compensating transactions must themselves be idempotent. The agent must be able to safely retry the rollback if the rollback protocol is interrupted mid-execution. LangGraph and Microsoft Agent Framework provide native checkpoint/resume primitives: snapshot the agent state at decision points, and resume from the last checkpoint rather than from scratch. This is distinct from idempotency — idempotency prevents duplicate side effects; checkpointing preserves partial progress.

### 6. Degrade gracefully

Define fallback behaviors for each failure class before deployment. Options: serve a cached response, fall back to a simpler model, return a partial result with a clear uncertainty flag, or escalate to human review. Notion's response to the June 2026 Anthropic outage is the canonical example — they immediately disabled Anthropic models from their picker and rerouted requests to alternatives. Users experienced a model switch, not an outage. Teams that had configured provider-level fallbacks were resilient; teams that had not were scrambling.

## Evidence

- **GitHub Issue:** LangChain issue #36139 (closed) — `ProgressGuardMiddleware` proposal for progress-aware loop detection in agent tool execution, tracking same-tool + same-args + same-error patterns as the signal to terminate. — [github.com/langchain-ai/langchain/issues/36139](https://github.com/langchain-ai/langchain/issues/36139)
- **Production Case Study:** Asynq.ai candidate evaluation agent — hallucinated tool parameters, got stuck in loops, produced contradictory evaluations, cost 3x budget in production. Engineering response: explicit timeout configuration, retry budgets, loop detection, and observability instrumentation. — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Engineering Post:** Tanuj Garg (April 2026) — five distinct agent failure modes: hallucination-driven action, goal drift, tool hammering, context overflow, and cascade failures. Core thesis: agent reliability is a systems engineering problem, not a model quality problem. — [tanujgarg.com/blog/ai-agent-reliability-patterns](https://tanujgarg.com/blog/ai-agent-reliability-patterns)
- **Pattern Library:** AgentPatterns.ai — idempotent agent operations: check-before-act, upsert over create, state labels as checkpoints, unique identifiers as keys. — [agentpatterns.ai/agent-design/idempotent-agent-operations](https://www.agentpatterns.ai/agent-design/idempotent-agent-operations)
- **Guardrail Patterns:** LambdaFlux — "Agentic Death Loop": three loop patterns (tool hammering, logic shuffling, hallucinated parameters) with self-correction (soft) vs. circuit breaking (hard) as the two remediation strategies. — [lambdaflux.substack.com/p/the-ai-engineers-guide-to-agentic](https://lambdaflux.substack.com/p/the-ai-engineers-guide-to-agentic)

## Gotchas

- **Iteration limits stop late, not early.** Setting `max_iterations=50` caps total steps but doesn't detect that steps 20–50 were all failures. You need progress tracking on top of iteration limits.
- **LLM self-correction is unreliable for semantic failures.** The LLM that produced the wrong answer will often double down rather than pivot. Self-correction works for minor refinements; for fundamental errors, the harness must force an exit.
- **Retry without idempotency amplifies failures.** A non-idempotent tool called 3 times on retry becomes 3 duplicate records. Design idempotency into tools before adding retry logic.
- **Cascade failures are the hardest.** A transient error in tool A causes the agent to take a different path, which leads to a semantic error in tool B. The root cause (tool A) is gone by the time the real failure surfaces. This is why inter-agent trace data is essential.
- **Silent failure is worse than loud failure.** An agent returning "Done" after exhausting retries looks successful. Always emit a structured failure signal with the termination reason — `no_progress_detected`, `max_retries_exceeded`, `policy_violation` — not just "Agent stopped due to max iterations."
