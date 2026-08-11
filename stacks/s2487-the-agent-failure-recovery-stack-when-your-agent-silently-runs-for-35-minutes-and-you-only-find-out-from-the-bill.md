# S-2487 · The Agent Failure Recovery Stack — When Your Agent Silently Runs for 35 Minutes and You Only Find Out from the Bill

An agent in production doesn't crash with a stack trace. It loops silently, burns budget, spawns redundant subprocesses, accumulates context until the model halts, or takes an irreversible action — and none of this shows up as "an error." The failure modes are qualitatively different from traditional software, and the remedies are too. The teams that survive production agent deployments share one discipline: they build stopping conditions before they build the agent.

## Forces

- **The reliability cliff.** A 10-step pipeline where each step succeeds 85% of the time succeeds end-to-end only ~20% of the time. Every additional tool call compounds failure probability — yet most teams don't model this until they have a production incident. — [Zylos Research, 2026](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery)
- **Agents fail creatively, not predictably.** Traditional software returns a 500 or a null pointer. An agent may return a valid JSON response that is confidently, plausibly wrong — 200 OK, catastrophic outcome. — [Cowork.ink, 2026](https://cowork.ink/blog/ai-agent-error-handling/)
- **Retrofitting resilience is 10x harder than designing it.** Error handling built after the agent is deployed means re-architecting the loop, not just adding a try/catch. — [Cowork.ink, 2026](https://cowork.ink/blog/ai-agent-error-handling/)
- **The $47K wake-up call.** A team deployed a four-agent LangChain A2A/MCP system for market research. Two agents entered an infinite loop. The bill hit $47,000 before anyone noticed. — [Towards AI, October 2025](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33)

## The move

Build a layered failure-recovery system in this order of precedence — stopping conditions first, then retries, then degradation, then escalation.

### 1. Hard execution caps (non-negotiable)

- **Max steps = 12.** Set a hard iteration ceiling. A task that needs more than 12 steps is a task that needs to be decomposed, not extended. In LangGraph: `recursion_limit=12`. In raw loops: `for step in range(MAX_STEPS)`. — [Rajpoot, 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026/)
- **Per-step timeout.** A single tool call or model invocation that never returns will hang the whole run. Cap each call in the 30–120s range depending on expected latency. — [GitHub: agentic-ai-production-readiness, 2025](https://github.com/jjjsood/agentic-ai-production-readiness/blob/main/docs/limits-and-budgets/rate-loop-timeout-caps.md)
- **Wall-clock timeout.** A run that stays under the step cap but grinds slowly for hours is still a failure. Set a total elapsed ceiling (e.g., 10 minutes per run) and hard-kill. — [GitHub: agentic-ai-production-readiness, 2025](https://github.com/jjjsood/agentic-ai-production-readiness/blob/main/docs/limits-and-budgets/rate-loop-timeout-caps.md)
- **Cost cap per run.** Default: $1. Track cumulative spend against the task. Stop when the cost of continuing exceeds the value of completion. — [Rajpoot, 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026/)

### 2. Per-tool retry discipline

- **Retry transient errors only.** Rate limits (HTTP 429), timeouts, 503s — these resolve on their own with a wait. Semantic errors (wrong schema, hallucinated function name) do not retry into correctness. — [Neel Mishra, agent error taxonomy](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Exponential backoff with jitter.** `wait = min(base * 2^attempt + random(0, jitter), max_wait)`. Without jitter, a thundering herd of retried agents can recreate the original rate limit. — [Neel Mishra](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Max retries per tool, not global.** A search tool that times out should not consume retries that the file-write tool might need. Track per-tool retry counts independently. — [Rajpoot, 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026/)
- **Descriptive tool errors.** When a tool fails, return the error message verbatim to the model, not a generic "tool call failed." The model can often self-correct on retry with the error context. — [Rajpoot, 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026/)

### 3. Circuit breakers for cascading failures

- **Three states.** CLOSED (normal → failures increment, open at threshold) → OPEN (all calls fail fast, protecting the dependency) → HALF-OPEN (probe call to test recovery). — [Cowork.ink, 2026](https://cowork.ink/blog/ai-agent-error-handling/)
- **Trigger on failure rate, not count.** A tool that fails 5 times in 10 seconds opens the breaker. A tool that fails 5 times over 10 hours is a different problem. — [Cowork.ink, 2026](https://cowork.ink/blog/ai-agent-error-handling/)
- **Scope to the dependency, not the agent.** If the weather API is degraded, the circuit breaker should degrade weather lookups — not halt the entire agent. Partial results with a disclaimer are better than complete failure. — [Neel Mishra](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

### 4. State checkpointing and resume

- **Checkpoint after each successful tool call.** Serialize: conversation history, accumulated tool results, current plan, step count. On failure at step 4 of 7, resume from step 4 — not from scratch. — [Neel Mishra](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Idempotency is the prerequisite.** A resume that re-executes a refund API call will issue the refund twice. Every tool that writes state must accept an idempotency key. — [programa.space, 2026](https://programa.space/autonomous-agent-failure-modes-and-recovery-engineering-patt)
- **Cooperative cancellation.** When a hard cap fires, signal the agent cleanly (set a flag, append a "stopping" message) rather than hard-killing the process. A graceful stop produces a useful final state; a kill produces nothing. — [Rajpoot, 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026/)

### 5. Graceful degradation chains

- **Define fallback levels.** If live data lookup fails → return cached data with timestamp. If cache is stale → return best-effort summary with disclaimer. Never let a single dependency take the whole agent down. — [Neel Mishra](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Whole-agent fallback to a larger model.** On N consecutive hard failures, escalate the request to a more capable model before declaring defeat. This is the "ask a senior engineer" move. — [Rajpoot, 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026/)
- **Append the disclaimer.** When operating in degraded mode, tell the user: "This response was generated without access to live data." Obscured degradation breeds distrust; visible degradation preserves it. — [Neel Mishra](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

### 6. Observability (required to debug failures you haven't seen yet)

- **Log every run: input, step count, tools called + outputs, final outcome, cost, latency.** If you don't log it, you can't find it. — [Rajpoot, 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026/)
- **Track which agents loop, which tools error, which prompts cost most.** Aggregate failure patterns over time to find systematic problems — not just individual incidents. — [Rajpoot, 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026/)
- **Chaos-test failure paths in CI.** Deliberately inject tool timeouts, API errors, and malformed responses. Observe how the agent handles them. If the test fails, the agent isn't ready. — [COMPEL Framework: Operational Resilience for Agentic AI](https://www.compelframework.org/articles/operational-resilience-for-agentic-ai-failure-modes-and-recovery)

### 7. Human escalation (the backstop)

- **Escalation hook on terminal failure.** When all recovery paths are exhausted, create a ticket, send a notification, or surface the partial result to a human — don't just log and drop. — [Rajpoot, 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026/)
- **Least-privilege tool scopes.** The $1.2M refund incident happened because the agent could issue refunds up to $500 without review. Define action tiers: fully autonomous below X, human-review between X and Y, human-required above Y. — [Agentbrisk, 2026](https://agentbrisk.com/blog/ai-agent-failure-modes-real-incidents)
- **Canary deployments for high-stakes agents.** Roll out to 1% of traffic. Observe for cost anomalies and error rate spikes before scaling. — [programa.space, 2026](https://programa.space/autonomous-agent-failure-modes-and-recovery-engineering-patt)

## Evidence

- **HN/Anecdotal:** A team spent $47,000 over four weeks running four LangChain agents in production. Two agents entered an infinite loop in week three. Week four hit $18,400 before the system was pulled. The root cause: no max-step cap, no cost cap, no observability on per-agent spend. — [Towards AI, October 2025](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33)
- **Research Synthesis:** Specification failures account for ~42% of multi-agent failures; coordination breakdowns ~37%; verification gaps ~21%. A 10-step pipeline at 85% reliability succeeds ~20% of the time end-to-end. — [Zylos Research, May 2026](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery)
- **Audit of 40 post-mortems:** Tool-call hallucination leads failure modes at 22%, context window overflow at 18%, infinite loops at 15%. The 20% of agents that survive production all implement: hard tool schemas, context budgets, circuit breakers, longitudinal evals, and least-privilege scopes. — [GrowthEngineer.ai, May 2026](https://growthengineer.ai/blog/why-ai-agents-fail-in-production)
- **GitHub structured incident repo:** At least 10 significant AI coding agent incidents documented between October 2024 and March 2026 across 6 major tools, including data deletion, filesystem wiping, and zero-click autonomous chains achieving exfiltration — all without a single vendor postmortem published. — [LaureanoPacheco/ai-agent-incidents, GitHub](https://github.com/LaureanoPacheco/ai-agent-incidents)

## Gotchas

- **A retry is not a recovery strategy — it's a pause.** Retrying the same failing operation without changing the input only makes sense for transient errors. For semantic errors (wrong schema, hallucinated tool), retrying with the same context produces the same failure. Fix the input, not just the attempt count.
- **Hard caps that are too high are the same as no caps.** A `MAX_STEPS=1000` cap means your agent can still loop for 999 steps at $0.02/step. Calibrate caps to the task's reasonable upper bound — not to what feels "safe."
- **Circuit breakers that never open are not protecting you.** If your threshold is 1,000 failures before opening, the breaker is decorative. Set thresholds based on your actual SLA requirements and the cost of cascading failure.
- **Checkpointing without idempotency creates new failures.** A resume that re-executes a payment, a write, or a delete is worse than a failed run — you've now introduced a side effect. Every state-mutating tool must be idempotent or tracked with a ledger.
- **Observability that nobody reads is not observability.** Logging every run to a table that nobody queries is engineering theater. Build the alert that fires before the cost cap hits, not just the log line.
