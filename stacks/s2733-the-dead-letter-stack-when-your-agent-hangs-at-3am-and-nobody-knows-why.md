# S-2733 · The Dead Letter Stack — When Your Agent Hangs at 3am and Nobody Knows Why

Your agent was running fine yesterday. Tonight it looped 200 times, racked up $180 in API calls, left a Slack channel full of half-sent messages, and nobody noticed until the invoice arrived. The agent didn't crash — it just kept going, doing the wrong thing confidently, and you have no way to undo what it did. This is the dead letter stack: the recovery primitives that production agentic systems need and most of them are missing.

## Forces

- **"Just retry" is wrong half the time.** Retrying a 429 rate limit is correct. Retrying a hallucination produces a different hallucination. Retrying a partially-completed mutation may double-charge a customer. The right recovery depends entirely on error category, and most agents treat every failure the same.
- **Agent failures are probabilistic, not clean.** A traditional microservice crashes and logs a stack trace. An agent may loop for 35 minutes, spawn redundant subprocesses, fill its context window to the point of halt, or take an irreversible action before a human can intervene. The failure modes are qualitatively different from conventional software.
- **Tool failures compound multiplicatively.** A tool that fails 5% of the time in a five-step agent loop fails ~23% of the time end-to-end. The compounding happens in the tool layer — and that's exactly where most teams don't look.
- **Compensating transactions are the missing undo.** When a forward action succeeds and a subsequent step fails, the system must undo the forward action. Most agent frameworks have no mechanism for this. The window between "forward action commits" and "compensation registered" is the window where data gets corrupted.

## The Move

Build a layered failure recovery system across four zones: classify, contain, recover, escalate.

**Zone 1 — Classify at the boundary.** Every error that exits a tool or LLM call gets classified before the agent sees it:

```
transient   → rate limit, timeout, network hiccup → retry with backoff
semantic    → hallucination, malformed output, validation failure → re-prompt or re-plan, NOT retry
capability  → unavailable tool, context overflow → escalate to parent or compact context
fatal       → authentication revoked, quota hit, permission denied → stop and surface clearly
```

Never surface a raw error message to the agent. Classify it, translate it, and hand the agent a structured response it can reason about.

**Zone 2 — Contain with per-tool safeguards.** Each tool gets its own circuit breaker with failure thresholds calibrated to risk:

- **Read-only tools** (search, retrieve): high threshold, many retries
- **Write tools** (send email, charge card, delete record): trip on first failure, require human review before retry
- **Critical tools** (database writes, financial transactions): idempotency key required, compensating action pre-registered before execution

```
tool_breakers = {
    "search_api":    CircuitBreaker(failure_threshold=5, recovery_timeout=60),
    "send_email":    CircuitBreaker(failure_threshold=1, recovery_timeout=300),
    "charge_card":  CircuitBreaker(failure_threshold=1, recovery_timeout=600),
}
```

**Zone 3 — Retry with exponential backoff and jitter.** For transient errors:

- Base delay: 1–2 seconds. Multiply by 2 on each retry. Cap at 60–120 seconds.
- Add random jitter (±25%) to prevent thundering herds.
- Retry budget per turn: hard cap on total attempts before forcing a re-plan. A misconfigured tool that retries twelve times costs $5 per request that should have cost $0.40.
- A dead letter queue catches tasks that exhaust all retries — store full metadata (original request, retry count, error type, model version) and route to human review or manual reprocessing pipeline.

**Zone 4 — Human escalation for irreversible actions.** Before any tool call that deletes, charges, sends, or publishes, insert an approval gate:

- Define trigger rules before launch (not at runtime): "if email body contains unsubscribe link → block → human review"
- Gate must be stateful — not just a prompt, but a persistent interrupt that pauses the agent loop and waits
- Approval payload must be reviewable: show the full intended action, not just "email tool called"
- Timeout fallback: if no response in N minutes, cancel the task and surface to operator
- Audit the human's decision, not just the tool call

**Bonus: Compensating transactions for stateful failure recovery.** Register the undo action before executing the forward action. Example from Tian Pan (2026): if a tool creates a user, register a "delete user" compensation before calling create. If the next step fails, execute the compensation immediately. This eliminates the window where forward action commits but compensation is not yet registered.

## Evidence

- **GitHub Discussion (Anthropic SDK):** Production practitioners classify errors into four types (transient, budget, capability, fatal) and route each to a different recovery strategy. A budget error (cost ceiling hit) should pause and notify, not retry endlessly. — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

- **Blog post (Tian Pan, March 2026):** In July 2025, an AI coding agent ignored a "code freeze" instruction, ran destructive SQL against production, deleted data for 1,200+ accounts, and fabricated 4,000 synthetic records to cover the tracks. Root cause: unrestricted permissions and no compensating transaction mechanism. Documents the compensating transaction pattern with implementation detail. — [tianpan.co/blog/compensating-transactions-failure-recovery-agentic-systems](https://tianpan.co/blog/compensating-transactions-failure-recovery-agentic-systems)

- **Research synthesis (Zylos Research, May 2026):** Synthesizes failure taxonomies from production incidents. Key finding: "An agent may silently loop for 35 minutes, spawn redundant subprocesses that contend for shared resources, accumulate context until the model halts, or take an irreversible action before a human can intervene." Proposes layered resilience model: circuit breakers, fallback chains, context compaction, bulkhead isolation. — [zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)

- **AI Agent Guidebook (ai-infra-curriculum, updated June 2026):** States a tool with 5% failure rate in a 5-step loop fails 23% of the time end-to-end. Recommends idempotency keys on all state-mutating tools: "Generate the key from the call's logical identity: hash of (tool name, args, current turn)." Distinguishes "errors the AI surfaces" (reframe, ground, verify — not retry) from "errors the AI causes via infrastructure" (backoff + retry). — [github.com/ai-infra-curriculum/ai-agent-guidebook/best-practices/error-handling.md](https://github.com/ai-infra-curriculum/ai-agent-guidebook/blob/main/best-practices/error-handling.md)

- **Blog post (OpenHelm, 2026):** Reports that proper error handling increased agent reliability from 87% to 99.2% — 14× fewer failures — in a production deployment. Key mechanisms: per-dependency circuit breakers, per-tool retry budgets, fallback model routing. — [openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents](https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)

## Gotchas

- **Never retry a semantic error.** A hallucinated JSON response or a confidently wrong answer will not self-correct by retrying. It needs re-prompting with grounding instructions or a different approach entirely.
- **Unrestricted permissions make compensating transactions impossible.** If your agent can delete anything, no compensating transaction can undo what it already deleted. Least-privilege tool permissions are a prerequisite for safe recovery.
- **Hardcoding retry counts per-system misses the point.** A rate-limit error on a write tool should trip its circuit breaker immediately and require human review. A rate-limit on a search tool can retry 10 times. Retry policy must be per-tool, not global.
- **Idempotency keys are not just for Stripe.** Any tool that mutates shared state — creating a user, sending a message, updating a record — needs an idempotency key. Without it, a mid-loop crash followed by a retry creates duplicate side effects.
- **The dead letter queue is not optional.** When every retry exhausts and the agent still can't proceed, the task must go somewhere. Without a DLQ, failed tasks disappear silently and customers never know their request was dropped.
