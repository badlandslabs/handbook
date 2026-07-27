# S-1738 · The Recovery Stack: When Your Agent Can Keep Running but Can't Keep Itself Alive

[Your agent loops, calls tools, returns results. Then a rate limit hits mid-workflow, an API returns garbage JSON, and the agent either crashes outright or — worse — continues with a corrupted internal state, returning confident nonsense with a 200 OK. The recovery mechanisms you planned for are now the ones burning through your API quota and locking your memory store.]

## Forces

- **Agents fail non-deterministically.** A prompt that worked once fails the next time due to model drift, token fluctuation, or a hallucinated tool argument. Traditional `try/catch` blocks don't cover the space between "crashed" and "wrong answer."
- **Recovery loops can run off the cliff.** The Claude Code codebase has a documented incident: an agent's retry logic lacked a ceiling and burned ~250,000 API calls in a single day, executing recovery logic it had been given exactly as specified — just with no cap.
- **Failure compounds in multi-agent pipelines.** Single agents fail predictably; two agents sharing a memory store create deadlock surfaces. A third adding a background compaction loop creates a new failure mode nobody modeled.
- **Silent failures are worse than loud ones.** An agent that crashes is obvious. An agent whose MCP server went silent three days ago — still returning 200, still dispatching tasks, all against stale data — is a production incident waiting to surface.

## The Move

Build a layered defense stack where each layer covers a distinct failure mode. Remove any one layer and a specific class of failure becomes your next incident.

### Layer 1 — Surface Errors: Retry with Exponential Backoff + Jitter

- Retrying immediately after a rate-limit error worsens the problem. Double the delay each attempt (1s → 2s → 4s → 8s → 16s).
- Cap at 60 seconds. Add 30% jitter to prevent thundering-herd synchronization across parallel agents.
- Limit to 3–5 retries before escalating.

### Layer 2 — Sustained Failures: Circuit Breakers

- After N consecutive failures to a specific service, open the circuit: stop calling it, return a fast error, and probe it periodically.
- Typical config: 5 consecutive failures triggers open state; 30-second recovery window before half-open probe.
- Circuit breakers operate at the per-service level (separate breakers for LLM, vector DB, external APIs).

### Layer 3 — Model-Level Failures: Fallback Chains

- Chain models in order of capability: Opus → Sonnet → Haiku → queue for retry. Learned the hard way during the November 2025 API outage.
- Route by failure type: context-window exceeded → smaller model with compressed history; quality concern → upgrade model with same prompt.
- Never let the fallback chain itself loop — cap the chain depth.

### Layer 4 — Tool/Skill Failures: Isolation + Self-Testing

- Set per-tool timeouts (30 seconds is common). Log the failure, return a structured error, continue the pipeline in degraded mode — don't let one tool's failure crash the session.
- After one MCP server silently broke for 3 days, miaoquai.com built **openclaw-skill-validator**: a self-test suite that scores each tool at 100% before it enters rotation.
- Sandboxed execution for agent-generated scripts. Agentic systems that run AI-written Python need `eval()` calls caught before they can touch the filesystem.

### Layer 5 — State Corruption: Checkpoint-and-Resume

- Save session state (current step, tool results so far, LLM outputs) to durable storage at every milestone, not just at the end.
- On restart, the agent reads the checkpoint and resumes from the last good state — not from scratch.
- Combine with idempotency guards: each checkpoint records what work has been done so duplicate steps aren't re-executed on recovery.

### Layer 6 — Unrecoverable Failures: Escalation Queue

- After all automated recovery is exhausted, escalate to a human-in-the-loop queue with full context: what failed, what was tried, what the agent's last coherent output was.
- Every AI-triggered action gets an audit log with a structured explanation — not just "it failed," but "it failed because X, tried Y, then Z, then escalated."

## Evidence

- **GitHub Discussion:** Production team running 5 AI agents 24/7 for 95+ days at miaoquai.com published a 4-layer error recovery stack covering connection resilience, model fallback chains, tool failure isolation, and state checkpointing — built after surviving repeated incidents — [GitHub #1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **GitHub Engineering:** Running autonomous agents on 40 million daily jobs; documented recovery incidents from unbounded retry loops and silent downstream failures — [jangwook.net](https://jangwook.net/en/blog/en/self-healing-ai-systems)
- **DevPlaybook:** 11-round debugging marathon across a multi-agent system, catalogued 70+ production bugs — every pattern in their monitoring daemon exists because something actually broke in production. Found: agent-generated scripts containing `eval()` calls, processes crashing silently, tasks stuck in "doing" status indefinitely, infinite restart loops burning logs — [devplaybook.cc](https://devplaybook.cc/blog/how-to-build-ai-agent-self-healing-system/)
- **OpenHelm:** Proper layered error handling increased agent reliability from 87% to 99.2% — a 14× reduction in failures — [openhelm.ai](https://www.openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)
- **Zylos Research:** Failure taxonomy from production incidents: ~42% specification failures (agent misinterprets goals), ~37% coordination breakdowns (multi-agent handoff failures), ~21% verification gaps (no output validation) — [zylos.ai](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery)

## Gotchas

- **No ceiling on retry → runaway cost.** Add a hard cap on retry attempts per session and a global cost floor. The recovery mechanism that keeps the agent running is the one most likely to run up the bill.
- **Per-service circuit breakers, not global ones.** A circuit breaker on the LLM API shouldn't also trip when your GitHub API tool fails — they're independent failure modes.
- **Degraded != dead.** When a tool fails, the agent should continue with degraded capability and signal that, not crash. "The search tool timed out; proceeding with cached results and flagging for review" is a valid outcome.
- **Tool self-testing is not optional for production.** A tool that passes a one-time smoke test and then silently breaks is worse than a tool that was never connected. Self-test on every rotation into active use.
- **Checkpoint on milestone, not on every step.** Over-checkpointing creates performance overhead and storage cost; under-checkpointing means the agent restarts too far back. Checkpoint at natural task boundaries.
