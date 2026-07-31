# S-1929 · The Fallback Ladder Stack — When Your Agent Can Recover but Doesn't Know How

You built the agent. It handles happy paths perfectly. Then a rate limit hits at 2 a.m., the API schema drifts silently, or step 6 of 10 throws an unhandled exception — and your agent either crashes loudly or, worse, keeps running confidently in the wrong direction. 86% of agent failures are recoverable. Most agents never recover because nobody gave them the playbook.

## Forces

- **Agents introduce side effects that break naive retry.** A retry that re-sends an email or creates a duplicate record isn't recovery — it's a new incident. Idempotency must be designed into every tool, not assumed.
- **The LLM is the worst error classifier.** When a tool fails, agents often continue with hallucinated fallback values rather than surfacing the failure. You cannot trust the model to triage its own errors.
- **Failure costs compound exponentially.** A single uncaught exception in step 4 of a 10-step pipeline wastes steps 1-3 and any tokens spent on steps 5-10 that built on corrupted state. Without checkpointing, you restart from zero.
- **Graceful degradation requires a ladder, not a switch.** Binary fallback ("use the backup model or return an error") abandons partial value. A tiered fallback preserves as much work as possible at each degradation level.

## The Move

Build a layered recovery architecture. The stack has five layers, each addressing a distinct failure mode:

**Layer 1 — Classify before retrying.** Not all errors deserve the same response. Categorize into: transient (rate limit, timeout → retry), semantic (malformed output → re-prompt), resource (token budget hit → reduce/summarize), or fatal (auth failure → abort). A retry loop hammering a 401 endpoint wastes tokens and time. Classification happens at the tool wrapper level, not in the agent prompt.

**Layer 2 — Exponential backoff with jitter for transient errors.** Wait doubling intervals (1s, 2s, 4s, 8s...) with random jitter to prevent synchronized retries from multiple agents. Cap at a max delay and a max retry count. After that, escalate.

**Layer 3 — Idempotency keys on every side-effecting tool.** Before executing a tool with external effects (email, database write, payment), generate a deterministic idempotency key from the checkpoint sequence number. Store it. On retry, check if the key exists. If yes, skip the execution and return the cached result. This makes retry safe by definition.

**Layer 4 — Checkpoint state before every side-effecting step.** Persist the execution state (completed steps, tool results, context buffer) to durable storage (SQLite for small state, S3 for artifacts) at every step boundary. On failure, replay from the last checkpoint — don't re-run completed steps. Append-only semantics keep the audit trail clean. Recovery must be deterministic, not LLM-generated.

**Layer 5 — Circuit breaker and fallback ladder for persistent failures.** When a service or model fails N times in a row, open the circuit — stop calling it and route to the fallback. The fallback ladder goes: primary model → smaller/faster model → cached response → rule-based heuristic → human escalation. For agents: 86% of failures are recoverable at the circuit-breaker layer without human intervention.

## Evidence

- **GitHub Discussion (Anthropic SDK):** Practitioners report using a tiered approach with session-based checkpoints every N messages and explicit error type classification (transient / budget / capability / semantic / fatal). The insight: "Error recovery is 30% code, 70% expecting things to fail in ways you never imagined." — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

- **AgentWorks:** Documents a 5-layer recovery architecture: idempotency keys → error classification → structured error feedback → circuit breakers with model fallbacks → human-in-the-loop escalation. Key finding: "A retry is not automatically safe — if a tool call already created a record or sent an email, blindly retrying duplicates the effect." — [agent-works.ai/insights/agent-error-handling-recovery-patterns](https://agent-works.ai/insights/agent-error-handling-recovery-patterns)

- **Real incident (Coasty AI / Y Combinator):** A computer-use agent against a third-party API had the API silently change its authentication method. The agent: did not detect the change, did not throw an error, did not stop — hammered the endpoint for hours generating thousands in charges. Moral: agents that fail silently cost more than ones that fail loudly. — [coasty.ai/blog/ai-agent-error-handling-recovery-2025-20260327](https://coasty.ai/blog/ai-agent-error-handling-recovery-2025-20260327)

- **EngineersOfAI:** Production checkpointing guide: "Any task running more than a few minutes will encounter failures: rate limits, network timeouts, OOM errors, power outages, deployment restarts. Checkpointing is not optional for long-horizon agents — it is the difference between a viable system and a toy." — [engineersofai.com/docs/agentic-ai/long-horizon-planning/checkpointing-and-recovery](https://engineersofai.com/docs/agentic-ai/long-horizon-planning/checkpointing-and-recovery)

## Gotchas

- **Checkpointing synchronously tanks latency.** Sync checkpoint writes add 50-200ms per step. Use async flush with bounded durability windows (5-15ms overhead) — trade a small consistency window for acceptable performance.
- **Never let the LLM decide recovery paths.** LLMs should execute pre-validated recovery workflows stored in the state machine, not reason their way to a recovery strategy. Generated recovery paths are non-deterministic and unsafe.
- **The fallback ladder must be designed upfront.** Retrofitting fallback tiers after an incident means partial results get dropped, audit trails get broken, and degraded-mode behavior is untested. Design the full ladder in the architecture phase.
- **Token budget errors require context reduction, not retry.** Sending the same prompt again with a full context window will hit the same wall. Reduce the payload (summarize history, drop low-value context) or switch to a model with more context headroom.
