# S-837 · The Agent Failure Recovery Stack — When Silent Stalls Cost More Than Crashes

An agent in production that loops forever or stalls silently is worse than one that crashes loudly. A crash alerts you. A stalled agent burns tokens, acquires locks, and produces nothing — and you may not notice for hours. This stack is for when you need agents that survive failure gracefully, resume from checkpoints, and escalate rather than loop.

## Forces

- **Agents fail non-deterministically.** A retry does not guarantee the same output, and a tool call with side effects cannot be blindly re-executed. Standard software retry logic breaks down. (Preporato, NCP-AAI, 2026)
- **Process monitoring misses logical stalls.** CPU and memory are fine. The process is alive. But the agent has been running the same three tool calls for 47 minutes with no progress. (Antigravity Lab, 2026-05-29)
- **Fallback chains have single points of failure.** Teams add a fallback provider thinking it solves resilience — but if the fallback itself is a single-threaded choke point, one API outage takes down the whole pipeline. (Riversea Lab, 2026-06-01)
- **Cascading failure is the default.** A rate limit at step 3 of 8 throws an uncaught exception. Without checkpointing, you lose steps 1–2 and restart from zero — or worse, leave the system in an undefined state. (AI Agents Blog, 2026-03-05)
- **Retry semantics are step-level, not agent-level.** Retrying the whole agent re-runs everything, including steps that already succeeded. The minimal retriable unit is the individual step. (Let's Build Solutions, 2026-03-31)

## The Move

Implement a layered failure recovery architecture: hard budget guards, checkpoint/resume, tiered recovery escalation, and provider fallback chains. Each layer catches a different failure mode. Combined, they make silent stalls unreachable.

### 1. Hard Iteration Budgets First

Before tuning prompts, set hard limits. A loop that runs 47 steps with no observable progress is a design problem, not a model problem.

- Set `max_steps` (typically 10–30 depending on task complexity) and trap the limit explicitly
- Set `max_retries` per step (2–3 is standard; more invites non-deterministic cascades)
- Set `max_runtime_seconds` as a wall-clock guardrail
- When any budget exhausts, enter a **bounded failure state** — return partial results and flag for human review instead of looping

> *"Repeated tool calls usually signal a workflow-control problem, not just a model problem. Set hard limits on iterations, retries, and runtime before debugging prompts."* (Nerova, 2026-05-21)

### 2. Checkpoint-and-Resume at Step Granularity

The minimal retriable unit is the individual step, not the entire agent run.

- Serialize agent state after each successful step: tool outputs, intermediate results, and the next action to attempt
- On retry, load the last checkpoint and re-execute only from the failed step forward
- Steps with side effects (external API writes, database mutations) must be **idempotent or have compensating rollbacks** — you cannot safely re-run them blindly
- Idempotency keys on mutations allow safe retry without duplicate writes

### 3. Watchdog + Tiered Recovery Escalation

Agents keep running while completely broken. Use a supervisor layer that monitors heartbeat, progress, and loop signatures — not just process aliveness.

Antigravity Lab documented three stall modes across 142 abnormal terminations over 8 weeks:

| Stall Mode | Frequency | Detection Signal |
|---|---|---|
| **LLM unresponsive** | 41% | no response within expected latency window |
| **Logical loop** | 33% | same 2–3 tool calls cycling within N iterations |
| **Context overflow** | 26% | response length drops to near-zero while steps continue |

Recovery escalation tiers (Antigravity Lab pattern):

1. **Re-run** the same agent with tighter constraints (shorter max steps, reduced tool set)
2. **Escalate to supervisor agent** — a parent LLM with broader context that can re-plan from the checkpoint
3. **Hand off to human** with full context — partial state, last checkpoint, failure reason

### 4. Fallback Chains with Circuit Breakers

A fallback provider is not a fallback if it has no fallback of its own.

- Chain: **primary model → secondary model → cached/synthetic answer → human handoff**
- Insert circuit breakers between each hop: after N consecutive failures to provider X, skip directly to the next tier for a cooling period
- Track circuit state in a durable KV store (Redis, DynamoDB) so the breaker state survives restarts
- RiverSea Lab measured a 78% reduction in outage impact (43 minutes → 9 minutes) using KV-persisted circuit breakers, at a cost of $0.40/month in writes

### 5. Surface Failures Explicitly — No Silent Drops

The failure design hierarchy (SaasDash, 2026-06-21):

| Level | Behavior |
|---|---|
| **Best** | Agent gracefully declines — unable to complete, explains why, returns partial result |
| **Acceptable** | Recoverable error with rollback — step failed, state reverted, reason logged |
| **Acceptable** | Recoverable error with restart — checkpoint restored, retry from step N |
| **Bad** | Unhandled exception — partial state, no recovery path |
| **Worst** | Silent stall — process alive, nothing happening, no alert |

Always land in one of the top three. Default to graceful decline over silent continuation.

## Evidence

- **Engineering blog — Antigravity Lab:** 8-week study of 142 abnormal agent terminations on production background agents (AdMob eCPM tuning, Crashlytics triage). Documents three stall modes, watchdog architecture with delegation-loop detection, hallucination checking, and tiered recovery. — [antigravitylab.net](https://antigravitylab.net/en/articles/agents/antigravity-long-running-agent-supervision-architecture)
- **Engineering blog — RiverSea Lab:** Documents fallback chain redesign for a 12-worker multi-agent pipeline. Key finding: fallback provider was single-threaded, making it the actual single point of failure. Metric: 43-minute outage impact reduced to 9 minutes using circuit breakers with KV-persisted state ($0.40/month). — [riversealab.com](https://www.riversealab.com/en/posts/agent-graceful-degradation-fallback)
- **Reference library — Tanay Shah (open source, 2025/2026):** Open-source library implementing 4 production reliability patterns for AI agents with tests: circuit breaker, checkpoint-and-resume, fallback chain, and escalation queue. — [tanayshah.dev](https://tanayshah.dev/projects/ai-agent-error-patterns)
- **Blog post — AI Agents Blog:** Five-pattern guide (exponential backoff, circuit breakers, checkpoint-and-resume, fallback strategies, escalation queues) implemented with Anthropic SDK. — [aiagentsblog.com](https://aiagentsblog.com/blog/agent-error-recovery-patterns)
- **Guide — Let's Build Solutions:** Step-level retry semantics as the core principle — retry the smallest retriable unit, enforce idempotency for side-effectful steps. — [letsbuildsolutions.com](https://letsbuildsolutions.com/blog/ai-ml/ai-agent-reliability-engineering-retry-semantics-fallback-chains-and-graceful-degradation)
- **Research — Zylos Research:** Taxonomy of multi-agent failures: ~42% specification failures, ~37% coordination breakdowns, ~21% verification failures. Circuit breaker and supervisor-tree patterns. — [zylos.ai](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery)
- **Hacker News — Ask HN:** Community discussion on agent limitations in production — rate limits, state management, observability, cost unpredictability, and recovery as the top pain points. — [HN #47039354](https://news.ycombinator.com/item?id=47039354)

## Gotchas

- **Circuit breaker state must be durable.** If you store breaker state in-memory, a restart resets all breakers simultaneously — the storm you're trying to prevent hits the fallback immediately on restart. Persist to Redis/DynamoDB.
- **Hard limits prevent debugging.** Setting `max_steps=5` stops loops but also stops legitimate long tasks. Profile your actual step distribution first, then set the budget at the 95th percentile.
- **Checkpoint size grows.** Serializing full conversation history at every step balloons storage. Checkpoint only the minimal state needed to re-run from that step: last tool outputs, current goal, and the failed-step context.
- **Fallback chains can exceed latency budgets.** Each fallback tier adds latency. If your SLA is 2 seconds and you have 3 fallback hops each taking 500ms, you are already over budget before the last hop. Add timeouts at each tier, not just the final one.
- **Silent failure feels like success.** Agents that fail to complete a task often return a plausible-looking partial result that a human reviewer might approve. Build semantic validation — does the output match the requested action's expected effect? — not just syntax checks.
