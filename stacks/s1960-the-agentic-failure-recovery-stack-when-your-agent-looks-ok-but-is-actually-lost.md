# S1960 · The Agentic Failure Recovery Stack

When your agent looks fine but is actually lost — looping, hallucinating tool params, or silently degrading mid-session with no error to catch.

## Forces

- Agents fail **probabilistically**, not cleanly — they return HTTP 200 while hallucinating, or keep iterating past the point of usefulness without any exception thrown
- Traditional try-catch blocks don't protect against LLM-specific failure modes (confident nonsense, malformed tool calls, context overflow)
- Retries are a package deal with idempotency — a retry without an idempotency key duplicates the side effect it was trying to fix
- The max_iterations=N cap is wrong in both directions: cuts off loops still improving, and burns budget on loops past their best answer
- Non-deterministic divergence: a retry of the same prompt may differ, invalidating assumptions made in steps already executed
- Cascade failures: one stuck agent in a multi-agent pipeline takes the whole system down silently

## The Move

Five layered patterns for agentic failure recovery, applied at the right granularity:

### 1. Per-Call Retry Contracts (Not One Wrap Around Everything)

Every LLM or tool call needs its own retry contract before writing the first call — specify exception classes, max attempts, and backoff per call site.

- **Retry on**: transient network errors, HTTP 429 rate limits, 503 service unavailable, JSON parse failures (indicates malformed output)
- **Do NOT retry on**: tool parameter hallucination, semantic quality failures, context overflow — repeating the same prompt won't fix these; they need a different correction
- **Backoff curve**: 1s → 2s → 4s → 8s → 16s with full jitter to avoid thundering herd on recovery
- **Key**: make the retry unit the smallest atomic step, not the whole agent run

### 2. Circuit Breakers for External Dependencies

Track failure rates per dependency and transition through three states:

- **Closed (normal)**: requests pass through, failures are counted
- **Open (failing fast)**: after N consecutive failures, block requests for X minutes — prevents retry storms that deepen outages
- **Half-open (testing)**: after the timeout, allow N test requests through; if they succeed, close the circuit

Implement per-model, per-tool, and per-agent-circuit breakers. A provider-level breaker prevents cascade when your primary model degrades.

### 3. Checkpoint-and-Resume with Durable Execution

Agents crash mid-step. Without state persistence, you lose all progress.

- **LangGraph checkpointer**: saves state graph after each node; resumes from last checkpoint on worker restart. Works for single-agent persistence within a session.
- **Temporal workflow engine**: run LangGraph inside Temporal activities with heartbeat checkpointing. Temporal powers agent infrastructure at OpenAI, Cursor, Lovable, Block, Abridge, and Hebbia (per their 2026 blog post). Activities resume from last heartbeat checkpoint on worker failure.
- **GitHub template**: steveandroulakis/temporal-langgraph-checkpoint-recovery provides a production-ready scaffold with dual heartbeat pattern (background heartbeats + superstep checkpoints).
- **Practical guard**: `MEMORY.md` pattern — each agent writes state to a shared file; on crash, replay from last checkpoint before restarting.

### 4. Convergence Gates Instead of Iteration Caps

Replace `max_iterations=N` with actual quality measurement:

- **LoopGain** (open-source, HN Show HN): uses control theory to measure whether a verify-revise loop is still improving. On a 2,000-trial benchmark across 5 loop patterns, 6 framework adapters, 3 model providers, LoopGain cut API spend by **92.8%** vs `max_iterations=20` ($27.05 → $1.94) and median wall-clock time by **~15x** (30.9s → 2.1s). A cross-vendor judge preferred LoopGain outputs on weighted average.
- **Simpler fallback**: track the best answer seen so far with a reward signal; exit when quality plateaus for N consecutive steps (don't stop at iteration N, stop when N steps have produced no improvement)
- **Budget gate**: put a hard token/dollar ceiling at the loop gateway, not inside loop code — exits on ceiling hit, returns best answer found
- **Explicit stop conditions**: "stop when you have high confidence in the answer" is more effective than arbitrary iteration counts

### 5. Fallback Chains and Graceful Degradation

Build explicit degradation chains per step rather than one global fallback:

- **Model fallback**: primary model → cheaper/faster model → cached response → partial answer with error flag
- **Tool fallback**: primary tool → alternative tool → skip step with warning → return degraded result
- **Quality guard**: validate LLM output with a Pydantic schema or rule-based checker before executing tool calls; if validation fails, retry once with a corrected system prompt, then escalate
- **Partial result policy**: never return nothing; always return the best partial answer with explicit confidence and limitations stated

### 6. Escalation Triggers (Human-in-the-Loop)

Escalate when the agent signals it cannot resolve the situation:

- Detect repeated failures at the same step (N failures on same tool = escalate)
- Flag irreversible actions (payments, deletions, public posts) for human confirmation
- In multi-agent pipelines: use bulkhead isolation — each agent runs in its own sandboxed session. One agent failure doesn't cascade. Anthropic SDK community discussion documents a case where a Discord cron job retry storm produced 50 duplicate posts from a single cascade failure; isolation + idempotency keys solved it.
- Timeout escalation: if a step exceeds its SLA (e.g., 90s for a tool call), escalate rather than wait indefinitely

## Evidence

- **Company engineering post:** Harsh Rastogi (AI Product Engineer, Modelia.ai & Asynq.ai) documented real production failures — an Asynq.ai candidate evaluation agent hallucinated tool parameters, got stuck in loops, and cost 3x budget; a Modelia.ai image agent approved obviously flawed images because it was optimizing for workflow completion over quality. Both solved with per-call retry contracts, loop convergence metrics, and fallback chains.
  — [Agentic AI in Production: Error Recovery, Observability, and Scaling Patterns](https://harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns) (March 2026)

- **Durable execution proof:** Temporal's 2026 blog post confirms their LangGraph plugin is used in production by OpenAI, Cursor, Lovable, Block, Abridge, and Hebbia. Their plugin adds automatic crash recovery, distributed node execution, and zero-cost human-in-the-loop waits — addressing the checkpoint-and-resume problem at production scale.
  — [LangGraph in Production: Temporal's LangGraph Plugin](https://temporal.io/blog/temporal-langgraph-plugin-durable-execution) (2026)

- **Convergence benchmark:** LoopGain reduced agent loop API spend by 92.8% vs `max_iterations=20` in a 2,000-trial benchmark (5 loop patterns, 6 framework adapters, 3 model providers). Presented as open-source library replacing iteration caps with convergence gates.
  — [Show HN: LoopGain – Stop agent loops with control theory, not max_iterations](https://news.ycombinator.com/item?id=48919562) (May 2026)

- **Real cascade failure:** Anthropic SDK GitHub Discussion #1341 documents a team running 5 autonomous agents 24/7 whose Discord cron job produced 50 duplicate posts from a retry storm. Solution: idempotency keys, "already posted" guards, and session-level isolation.
  — [What patterns do you use for AI agent error recovery?](https://github.com/anthropics/anthropic-sdk-python/discussions/1341) (April 2026)

- **Field convergence:** Zylos Research (May 2026) documents the 2025-2026 field convergence on a seven-layer resilience model: LLM API fallback chains, circuit breakers, context window overflow handling, tool error recovery, rate limiting/backpressure, agent-to-agent communication resilience, and partial result policies.
  — [Graceful Degradation Patterns for AI Agent Systems](https://zylos.ai/research/2026-05-30-graceful-degradation-patterns-ai-agent-systems)

- **HN community consensus:** A 447-point HN thread (43998472) on LLM agent loop effectiveness surfaced the community insight that "agents aren't reflecting on their own performance and pausing their own execution to ask a human for help aggressively enough." One commenter called it "a junior that doesn't realize when they're over their depth."
  — [The unreasonable effectiveness of an LLM agent loop with tool use | Hacker News](https://news.ycombinator.com/item?id=43998472) (May 2025)

## Gotchas

- **Wrapping retries around the whole agent** — if the agent is at step 5 of 8 and the step 3 API call fails, you want to retry step 3, not restart the entire 8-step sequence. Per-call contracts enable targeted recovery.
- **Retrying side-effectful operations without idempotency keys** — a retried payment API call with no idempotency key duplicates the payment. Every tool call with side effects needs an idempotency key before retry.
- **`max_iterations` as the only stop condition** — this is a budget cap with no quality signal. The loop exits at N regardless of whether the answer is good. It also can't detect when to exit early. Use convergence measurement alongside iteration caps.
- **Treating semantic failures like infrastructure failures** — hallucinated tool parameters don't fix themselves on retry. They need a different intervention: a validator guard that tells the model exactly what was wrong, or a simpler fallback to a manual step.
- **No partial-result policy** — when an agent fails mid-workflow, returning nothing means losing all work. Always structure workflows to return the best partial answer with an explicit failure flag.
- **Hardcoded iteration limits in channels** — the ZeroClaw Rust agent had a hardcoded `MAX_TOOL_ITERATIONS: usize = 10` in `channel/mod.rs` that ignored the user's `max_tool_iterations` config (GitHub issue #777, fixed February 2026). Config knobs that don't actually control the runtime are worse than no config — they give false confidence.
