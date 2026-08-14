# S-2638 · The Recovery Pipeline Stack — When Step 8 of 11 Fails and Steps 1–7 Are Gone

[When an 11-step agent pipeline breaks at step 8 — a rate limit, a malformed tool response, a timeout — and the entire workflow rolls back to zero. No partial results, no resume point, no recoverable state. The agent didn't crash. It just... lost everything. That's the cascading failure problem, and the fix is a layered recovery architecture that treats failure as an architectural concern, not an afterthought.]

## Forces

- **Cascading failure compounds reliability.** A 98% per-step success rate sounds fine until you chain 5 agents sequentially: that's ~90% end-to-end reliability, and every step failure erases all previous work. Without checkpointing, the cost of failure grows with progress.
- **Agents fail without raising exceptions.** They return confident, plausible outputs that pass downstream parsing and corrupt the execution chain silently. The system keeps running — which is worse than crashing.
- **Standard retry patterns break on AI.** Classic "retry 3x with fixed backoff" creates thundering-herd problems when hundreds of agents simultaneously retry after an outage, and doesn't account for non-transient failures that just waste budget.
- **Dead-letter queues are underused.** Most agent frameworks have no concept of "this task exhausted its recovery options" — failed tasks disappear into logs instead of surfacing for human review.

## The Move

Build a **layered defense architecture** where each layer handles a different failure class, and failures that survive all layers land in a human-review queue instead of disappearing.

### Layer 1: Retry with Exponential Backoff + Jitter

Handle transient failures — rate limits (429), timeouts, momentary network blips. The standard approach from 2025–2026 production deployments:

- Exponential backoff: `delay = min(base × 2^attempt + random(0, jitter), max_delay)`
- Typical config: base=1s, max=60s, jitter=30%, max_retries=5
- Jitter is non-negotiable — it spreads retries across time and prevents the thundering-herd problem where all agents hammer the API simultaneously after an outage
- Distinguish transient from permanent failures: retry only on 429/503/timeouts; fail fast on 400/bad input

### Layer 2: Circuit Breakers — Stop Hammering What's Already Broken

After N consecutive failures on a dependency, stop calling it entirely and fail fast. Three states:

- **Closed** (normal): requests pass through; failures increment a counter
- **Open** (tripped): after 5 consecutive failures, return immediately with a fallback or error — no more wasted calls
- **Half-open**: after a cooldown period (e.g., 30s), allow one probe request; if it succeeds, close the circuit; if it fails, reopen it
- Each dependency needs its own circuit breaker — one flaky MCP server shouldn't trip your entire agent
- From AgentWorks team: "Circuit breaker after 5 consecutive failures" became standard after an MCP server broke silently for 3 days

### Layer 3: Model Fallback Chain

When the primary model fails or degrades, fall through to the next tier without human intervention:

- Design the chain explicitly: e.g., Claude Opus → Claude Sonnet → Claude Haiku → queue for later retry
- Latency and cost increase at each tier — that's intentional; degraded output is better than no output
- Make fallback quality degradation visible in logs: flag when the agent is running on a lower-tier model
- Teams learned this during the November 2025 outage when the primary model went down and fallback chains kept agents running

### Layer 4: Dead Letter Queue (DLQ) — Capture What Exhausted Recovery

Tasks that survive all retry and fallback layers land here instead of vanishing:

- DLQ holds: task ID, failure reason, step number, all intermediate outputs, retry count, timestamp
- Two DLQ types in production: a **retry queue** (exponential backoff, requeue for later) and a **human-review queue** (flag for human inspection)
- From Brandon Lincoln Hendricks (Autonomous AI Agent Architect, systems processing 50,000+ tasks/hour): DLQ design as state machine — primary → retry queue (backoff) → DLQ → human review → resolution
- DLQ is where silent failure becomes visible: surface DLQ depth as an ops metric, alert on spikes

### Layer 5: State Checkpointing — Resume from Step 8, Not Step 1

The highest-impact and most-neglected layer:

- Persist agent state after each successful step: completed outputs, current context, next action
- On failure, resume from the last checkpoint instead of replaying everything
- Implementation: serializable state snapshots to object storage or a state DB; on resume, hydrate the agent context and restart from the checkpoint step
- Particularly critical for multi-step pipelines: a 2-minute failure at step 8 with checkpointing costs 2 minutes; without it, steps 1–7 replay, burning budget and time
- Combine with idempotency keys on tool calls so replaying a step doesn't cause duplicate side effects (e.g., don't charge a credit card twice)

### Layer 6: Human-in-the-Loop Escalation — Escalate Before Cost or Quality Compounds

For high-stakes or ambiguous failures:

- Trigger escalation when: confidence below threshold, failure persists across all recovery layers, or the task involves destructive operations
- Present the human reviewer with: failure reason, partial outputs, retry count, next proposed action
- Allow manual override or approval at key checkpoints — particularly for agents making financial decisions, deployments, or data modifications
- From AgentReviews: "Build recovery into the agent's DNA. This isn't about better prompts; it's about architectural decisions."

## Evidence

- **Engineering post (Harsh Rastogi, Modelia.ai/Asynq.ai, March 2026):** Documented 5 production failure modes — tool parameter hallucination, goal drift, retry loops, cascading errors, silent quality degradation — and the layered recovery architecture that addresses each. Their candidate evaluation agent burned 3x its budget before they added input validation at Layer 1.
- **Engineering post (Brandon Lincoln Hendricks, March 2026):** DLQ architecture for production AI agents processing 50,000+ tasks/hour on Google Cloud infrastructure. Specific implementation: Cloud Pub/Sub → Cloud Tasks (exponential backoff retry) → Dead letter topic → Human review. Emphasizes that AI DLQ design differs from traditional software DLQ because task state must be preserved for meaningful human review.
- **Systems analysis (Supergood Solutions, March 2026):** "A 98% per-agent success rate across five sequential agents produces only ~90% end-to-end reliability without fault tolerance." Quantifies the compounding failure problem and recommends the four core patterns: exponential backoff + jitter, circuit breakers, dead letter queues, idempotent actions.

## Gotchas

- **Don't retry non-transient failures.** Retrying a 400 Bad Request or a model that is genuinely down wastes budget and delays failure visibility. Classify errors by type before deciding to retry.
- **Circuit breakers need per-dependency tuning.** A circuit breaker on "all external calls" is useless — one broken tool shouldn't trip the breaker for all other tools. Each tool, API, and model gets its own breaker with thresholds tuned to its SLA.
- **Checkpointing without idempotency causes double-effects.** If step 7 of your pipeline sends an email, replaying step 7 after a failure at step 8 sends two emails. Stamp every action with an idempotency key and check it before executing.
- **DLQ depth is a vanity metric without triage.** A DLQ that fills up with 10,000 tasks and nobody reviews is just a more expensive place to store failures. Set SLOs on DLQ resolution time, not just DLQ existence.
- **Jitter is not optional.** Fixed backoff without jitter creates synchronized retry storms. Always add randomness — typically 20–30% of the current delay value.

---

*Research phase: Failure handling / recovery patterns. Primary sources: HN discussions (447-point thread on agent loops), Modelia.ai/Asynq.ai engineering post, Supergood Solutions systems analysis, Brandon Lincoln Hendricks DLQ architecture, AgentWorks resilience patterns, Zylos Research error taxonomy, AgentReviews failure recovery methods. August 2026.*
