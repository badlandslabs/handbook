# S-2822 · The Bounded Recovery Ladder Stack — When Your Agent Is Stuck but You Can't Tell It from One That's Slow

Your agent is looping. You think. Maybe it's just doing complex work? You don't know because your only signal is "is it still making API calls?" It is — but it has been calling the same wrong tool with the same wrong arguments for 47 iterations. The fix isn't a longer timeout. It's a recovery system that distinguishes stuck from slow, escalates interventions proportionally, and has a hard ceiling before it hands off to a human.

## Forces

- **Agents fail in ways traditional try/catch can't model.** Traditional software has clear exception boundaries (DB error, HTTP timeout). Agents produce partial progress, ambiguous state ("did the action happen?"), cascading latency, and soft failures where the LLM returns but in the wrong format. None of these trigger a caught exception.
- **Activity is not progress.** API call counts, file edit volume, and log output rise during a stuck loop as readily as during legitimate work. You cannot distinguish stuck from slow using activity metrics alone — only a progress metric that only increases on real outcomes (tests resolved, unique sources gathered, checklist items completed) separates the two.
- **The wrong recovery move wastes more time than no recovery.** A simple nudge (injecting a hint into the next step) breaks a repeater. A full state reset burns all prior work and restarts from scratch. Human handoff is the heaviest move and is overused as a first choice when a nudge would have sufficed. Recovery moves must be proportional.
- **Checkpointing and recovery are different problems.** Checkpointing saves execution state so a crashed agent resumes mid-step. Recovery saves a stuck agent from wasting cycles on a bad approach. Confusing them leads to systems that save state obsessively but never use it to recover intelligently.

## The move

**Design a bounded recovery ladder: one that escalates from cheapest to heaviest, fires on a genuine progress-metric flatline, and has a hard ceiling.**

### Layer 1 — Progress-metric detection
Implement a metric that only increments when real work is done — not when the agent is active. Examples:
- Failing tests resolved (unit/integration)
- Unique source documents processed
- Checklist items completed and verified
- Distinct steps in an execution plan marked done

Track this across heartbeats. A loop is stuck when the metric is flat across N consecutive heartbeats while activity continues.

### Layer 2 — Guardrails at the tool boundary
Don't let bad tool outputs propagate into the agent's context:
- Binary detection: reject PNG/PDF raw bytes from `cat` before they hit the context
- Schema validation: validate tool responses before returning them to the agent — catch malformed JSON, non-existent tool names, and argument type errors at the boundary, not inside the agent
- Timeout budgets: each tool call has a wall-clock budget; if it exceeds it, treat as a failure with specific error type

### Layer 3 — Bounded recovery ladder (escalate in order)
Once loop detection fires, climb this ladder — not skip ahead:

1. **Nudge:** Inject a targeted hint into the next step — "the previous `cat` call returned binary data; use `see photo.png` instead" — not a full explanation, not a restart. A nudge breaks a repeater in one move.
2. **Replan:** If nudge doesn't work within N iterations, ask the agent to re-evaluate the approach. Provide the full execution trace and ask "is this approach still valid?" Let the model choose a new path.
3. **Reset state:** Roll back to the last checkpoint (externalized to Redis or a database — not in-memory, since agent processes crash and get restarted by container orchestrators). Replay from checkpoint with the error context injected.
4. **Escalate to human:** If the ladder is exhausted, surface a structured summary — what the agent tried, what failed, what partial progress exists — to a human queue. Never silently fail; never loop forever.

### Layer 4 — Circuit breakers
Deterministic, not LLM-judged:
- If tool X fails N times consecutively (e.g., CRM API returns 429 three times), halt the graph
- Execute fallback: route to a different model family, degrade to a simpler approach, or surface to human
- Track in Prometheus: `agent_retries_total`, `agent_fallbacks_total`, `agent_circuit_breaks_total`

### Layer 5 — Semantic error recovery
Not all failures are transient. Distinguish error types and route accordingly:
- **Transient** (rate limit 429, server 503, timeout): retry with exponential backoff (2s → 4s → 8s with jitter)
- **Semantic** (malformed JSON, wrong tool, schema violation): do not retry the same prompt — re-prompt with corrective context injected
- **Infrastructure** (auth failure, bad request 400): circuit breaker; do not retry
- **Agent logic** (wrong approach, goal drift): replan or reset, not retry

## Evidence

- **Blog post — Agentpatterns.ai: "Stuck-Loop Recovery":** The detection vs. recovery distinction: "Recovery is a separate discipline from detection because the cheap fix that breaks a *repeater* fails on a *wanderer*, and the heaviest move — human handoff — is a poor first choice when a single nudge would have sufficed." Documents the bounded ladder (nudge → replan → reset → hand off) and progress-metric-only detection approach. — [agentpatterns.ai](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)

- **HN Ask HN thread — "What breaks when you run AI agents unsupervised?":** Real two-week unsupervised deployment documented: $24.88 financial loss in 2 days from no P&L guards, 500KB documentation output instead of execution ("writing about doing > doing"), 47 iterations reading PNG bytes with `cat`. Root cause: tool result was the agent's eyes — returning garbage made the agent go blind. — [Hacker News](https://news.ycombinator.com/item?id=47112543)

- **Blog post — Neel Mishra "Agent Error Handling: Retries and Fallbacks":** Four-category error taxonomy with routing: transient (retry), semantic (re-prompt), infrastructure (circuit breaker), agent-logic (architectural fix). Production note: "Store checkpoints in Redis or a database, not in-memory. Agent processes can crash or be restarted by container orchestrators." — [neelmishra.github.io](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

- **Enterprise post — Open Empower "AI Agent Production Failures: 2026's First Wave":** Runaway loops, tool misuse, context window exhaustion, hallucinated actions, and cost explosions all observed in enterprise deployments en masse. Documents circuit breaker pattern: "if the agent attempts to call the CRM API and fails three times consecutively, the graph halts execution." — [openempower.com](https://www.openempower.com/blog/ai-agent-production-failures-enterprise-lessons-2026)

## Gotchas

- **Activity proxies can't distinguish stuck from slow.** Call counts, file edit volume, and log output rise during a stuck loop. Use only a progress metric that reflects real work completed — not agent busyness.
- **Retrying semantic errors wastes cycles.** If the agent called the wrong tool or got malformed JSON, retrying the identical prompt almost never helps. You need corrective context injected, not the same input again. Only transient infrastructure errors (429, 503, timeout) respond to blind retry.
- **In-memory checkpoints don't survive production.** Container orchestrators restart agent processes. Checkpoint state must live in Redis, a database, or object storage — not in the process heap.
- **Hard-circuit-breaker limits are non-negotiable.** If the circuit breaker's threshold is LLM-judged or configurable at runtime, a misbehaving agent can raise its own ceiling. The threshold should be a compile-time or deployment-time constant, not a runtime variable.
- **The ladder's ceiling must always exist.** If your recovery system has no human handoff step, a sufficiently hard loop will run forever within budget. Every bounded ladder needs a top — even if it's rarely hit.
