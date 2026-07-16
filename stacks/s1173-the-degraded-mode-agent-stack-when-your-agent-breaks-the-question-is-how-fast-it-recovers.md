# S-1173 · The Degraded-Mode Agent Stack

When an LLM API returns a 429, a tool call times out at 90 seconds, or an agent wanders into a loop — you need a plan before it happens, not after.

## Forces

- LLM failures are probabilistic, not clean: no exception thrown, just a hanging request or a malformed JSON tool call
- The happy path always works; the first production incident reveals every assumption you skipped
- An agent that errors out completely serves zero users; one that degrades gracefully still serves most
- Agents drift — constraint adherence degrades over long chains, not just at step boundaries
- A loop that never stops costs money and can cascade into downstream failures

## The Move

Design for graceful degradation from the start. Every agent action needs a failure budget, a tiered fallback chain, and a defined stop condition.

### Classify failure types before choosing a response

Not all failures deserve retries:

- **Transient** (rate limit, timeout, brief API glitch) → retry with backoff
- **Capability** (model doesn't know how, context exhausted) → switch model or simplify task
- **Structural** (wrong tool called, malformed output) → rewrite the tool call, don't re-run the same one
- **Environmental** (external API down, DB locked) → switch to cached response, degraded mode, or escalate

### Build a tiered fallback chain per action type

Internal draft generation can tolerate ambiguity. Customer emails, CRM writes, and money movement cannot. Map every agent action to a fallback tier:

1. Retry with modified parameters (exponential backoff, jitter)
2. Switch to a smaller/faster model for this step only
3. Return a cached or templated response
4. Skip optional substeps, complete the mandatory path
5. Queue for human review and continue
6. Fail closed (do nothing, log, alert)

### Add explicit stop conditions, not just timeouts

Agents without stop conditions loop indefinitely. Every workflow needs:

- A maximum step count (e.g., "halt after 3 failed retrieval attempts")
- A cost ceiling (e.g., "stop this workflow class after $2 in API spend")
- A latency budget (e.g., "escalate if total runtime exceeds 90 seconds")
- A pattern detector: track recent tool calls and halt if the same call returns the same result three times in a row

### Implement checkpointing for long-running tasks

Save operational state at defined intervals: memory contents, conversation history, progress markers, intermediate computations. On failure, resume from the last checkpoint rather than restarting. A document analysis agent that times out at minute 58 of a 60-minute task should resume where it left off — not start over.

### Place human checkpoints at risk boundaries

Four patterns, in order of throughput impact:

- **Escalation-triggered**: agent runs autonomously until a guardrail fires (cost breach, repeated failure, high-risk action), then pauses for human decision
- **Approval-gate**: agent proposes, human approves — use for decision-support tools, not autonomous agents
- **Sampling-based**: random or risk-stratified post-execution review for audit and drift detection
- **Shadow mode**: new agent runs in parallel to a human, compares outputs, escalates on divergence

Escalation-triggered is the production sweet spot: preserves autonomy for the 95% that go fine, catches the 5% that don't.

### Treat loops as a failure mode, not an edge case

Circular dependencies — where Agent A calls Agent B, which calls Agent A — are common in multi-agent systems. Detect and break them with step-count guards and result-deduplication checks. A 2025 post-mortem on a Cloudflare Durable Object loop accumulated $34,895 in charges over 8 days with zero users, purely from unchecked self-wake loops.

## Evidence

- **HN Ask HN discussion (2025):** Practitioners report agents "drift fast" — internal state can't be trusted over long chains, and constraint adherence degrades as chains lengthen, not gradually but correlated with constraint tension. Recommended fixes include step limits, resource checks, and explicit enforcement layers. — [HN #47039354](https://news.ycombinator.com/item?id=47039354)
- **Zylos Research (2026):** Documents the layered resilience model converging across production systems: circuit breakers, fallback chains, context compaction, and bulkhead isolation — each adapted specifically for non-deterministic LLM failures (rate limits, malformed JSON, slow 60–120s timeouts). — [Zylos Research](https://zylos.ai/research/2026-05-30-graceful-degradation-patterns-ai-agent-systems)
- **AgentixForce blog (2026):** A customer support agent using a mid-tier model during outage resolves ~70% of queries correctly; one that errors out resolves 0%. A 30-minute outage with graceful degradation means hundreds of customers served vs. hundreds frustrated. — [AgentixForce](https://agentixforce.ai/blog/graceful-degradation-strategies-agents)

## Gotchas

- **Timeout ≠ failure:** LLM requests hang 60–120s before timing out. Set your retry budgets accordingly, not based on a naive "try once and give up" model
- **Backoff alone isn't enough:** Exponential backoff with jitter prevents thundering herd, but you still need to distinguish permanent from transient failures — otherwise a content policy rejection just wastes retries
- **Degradation is NOT appropriate for medical, legal, or financial trading decisions** — reduced-capability outputs in these domains are worse than no output; fail closed instead
- **Testing degradation paths is different from testing the happy path:** You need chaos engineering–style tests — block the primary model, drain the cache, inject tool failures — and verify the agent falls through correctly at each tier
- **Context window overflow is a silent failure:** The agent doesn't crash; it just starts dropping earlier context. Implement context compaction or summarization proactively, not when the error surfaces
