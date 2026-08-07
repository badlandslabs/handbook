# S-2288 · The Graceful Degradation Stack — When Your Agent Fails and Everyone Finds Out at 3am

Your agent has been running for 72 hours straight. At 2:47am a network blip causes a timeout. The retry storm that follows posts 50 duplicate messages to your Discord channel before anyone notices. The agent reports "task complete" with high confidence. The output is plausible but wrong. Nobody caught it until the customer complained.

This is the failure handling gap: the moment between "agent does something unexpected" and "you find out about it" — and it is where agentic systems most reliably destroy trust.

## Forces

- **Errors in agents are not software errors.** Traditional try-catch blocks handle HTTP 500s and timeouts. They do not handle an agent that returns HTTP 200 with hallucinated data, or a tool call that succeeds technically but fails semantically. The error surface of an agentic system is categorically different from deterministic software.
- **Recovery strategy must match error type.** A network retry is the right response to a transient timeout. It is the wrong response to a capability gap — retrying won't make the tool suddenly exist. Using one recovery pattern for every failure type guarantees either over-retrying (cost spiral, cascade failure) or under-recovering (silent degradation).
- **Multi-agent failure cascades are the dominant production failure mode.** One agent goes down; without isolation boundaries, it takes the entire pipeline with it. This was documented by multiple independent teams running multi-agent systems at scale.
- **The completion bias is invisible until it isn't.** Agents report "task complete" even when the output is plausible-but-wrong. Without automated validation gates at output boundaries, you will not catch failures until production breaks or a customer reports it.

## The move

**Classify errors at detection time, then dispatch the correct recovery strategy.** The pattern has four layers that must be wired together:

### Layer 1 — Error classification taxonomy

Every failure falls into one of four buckets. Dispatching the wrong recovery to the wrong type is the most common production mistake:

| Error Type | Examples | Recovery Strategy |
|---|---|---|
| `transient` | Network blip, rate limit hit, brief API outage | Exponential backoff + retry with jitter. Cap at 3–5 attempts. |
| `budget` | Cost ceiling or token limit hit mid-task | Pause task, write checkpoint, notify orchestrator, await top-up or human decision |
| `capability` | Agent requests unavailable tool or skill | Escalate to parent/supervisor agent. Do not retry — the tool doesn't exist. |
| `semantic` | LLM output fails validation (wrong format, hallucinated params) | Retry with explicit format correction injected into next turn's system prompt |

### Layer 2 — Three-state circuit breaker

Borrowed from distributed systems, adapted for agentic behavior:

- **CLOSED (normal):** Agent operates normally. Monitor for error rate thresholds.
- **OPEN (tripped):** After N consecutive failures (typically 3–5), stop executing and alert. Do not keep retrying into a failing dependency.
- **HALF-OPEN (probing):** After a cooldown window, allow one probe request. If it succeeds, return to CLOSED. If it fails, return to OPEN and extend the cooldown.

The key adaptation for agents: the circuit breaker monitors *behavior patterns* (repeated tool calls with identical or near-identical parameters, frequency of error types), not just HTTP status codes. A tool returning 200 with garbage data should trip the circuit.

### Layer 3 — State checkpointing for resumable execution

A 10-step chain at 85% per-step reliability has a ~20% end-to-end success rate — not because the model fails, but because each step is a fresh opportunity for failure. Checkpointing turns a restart from "begin from step 1" into "resume from step 47."

Three proven approaches from production systems:

- **Session-based checkpoints every N messages:** Serialize agent state (goal, completed steps, intermediate results, decisions made and why) to durable storage at defined intervals. On restart, read the last checkpoint before resuming.
- **MEMORY.md shared state:** For multi-agent systems, each agent reads a shared markdown file at session start and writes to it at session end. Fields include: original goal, current plan, completed steps, facts discovered, decisions made. Validated across 95+ days of continuous multi-agent operation at miaoquai.com.
- **Event-sourced audit log:** Append-only log of every agent action with timestamp, intent, and result. Recovery replays the log. Best when auditability matters (compliance, debugging, accountability). Snapshots compress long histories.

### Layer 4 — Idempotency guards for side-effect containment

When an agent retries a failed write operation (post to Slack, create a ticket, send an email), blind retries cause duplicate side effects. The pattern:

1. Generate a stable idempotency key from the operation intent (e.g., `weekly-digest-{user_id}-{week}` — human-readable, not a hash).
2. Before executing, check whether the key already exists in an action log (primary key constraint prevents duplicates).
3. If the insert succeeds, execute the action and update with the result.
4. If the insert fails (duplicate key), return the cached result.

Real war story: a cron agent that posts to Discord at 22:00 experienced a network timeout + retry storm. Without idempotency guards, this produced 50 duplicate posts within 5 minutes. With guards in place, the retry returns the original post ID without re-executing.

### Layer 5 — Loop detection as circuit breaker trigger

Agents loop for four distinct reasons, each requiring a different detection strategy:

- **Exact repetition:** Same tool call with identical parameters. Detect with O(1) string-hash comparison of consecutive calls. Trigger: same call hash appearing 2–3 times consecutively.
- **Near-identical repetition:** Same tool with slightly different params (e.g., iterating on a query). Detect with semantic embedding similarity (cosine distance). Trigger: cosine similarity > 0.9 across N consecutive calls.
- **Behavioral loops:** Agent takes different tool calls but doesn't progress toward goal. Detect with frequency analysis — tracking goal progress score over time. Trigger: progress score flatlined for N steps.
- **Semantic drift:** Agent's output gradually diverges from original task (starts summarizing, then rewrites, then editorializes). Detect by checking output against the original task description at each step.

The `agent-guard-mcp` open-source project (mdfifty50-boop/agent-guard-mcp) provides circuit breakers and pattern detection via the Model Context Protocol as a reusable implementation of these detection strategies.

## Evidence

- **GitHub Discussion (production war story):** A team running 5 autonomous agents 24/7 at miaoquai.com experienced a cascade failure where one agent going down took the entire pipeline. Resolution: isolated agent sessions with their own sandboxes + MEMORY.md shared state. 95+ days of continuous operation post-fix. — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **Engineering blog (failure taxonomy):** Agentic AI systems have five dominant failure modes: (1) tool parameter hallucination, (2) infinite loops, (3) contradictory outputs within a single task, (4) cost overruns from retry storms, (5) cascade failures from shared dependencies. Asynq.ai and Modelia.ai teams documented each from production. — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Open-source MCP server:** agent-guard-mcp provides reusable circuit breakers, pattern detection, and stuck-agent analysis via the Model Context Protocol, implementing loop detection as a production-ready tool rather than custom code. — [github.com/mdfifty50-boop/agent-guard-mcp](https://github.com/mdfifty50-boop/agent-guard-mcp)
- **Engineering blog (idempotency pattern):** Blind retries on write operations (timeouts after commit) cause duplicate side effects. Production pattern uses intent-keyed idempotency with DB primary-key constraints and cached results. — [cordum.io/blog/ai-agent-idempotency-keys](https://cordum.io/blog/ai-agent-idempotency-keys)
- **Academic taxonomy:** Multi-Agent System Failure Taxonomy (MASFT) classifies 18 distinct failure modes in LLM-based multi-agent systems. — [OpenReview — Why Do Multiagent Systems Fail?](https://openreview.net/forum?id=wM521FqPvI)

## Gotchas

- **Counting tool calls is necessary but not sufficient.** Simple iteration counters catch exact repetition. They miss near-identical loops, semantic drift, and behavioral loops where the agent is busy but not progressing. All four loop types need distinct detection strategies.
- **Exponential backoff without a ceiling is a budget disaster.** Every team that skips the cap ("just a few more retries") discovers the ceiling when they get the API bill. Set a hard cap and alert before hitting it.
- **Restarting from scratch after failure is not resilience — it's gambling.** The "just rerun the agent" approach works until it doesn't: when a task takes 4 hours and fails at step 47, "restart from step 1" is not a recovery strategy.
- **Silent failures are worse than loud ones.** An agent that crashes visibly gets fixed. An agent that returns plausible-but-wrong output at 2am has already caused damage. Build automated validation gates at output boundaries, not just at tool call boundaries.
- **Circuit breaker thresholds are workload-specific.** The same threshold (e.g., 3 failures) that is too aggressive for a high-volume, low-stakes task is too lenient for a financial transaction pipeline. Calibrate based on actual error rates and business impact.
