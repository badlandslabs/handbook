# S-1969 · The Error Classification Stack · When Your Agent Crashes Silently and Burns Budget

When your AI agent hits a rate limit at step 3 of a multi-step workflow, throws an uncaught exception, and leaves your system in an undefined state — no checkpoint, no retry, no fallback, no alert. Just silence and a broken pipeline you restart by hand.

## Forces

- **Agent failures are non-deterministic** — a prompt that worked once might fail the next time due to model drift, token limits, or a hallucinated tool argument. Standard try/catch doesn't cover these modes.
- **Retries are expensive in a new way** — unlike HTTP retries, agent retries resend the full conversation context. Ten retries × 8,000 tokens of accumulated context = 80,000 tokens of input processing for zero productive work.
- **Failure cascades invisibly** — an error at step 2 poisons steps 3–5. Multi-step chains degrade fast: 90% per-step reliability gives you 42% across three steps. The agent may loop for 35 minutes before a human notices.
- **The 88% production gap** — ~88% of AI agent projects never reach production, largely because failure handling wasn't architected from the start.

## The Move

Classify errors at the tool level and branch recovery strategy accordingly, layered with budget guards and checkpoint state:

**1. Classify errors into five types at the tool-definition level, not at the orchestration level:**
- `transient` — network hiccups, rate limits (429). Strategy: exponential backoff + retry.
- `budget` — cost ceiling hit mid-task. Strategy: `budget-paused` state, notify orchestrator.
- `capability` — agent requested an unavailable tool. Strategy: escalate to parent agent.
- `semantic` — LLM output failed validation (valid JSON, wrong schema). Strategy: retry with explicit format correction in system prompt.
- `fatal` — unrecoverable state (irreversible action already committed). Strategy: mark task failed, return partial results + error, trigger human review.

**2. Cap retry token burn with context-aware backoff:**
- Each retry in an agent resends the full conversation. Cap total retries per request (3–5 max).
- Use jitter: 1s, 2s, 4s, 8s, cap at 30s. Without jitter, concurrent agents create thundering herds.
- If retry N+1 burns more tokens than the entire task budget, stop immediately and escalate.

**3. Circuit breaker: treat repeated identical errors as a circuit trip:**
- After 5+ consecutive identical errors (regardless of HTTP code), stop retrying for X minutes.
- This prevents cascading failures from a single degraded endpoint poisoning a multi-agent pipeline.

**4. Checkpoint state before irreversible tool calls:**
- Before any state-mutating operation (file write, DB commit, API POST), write a rollback marker.
- On failure, restore from checkpoint instead of re-running from step 1.
- Teams building rollback into filesystem ops, database writes, external API calls, and multi-agent pipelines treat this as foundational infrastructure, not an afterthought.

**5. Guardrails as enforcement, not detection:**
- Pre-LLM guardrails: intercept bad inputs before they reach the model (PII redaction, scope validation, jailbreak detection).
- Post-LLM guardrails: catch hallucinated claims, out-of-scope actions, or invalid JSON before output reaches the user.
- Human-in-the-loop (HIL) approval for irreversible actions (deletions, payments, policy changes) lives *outside* the agent's prompt — it's an architectural gate, not a prompt instruction.
- Risk-tier escalation: define low/medium/high/critical tiers. Low = autonomous; high = human approval required before execution.

**6. Max iterations as a safety net, not a strategy:**
- Set `max_iterations` (LangChain default: 15) to hard-stop infinite loops.
- One team reported 92% token cost reduction after setting `max_iterations=10` with `early_stopping_method='force'`.
- But: hitting max iterations is a signal of unresolved complexity. Log it, alert on it, don't just swallow it.

**7. Tool error isolation:**
- When an MCP tool call times out or errors, it should not crash the entire agent. Catch tool-level errors in the agent loop, allow the agent to attempt recovery or an alternative approach.
- Without isolation, one slow MCP endpoint poisons the entire agent execution. VoltAgent filed and fixed this exact bug (GitHub #430, July 2025).

## Evidence

- **GitHub Discussion:** AI Agent Error Recovery Patterns — Anthropic SDK community discussion covering error classification framework (transient/budget/capability/semantic/fatal), tiered retry strategies, and multi-model fallback chains. Reports: proper error handling increased agent reliability from 87% to 99.2% (14× fewer failures). — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

- **Engineering Blog:** The Retry Storm Problem in Agentic Systems — Detailed analysis showing 10 retries × 8,000-token context = 80,000 tokens for zero productive work. Introduces the concept of "cost amplification factor" unique to agents vs. traditional microservices. — [tianpan.co/blog/2026-04-10-retry-storm-problem-agentic-systems](https://tianpan.co/blog/2026-04-10-retry-storm-problem-agentic-systems)

- **Company Engineering Post:** Human-in-the-Loop Escalation Design — Production data showing 88% of AI agent projects never reach production; 3-step chain at 90%/step = 42% overall reliability; calibration gap of ~15 percentage points between claimed and real accuracy. — [digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026](https://www.digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026)

- **Primary Source (2025):** Taxonomy of Failure Modes in Agentic AI Systems — Microsoft Security whitepaper identifying four systemic failure categories: security lapses, hallucinations, memory poisoning, and planning loops. Released April 2025. — [microsoft.com/en-us/security/blog/2025/04/24/new-whitepaper-outlines-the-taxonomy-of-failure-modes-in-ai-agents](https://www.microsoft.com/en-us/security/blog/2025/04/24/new-whitepaper-outlines-the-taxonomy-of-failure-modes-in-ai-agents)

- **GitHub Issue:** MCP Tool Execution Error Crashes Whole Agent — VoltAgent bug report (July 2025) documenting that MCP tool timeout causes entire agent to fail. Filed and merged PR #436. Confirms tool error isolation is a common architectural oversight. — [github.com/VoltAgent/voltagent/issues/430](https://github.com/VoltAgent/voltagent/issues/430)

## Gotchas

- **Don't retry everything** — classifying every error as transient leads to retry storms that amplify both latency and cost. Error classification must happen at the tool definition level, not guessed by the orchestrator.
- **Don't skip the budget guard** — without a hard cost ceiling per request, a single agent task can burn through budget in retry loops. Set `max_total_retries` and `max_tokens_per_request` as architectural constraints, not just config values.
- **Don't rely on max_iterations alone** — it's a hard stop, not a recovery strategy. It tells you the agent failed; it doesn't tell you why or recover state. Treat it as an alert trigger, not an error handler.
- **Don't put HIL approval in the prompt** — if human oversight is implemented as a system prompt instruction ("ask for approval before deleting"), a sufficiently capable agent may reason around it. HIL must be an out-of-band architectural gate, not a prompt-level constraint.
- **Don't skip logging error context** — "Error: request failed" is useless in production. Log the full request, response, agent state, step number, token count, and retry count. Without this, debugging is archaeology.
