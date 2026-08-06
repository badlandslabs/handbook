# S-2231 · The Agent Failure Handling Stack

When your agent loops silently for 8 hours burning $437, or deletes a production database in 9 seconds — and you have no guardrail that caught it.

## Forces

- Agents fail in ways traditional software doesn't: non-deterministic loops, semantically wrong outputs, irreversible side effects, and silent degradation that standard monitoring tools miss entirely.
- A naive `except Exception: retry` block is worse than no error handling — it retries everything including cases where retrying wastes money and compounds damage.
- The same autonomy that makes agents useful makes them dangerous: an agent with Railway API credentials and no permission boundary will "helpfully" delete a volume when it encounters a staging error.
- Building robust failure handling feels like over-engineering during development. It isn't over-engineering by the time you wake up to a $437 overnight bill or a 30-hour outage.
- Existing observability tools (LangSmith, LangFuse, Arize, Helicone) answer *what happened* but not *is my agent actually reliable right now*.

## The move

### 1. Classify failures before responding

Not all failures are equal. Route each error to the right recovery strategy:

| Failure type | Examples | Response |
|---|---|---|
| **Transient** | 429 rate limit, brief timeout, 503 | Retry with exponential backoff (2s, 4s, 8s… cap at 60s) |
| **Persistent** | Provider outage, exhausted quota, bad API key | Fallback to secondary model or route; alert human |
| **Semantic** | Tool returns data that parses but is wrong | Self-correction loop with explicit validation before proceeding |
| **Agentic** | Loop detection, context overflow, plan abandonment | Hard ceiling + checkpoint restore + human notification |
| **Irreversible** | Destructive action already taken | Compensating workflow (saga pattern), then stop |

**Do not** use a single `try/except/retry` for everything. The retry loop that handles a transient 429 can silently compound a semantic failure into thousands of wasted API calls.

### 2. Install circuit breakers at three layers

Generic retry logic is not enough. Break the circuit at the right granularity:

- **LLM layer**: Track consecutive failures per model endpoint. Trip at 3–5 failures. On trip: switch to fallback model, alert, log. Do not keep calling a failing provider.
- **Tool layer**: Per-tool failure counters. If `volumeDelete` has failed 2x in a row, route through human confirmation regardless of what the agent decided.
- **Session layer**: Hard token budget per conversation turn (e.g., 50K tokens). Hard step ceiling (e.g., `recursion_limit=50` in LangGraph). These are the only things that stop the overnight loop.

A kill switch is reactive ("stop this after damage"). A circuit breaker is preventive ("stop this before damage"). Build both.

### 3. Checkpoint state so failures are recoverable

Long-running agents must be able to resume, not restart. This is not optional for production:

- Use LangGraph's SQLite/Redis checkpointer to snapshot graph state at each step.
- On crash: restore from last checkpoint, not from scratch. A 40-step workflow that fails at step 38 should resume at 37, not re-run from the beginning.
- Store operation IDs (UUId per action) to make retries idempotent — same action with same ID does nothing on replay.
- Pair checkpoints with a step manifest: what the agent intended to do, what it did, what the result was.

### 4. Pre-declare compensation for every side effect

If your agent can change systems, it needs a tested undo path before it executes. Use the saga pattern:

- Every side-effecting step (API call, DB write, file mutation, deployment) declares a compensating action upfront.
- Compensations are pushed onto a per-workflow LIFO stack.
- On `FAILED_FATAL` (unrecoverable error): orchestrator pops and dispatches each compensation as a separate job, gated by the safety layer.
- **Key constraint**: Compensations must be idempotent and independently executable. A `volumeCreate` compensation that fails leaves you in a worse state than the original failure.

### 5. Sandcastle the blast radius before deployment

The Cursor/Railway incident proves: no jailbreak, no prompt injection — just an agent doing what it was built to do, with credentials that were too broad.

- **Run in a sandboxed environment**: dedicated VM or container with limited OS-level permissions. Never give an agent account-scoped tokens if it only needs scoped resources.
- **Dry-run mode**: for any destructive or external API call, execute in a sandbox first, evaluate the result, then re-execute in production only if the sandbox result is acceptable.
- **Permission least-privilege**: if the agent only needs to read Railway volumes, give it a read-only token. The `volumeDelete` mutation should require a separate, explicitly approved credential.
- **Deployment-length evaluation**: before each agent run, have a separate evaluation pass assess whether the planned actions are within the approved scope.

### 6. Watch the blind spots your observability stack ignores

Standard agent observability tools (LangSmith, LangFuse, Arize, Helicone) give you traces, latency, and token counts. They do **not** tell you:

- Is my agent actually producing business value right now?
- Is it looping without me noticing?
- Has it silently degraded?
- Will I know before my users do?

Instrument for **outcome reliability**, not just trace completeness:

- Flag sessions where step count exceeds a threshold (e.g., >30 steps for a task that normally takes 5).
- Alert on token-per-minute anomalies — a spike in tokens without a corresponding spike in successful completions.
- Monitor `circuit_breaker_open_total` and `loop_detected_total` as first-class business metrics.

### 7. Design human escalation as a first-class control, not an afterthought

Escalation paths must be documented, tested, and accessible under stress:

- Define explicit escalation triggers: circuit breaker opens, per-session budget exhausted, agent requests destructive action, agent behavior diverges from task description.
- Make escalation **interruptible** — ability to pause, steer, or cancel a running agent mid-execution is more valuable than a post-hoc kill switch.
- String-matching denylists and client-side approvals are not security boundaries. Pair them with verification evidence (output validation, sandbox results) not just rationale.
- Log every escalation: what triggered it, what the agent was doing, what state it was in.

## Evidence

- **HN Post (Ask):** "What's the worst thing your AI agent did in production" — real-world failures including an agent that "applied remediation measures by altering configuration" and only stopped when discontinued. — [https://news.ycombinator.com/item?id=48658607](https://news.ycombinator.com/item?id=48658607)
- **Engineering Post:** The PocketOS/Railway incident — Cursor agent (Claude Opus 4.6) deleted production database and all volume-level backups in 9 seconds via a single authenticated GraphQL mutation. Root token was account-scoped with no privilege separation. Agent wrote a post-incident "confession." 30-hour outage. — [https://elmoz.de/blog/cursor-deleted-production-database-railway-pocketos](https://elmoz.de/blog/cursor-deleted-production-database-railway-pocketos) + [https://www.theregister.com/software/2026/04/27/cursor-opus-agent-snuffs-out-startups-production-database/5224442](https://www.theregister.com/software/2026/04/27/cursor-opus-agent-snuffs-out-startups-production-database/5224442)
- **Post-Mortem:** $437 overnight API bill — document-processing agent entered a retry loop at 11 PM, ran unchecked until 7 AM, thousands of identical failing tool calls. No alert fired. No threshold tripped. — [https://www.waxell.ai/blog/ai-agent-circuit-breaker-pattern](https://www.waxell.ai/blog/ai-agent-circuit-breaker-pattern)
- **GitHub OSS:** ARF — Agentic Reliability Framework, separates detection/diagnosis (OSS) from governed execution (Enterprise). Three-agent system: Detective (FAISS anomaly detection), Diagnostician (causal reasoning), Predictive (failure forecasting). Reported 2-minute MTTR vs 45-minute manual. — [https://github.com/petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)
- **Research:** AI Agent Self-Healing taxonomy — six agentic failure modes distinct from microservice failures: infinite loops, context overflow, plan abandonment, semantic drift, resource contention, credential hallucination. — [https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/)
- **Engineering:** LangGraph production patterns — `recursion_limit` for hard step ceilings, SQLite/Redis checkpointing for state persistence, per-tool circuit breakers, saga compensation stack. — [https://cloudzy.com/blog/why-ai-agent-loops-fail-in-production](https://cloudzy.com/blog/why-ai-agent-loops-fail-in-production)
- **Engineering:** Saga rollback pattern — compensating workflows triggered on `FAILED_FATAL`, LIFO compensation execution, per-workflow lock prevents parallel rollback race conditions. — [https://cordum.io/blog/ai-agent-rollback-compensation](https://cordum.io/blog/ai-agent-rollback-compensation)
- **DEV Community:** Agent monitoring blind spots — existing observability tools (LangSmith, LangFuse, Arize, Helicone) show traces but not outcome reliability. — [https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai](https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai)
- **Anthropic:** Computer use safety guidance — dedicated VM/container, limited privileges, domain allowlists, pauses before unauthorized actions, deployment-length evaluations, rollback and compensation. — [https://aigcdev.com/en/articles/claude-computer-use-safe-workflow](https://aigcdev.com/en/articles/claude-computer-use-safe-workflow)
- **Framework:** Human-in-the-loop control surfaces — permissioning/gating, interrupt/steer/cancel, human escalation. Emphasizes that string-matching denylists are not security boundaries. — [https://looprails.dev/framework](https://looprails.dev/framework)

## Gotchas

- **Naive retry blocks make things worse.** A generic `except Exception: retry` will retry semantic failures (wrong data) the same as transient ones (rate limit). Classify first, then route to the appropriate recovery.
- **Your observability tool is not your safety system.** LangSmith traces show you what happened; they don't alert you when your agent is looping or degrading silently. Instrument outcome reliability metrics separately.
- **Hard limits are the only thing that stops the overnight loop.** A circuit breaker that only counts failures but has no budget cap can still run up thousands of dollars if each failure call is expensive.
- **Idempotency is not automatic.** If your agent retries a non-idempotent action (e.g., sends an email, deletes a volume), the retry may succeed and compound the damage. Every side effect needs a unique operation ID and a guard that skips execution if that ID has already been processed.
- **The Cursor/Railway incident was not a safety failure — it was a credential architecture failure.** The agent did exactly what it was designed to do. The gap was that nobody applied least-privilege to the token's scope. Scope your tokens to the minimum actions the agent actually needs.
- **Compensation is not rollback.** You cannot undo a database deletion. Compensation is running a second, forward-looking workflow that restores the desired state. Write and test compensations before production deployment, not after the incident.
- **Loop detection and loop handling are different.** Detecting that an agent is stuck is solvable (step count, token budget, repeated action fingerprints). Deciding what to do about it — resume, escalate, abort — requires a policy defined before it happens.
