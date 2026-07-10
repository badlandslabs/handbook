# S-903 · The Cascading Failure Stack — When Your Agent Succeeds Nine Times and Fails on the One That Matters

Your agent worked perfectly in testing. In production, it works perfectly 95% of the time — per step. Chain 10 steps together and you get roughly 60% end-to-end success. You never saw the failures because you tested each step in isolation. The agent doesn't fail in one dramatic way; it accumulates small probability of failure across each tool call, each API response, each branching decision, until something in the chain breaks silently and you only notice when a customer asks why their task never completed.

## Forces

- **Step-level accuracy ≠ system-level reliability.** A 95% accurate step sounds good. Ten such steps chained together yields 0.95^10 ≈ 60%. Most agent workflows chain 5–12 steps. This math is invisible in isolated benchmarks.
- **Agents fail silently, not loudly.** Traditional software throws exceptions. Agents often just... stop producing output, return malformed JSON, or hallucinate that a tool succeeded when it didn't. No stack trace. No log line. Just a task that never finished.
- **The failure taxonomy is different from conventional software.** AI agents fail in non-deterministic ways: hallucinated tool calls (the model invents a tool that doesn't exist), schema violations (wrong arguments to a real tool), environment errors (the API is down), and logical stalls (the agent retries the same failing action indefinitely). Standard try/catch doesn't cover any of these.
- **89% of teams monitor but don't evaluate.** Observability without outcome evaluation means you watch the agent run while having no idea whether the output is correct. 71% of organizations are experimenting with agents; only 11% have reached production. 40%+ of agent projects are predicted to be canceled by 2027 — not because the models are bad, but because the failure handling infrastructure was an afterthought.

## The move

**Design failure handling as an explicit layer, not a catch block.**

### Classify errors by who can fix them

The single most important architectural decision: every error type routes to a different handler. In practice, three classes:

| Class | Who Fixes It | Mechanism | Example |
|-------|-------------|-----------|---------|
| **Transient** | The system, automatically | Exponential backoff + jitter (1s → 2s → 4s → 8s → 16s), 3–5 retries, then circuit breaker | API 429, DNS blip, network timeout |
| **LLM-Recoverable** | The LLM itself, given context | Feed error back into state: "Action failed with X. Try a different strategy." Reasoning models (Claude Opus, GPT-5.5, DeepSeek-R2) have higher one-shot recovery on this | Tool returned bad JSON, wrong tool selected, plan drifted |
| **Irreversible / User-Fixable** | The human | `interrupt()` checkpoint — halt execution, surface the issue, wait for a decision | Destructive actions, ambiguous user intent, repeated loop detection |

### Checkpoint state before every high-risk step

For long-running agents, an error in step 9 should not require restarting from step 1. Store state snapshots (checkpoints) at decision boundaries. LangGraph, Microsoft Agent Framework, and Temporal all provide primitives for this. A checkpoint should include: current plan, retrieved context, completed tool outputs, and the error history so far.

### Build an explicit loop detector

The "ReAct Loop of Death" — the agent performing the same failing action repeatedly — is one of the most common production failure modes. Track the last N (3–5) action hashes. If the agent attempts the same action three times with no state change, hard stop and escalate to human review. Don't rely on the model to notice it's looping.

### Layer circuit breakers at the tool level

A circuit breaker prevents the agent from hammering a failing dependency. After N consecutive failures against a specific tool or API, open the circuit for X minutes. During open state, route to fallback (cached response, degraded mode, or human escalation). Prevents rate-limit storms from cascading into a full outage.

### Make failure observable through outcome evaluation, not just logs

Store each step's output and the final outcome. Don't just log that tool X returned — log whether the overall task succeeded. The gap between watching your agent run and knowing whether it produced the right answer is where most production failures hide undetected.

## Evidence

- **Practitioner field report (paperclipped.de, 2026):** 71% of organizations using agents; only 11% reaching production. 40%+ predicted cancellations by 2027. Single agent at 95% accuracy per step drops to ~60% by step 10. Production success rates 54–77% for individually-tested agents. — [https://www.paperclipped.de/en/blog/ai-agent-production-issues](https://www.paperclipped.de/en/blog/ai-agent-production-issues)

- **Real-world case study — Supergood Solutions (April 2026):** Lead-enrichment agent ghosting in production. Root cause: three concurrent instances hitting Clearbit free tier (10 req/sec), causing 429s that silently dropped. The agent timed out, moved on, and never alerted anyone. Fix: three-layer resilience pattern — exponential backoff with jitter at the request level, per-API circuit breakers, and a fallback chain that degraded gracefully (returned partial enrichment rather than silently skipping). — [https://supergood.solutions/blog/when-your-agent-fails-silently](https://supergood.solutions/blog/when-your-agent-fails-silently)

- **Ask HN thread (HN id 48014837, July 2026):** Practitioners reporting they moved from autonomous agentic loops to deterministic pipelines. Core pattern: use LLM to generate scripts, execute scripts via OS-native schedulers (cron), store results in SQLite. LLM only involved at analysis stage, not automation. Prevents the entire failure surface of autonomous loops from affecting automated workflows. — [https://news.ycombinator.com/item?id=48014837](https://news.ycombinator.com/item?id=48014837)

- **LangGraph error handling patterns (focused.io, April 2026):** Error classification matrix showing three handler types. Key insight: "Errors are data, not just exceptions. Store them in state so the LLM can see what went wrong and adjust its approach." Recommends RetryPolicy for transient errors, state-injected error context for LLM recovery, and `interrupt()` for human-gated actions. — [https://focused.io/lab/langgraph-agent-error-handling-production](https://focused.io/lab/langgraph-agent-error-handling-production)

- **MAST taxonomy (Berkeley/Stanford, March 2025):** Analyzed 1,642 agent execution traces across seven frameworks. Agent failure rates: 41% to 86.7% depending on harness. Tool responses account for 67.6% of all tokens in agent traces — most teams spend hours refining system prompts when the real failure surface is tool interactions. — [https://www.buildmvpfast.com/blog/debugging-ai-agents-production-error-recovery-self-healing-2026](https://www.buildmvpfast.com/blog/debugging-ai-agents-production-error-recovery-self-healing-2026)

- **Self-healing market research (Zylos, February 2026):** 67% of AI system failures stem from improper error handling, not algorithmic issues. Self-healing implementations achieve 60% average downtime reduction. Self-healing cycle: Detect → Diagnose → Repair → Validate → Adapt. — [https://zylos.ai/research/2026-02-17-ai-agent-self-healing-auto-recovery](https://zylos.ai/research/2026-02-17-ai-agent-self-healing-auto-recovery)

## Gotchas

- **Don't retry everything.** Only retry transient failures (network, rate limits, timeouts). Permanent failures (invalid schema, hallucinated tool) that retry with the same input will always fail. Classify first; retry second.
- **Exponential backoff without jitter causes thundering herd.** If you retry at exactly 1s, 2s, 4s... and many agents hit the same endpoint, they'll all retry simultaneously. Add random jitter (±20%) to spread retry windows.
- **Loop detection must track state, not just action.** Checking if the same action was called is insufficient — the agent may call different tools but make the same logical mistake. Track a hash of (action + tool outputs + plan state).
- **Circuit breakers need per-API granularity, not global.** A circuit breaker on "all external calls" means a Stripe failure takes down your Slack integration. Scope breakers to each external dependency independently.
- **Human-in-the-loop is not optional for destructive actions.** Agents will execute `DELETE * FROM users` if the plan calls for it and the tool definition exists. Every irreversible action needs a checkpoint before execution, not a confirmation dialog after.
