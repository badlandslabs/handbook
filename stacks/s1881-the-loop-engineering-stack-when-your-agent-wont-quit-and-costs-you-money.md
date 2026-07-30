# S-1881 · The Loop Engineering Stack — When Your Agent Won't Quit and Costs You Money

Your agent is running. It has been running for 47 minutes. The ticket status says "in progress." No errors have surfaced. Nothing has been produced. The tool it was calling started returning timeouts four minutes in — so the agent started retrying, which turned into re-planning, which hit the same tool with slightly different parameters, which timed out again. This is not a stuck agent. It is a loop. And loops are the dominant failure mode of production agentic systems in 2026 — not crashes, not panics, not hallucinations. Loops that look productive from the outside and burn money from the inside.

## Forces

- **The LLM re-plans on failure, not just retries.** Unlike a conventional retry loop, an LLM that sees a timeout treats it as new information. "The API timed out" → "try a different approach" → a slightly different call to the same endpoint. Infrastructure circuit breakers can't see this because the retry is happening inside the model's reasoning, not in your code. — [BuildMVPFast, 2026](https://www.buildmvpfast.com/blog/agent-timeout-circuit-breaker-patterns-runaway-ai-workflows-2026)
- **"Busy" and "productive" are indistinguishable without instrumentation.** An agent calling a broken tool 400 times in 5 minutes looks exactly like an agent doing real work from every external signal: it is running, it is responding to pings, its ticket is "in progress." — [HackerNoon / The AI Turtle, July 2026](https://hackernoon.com/your-agent-is-not-stuck-it-is-looping-there-is-a-difference-and-it-costs-you-either-way)
- **Self-healing mechanisms have no ceiling by default.** A recovery loop that retries with exponential backoff will eventually succeed in a transient failure scenario — or it will exhaust your budget first. One engineering team documented a compaction loop that burned ~250,000 API calls in a single day before anyone noticed. — [Zylos Research, May 2026](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery/)
- **Multi-agent systems multiply the problem.** When a sub-agent times out mid-pipeline, the caller gets partial state — not an error. The orchestrator receives something that looks like a result but isn't. Agent B waits on Agent A, Agent C waits on Agent B, the entire pipeline hangs, and there is no clean way to resume. — [AI Codex, 2026](https://www.aicodex.to/articles/multi-agent-failure-handling)

## The move

### 1. Classify errors before you retry
Not all failures warrant the same response. Divide errors into four categories before building any retry logic:

| Category | Signal | Response |
|---|---|---|
| **Transient** | 429, timeout, 503, DNS | Retry with backoff |
| **Semantic** | Malformed JSON, bad tool name, schema violation | Re-prompt with corrective context |
| **Resource** | Token budget exceeded, context overflow | Reduce payload (summarize, drop results, switch model) |
| **Fatal** | Auth failure, revoked key, policy violation | **Abort immediately**, alert operator |

Classifying a fatal error as transient is how you get 250,000 API calls in a day. — [Neel Mishra, MLOps Series, 2026](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

### 2. Set hard caps at three levels
Layer cost and step controls, not just one:

- **Per-step cap** (e.g., LangChain `max_iterations=50`): the agent cannot take more than N tool calls in a single turn. Catches runaway loops at the infrastructure level.
- **Per-turn token budget**: track cumulative tokens per task invocation. Kill the agent when the budget is exceeded — not when the user cancels, not when the session ends.
- **Weekly active-compute cap**: separate from monthly quotas; counts only when the model is actively processing. This is the layer that has stopped surprise four-figure bills for Claude Code users who thought their monthly cap was their safety net. — [GitHub gist / yurukusa, 2026](https://gist.github.com/yurukusa/a0b66592fe016d3823b8090d25af1a18)

### 3. Treat sub-agents as fire-and-forget blast zones
In production multi-agent systems, sub-agents must be treated as unreliable:

- **Never rely on a sub-agent completing before the parent continues.** Use checkpointing at each agent boundary — save state before dispatch, resume from checkpoint on timeout.
- **Give sub-agents a SIGUSR1-before-SIGTERM sequence** so they can flush state before termination. Without this, a sub-agent that wedges after completing its work keeps consuming tokens and cannot be killed from the parent session (the `Agent` tool returns an `agentId`, but `TaskStop` requires a `task_id` — these are different identifiers, and the `/tasks` panel Stop button also fails). — [GitHub Issue #58604, anthropics/claude-code, May 2026](https://github.com/anthropics/claude-code/issues/58604)
- **Wrap every sub-agent in a dead letter queue (DLQ).** Failed or timed-out sub-agent tasks go to a DLQ, not back into the main pipeline. This prevents retry storms from cascading into pipeline-wide hangs. — [Brandon Lincoln Hendricks, 2026](https://brandonlincolnhendricks.com/research/dead-letter-queues-retry-policies-ai-agent-production)

### 4. Distinguish looping from converging at runtime
The critical question is not "is the agent running?" — it is "is the agent producing different outputs over time?" Track:

- **Output delta**: compare the agent's current state to its state 3 steps ago. If they are semantically identical (not just textually), flag as looping.
- **Tool call fingerprint**: if the agent has called the same tool with the same or near-identical parameters N times without new information, trigger escalation.
- **Progress horizon**: define what "done" looks like explicitly, and check against it at each step. This is the "scarce skill" of 2026: not writing prompts, but defining what good and done mean. — [HackerNoon, July 2026](https://hackernoon.com/your-agent-is-not-stuck-it-is-looping-there-is-a-difference-and-it-costs-you-either-way)

### 5. Build a fallback chain, not a fallback call
When retries exhaust, do not surface a raw error. Instead, walk a deliberate downgrade path:

```
ReAct multi-step reasoning → single-shot tool call → direct LLM answer → cached response → notify_human
```

Each step reduces capability and increases reliability. The agent does not "fail" — it degrades gracefully. — [Neel Mishra, 2026](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

## Evidence

- **Post-mortem:** A customer support agent called a broken order lookup tool 400 times in 5 minutes after a timeout began. No alert fired. Ticket remained "in progress." Cost of a single agent in production: ~4x standard chat. Cost of multi-agent systems looping: ~15x. — [HackerNoon / The AI Turtle, July 2026](https://hackernoon.com/your-agent-is-not-stuck-it-is-looping-there-is-a-difference-and-it-costs-you-either-way)
- **GitHub incident:** Claude Code sub-agents using Opus 4.7 (1M context) with `run_in_background: true` complete their assigned work successfully, then enter an infinite generation loop on post-task finalization. The parent has no mechanism to kill them. — [GitHub Issue #61877, anthropics/claude-code, May 2026](https://github.com/anthropics/claude-code/issues/61877)
- **Framework comparison:** LangGraph provides full visibility into which agent failed and why during multi-agent pipeline failures. CrewAI provides a black box — the orchestrator fails, and the team cannot determine whether a sub-agent timed out, produced bad output, or never started. — [SudoAll, June 2026](https://sudoall.com/multi-agent-coordination-2026-playbook)
- **Real-world compensation:** Claude Code users who left agents running on long tasks have reported waking up to four-figure bills. Root causes include: the silent API key leak (agents spawned by tools that expose the key), the June 2026 pool split (subscription vs. metered billing confusion), and the runaway sub-agent that continues consuming tokens after its parent session ends. — [GitHub gist / yurukusa, 2026](https://gist.github.com/yurukusa/a0b66592fe016d3823b8090d25af1a18)

## Gotchas

- **Circuit breakers at the infrastructure level cannot see reasoning-layer retries.** If the agent decides "try a different approach" after a timeout, that retry bypasses your infrastructure-level rate limit and circuit breaker entirely. You need cost guards at the agent level, not just the API level.
- **A completion message from a sub-agent does not mean the agent has stopped.** The work can complete successfully and the agent process continues running, burning tokens, with no completion notification firing. Treat the completion signal as separate from the termination signal.
- **LangGraph checkpointing is not the same as DLQ handling.** Checkpointing lets you resume from a saved state — useful for transient failures. DLQ handling catches non-recoverable failures and routes them to human review. You need both, and they are not interchangeable.
- **"It worked in testing" is especially dangerous for loops.** Loop failures manifest under real conditions: longer runtime, degraded dependencies, partial outputs. A 5-minute test will not surface the behavior that burns $1.3M/month.
- **Partial outputs look like success.** An agent that returns truncated JSON or an error message embedded in text is not returning a failure — it is returning something that the orchestrator may interpret as a result. Always validate output schema explicitly, not just the presence of a response.
