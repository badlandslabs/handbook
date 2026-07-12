# S-979 · The Loop Detector Stack: When Your Agent Runs All Night Draining Your Budget

Your agent appeared to work fine during testing. In production, it encounters an unexpected edge case, enters a retry cycle, and loops for 8 hours burning $700 in API calls before the billing alert fires at 6am. Runaway agents don't crash — they silently drain your budget while you sleep. The fix isn't a bigger timeout. It's layered guardrails: hard iteration caps, semantic loop detection, circuit breakers, and supervisor agents that watch the watcher.

## Forces

- **Individual steps look reasonable.** Each retry looks fine in isolation. The loop only becomes visible in aggregate — by which point you've already paid for it.
- **Hard caps stop loops but don't diagnose them.** A max-steps ceiling prevents infinite runs but throws away all work and provides no signal about what went wrong.
- **Backoff reduces cost-per-loop but doesn't bound the loop.** Exponential backoff with jitter cuts retry storm damage by 60–80%, but if your backoff ceiling is 5 minutes and the underlying issue persists, you still hit the ceiling repeatedly.
- **Supervisor loops are possible.** A supervisor that interprets every stop as a failure and restarts its agent indefinitely is the same problem one level up — the supervisor needs its own ceiling.
- **Checkpoint timing is a design decision, not a given.** If your agent mutates state then fails before checkpointing, recovery restarts from the pre-mutation checkpoint and the mutation is lost.

## The move

Layer three distinct guardrails in order of cost and information value:

- **Hard iteration cap as the floor.** Set a maximum number of agent steps (e.g., 50–100). This is your last-resort circuit breaker — it will fire eventually, but it throws away all in-progress work. Design step-counting into your agent loop explicitly so you can emit it as telemetry on every iteration.

- **Semantic loop detection above the cap.** Hash tool-call sequences and detect exact repetition in O(1) time. Beyond exact matches, compute semantic similarity of recent tool-call arguments using embeddings or even a lightweight LLM check — catches near-identical loops where the agent tries slightly different parameters on each pass. Track distinct error types separately from total iteration count; counting by error type alone misses recursive fallback chains where each step succeeds but the chain loops.

- **Checkpoint before mutation, not after.** Take a recovery checkpoint at the start of each step, not at the end. If the step mutates state and then fails, recovery from the post-step checkpoint would replay the failure. The checkpoint must precede the mutation. Store checkpoints with step number, tool-call signature, and a hash of accumulated context so recovery can verify state integrity.

- **Circuit breaker on external calls.** Wrap every tool call, API call, and model invocation in a retry budget (3–5 attempts with exponential backoff + jitter) and a circuit breaker that opens after N failures in a window. When the circuit opens, stop retrying and surface the failure to the caller rather than continuing to hammer the failing service. This prevents retry storms that cascade into infrastructure outages.

- **Budget kill-switch.** Set a hard cost ceiling per task or per 24-hour window. When the ceiling is hit, halt immediately. A financial services firm burned $12,000 over a weekend maintenance window because their agent's loop-detection counted distinct error types instead of total iterations. Budget caps would have stopped it regardless of what the loop looked like.

- **Supervisor agent with its own ceiling.** For high-stakes deployments, a meta-agent that monitors the primary agent's progress can detect when the agent is making no progress (e.g., last N outputs are semantically similar, or the agent keeps re-attempting the same tool with no new information). The supervisor needs its own hard cap — otherwise it becomes a second unbounded loop.

## Evidence

- **Engineering blog:** A financial services company running autonomous trading agents burned through $12,000 during a weekend maintenance window. Their loop detection counted distinct error types, not total iterations — 47,000 failed API calls over three days before the billing alert fired. The fix: iteration-count-based loop detection with a hard ceiling. — [TrackAI Engineering](https://trackai.dev/tracks/observability/debugging-tracing/loop-detection)

- **Engineering blog:** $700 in one night from an agent that entered a retry loop — each individual call looked reasonable in isolation. The team found it via a morning billing alert. Pattern: tool call fails → agent retries → gets a different error → tries different approach → hits same API → repeats for 8 hours. Solution: layered circuit breakers at both the retry level and the overall agent level, with per-step cost tracking. — [BuildMVPFast](https://www.buildmvpfast.com/blog/agent-timeout-circuit-breaker-patterns-runaway-ai-workflows-2026)

- **Research synthesis:** Galileo 2025 analysis of production agent failures: specification failures (42%), coordination breakdowns (37%), verification gaps (21%). AWS research: exponential backoff with jitter reduces retry storm damage by 60–80%. 10-step pipeline with 85% reliability per step succeeds only ~20% of the time end-to-end — making failure recovery essential, not optional. — [Zylos Research](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)

- **Primary research:** The agentguard Python library (production-ready fault tolerance) implements per-call budgets, fallback chains, and supervisor-loop detection as composable decorators. Demonstrates that guardrails belong in the agent loop, not as an afterthought — a guardrail that can be bypassed provides false confidence. — [GitHub: maheshmakvana/agentguard](https://github.com/maheshmakvana/agentguard)

## Gotchas

- **A loop detector that resets on each error type misses recursive fallback chains.** If each step succeeds but the overall chain loops (agent tries approach A, fails, tries B, fails, tries A again), a per-error-type counter never accumulates and the loop runs forever. Track total iterations regardless of error type.
- **Exponential backoff without jitter causes thundering herds.** If N agents all retry at the same base interval, they all retry simultaneously after a failure. Jitter (randomized backoff) spreads retries over time — this alone reduces retry storm damage by 60–80%.
- **Logs tell you what happened after it broke. Metrics tell you it's about to break.** Agent loop detection needs real-time instrumentation — step counts, cost accumulated, semantic similarity of recent outputs — not just post-hoc log analysis.
- **Graceful degradation is not the same as failure recovery.** If your agent's search tool fails, returning "no results" (degraded) is different from recovering to a working state. Know which you want: a degraded response that satisfies the user, or a full recovery that retries the operation.
