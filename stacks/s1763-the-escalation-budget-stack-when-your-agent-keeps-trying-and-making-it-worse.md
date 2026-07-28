# S-1763 · The Escalation Budget Stack

When your agent fails silently, retries forever, or takes an irreversible action before you can intervene — and you realize the problem isn't the model, it's that nothing is watching the agent think.

## Forces

- **Agents fail differently than software.** A conventional service crashes and logs a stack trace. An agent may silently loop for 35 minutes, spawn redundant subprocesses, accumulate context until the model halts, or take an irreversible action before intervention is possible.
- **Retry loops amplify outages.** Retrying every non-200 response without circuit-breaking turns a transient dependency failure into a cascading incident — hammering a degraded service until it goes down entirely.
- **Safety and reliability are not the same thing.** You can have an agent that never crashes but consistently drifts into wrong outcomes. Failure-handling must cover both: crashes (exceptions) and drift (confidence, scope, cost velocity).
- **Traditional try-catch doesn't protect against semantic failure.** The agent returned HTTP 200 — but it refunded $10,000 instead of $100. The tool call succeeded technically and failed economically.

## The Move

Layer three concentric controls around agent execution: **guard rails that intercept before action**, **circuit breakers that isolate after failure**, and **escalation paths that hand off when both fail.

### Guard Rails — Intercept Before the Call

- **FailWatch (Python SDK):** Synchronous circuit breaker that intercepts tool calls *before* execution, enforcing hard policy blocks on numeric thresholds, action types, and cost ceilings. Runs deterministically — no LLM involved in the gate check. A refund over $500? Blocked before it touches the payment API.
- **agent-circuit-breaker (TypeScript):** Deterministic local runtime control for the action layer — commands, MCP calls, SQL, filesystem operations, and trajectory-level checks. Targets AI coding agents that run shell commands and touch databases.
- **Policy-as-code:** Define rules as data, not prompts. "Max tokens per run," "no DELETE operations on production DB," "require human approval for any transaction over $X." FailWatch, MonetiseBG/circuit-breaker, and Cordum all enforce these as deterministic gates, not LLM-generated opinions.

### Circuit Breakers — Isolate After Repeated Failure

- **State machine with three phases:** CLOSED (normal) → OPEN (failing, fast-fail) → HALF-OPEN (probing recovery). Cordum defaults: 3 consecutive failures → OPEN for 30s → 2 successful probes → CLOSED. Agents stop routing calls to the degraded dependency during OPEN.
- **Failure-aware retries:** Not every non-200 response warrants retry. Distinguish transient (429, 503) from permanent (400, 401). Retry only the former, and only up to a budget.
- **Exponential backoff with jitter:** Standard 1s → 2s → 4s → 8s with ±20% jitter to prevent thundering herds. Inference Labs recommends evaluating the degraded path — measure user-visible quality for primary, retried, and fallback executions before shipping the policy.
- **Budget-mode circuit breakers:** MonetiseBG/circuit-breaker wraps OpenAI Agents SDK with `withCircuitBreaker(agent)`, defaulting to 10k/10k token caps. Three modes: `budget-guard` (hard token ceiling), `loop-killer` (same-state recurs > maxRetries), and `worth-it` (projected total cost exceeds budget).
- **State sharing across instances:** Use Redis keys (e.g., `cordum:cb:safety:failures`) so circuit breaker state is shared across distributed agent instances. Without shared state, two instances retry in parallel and defeat the isolation.

### Escalation Paths — Hand Off When Controls Fail

- **Supervisor/Watchdog pattern:** A lightweight parent agent monitors worker agent outputs, evaluates confidence and error signals, and escalates to a higher-level agent or human when thresholds are breached. GitHub's `agentic-arch-patterns/skills/supervisor` defines this as hierarchical oversight with explicit escalation paths — not a human paging, but a structured handoff with full context packaged.
- **Checkpoint-and-resume:** Long-running agents (hours-long data processing, multi-step workflows) must persist state after each milestone. Dapr Actors (stateful) or state-snapshot (stateless) approaches let agents survive restarts and continue from the last saved index. The `agent-resume` Python library (dev.to, 2026) checkpoints each processed item and resumes from the last saved index — a zero-dependency solution for batch jobs.
- **Structured HITL escalation:** Not every escalation is "page a human." Zylos Research (2026) defines three escalation tiers: confidence below threshold → supervisor agent review; action outside allowed scope → human approval gate; system state degraded → graceful degradation with user notification. The handoff must include full conversation history, tool call log, and what the agent was attempting — not just a "failed" flag.
- **Idempotency and request IDs:** Every agent action must carry a unique request ID. If a retry resumes from checkpoint, the downstream system must recognize the duplicate and not re-execute. This is the difference between "safe retry" and "double-payment."

## Evidence

- **Engineering blog — Waxell.ai (2026):** Developer woke to a $437 API bill after an agent entered a retry loop at 11 PM and ran unchecked until 7 AM. No alert fired. The fix took 20 minutes. Root cause: no circuit breaker, no cost ceiling, no iteration cap. The lesson isn't "add a kill switch" — it's that kill switches require a human watching. Circuit breakers operate autonomously.
  — [Waxell.ai: AI Agent Circuit Breakers: The Pattern Teams Need](https://www.waxell.ai/blog/ai-agent-circuit-breaker-pattern)

- **Open-source tool — MonetiseBG/circuit-breaker (GitHub, 2026):** A TypeScript library wrapping autonomous AI workflows with `@monetisebg/circuit-breaker/openai-agents`. Default caps at 10k input + 10k output tokens per run. Three governance modes: `budget-guard` (hard token ceiling), `loop-killer` (same-state retry threshold), `worth-it` (predictive cost projection). Production teams can compose modes — an agent handling financial transactions should enable `budget-guard` + `loop-killer` simultaneously.
  — [github.com/MonetiseBG/circuit-breaker](https://github.com/MonetiseBG/circuit-breaker)

- **Research — Zylos Research (2026):** Failure distribution across multi-agent production deployments: 42% specification failures (wrong goal), 37% coordination breakdowns (deadlock/contention), 21% verification gaps (no output check). The six core failure categories unique to agents: tool misuse, context loss, goal drift, retry loops, cascading errors in multi-agent systems, and silent quality degradation. Self-healing implementations achieve 60% reduction in system downtime; 67% of AI system failures stem from improper error handling rather than algorithmic issues.
  — [zylos.ai: AI Agent Self-Healing and Failure Recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)

- **Engineering blog — Cordum (2026):** Retry loops turn short dependency outages into cascading incidents. Circuit breaker defaults: 3 failures → open 30s → 2 successful probes → close. When safety system is unavailable, `POLICY_CHECK_FAIL_MODE=closed` (default) requeues requests; `open` bypasses the safety check and lets requests through with bypass signals. Redis-backed state sharing across distributed instances.
  — [cordum.io: AI Agent Circuit Breaker Pattern](https://cordum.io/blog/ai-agent-circuit-breaker-pattern)

- **Engineering blog — Inference Labs (2026):** Production systems must measure user-visible quality for primary, retried, and fallback executions before shipping policies. Retrying every non-200 response increases cost and tail latency without improving success rates. Fallback should be policy-driven: route by task criticality, latency budget, and quality threshold — not a single static backup model.
  — [inference-labs.com: LLM Fallback and Retry Strategies Production](https://blog.inference-labs.com/posts/llm-fallback-and-retry-strategies-production)

## Gotchas

- **Don't put safety policy in a prompt.** Policy-as-code (deterministic guards) catches failures that a model-generated opinion misses. The model might be distracted; the if-statement is not.
- **Don't share circuit breaker state only in-memory.** In distributed agent deployments, each instance maintaining its own failure count defeats the pattern — a degraded dependency still receives parallel requests from all instances. Redis-backed state is required for the isolation to actually work.
- **Don't retry on permanent failures.** A 400 Bad Request will not succeed on retry. Distinguish transient (429, 503) from permanent (400, 401) at the error-classification layer before deciding whether to retry at all.
- **Checkpoint granularity matters.** A checkpoint after every step is safe but slow. A checkpoint after every 100 steps means up to 99 steps re-executed on failure. Choose checkpoint intervals based on step cost — expensive operations (API calls, DB writes) get their own checkpoints; cheap operations (parsing, formatting) batch.
- **Escalation without context is useless.** Handing off to a human with just "agent failed" is worse than no escalation — you've interrupted a person and given them nothing to act on. Package the full tool call log, conversation history, and what the agent was attempting.
