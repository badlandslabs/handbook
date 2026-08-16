# S-2726 · The Circuit Breaker Stack — When Your Agent Keeps Failing the Same Way for Hours

Your agent hits a flaky API. It retries. Fails again. Retries again. Forty-seven times. It has now spent $180 on a task worth $3 and produced nothing. The API was down for 8 minutes, but your agent doesn't know that — it just knows it hasn't succeeded yet, so it hasn't stopped. This is the loop-of-last-resort problem: the agent mistaking persistent failure for incomplete progress.

Standard error handling doesn't work here. The agent's "success" signal is "did the task complete?" not "did the tool call succeed?" Without explicit failure-handling architecture, agents retry their way into cost overruns, deadlock on bad tool schemas, and confidently ship broken outputs.

## Forces

- **Agents don't natively distinguish failure types.** A tool returning `null` and a tool returning garbage look identical to an agent that has no schema to validate against.
- **Retry loops are invisible until they aren't.** Agents that loop on bad tool parameters look exactly like agents that are thinking deeply.
- **Cost compounds before anyone notices.** Each LLM call costs money; a 50-retry loop is a production incident that only surfaces when the invoice arrives.
- **Some failures should escalate, not retry.** A 403 from an API means "check your credentials," not "try again." Agents need enough context to make that distinction.
- **Lab testing misses cascading failures.** Standard evaluation suites (MT-Bench, AgentBench) are single-session, single-task. They cannot detect compounding errors or retry cascades that emerge over multiple tool interactions in production.

## The move

Explicit circuit breaker + bounded retry + structured recovery patterns at the tool layer:

- **Fail-fast on schema mismatch.** Before retrying, validate the tool's output against its expected schema. Hallucinated parameters (fabricated IDs, invalid formats) must be caught and surfaced as a distinct failure class — not silently accepted.
- **Set per-tool retry budgets with exponential backoff.** A hard cap (e.g., 3 retries) with jitter prevents thundering herds and runaway costs. When the budget is exhausted, escalate — don't loop.
- **Distinguish retryable vs. non-retryable failures.** Network timeouts and 5xx errors → retry with backoff. Auth errors (401/403), schema violations, and validation errors → fail immediately and alert.
- **Build a bounded self-heal loop.** Let the agent attempt a fix, but cap the attempt count. A candidate evaluation agent at Asynq.ai that produced obviously flawed outputs was corrected by adding a validation step between the agent and output — not by adding more agent reasoning.
- **Instrument the loop itself.** Track: retry count per tool, failure type distribution, cost-per-task, and task completion rate. A spike in retry count is a leading indicator of an upstream API problem, not an agent problem.
- **Validate semantic success, not just HTTP success.** A tool returning HTTP 200 with hallucinated data is worse than a 500. Add a semantic validation layer: does the output make sense given the query?

## Evidence

- **HN Ask HN (2026):** "There's absolutely 0 framework out there that's good enough for serious work" — production practitioners overwhelmingly building custom orchestration with explicit retry and circuit-breaker logic layered in, rather than relying on framework defaults. — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **AI Practitioner Blog (2026):** At Asynq.ai/Modelia.ai, a candidate evaluation agent hallucinated tool parameters and got stuck in loops, while an image generation agent optimized for workflow completion over quality. Fix: add a structured validation step, not more agent reasoning. — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **arXiv (2026):** Seven production failure modes identified at billion-event scale; standard metrics (ROUGE, BERTScore, Accuracy) fail to detect 4 of 7 failure modes entirely. Lab benchmarks designed for single-session evaluation are structurally blind to cascading retry failures. — [arxiv.org/html/2605.01604](https://arxiv.org/html/2605.01604)
- **Microsoft Agent Framework (2025):** Semantic Kernel's multi-agent orchestration ships with explicit termination conditions and failure escalation paths — the architectural acknowledgment that agents need hard stops, not just goal definitions. — [devblogs.microsoft.com/agent-framework/semantic-kernel-multi-agent-orchestration](https://devblogs.microsoft.com/agent-framework/semantic-kernel-multi-agent-orchestration/)

## Gotchas

- **Adding more agent reasoning doesn't fix agent failures.** The instinct is to give the agent a "retry more carefully" prompt. The fix is structural: validation, retry budgets, and circuit breakers at the orchestration layer.
- **Counting completion != counting success.** A task that "completed" by shipping a confident report based on hallucinated data is a failure, not a success. Measure semantic outcome, not just task completion.
- **Loop detection by token count is too late.** By the time an agent has burned through 128K tokens, the cost is already incurred. Set per-step budgets before the agent runs, not after.
- **Graceful degradation beats hard failure.** If a non-critical tool fails, let the agent continue with a warning flag rather than aborting the whole task. A research agent that can't access one data source should flag it and use the other four — not halt.
