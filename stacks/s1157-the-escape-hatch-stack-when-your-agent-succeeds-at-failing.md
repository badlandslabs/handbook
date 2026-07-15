# S-1157 · The Escape Hatch Stack — When Your Agent Succeeds at Failing

[Your agent loops for 47 minutes, burning $12 in API calls, deleting files that don't exist. No crash, no error message, no alarm — just a system that is confidently doing the wrong thing at great expense. This is the failure mode that doesn't look like failure until it costs you.]

## Forces

- **Agents fail creatively, not predictably.** A traditional service crashes with a stack trace. An agent may return HTTP 200 with a confident hallucination, call a non-existent file path repeatedly, or accumulate context until it silently halts. The failure modes are qualitatively different — and so are the remedies.
- **21.5% of production agent runs hit some form of error.** Without structured recovery, that means roughly 1 in 5 tasks fails end-to-end. With proper error handling, 95%+ of those failures are recoverable.
- **The hardest failures to catch are the ones that look like success.** An agent completing steps 1–4 of 8, then proceeding on bad data, is worse than a crash. The crash is obvious. The silent corruption is not.
- **Self-correction is retry with better context — not magic.** When practitioners say an agent "self-corrects," they mean a validator caught malformed output, re-prompted the model with the specific error, and the model generated a corrected response. The recovery mechanism is the retry infrastructure, not the model.

## The move

Build a layered failure-recovery system before you deploy, not after.

- **Map failure domains first.** Agents fail in four distinct categories: transient infrastructure errors (rate limits, network timeouts), LLM output failures (malformed JSON, hallucinations), tool execution errors (wrong parameters, permission denials), and agent state failures (lost context, corrupted memory). Each requires a different recovery strategy.
- **Retry with exponential backoff + jitter, scoped by exception class.** Do not wrap the whole agent in a single try/except. Specify exception types and max attempts per call site. A rate limit error should retry 3 times with 1s→10s→30s delays and 30% jitter. A malformed JSON output should retry with a validator-injected error message. A structural failure (wrong approach) should not retry — it should escalate.
- **Use circuit breakers to contain cascading failures.** After N consecutive failures to a downstream service, open the circuit: stop calling it, return a structured degraded response, and alert. One broken MCP server that silently failed for 3 days taught one team to add per-tool circuit breakers with 30-second timeouts.
- **Separate retry budget from escalation budget.** A common mistake: exhausting your retry budget on a fundamentally broken task, then having nothing left when a genuinely transient error hits. Partition them.
- **Build checkpoint-and-resume for multi-step workflows.** Store agent state at each step boundary. When a run fails mid-pipeline, it resumes from the last checkpoint, not from scratch. In-memory checkpointing is not durable — a pod restart loses everything.
- **Instrument loop detection.** Cap the maximum number of reasoning steps. Track whether the agent is making progress (state changes between iterations). An agent that calls the same tool with the same parameters twice in a row is looping — stop it.
- **Route irrecoverable failures to a dead-letter queue, not silence.** Failed tasks should persist to a queue with full trace data for human review. The worst production incidents start as silent failures that nobody notices until a user reports them.

## Evidence

- **Engineering blog:** Ivern AI's analysis of 10,000+ production agent runs found that 21.5% of runs experienced errors across five failure modes: API rate limits (12%), model timeouts (8%), malformed JSON output (6%), hallucinated tool parameters (5%), and cascading hangs (4%). With proper error handling, 95%+ of failures were recoverable. Teams achieved 99.5–99.9% uptime with a layered stack of retries, circuit breakers, model fallback chains, and dead-letter queues.
  — https://ivern.ai/blog/ai-agent-error-handling-and-fallback-strategies-2026

- **GitHub + HN:** An HN post about a production email gateway agent that crashed during a high-volume period, blocking all incoming messages for hours. Root cause: a single unhandled API timeout cascaded into complete system failure. The agent had no retry logic, no circuit breaker, and no graceful degradation. Post-incident fix: exponential backoff with jitter, per-step state checkpoints, and a fallback to a human escalation queue.
  — https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/

- **GitHub:** An open-source `infinite-agentic-loop` repository (604 stars) demonstrating the "Ralph Wiggum Loop" — a failure mode where an autonomous agent, having achieved its stated goal, decides to optimize further and loops indefinitely. The solution: a supervisor layer that tracks step counts, compares agent state between iterations, and terminates when no progress is detected. Separate from the agent itself — a structural escape hatch.
  — https://github.com/disler/infinite-agentic-loop

## Gotchas

- **Setting `output_retries=0` because retries "felt risky."** When a validator catches malformed output and the run fails immediately, you lose the self-correction loop entirely. The retry budget on model output is what enables the agent to fix its own mistakes — zero it out and you guarantee every malformed response becomes a hard failure.
- **Treating all failures as retriable.** Retrying a structurally broken task burns budget and can cascade. A rate limit error is transient — retry. A tool returning "file not found" after the agent has already verified the path is structural — escalate. The distinction matters at the exception-class level, not the whole-agent level.
- **Checkpointing in memory.** State lost on every pod restart means your "durable" run was not durable. Use PostgresSaver, DynamoDBSaver, or a Temporal workflow for state persistence. In-memory is fine for testing — production requires external state.
- **No loop detection until it's too late.** An agent that calls the same tool with the same parameters twice in a row is almost certainly looping. Track this structurally, not by inspecting logs after the fact. The loop that burns $12 in 47 minutes will not stop itself.
