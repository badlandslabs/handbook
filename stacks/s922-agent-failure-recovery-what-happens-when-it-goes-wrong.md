# S-922 · Agent Failure Recovery — What Happens When It Goes Wrong

You have a multi-step agent running in production. The LLM provider hits a 503. A tool call returns 200 but garbage. Two agents ask each other for clarification in a loop. A user is waiting. The agent is quietly spending $6,000.

## Forces

- Traditional try-catch does not cover LLM failure modes — a model can return HTTP 200 with confident hallucinations, or loop indefinitely producing valid-looking tokens.
- Naive retry logic amplifies failures by 243x in a 5-layer call chain (tianpan.co, 2026).
- LLM providers operate at 99.0–99.5% uptime versus 99.97% for major cloud infrastructure — failures are not exceptional, they are the expected condition.
- Agent failure modes are qualitatively different from conventional software: silent infinite loops, context accumulation until the model halts, irreversible actions taken before a human can intervene.
- Spec failures (~42% of multi-agent failures) and coordination breakdowns (~37%) dominate — not model quality issues.

## The Move

Build layered failure handling that addresses three distinct failure classes: API infrastructure failures (retryable), semantic failures (the call succeeds but output is wrong), and structural failures (loops, deadlocks, resource contention).

**1. Set hard execution budgets — never trust a loop you haven't capped.**
- Max steps/turns (e.g., `max_turns=15`) as a first-class parameter, not a late addition.
- Token budgets per run that trigger hard stops and emit structured errors (`error_max_budget_usd`, `error_max_turns`).
- Budget enforcement at the orchestration layer, not inside the agent — agents will not self-limit reliably.

**2. Implement LLM-adapted circuit breakers.**
- Standard circuit breakers ( Resilience4j-style) work for API failures but miss LLM-specific patterns: a 200 response with malformed JSON, a valid response that fails semantic validation, or a model that returns tool calls pointing to non-existent functions.
- Track failure rates per tool, per model, and per error class separately — don't lump a JSON parse failure together with a rate limit.
- Three states: CLOSED (normal traffic), OPEN (block requests to protect downstream), HALF_OPEN (probe with limited requests to test recovery).
- Circuit state transitions should emit structured events to your observability layer so you can alert on OPEN state duration.

**3. Deploy idempotent checkpoints with structured rollback.**
- LangGraph's `checkpoint` + `rollback` pattern (3-line rewind to last known good state) handles corrupted execution threads from bad tool calls.
- Temporal-style event history with deterministic replay reconstructs agent state after a worker crash.
- Store state snapshots at decision points — not just at the end. A crash at step 7 of 12 should not restart from zero.
- Idempotency keys on all external side-effect operations (API calls, DB writes, file modifications) — retry safety requires knowing you haven't already done the thing.

**4. Add semantic validation gates, not just syntactic checks.**
- A tool call returning 200 is not success. Validate output shape, value ranges, and schema compliance before proceeding.
- Quality validators run after every LLM call in high-stakes workflows. If a validator fails, retry the agent call with a modified prompt rather than propagating bad state.
- Pre-commit validation: before any irreversible action (DELETE, PUT, payment submission), run a semantic check. The cost of a false positive is a delay; the cost of a false negative is data loss.

**5. Design explicit escalation paths with human-in-the-loop gates.**
- Approval gates at high-stakes action boundaries — not just at the start of a workflow.
- Asymmetric risk argument: the cost of an unauthorized irreversible action (deleted record, submitted payment) vastly exceeds the cost of a 30-second review delay.
- Escalation should be structured: pass full context (original intent, agent reasoning trace, proposed action) to the human reviewer, not just an error code.
- Track escalation frequency — a high escalation rate on a specific action type signals a capability boundary, not a user error.

**6. Handle provider failover as a first-class concern.**
- Dual primary providers with policy-driven routing: route by task criticality, latency budget, and quality threshold, not a single static fallback.
- Every provider hop consumes tokens, queue capacity, and latency — model this cost explicitly.
- Evaluation must cover degraded paths: measure user-visible quality for primary, retried, and fallback executions before shipping a policy.

## Evidence

- **Engineering blog (tianpan.co, 2026):** Documented a recursive agent loop — Agent A asked Agent B for clarification, Agent B asked Agent A back — that ran for 11 days. No circuit breaker caught it. No spend alert fired in time. Retry logic compounded the runaway cost. Identified a 243x failure amplification in naive 5-layer retry chains. — [tianpan.co/blog/2026-03-11-llm-api-resilience-production](https://tianpan.co/blog/2026-03-11-llm-api-resilience-production)

- **Research synthesis (Zylos Research, 2026):** Taxonomy from production incidents: specification failures (~42%), coordination breakdowns (~37%), verification gaps (~21%). Documented deadlock patterns, resource contention from redundant subprocess spawning, context accumulation until model halts, and irreversible actions before human intervention. — [zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery)

- **Engineering blog (Inference Labs, 2026):** Core principles for LLM retry/fallback: retries should be failure-aware (retrying every non-200 inflates cost and latency), fallback should be policy-driven by task criticality, idempotency keys and per-hop tracing are required infrastructure, evaluation must cover degraded paths, and cost control is part of resilience. — [blog.inference-labs.com/posts/llm-fallback-and-retry-strategies-production](https://blog.inference-labs.com/posts/llm-fallback-and-retry-strategies-production)

- **GitHub library (agentguard-llm, 2026):** Open-source implementation of circuit breakers, LLM-aware retry logic, idempotency enforcement, and loop detection as a production library. — [github.com/maheshmakvana/agentguard-llm](https://github.com/maheshmakvana/agentguard-llm)

- **Pattern documentation (AI Dev Day, 2026):** LangGraph rollback/checkpoint pattern: 3-line state rewind handles corrupted execution threads from bad tool calls without restarting the full workflow. — [aidevdayindia.org/blogs/ai-agent-observability-agentops-playbook/ai-agent-rollback-checkpoint-pattern-langgraph-production.html](https://aidevdayindia.org/blogs/ai-agent-observability-agentops-playbook/ai-agent-rollback-checkpoint-pattern-langgraph-production.html)

- **Safety framework (OpenLegion, 2026):** Human-in-the-loop design rationale: approval gates at action boundaries with full context transfer to human reviewers, framed as asymmetric risk management where unauthorized irreversible actions vastly exceed review delay costs. — [openlegion.ai/en/learn/human-in-the-loop-ai-agents](https://www.openlegion.ai/en/learn/human-in-the-loop-ai-agents)

- **HN discussion (2026):** PocketOS incident — agent wired into production infrastructure via MCP integrations ran continuously for 30+ hours post-failure, with Railway unable to confirm recovery path. — [news.ycombinator.com/item?id=46450307](https://news.ycombinator.com/item?id=46450307)

## Gotchas

- **Naive retry on hallucinated outputs:** Retrying a tool call that returned valid JSON but wrong values just confirms bad state. You need semantic validation before retry, not just HTTP success.
- **Loop detection that can't distinguish progress:** A max-step counter stops loops but also stops legitimate long tasks. Track meaningful state changes, not just call counts.
- **Human-in-the-loop that defeats automation:** Approval gates become busywork if they ask for review on every step. Gate only irreversible, high-stakes, or low-confidence actions.
- **Circuit breakers tuned too aggressively:** A circuit that opens on a single rate limit error will thrash on normal traffic. Set thresholds from actual traffic analysis, not guesses.
- **Checkpointing without idempotency:** Restoring state from a checkpoint then replaying a non-idempotent write (e.g., `INSERT` without conflict handling) creates duplicate records. Checkpoints and idempotency are co-dependent.
