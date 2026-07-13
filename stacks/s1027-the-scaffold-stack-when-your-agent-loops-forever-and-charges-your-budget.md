# S-1027 · The Scaffold Stack — When Your Agent Loops Forever and Charges Your Budget

Your agent ran for 47 minutes, made 156 tool calls, and produced nothing. No error message, no crash, no human alert — just silence while it burned $23 in API costs retrying a fix that made the problem worse. This is not a model quality problem. It is a **scaffold problem**: the agent has no infrastructure to detect that it is stuck, recover gracefully, or stop before it costs money it shouldn't.

## Forces

- **Agents fail differently than software.** Traditional software crashes with a stack trace. An agent may loop silently, drift semantically (high activity, zero progress), exhaust context tokens, or take irreversible actions before anyone notices.
- **Standard watchdog patterns miss AI-specific failures.** A heartbeat check confirms the process is alive — it doesn't confirm the agent is making progress. Liveness ≠ progress.
- **The stakes are asymmetric.** A failed API call costs one request. A failed agent loop can cost hundreds of calls, corrupt state, trigger side effects multiple times, and accumulate token debt that makes the session unrecoverable.
- **Recovery must be safe for the real world.** LLM nondeterminism means retrying the same action can produce different results — but the side effects (emails sent, database writes, money moved) must be deterministic. The agent can reason differently; the world must not change differently.
- **Production reality is harsh.** Only 5% of surveyed enterprises had AI agents live in production as of 2025. Of those, fewer than 1 in 3 were satisfied with their observability and guardrails. 70% of regulated enterprises rebuild their agent stack every 3 months.

## The Move

Build a failure-handling scaffold around the agent loop — not inside it. The scaffold intercepts, validates, limits, recovers, and escalates. It treats the LLM as an unreliable component in a system that must be reliable.

### 1. Classify errors before you react

Not all failures are equal. Sort them into three buckets:

- **Transient** — network blip, rate limit, timeout. Retry with backoff.
- **Permanent** — auth failure, bad input, API permanently down. Stop, log, escalate.
- **Degraded** — partial success, malformed response, ambiguous state. Pass to fallback.

A payment timeout is transient. A 401 auth error is permanent. An ambiguous API response where you can't tell if the action happened is degraded.

### 2. Detect loop patterns explicitly, not by count

Don't just cap iterations. Detect the three AI-specific progress failures:

- **The Repeater** — agent calls the same tool with the same arguments repeatedly. Track a hash of each tool call; if you see the same hash N times in a row without state change, intervene.
- **The Wanderer** — agent drifts away from task goal. Compare recent actions against the original task description using embedding similarity; if similarity drops below threshold, intervene.
- **The Compounder** — agent makes a small error, then tries to fix it, creating a new error, in a widening spiral. Track a "problem counter" that increments on errors and decrements on confirmed progress. If the counter exceeds threshold, halt.

```python
from collections import Counter

class LoopDetector:
    def __init__(self, repeat_threshold=3, drift_threshold=0.6, compound_limit=5):
        self.call_history = []
        self.error_count = 0
        self.progress_count = 0
        self.repeat_threshold = repeat_threshold
        self.drift_threshold = drift_threshold
        self.compound_limit = compound_limit

    def record(self, tool_call: dict, error: str | None, confirmed_progress: bool):
        call_hash = hash((tool_call.get('name'), str(tool_call.get('args'))))
        self.call_history.append(call_hash)
        self.call_history = self.call_history[-10:]  # keep last 10

        if error:
            self.error_count += 1
        if confirmed_progress:
            self.error_count = max(0, self.error_count - 1)
            self.progress_count += 1

    def is_stuck(self) -> dict:
        # The Repeater: same call repeated
        counter = Counter(self.call_history)
        most_common_count = counter.most_common(1)[0][1] if counter else 0
        repeat_stuck = most_common_count >= self.repeat_threshold

        # The Compounder: errors outnumber progress
        compound_stuck = self.error_count >= self.compound_limit

        return {
            "stuck": repeat_stuck or compound_stuck,
            "repeat_stuck": repeat_stuck,
            "compound_stuck": compound_stuck,
            "error_count": self.error_count,
            "progress_count": self.progress_count,
        }
```

### 3. Design tools to be safely retryable

Agents call tools multiple times with identical inputs due to network timeouts, rate limits, and model stochasticity. Every tool must be idempotent by design:

- **Upsert instead of create + update.** One `upsert_user(email, name)` call is retry-safe. Two calls — `create_user` then `update_user` — are not, because a mid-operation failure leaves unknown state.
- **Use idempotency keys.** Client-generated UUID passed through every request. Server deduplicates on retry. Pattern: `POST /api/orders` with header `Idempotency-Key: <uuid>`. If the server sees the same key twice, it returns the cached response instead of re-executing.
- **Annotate tools by effect class.** MCP's `readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint` let downstream safety reasoning happen. A tool labeled `destructiveHint=true` should require human-in-the-loop approval before execution.
- **Add dry-run modes.** Before mutating, call with `dry_run=True` to get a preview of what would happen. Agent confirms, then triggers the real call.

### 4. Checkpoint state before each mutation step

For long-running multi-step workflows, serialize agent state to durable storage after each completed step. A checkpoint contains:

- Full message history (conversation context)
- Current task state (what's done, what's pending)
- Tool execution log (what was called, what succeeded)
- Timestamps

If the agent crashes, restarts, or loops, reload from the last checkpoint and resume. Resume logic must handle idempotency: if step 3 completed but you don't know whether the side effect fired, check before re-executing.

### 5. Layer circuit breakers and escalation gates

- **Circuit breaker on tool calls.** If a specific tool fails N times in a window, stop calling it and route to a fallback. Don't let the agent keep hammering a broken API.
- **Budget guardrails.** Set max tokens, max cost, and max wall-clock time per session. Alert and halt when any threshold is breached. This is the only protection against a silently spiraling cost explosion.
- **Escalation queue.** When the scaffold detects stuck state, route to a human queue rather than looping. Include the checkpoint, call history, and error log so a human can diagnose in under 60 seconds.
- **Human-in-the-loop for destructive actions.** Tools labeled destructive should pause execution and require explicit human approval. OpenAI's Agents SDK supports this via `approval_callback` on tool definitions.

### 6. Validate tool inputs before calling

The most common silent failure mode: the agent calls the right tool but with fabricated parameters — a non-existent user ID, an invalid enum value, a malformed date. Pre-validate every tool argument against the schema before the call fires. If `user_id` must be a 10-digit string matching a known format, validate before sending. A rejected call is better than a failed call that wastes context tokens on an error response.

## Evidence

- **Survey (Cleanlab, 2025):** Only 5% of surveyed enterprises (95/1,837) had AI agents live in production. Of those, fewer than 1 in 3 were satisfied with their observability and guardrails. 70% of regulated enterprises rebuild their agent stack every 3 months. — [Cleanlab, "AI Agents in Production 2025"](https://cleanlab.ai/ai-agents-in-production-2025)
- **Post-mortem (SFAI Labs, June 2026):** After shipping 12 production agents in 2025, SFAI Labs identified seven structural lessons. None were prompt-engineering tips. Key findings: eval-pre-architecture outperforms retrofitted evals; tools must be scoped tightly (each tool should do one thing with a clear success/failure signal); checkpoint before every external call; design for graceful degradation, not for success paths. — [SFAI Labs, "Inside an AI agency post-mortem"](https://sfailabs.com/guides/inside-an-ai-agency-post-mortem-what-we-learned-shipping-12-production-agents)
- **Engineering blog (Open Empower, June 2026):** Catalogued five systematic failure patterns: runaway loops (retry spiral), cost explosions (no budget guardrails), tool misuse (hallucinated parameters), context exhaustion (no truncation strategy), silent failures (no confirmation of side effects). Recommended layered guardrails: loop detection → circuit breaker → cost limit → escalation queue. — [Open Empower, "AI Agent Production Failures"](https://www.openempower.com/blog/ai-agent-production-failures-enterprise-lessons-2026)
- **Research (Zylos Research, 2026):** Identified three AI-specific progress failure modes — The Repeater, The Wanderer, The Compounder — distinct from traditional liveness failures. Recommended applying Erlang/OTP supervisor tree patterns to agent architectures: restart on transient failure, escalate on compound failure, halt on safety failure. — [Zylos Research, "AI Agent Self-Healing"](https://zylos.ai/research/2026-03-02-ai-agent-self-healing-recovery-patterns)
- **Pattern guide (AgentSurface.dev, 2026):** Detailed idempotency patterns for tool design: upsert over create+update, idempotency keys, dry-run modes, and effect-class annotations. Noted that MCP's `readOnlyHint`/`destructiveHint` enable downstream safety reasoning but are underused in practice. — [AgentSurface, "Idempotency and Safety"](https://agentsurface.dev/docs/tool-design/idempotency-and-safety)

## Gotchas

- **`max_iterations` is necessary but not sufficient.** A cap prevents infinite loops but doesn't detect semantic loops (the agent is calling different tools but making zero progress toward the goal). Pair it with progress detection.
- **Retrying without idempotency causes real-world damage.** A payment API timeout that retries without an idempotency key can double-charge a customer. The retry is correct; the lack of deduplication is the failure.
- **Checkpoint files can perpetuate hallucinated state.** If the agent included a fabricated assumption in its task state and you checkpoint it, you checkpoint the hallucination. Validate checkpoint contents before resuming, or treat checkpoints as suspect.
- **Circuit breakers must be per-tool, not global.** If your web search tool is rate-limited, you want to route to a fallback web search — not halt the entire agent. A global circuit breaker kills everything; a per-tool breaker isolates the failure.
- **Degraded errors are the hardest.** Transient errors either succeed on retry or fail clearly. Permanent errors are obvious. But ambiguous responses — "did the email send or not?" — require you to actively query the external system's state rather than trust the agent's memory of the tool call result.
