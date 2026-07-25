# S-1633 · The Hamster Wheel Stack — When Your Agent Repeats Itself Silently Until Your Cloud Bill Tells the Story

Your agent is still running. It hasn't errored out. It hasn't crashed. It is simply doing the same thing it did 30 iterations ago, and it will keep doing it until you kill it, run out of budget, or — as one financial services firm discovered over a weekend maintenance window — burn through $12,000 in compute costs on 47,000 failed API calls. The failure mode is a loop with no error signal, and the only alarm is your invoice.

This is the hamster wheel: agents that fail by repetition rather than by exception. The fix is not better prompts — it is bounded control with layered detection, checkpointed recovery, and explicit escalation paths.

## Forces

- **LLM agents are non-deterministic loop bodies.** Traditional software loops are explicit and inspectable. An LLM deciding "should I continue?" is a black box that can answer yes indefinitely, especially when the tool it depends on is subtly broken.
- **Framework-level guardrails are too coarse.** LangChain's `max_iterations` and `max_execution_time` exist, but they fire after the waste has occurred and don't detect semantic loops (near-identical tool calls with different inputs).
- **Failure-by-repetition has no stack trace.** It exits cleanly. Your monitoring sees no errors. Your dashboards are green. Your bill is the only anomaly signal.
- **Agents compound damage on multi-step tasks.** A looped agent on step 4 of 12 doesn't just waste time — it may re-trigger side effects (API calls, writes, downstream webhooks) with each repetition.

## The move

Layer three independent detection mechanisms around every agent run. None is sufficient alone; together they close the gap.

**1. Iteration counting with per-step budget guards.**
Set hard limits on total tool invocations, not just loop iterations. A more granular version: set per-tool invocation budgets (e.g., "search" tool capped at 5 calls per run). This catches loops that produce distinct but useless tool calls.

**2. Semantic similarity detection.**
Track embeddings of the agent's recent state/action pairs. Fire when cosine similarity between consecutive states exceeds a threshold (e.g., 0.92). This catches the hamster wheel even when the agent thinks it's making progress — it fires on near-duplicate reasoning traces, not just identical outputs.

**3. Token-and-time budget gates.**
Convert compute budget into a real-time kill switch. A 50-token-per-iteration loop on GPT-4o costs $500+/hour. A `max_tokens_per_run` guard that halts the agent when cumulative spend crosses a threshold is cheaper than discovering the limit empirically.

**4. Checkpoint before every tool call with resumable recovery.**
For long-running agents, persist state before each tool invocation. On interrupt (manual, budget, or error), the agent resumes at the last confirmed checkpoint — not the beginning. Crab (arXiv:2604.28138) shows sandbox restore via checkpoint reduces wall-clock time by up to 29% and rollback tokens by 36% compared to shell-level self-recovery.

**5. Structured escalation instead of silent halt.**
When any guard fires, route to a defined path — partial results, human review queue, or a fallback model — rather than returning an empty response. Tanay Shah's ai-agent-error-patterns (2025) shows that partial batch failures (e.g., 95/100 items succeeded) need explicit handling: return what succeeded, flag what didn't, and never retry idempotent operations blindly.

**6. Fail-closed on irreversible tools.**
For tools that mutate external state (database writes, API deletions, file overwrites), require explicit confirmation when a threshold of failed attempts is reached. A `DROP TABLE` after 3 consecutive failures on a backup check is a policy violation, not a retry.

## Evidence

- **GitHub repo + HN:** Agent Watchdog (woodwater2026/agent-watchdog) — a framework-agnostic PyPI package implementing loop detection, budget guards, and graceful halts for LangChain, CrewAI, AutoGPT, or any agent. MIT license, 27 commits. — [github.com/woodwater2026/agent-watchdog](https://github.com/woodwater2026/agent-watchdog)
- **Case study:** A financial services company running autonomous agents entered a retry loop during a weekend maintenance window. Loop detection counted distinct error types, not total iterations. Three days, 47,000 failed API calls, $12,000 in compute costs. — [trackai.dev — Loop Detection & Breaking](https://trackai.dev/tracks/observability/debugging-tracing/loop-detection)
- **Open-source patterns:** Tanay Shah's ai-agent-error-patterns (MIT, 2025, updated 2026) implements four production reliability patterns — circuit breaker, partial success, human-in-the-loop, graceful degradation — with Trigger.dev v4 and upgrade paths to Redis, Postgres, and Sentry. — [github.com/tanayshah11/ai-agent-error-patterns](https://github.com/tanayshah11/ai-agent-error-patterns)
- **Research:** Crab (arXiv:2604.28138v1) — semantics-aware checkpoint/restore runtime for agent sandboxes. Case studies show sandbox restore reduces wall-clock time by up to 29% and rollback tokens by 36% vs. shell-level recovery. — [arxiv.org/html/2604.28138v1](https://arxiv.org/html/2604.28138v1)
- **Enterprise taxonomy:** COMPEL Framework's operational resilience article defines five failure categories — planning failures (circular planning, suboptimal planning), execution failures (tool invocation, cascading propagation), and policy violations — with structured recovery paths for each. — [compelframework.org](https://www.compelframework.org/articles/operational-resilience-for-agentic-ai-failure-modes-and-recovery)
- **Framework docs:** LangChain's agent configuration guide: `max_execution_time`, `handle_parsing_errors=True`, and `BaseCallbackHandler` for token tracking are the three minimum viable guardrails. Profile on representative data before setting limits — too low breaks legitimate multi-hop reasoning. — [markaicode.com](https://markaicode.com/errors/ai-agent-loop-fix/)

## Gotchas

- **Iteration limits catch loops, not hamster wheels.** If the agent makes progress in each iteration (even 1% better), `max_iterations` won't fire. Use semantic similarity on state embeddings to catch gradual convergence to a dead end.
- **Retries amplify outages.** A retry loop with exponential backoff on a broken dependency can multiply the blast radius. Retries alone don't recover — they just delay the inevitable. Use circuit breakers: trip on N failures, open for a cooldown window, probe slowly on reopen.
- **Checkpointing adds latency.** Persisting state before every tool call is not free. Profile the overhead; for short tasks (< 10 steps) it may not be worth it. Target long-running autonomous agents (> 15 steps) where the cost of re-running is measurable.
- **Partial success is not the same as failure.** An agent that completes 95 of 100 items succeeded. Returning a generic "task failed" on any error discards 95% of the work. Track partial outcomes explicitly and surface them.
