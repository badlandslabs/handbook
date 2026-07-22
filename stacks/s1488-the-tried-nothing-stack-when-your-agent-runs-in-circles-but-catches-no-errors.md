# S-1488 · The Tried-Nothing Stack — When Your Agent Runs in Circles But Catches No Errors

When your agent silently loops for 35 minutes, spawns redundant subprocesses, or completes a 10-step plan that ends in incoherent output — and none of it surfaces as an error until the user notices.

## Forces

- **A command that exits zero is not the same as a task that succeeded.** A tool returning empty output, a plan completing step-by-step without achieving the goal, a user saying "that's not what I meant" — these are failures no exception handler catches.
- **Blind retries repeat the same mistake faster.** Retrying an LLM call or tool invocation without changing the approach just burns tokens. Recovery must change something.
- **A 10-step pipeline where each step has 85% reliability has 19.6% overall reliability.** Long agentic workflows are multiplicative failures waiting to happen. Without systemic recovery, a multi-step agent is almost guaranteed to fail.
- **Step caps are the only thing preventing infinite loops** — but without structured recovery on cap-exit, you've just failed loudly instead of silently.
- **67% of AI system failures stem from improper error handling, not algorithmic issues.** (Zylos Research, 2026) The problem is almost never the model. It's the scaffolding around it.

## The move

Build a layered failure recovery system — not retry loops, but a hierarchy that classifies errors before choosing a response:

**1. Classify before you recover.** Sort failures into types that demand different responses:

| Type | Signal | Response |
|------|--------|----------|
| `transient` | Network hiccup, rate limit, timeout | Exponential backoff + retry (1s → 2s → 4s → 8s) |
| `budget` | Cost ceiling hit | `budget-paused` state, notify orchestrator |
| `capability` | Missing tool, permission denied | Escalate to parent agent or halt with reason |
| `semantic` | LLM output fails validation | Retry with explicit format correction in system prompt |
| `fatal` | Hard cap hit, unrecoverable state | Mark failed, return partial results + error receipt |

*(Anthropic GitHub Discussion #1341, production patterns thread)*

**2. Hard step cap as the primary guardrail.** Set a maximum step count before any execution. When the cap is hit, stop, document state, and escalate — do not continue. A step cap without a structured exit is just a prettier failure.

```python
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    raise AgentExceededSteps(f"didn't finish in {MAX_STEPS}")
```

*(Rajpoot, "LLM Agent Error Recovery in 2026," 2026)*

**3. Circuit breakers prevent cascading token burn.** After N consecutive failures on a single tool or model, stop calling it and switch to a fallback. A circuit breaker that still retries the same broken service is just a more expensive loop.

**4. Checkpoint at every meaningful boundary.** Save execution state (not just conversation history) at defined intervals — before each major step, after each tool call. When a workflow resumes from checkpoint, it replays only the remaining steps, not the completed ones. LangGraph, Temporal, and Dagster all ship first-class checkpoint primitives. The overhead (typically 50–200ms per checkpoint) is negligible against the cost of re-running a failed 20-step pipeline.

**5. Return partial results + error receipt on fatal failures.** Never return nothing. A failed agent that returns what it accomplished plus a structured error document (what it tried, what failed, why it couldn't recover) lets downstream systems make decisions without a human in the loop.

**6. Treat output quality as a failure signal.** Empty tool output, output that doesn't match the expected schema, output the user rejects — these are failures even when no exception fires. Build semantic validation into the tool result handler.

*(Dan Groch, "Failure Recovery: Real Agents Need More Than Retries," 2026 — [dangroch.com](https://dangroch.com/2026/03/16/failure-recovery-for-ai-agents))*

## Evidence

- **Blog post:** Dan Groch's failure taxonomy expands "failure" to include semantic failure (plan completes but user rejects output), implicit failure (empty tool result), and compounding failure (error propagates through a multi-step plan) — arguing that production agents need metacognitive error detection, not just exception handlers. The full implementation is on [GitHub](https://github.com/dgroch/metacognition).

- **Microsoft whitepaper:** The Microsoft AI Red Team published a formal taxonomy of failure modes in agentic AI systems (April 2025), distinguishing Safety failures (unintended harm from correct action) from Security failures (integrity/availability from adversarial input). Novel agentic failure modes include goal hijacking, plan manipulation, tool poisoning, and cross-agent trust exploitation. The paper was validated across Microsoft Research, Azure Research, and external practitioner interviews. — [Microsoft Security Blog](https://www.microsoft.com/en-us/security/blog/2025/04/24/new-whitepaper-outlines-the-taxonomy-of-failure-modes-in-ai-agents/) · [Whitepaper PDF](https://cdn-dynmedia-1.microsoft.com/is/content/microsoftcorp/microsoft/final/en-us/microsoft-brand/documents/Taxonomy-of-Failure-Mode-in-Agentic-AI-Systems-Whitepaper.pdf)

- **GitHub discussion:** The Anthropic SDK Python community collected production error recovery patterns — the dominant strategy is five-tier error classification (transient/budget/capability/semantic/fatal) with per-type recovery handlers and a budget-paused state to prevent runaway costs. — [anthropics/anthropic-sdk-python#1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

- **Enterprise data:** Proper error handling (retry + circuit breaker + fallback + step caps + graceful degradation) increased agent reliability from 87% to 99.2% in a production deployment measured by OpenHelm — a 14× reduction in failure rate. — [OpenHelm Blog](https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)

- **Zylos Research (2026):** The five-stage self-healing cycle — Detection → Diagnosis → Repair → Validation → Optimization — is now implemented across major production frameworks. Specification failures account for ~42% of multi-agent failures, coordination breakdowns ~37%, and verification gaps ~21% (Galileo 2025 data). — [Zylos Research](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery/)

## Gotchas

- **Setting a step cap without a structured exit is just a louder crash.** The cap must trigger a defined recovery path — partial results, escalation, fallback — not just an exception.
- **Retrying without changing the input is not recovery.** If a tool call fails because the arguments were wrong, retrying with the same arguments just wastes tokens. Retry logic must include error-classification that drives a different approach.
- **Checkpointing conversation history is not the same as checkpointing execution state.** Saving the chat log doesn't let you resume mid-step. You need to save the workflow state graph — current step, pending operations, environment state.
- **Hard step caps that are too high defeat their purpose.** If your cap is 50 steps, your agent can still burn enormous cost before failing. Most production systems land on 8–15 steps as a reasonable bound.
- **Graceful degradation that degrades to nothing is not graceful.** If your fallback chain ends in "we couldn't do anything" with no notification, you've just moved the failure to a place nobody sees.
