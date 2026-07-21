# S-1436 · The Agent Failure Recovery Stack — When Your Agent Looks Fine But Is Silently Losing Money

Your agent is running. Every health check passes. CPU is nominal, memory is fine, the process hasn't crashed. Three hours later you check your API bill and it has multiplied. The agent spent the whole time in a logic loop, burning tokens on the same broken operation. Or worse: it returned a confident, well-formatted response that was subtly, completely wrong — and your user acted on it. Agent failure is not a crash. It is a silent budget drain and a correctness hole. This entry covers the recovery stack that makes agents fail loudly, cheaply, and recoverably.

## Forces

- **Agents don't raise exceptions — they return 200 OK with wrong answers.** Unlike traditional software where a failure is obvious, agent failures often produce valid HTTP responses that are fundamentally incorrect. No stack trace. No alert. Just quietly wrong outcomes.
- **A retry is not automatically safe.** Unlike a GET request, a tool call may have already mutated state (created a record, sent an email, charged a card). Retrying blindly causes duplicate side effects.
- **The agent plans its own call graph at runtime.** You cannot statically enumerate which tools get called, how many times, or in what order. Fixed retry counts and static exception handlers don't cover it.
- **Cost is the only reliable loop detector.** CPU and memory are useless for I/O-bound LLM calls. The agent looks healthy by every traditional metric while burning 200x its normal token budget.

## The Move

The failure recovery stack operates in five layers, from innermost to outermost:

1. **Hard step caps** — The single highest-leverage guardrail. If the agent doesn't finish in N steps (default: 12 for LangGraph via `recursion_limit`), stop, checkpoint, and escalate. The cap must be enforced outside the agent's own reasoning loop — it is a mechanical limit, not a self-imposed one.

2. **Structured error feedback** — Wrap every tool call in explicit `try/except` with a predefined recovery path. Feed the model a structured error object back into context: what failed, why, what a valid retry looks like. `"Error: invalid date format, expected ISO 8601 (YYYY-MM-DD)"` lets the model self-correct. A raw stack trace does not. Never let the LLM decide what to do when a tool fails — give it the answer.

3. **Error taxonomy drives recovery strategy** — Four categories, four different responses:
   - **Transient** (rate limits, timeouts, 503s): retry with exponential backoff + jitter
   - **Semantic** (malformed JSON, hallucinated tool args): re-prompt with corrective context, don't retry the same prompt
   - **Specification** (wrong instruction, bad tool definition): fix the prompt/tool before any retry
   - **Cascade** (early failure contaminates downstream steps): rollback to last checkpoint, restart from clean state

4. **Idempotency keys for safe retries** — Every mutating tool call must carry an idempotency key. On retry, the tool checks whether the operation already succeeded and returns the cached result rather than re-executing. This makes retries safe by design rather than by inspection.

5. **Escalation chain with state handoff** — When all recovery paths are exhausted: warn → nudge (send progress summary back to model with a "try differently" signal) → escalate to human → terminate with full checkpoint dump. Never kill the process without persisting state — losing checkpoint data means the next run repeats the same failure.

## Evidence

- **HN Show HN — Agentic Reliability Framework (ARF):** Former reliability engineer at NetApp built ARF after observing that production AI systems fail silently, cost $50K–$250K per incident, and take 30–60 minutes to recover manually. ARF's three-agent approach (Detective / Diagnostician / Predictive) reduced MTTR from 45 minutes to 2 minutes. — [github.com/petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)
- **r/LangChain — Practitioner post on monitoring:** "The agent looks 'healthy' by every metric except cost. Token usage goes from 200/min to 40,000/min. The fix: track token cost per heartbeat cycle — if it spikes 10–100x above baseline, something is wrong." — [reddit.com/r/LangChain/comments/1s5j8rn](https://www.reddit.com/r/LangChain/comments/1s5j8rn/three_ai_agent_failure_modes_my_old_monitoring)
- **Zylos Research — Agent failure taxonomy:** Analysis of multi-agent production deployments found ~42% specification failures, ~37% coordination breakdowns, ~21% verification gaps — each requiring a categorically different recovery approach. — [zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery)

## Gotchas

- **Don't retry without idempotency.** If a tool call created a database record, a blind retry creates a duplicate. Build idempotency into the tool layer before you write a single retry loop.
- **Step caps must be mechanical, not negotiated.** A step cap the agent can reason around is not a step cap. Enforce it in the orchestration runtime, not in the system prompt.
- **Cost monitoring is the only reliable loop detector.** Traditional APM (CPU, memory, process uptime) is blind to I/O-bound LLM loops. Set a token-budget-per-minute threshold and alert on it.
- **Cascade errors are the most dangerous failure mode.** A failed API call doesn't raise an exception — it returns `null`, which the next tool interprets as valid input. Build output validation guards at every tool boundary, not just at the final response.
