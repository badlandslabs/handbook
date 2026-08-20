# S-2907 · The Agent Failure Recovery Stack — When Your Agent Crashes but Looks Like It Succeeded

Your agent completed 4 of 8 steps in a critical workflow, failed silently on step 5, and reported success. Or it hit a rate limit, retried with exponential backoff as designed, and spent $437 before anyone noticed. Or it filled its context window, got silently truncated, and spent the next 20 turns repeating the same mistake. Traditional error handling does not cover these cases. The fix is a layered failure architecture that treats every class of agent failure differently.

## Forces

- **Agents fail probabilistically, not deterministically.** The same prompt succeeds once and fails the next — not because of a bug, but because of model variance, context shift, or a tool's non-deterministic response. Retry logic designed for database connections does not know when to stop retrying a semantic failure.
- **Success and failure look identical from the outside.** HTTP 200, but the tool response is hallucinated. Task completion reported, but the agent skipped validation. The agent needs behavioral checkpoints, not just status codes.
- **Naive retry amplifies cost, not reliability.** Exponential backoff without a circuit breaker is how a transient upstream error becomes a runaway budget event. The default recovery instinct makes things worse.
- **Failure cascades through context.** A bad output from step 5 poisons steps 6 through 20 silently. By the time you notice, the entire workflow output is compromised with no way to trace which step introduced the corruption.
- **Multi-step workflows lose partial progress by default.** If the agent crashes after step 4 of 8, restarting means repeating steps 1–4. Without state persistence, every interruption is a full replay.

## The Move

Build a layered failure architecture with five concentric safeguards. Each layer catches a different failure class and triggers a different response.

### Layer 1 — Retry with jitter for transient errors

Identify transient errors (429 rate limit, 503, timeout, network failure) and retry with exponential backoff plus jitter. Jitter prevents thundering-herd retry storms when multiple agents recover simultaneously. Cap the maximum number of retries, and count retries against a per-task budget — not just time.

```python
import asyncio, random, time

async def retry_with_jitter(fn, max_retries=4, base_delay=1.0):
    for attempt in range(max_retries):
        try:
            return await fn()
        except TransientError as e:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
```

### Layer 2 — Circuit breaker for cascade prevention

After N consecutive failures against a provider or tool, open the circuit breaker and fail fast for a cooldown period. This prevents the $437 incident: a transient error that retries successfully eventually, but not before burning through budget and latency. The circuit breaker trips on error density, not individual failures.

| State | Behavior |
|-------|----------|
| **Closed** | Requests pass through normally |
| **Open** | Fail fast; return cached fallback or error immediately |
| **Half-open** | Allow one probe request to test recovery |

Threshold guidance: trip after 5 consecutive failures, stay open for 30–60 seconds, allow 1 probe in half-open state before deciding to close or reopen.

### Layer 3 — Semantic validation before proceeding

Not all failures have HTTP status codes. A tool call can return HTTP 200 but hallucinate a function name, return structurally invalid JSON, or produce output that is technically correct but semantically wrong. Insert a validation step after every tool call and significant LLM transition:

- **Schema validation** — does the output match the expected structure?
- **Semantic checkpoint** — does the output make sense given the task? (Use a smaller/faster model to validate the output of a larger one)
- **Cross-reference check** — does the output contradict something established earlier in the conversation?

If validation fails, do not proceed. Re-prompt, substitute the tool, or escalate.

### Layer 4 — Checkpoint and resume for long workflows

Save the agent's execution state at defined milestones — after each completed step, after significant tool calls, before context boundary crossings. Store: conversation history cursor, completed steps, partial outputs, tool call results. On interruption (crash, timeout, budget exceeded), resume from the last checkpoint rather than replaying from the start.

State to checkpoint per step:
- Step identifier and completion status
- All tool call inputs and outputs
- LLM reasoning trace (if using structured reasoning)
- Any side effects already committed

Store checkpoints in durable storage (database, object store) — not in-memory. Process crash must not lose checkpoint state.

### Layer 5 — Human escalation for unrecoverable failures

Classify failures that cannot be retried, validated, or checkpoint-recovered. Trigger a human escalation path: pause the workflow, capture full state snapshot, notify the responsible team, and surface the specific step that failed and why. The escalation queue is not a failure of the system — it is a deliberate boundary that prevents the agent from proceeding on corrupted state.

Define escalation triggers explicitly:
- Max retries exhausted
- Semantic validation failed after N re-prompt attempts
- Context window overflow with no recovery path
- Tool permanently unavailable (auth revoked, endpoint gone)
- Cost or latency budget exceeded

## Evidence

- **Engineering blog (Modelia.ai / Asynq.ai):** A candidate evaluation agent in production hallucinated tool parameters, got stuck in loops, produced contradictory evaluations, and cost 3x budget. The fix was a layered approach: retry limits, semantic checkpoints after each tool call, and a cost budget that halts the workflow before runaway cost accumulation. — [Harshrastogi.tech, March 2026](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **HN Show HN (Gambit agent harness, bolt-foundry):** Introduced the agent harness concept — treating the agent as the central decision-maker with tools and context management wrapping it, rather than orchestrating it as a pipeline. The failure mode they address is over-orchestration: when you treat an agent as a pipeline step, a tool failure cascades through the entire DAG. A harness lets the agent decide whether to retry, substitute, or escalate. — [HN Show HN, ~91 points](https://news.ycombinator.com/item?id=46641362)

- **HN Show HN (Hive agent framework, Aden):** Built over 4 years for ERP automation (PO/invoice reconciliation) in construction. Key insight: existing frameworks fail in production because they model chatbots, not autonomous services. Real business users want reliable execution, not chat interfaces. Their self-healing graph re-routes around failed nodes instead of cascading — a graph-level circuit breaker at the orchestration layer. — [HN Show HN, ~107 points](https://news.ycombinator.com/item?id=46979781)

- **HN Ask HN (Multi-agent orchestration, 2025):** Practitioners building production multi-agent systems show strong consensus around bounded agent tasks with central orchestration and structured state passing. Error handling patterns varied: some use custom retry/exponential backoff, others use LangGraph's built-in error handling, others build their own. Common failure modes cited: provider rate limits, malformed tool responses, and silent context truncation. — [HN Ask HN, 11 comments, ~4 months ago](https://news.ycombinator.com/item?id=47660705)

- **Research blog (Zylos.ai):** LLM failures are fundamentally probabilistic, not deterministic. This changes the resilience model entirely: you cannot catch the failure with a try-catch because the failure is a wrong-but-confident output. They document five distinct failure classes requiring independent recovery strategies: transient (retry), permanent (fail fast), semantic (validate, do not retry), cascading (isolate with bulkheads), and quota exhaustion (graceful degradation). — [Zylos.ai Research, May 2026](https://zylos.ai/research/2026-05-30-graceful-degradation-patterns-ai-agent-systems)

- **Engineering blog (NiteAgent):** The $437 retry-loop incident — an agent hit a transient upstream error, retried with exponential backoff as designed, but the upstream was degraded (returning 200s with stale data) rather than fully down. Backoff made each retry succeed just enough to not trip a failure threshold, but the data was wrong and the workflow had to be manually reconstructed. Lesson: circuit breakers must trip on data quality signals, not just error codes. — [NiteAgent, July 2026](https://niteagent.com/blog/2026-07-14-building-reliable-agent-error-handling-guide/)

- **Enterprise blog (n1n.ai):** The "silent truncation loop" — a context window fills up, earlier conversation is silently dropped, the agent forgets it already attempted a tool call, repeats it indefinitely. Each individual LLM call is technically valid. The loop is invisible to normal monitoring. Detection requires tracking action fingerprints: if the agent calls the same tool with the same arguments N times within a rolling window, halt and checkpoint. — [n1n.ai, July 2026](https://explore.n1n.ai/blog/preventing-infinite-loops-llm-agent-pipelines-2026-07-10)

## Gotchas

- **Exponential backoff alone is not resilience.** It handles transient failures but makes semantic failures and cascade contamination worse by increasing exposure time. Always pair with circuit breakers and semantic validation.
- **HTTP status codes are insufficient for agent failure detection.** The most dangerous failures return 200. Validate behavior, not just transport status.
- **Checkpoint frequency is a tradeoff, not a maximum.** Checkpointing every tool call adds overhead; checkpointing only at step boundaries risks losing work on crashes. Checkpoint at every meaningful state change — completed tool call, LLM reasoning checkpoint, side effect committed.
- **Context window overflow is a silent failure mode.** Monitor context utilization proactively. If the agent is at 80% of context budget and has 5 more steps to go, trigger compaction or checkpoint before the silent truncation destroys reasoning continuity.
- **Escalation queues must not block the happy path.** Human escalation should be asynchronous — the workflow pauses and notifies, but does not wait indefinitely for a human response in the critical path. Set an SLA expectation and a deadline.
