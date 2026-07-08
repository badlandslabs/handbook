# S-789 · The Agent Recovery Problem: What Happens When It Hallucinates a Tool Call

[Your agent calls a tool that doesn't exist, gets a weird error, loops, then fails silently. Or it hits a rate limit, gets stuck, and a queue of 400 requests backs up behind it. The agent knows how to start tasks — it has no idea what to do when things go sideways. This is the recovery gap: agents that can act but can't recover.]

## Forces

- **Agents are non-deterministic where failures are deterministic.** A tool can timeout, return garbage, or not exist. The LLM doesn't know it's failing until the error propagates — and by then the agent may have drifted into an unrecoverable state.
- **Retrying blindly amplifies cost and can make things worse.** Exponential backoff on API calls helps, but retrying a malformed prompt 5 times just burns tokens. Recovery needs a plan, not just repetition.
- **Graceful degradation is rarely built-in.** A human would say "I can't reach the API, I'll check the backup." An agent needs explicit logic to do the same — and most frameworks don't provide it by default.
- **Failure cascades are invisible without observability.** If tool A fails and agent retries 12 times before giving up, you need traces to know it happened. Without that, you're debugging a black box.

## The Move

Design for failure at every layer before you need it. Recovery isn't an afterthought — it's a core part of the agent's capability surface.

**1. Wrap every tool call in structured error handling with typed failure modes.**
Distinguish rate limits (retry with backoff), timeouts (retry with timeout extension), malformed responses (fall back or surface to human), and "tool not found" errors (never retry — this is a code bug). Log each failure mode separately so you can distinguish a flaky dependency from a broken integration.

**2. Give the agent explicit recovery actions, not general retry logic.**
Instead of `max_retries=3`, give the agent options: "API unavailable — switch to cached data," "output malformed — reformat with post-processor," "rate limited — wait N seconds and retry with reduced payload." The agent decides which recovery path fits the context.

**3. Build a circuit breaker at the orchestration layer.**
Track failure rates per tool. If a tool fails 5 times in 60 seconds, open the circuit: stop sending requests, return a deterministic fallback, alert the team. This prevents cascade failures from taking down the whole agent. Reset automatically after a cooldown window.

**4. Implement a maximum step/scratchpad limit.**
Agents that loop without making progress will run up token costs indefinitely. Cap the execution loop (16–32 steps is typical) and define a deterministic exit: return partial results, surface what was completed, flag what wasn't.

**5. Use human-in-the-loop checkpoints for high-stakes actions.**
Any tool call that deletes, writes, sends, or spends money should have an explicit confirmation gate. The agent prepares the action, presents it for human approval, then executes. This turns a potential catastrophe into a recoverable review step.

**6. Log structured traces at every tool call boundary.**
Record: tool name, input, output (or error), step number, token count, latency. This gives you the data to diagnose failures, build evaluation datasets from real failures, and detect regressions when you change prompts or models.

## Evidence

- **Engineering blog:** Anthropic's "Building Effective Agents" recommends the "assistance" pattern — designing agents that resist hallucination by being explicit about what they can and cannot do, and surfacing uncertainty rather than guessing. They note that "simple, composable patterns" beat complex frameworks for reliability. — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **HN discussion:** Commenters on the Anthropic post noted that "an augmented LLM running in a loop" is the clearest definition of an agent — and the loop's failure modes (stuck in tool calls, looping without progress) are where production systems break down. 543 points, 88 comments on what "effective" actually means in practice. — [https://news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)
- **Engineering blog:** Geta Team's post on production failures documented that a single unhandled API timeout cascaded into a complete system shutdown affecting all incoming requests. Their fix: typed error handling per failure mode, exponential backoff, circuit breakers, and deterministic fallbacks. — [https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/)
- **Engineering blog:** A 2026 retrospective noted that "a demo agent that works 80% of the time is impressive. A production agent that fails 20% of the time is a disaster" — and identified deterministic fallbacks, observability, cost controls, and human-in-the-loop checkpoints as the four non-negotiables for production readiness. — [https://devstarsj.github.io/2026/05/07/ai-agents-in-production-patterns-pitfalls-2026](https://devstarsj.github.io/2026/05/07/ai-agents-in-production-patterns-pitfalls-2026)

## Gotchas

- **Don't retry everything.** Infinite retry loops are a common and expensive mistake. Retry only for transient failures (timeouts, rate limits, 5xx errors). For permanent failures (4xx, schema mismatch, tool not found), fail fast and escalate.
- **Observability is not optional.** You cannot debug a failing agent without traces. If you only log "agent completed" or "agent failed," you have no signal to diagnose which tool failed, why, or how often.
- **Fallbacks must be tested, not just defined.** A fallback that crashes at runtime is worse than no fallback. Every recovery path needs a unit test that exercises it under the simulated failure condition.
- **The loop limit is not a silver bullet.** Capping steps stops infinite loops but doesn't tell you what the agent accomplished. You need partial-result return — the agent should surface completed work even when it hits the cap.
