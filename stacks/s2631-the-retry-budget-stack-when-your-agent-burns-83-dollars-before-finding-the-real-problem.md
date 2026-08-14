# S-2631 · The Retry Budget Stack — When Your Agent Burns $83 Before Finding the Real Problem

[When your agent hits an error and immediately retries — then retries again, then falls back to a degraded mode, then gives up — and somewhere in that stack is the actual bug, buried under seven layers of recovery logic that no one can trace. The fix isn't more retry loops. It's a budget model that makes the failure visible before it becomes expensive.]

## Forces

- **Naive retry logic amplifies outages.** Classic "retry 3 times with exponential backoff" is tuned for transient network blips. Agent loops are automatic and parallel — loose retry budgets turn one slow dependency into a cascading failure amplification.
- **AI failures aren't boolean.** Traditional software returns errors or successes. AI agents return confident, plausible-sounding failures that pass downstream parsing and corrupt the execution chain.
- **Teams write retry logic first, budget logic never.** Every team has retry code. Almost no team can state their worst-case retry window in minutes. Without a budget model, you can't reason about failure blast radius.
- **Dead letter queues for AI agents must handle non-standard failures.** Hallucinated tool calls, token limit violations, and non-deterministic outputs break the standard DLQ contract — items that crash aren't the same as items that silently succeed with garbage.
- **The $83 mistake.** One engineer spent $83 in API retries before discovering the upstream API was timing out 15% of the time. The fix was a timeout adjustment. The cause was that no one had layered error detection between the agent loop and the dependency.

## The Move

Treat retry policy as budget policy, not count policy. Layer three mechanisms:

- **Safety timeout stack.** Wrap every tool call with a two-tier timeout: an inner safety timeout (Cordum recommends 2s) that fires on any hang, and an outer deadline budget that kills the entire task step if cumulative retry spend exceeds a threshold. The outer guard prevents the agent from spending unbounded time on a dead dependency.
- **Retry budget over retry count.** Instead of `max_retries=3`, set `max_retry_time=90s` or `max_retry_budget=15`. This keeps blast radius bounded even when backoff curves stretch unexpectedly. When the budget is spent, the task goes to DLQ — not back to retry.
- **DLQ with triage, not replay.** AI agent dead letter queues need three lanes, not one: (1) **Transient** — retry after a fixed delay (upstream blip), (2) **Structural** — tool/schema mismatch, requires code fix before replay, (3) **Semantic** — model produced malformed output, requires prompt or model change. Replay only the transient lane automatically; surface the other two.
- **Escalation path with preserved state.** When the DLQ determines a task needs human review, attach the full execution trace — not just the error message. The trace shows what the agent tried, what each tool returned, and where the branch diverged. Without it, review is guesswork.
- **Idempotency keys on every agent action.** Any action that can be retried must carry an idempotency key. Without this, replay-safe retries are impossible — the agent re-executes side effects instead of resuming from the failure point.
- **Model drift detection in the recovery path.** After provider updates, tool name formatting can shift by 2–3% of completions. Run Levenshtein distance checks with a semantic fallback on every tool-call parse in recovery. Auto-correct matches within threshold; surface outliers as structured errors.

## Evidence

- **HN Discussion:** "One engineer burned $83 in retries before discovering the API was timing out 15% of the time. The fix was a timeout adjustment." — thread on AI agent error handling, consensus that naive retry loops are the primary cost amplifier in production. — [HN: "Why 90% of Computer Use Proposals Explode in Production"](https://news.ycombinator.com/item?id=42431361)
- **Engineering Blog:** Cordum's production timeout model recommends a 2s inner safety timeout + 3s outer deadline budget per task step, with "retry budget first, retry loop second" as the governing principle. The post demonstrates how a 50-attempt cap with 1s–30s backoff can stretch failure realization to ~25 minutes without a hard budget boundary. — [Cordum: "AI Agent Timeouts, Retries, and Backoff in Production"](https://cordum.io/blog/ai-agent-timeouts-retries-backoff)
- **Research/Architecture:** DLQ patterns for AI agents must handle hallucinated tool calls, token limit violations, and non-deterministic outputs that silently corrupt downstream parsing — standard retry patterns break because AI responses are probabilistic. Google's Vertex AI Agent Engine pattern uses Cloud Pub/Sub for message durability + Cloud Tasks for retry orchestration with exponential backoff, combined with a DLQ that triages by failure type before replay. — [BLH: "Dead Letter Queues and Retry Policies for Production AI Agent Systems"](https://brandonlincolnhendricks.com/research/dead-letter-queues-retry-policies-ai-agent-production)

## Gotchas

- **Circuit breakers hide broken tool integrations.** A circuit breaker that trips when a tool fails 5 times is correct for transient failures but catastrophic for a tool that was silently deprecated. Validate that your breaker trips on *rate* of failure, not just count — and that the failure mode that trips it actually resolves.
- **False-positive loop detection flags legitimate exploration.** Agents that try multiple approaches to disambiguate a task look identical to a loop detector. Tune thresholds on actual trajectory length, not step count, and allow the model to signal that exploration is intentional.
- **Over-engineering the DLQ for a simple agent.** Three-lane triage is correct for production multi-step agents. For a single-step research agent, a single "retry or fail" lane is fine — the DLQ overhead must justify itself against the failure complexity of your actual system.
- **Retry budget drift over model versions.** A model that switches provider (Claude 3.5 → 3.7) may change how it formats tool names in ~2% of completions. Without a Levenshtein + semantic fallback in your recovery path, this 2% silently degrades to silent failures that pass as successes.
