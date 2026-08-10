# S-2421 · The Agent Recovery Stack — When Silent Failures Cost More Than Crashes

Your agent ran for 47 minutes last night. Every tool call returned successfully. The trace shows no errors. The task was not completed. It looped — calling the same three tools with slight variations, never converging, never escalating, never stopping. Your monitoring logged zero failures. Your users got nothing. This is the failure mode that traditional observability doesn't catch, and the teams that survive production agents have built recovery infrastructure specifically for it.

## Forces

- **Agents fail silently in ways services don't.** A web service crashes and logs a stack trace. An agent loops for 35 minutes, spawns redundant subprocesses, and takes no observable action — while returning HTTP 200 on every tool call.
- **Failure taxonomies differ from traditional software.** API rate limits, hallucinated tool arguments, context overflow cascades, and retry death spirals don't map to try/catch blocks.
- **Recovery paths must be built in, not improvised.** When a tool fails, the agent needs a defined path forward — not a model staring at an error message it doesn't know how to act on.
- **Escalation costs must be weighed against inaction costs.** Escalate too early and you burn human time. Escalate too late and you get silent corruption, wasted compute, or irreversible actions.

## The Move

Build a layered recovery stack from the bottom up. Each layer addresses a distinct failure class, and together they make the system self-healing rather than catastrophically fragile.

**Layer 1 — Idempotency-first retries.** Before any retry, attach an idempotency key to the tool call. Without it, a retry after a partial success can double-charge a customer, send two emails, or create two records. Design every tool call as if it might execute more than once.

**Layer 2 — Classify errors at the tool boundary.** Separate transient errors (timeout, 429, connection reset) from terminal errors (auth failure, schema mismatch, malformed LLM output). Transient errors retry. Terminal errors escalate. Never retry authentication failures or malformed JSON — retrying burns quota and compounds the problem. Distinguish rate limit errors from quota exhaustion: the former backs off and retries; the latter stops and alerts.

**Layer 3 — Surface structured errors to the model.** When a tool call fails, return a structured error object (not a raw exception) that tells the model *what* failed, *why* it likely happened, and *what the agent should do next* (retry with different params, skip this step, escalate). An agent that receives "Error: 429" cannot self-correct. An agent that receives `{ "error": "rate_limited", "retry_after": 30, "suggested_action": "wait_and_retry" }` can act on it.

**Layer 4 — Circuit breakers at two levels.** First: per-tool circuit breakers. If a tool fails 5 times in 60 seconds, open the circuit and skip the tool for a cooldown period rather than burning through retries. Second: per-model circuit breakers. If the primary model returns malformed outputs N times in a row, switch to a fallback model. These are independent signals — a tool can be broken while the model is fine, and vice versa.

**Layer 5 — Hard guardrails on loops and depth.** Set a recursion limit on agent steps (25–50 is common). When the agent hits the limit, stop execution, surface the full trace, and trigger human-in-the-loop escalation. Track step counts, token accumulation, and action repetition rate. If the agent has called the same tool 3+ times with functionally identical arguments, inject a reflection prompt or halt.

**Layer 6 — Human escalation with context, not just logs.** When escalation triggers, package: the original user intent, the steps taken, the state of external systems at failure time, and a suggested remediation. Writing to a log file is not escalation. Active notification (Slack, PagerDuty, ticket creation) with enough context for a human to act in under 5 minutes is.

## Evidence

- **HN Ask HN (128 points, July 2025):** Practitioners emphasized starting with broad eval suites then narrowing, categorizing evals by purpose, and treating absence of evals as not knowing if changes matter. A prompt tweak "passed an initial vibe check" but failed the full eval suite — the gap between intuition and measurement is where failures hide. — [news.ycombinator.com/item?id=44712315](https://news.ycombinator.com/item?id=44712315)

- **AgentWorks (2026):** "An agent that fails silently costs more than one that fails loudly." The five-layer recovery architecture (idempotency keys, error classification, structured feedback, circuit breakers, escalation thresholds) addresses the core insight: a retry is not automatically safe after a successful tool call, and a tool call that times out may have partially succeeded. — [agent-works.ai/insights/agent-error-handling-recovery-patterns](https://agent-works.ai/insights/agent-error-handling-recovery-patterns)

- **Zylos Research (May 2026):** Across multi-agent systems, ~42% of failures are specification failures (wrong task definition), ~37% are coordination breakdowns (agents blocking each other), and ~21% are verification gaps (agent completed task but output was wrong). The qualitative failure taxonomy — deadlock, cascade, context overflow, hallucinated parameters — requires recovery patterns that don't exist in traditional backend engineering. — [zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery)

- **CyberQuickly (April 2026):** Nine documented production failure classes with real costs: retry death spirals burning quota and cascading to downstream agents, context overflow cascades where each step adds tokens until the model halts mid-task, and silent data corruption where the agent completes but writes wrong state. The <25% first-attempt task completion rate on real-world benchmarks (vs. 72% on curated benchmarks like SWE-bench) shows the gap between capability and reliability. — [cyberquickly.com/2026/04/07/ai-agents-production-failure](https://www.cyberquickly.com/2026/04/07/ai-agents-production-failure)

## Gotchas

- **Hard-coding retry counts without idempotency keys creates partial-success doubles.** If a payment API call succeeds but the response times out, a blind retry charges the customer twice. Every tool that modifies external state needs idempotency.
- **Circuit breakers that open too aggressively stall the agent; too lenient and they don't protect.** Start with per-tool thresholds and tune based on actual failure rates — a flaky search API and a reliable database should have different thresholds.
- **Returning raw exception text to the model produces unpredictable behavior.** The model may apologize, explain the error, or ignore it. Structured error schemas with suggested actions are the only reliable interface between tools and agents.
- **Recursion limits that are too low cause false escalations on complex legitimate tasks.** A 50-step limit should handle 95% of valid workflows; if it fires too often, the limit is masking a deeper problem (the agent shouldn't need 50 steps for that task).
- **Fallback usage rate above 20% indicates systemic primary failure, not resilience.** If one in five requests is hitting the fallback, the primary path needs fixing — not more fallback capacity.
