# S-1711 · The Silent Failure Stack — When Your Agent Returns 200 OK and the Wrong Answer

Your agent just finished a complex multi-step task. It returned a clean `200 OK`. Your monitoring dashboard is green. Three hours later a customer notices the agent reported `$16.3B` in revenue when the tool output clearly showed `$26.97B`. The agent never crashed. It never flagged an error. It was silently, confidently wrong — and by the time you noticed, the bad output had propagated through three downstream systems.

Traditional error handling assumes failures look like exceptions. Agentic AI breaks that assumption. Agents fail silently, non-deterministically, and catastrophically through cascades. The stack that actually survives production treats every layer as a potential failure point.

## Forces

- **The 200-OK trap** — agents return HTTP 200 while producing fundamentally wrong outputs; your monitoring never alerts on correct-looking failures
- **Cascade geometry** — one bad step in a 10-step pipeline doesn't fail fast; it propagates garbage forward and compounds errors with each tool call
- **Non-deterministic blast radius** — the same agent run produces different failure modes on different inputs; a failure that didn't bite today will bite tomorrow on Unicode input
- **The agent doesn't know it failed** — semantic errors (hallucinated tool outputs, miscombined facts, wrong objectives) return no exception; only structured validation catches them
- **Retry storms** — naive retry logic on rate-limited or degraded services compounds the problem into a thundering-herd outage

## The Move

Build a layered failure architecture where every tier catches a different failure mode, and recovery is always cheaper than forward progress.

**Layer 1 — Error taxonomy before strategy.** Agent failures split into four distinct types, each demanding a different recovery approach:

| Failure type | What it looks like | Recovery |
|---|---|---|
| **Transient** | Rate limit (429), timeout, 503 | Retry with exponential backoff + jitter |
| **Tool** | Missing tool, wrong arguments, malformed output | Fallback chain to alternative tool |
| **Semantic** | Hallucinated tool output, miscombined facts | Validation layer (LLM-as-judge, NeMo Guardrails output rails) |
| **Cascade** | Agent A fails → pipeline compounds → full outage | Isolation + checkpoint + halt |

**Layer 2 — State checkpointing with rollback.** Long-running multi-step agents must checkpoint progress to durable storage (not memory):

```python
from langgraph.checkpoint.sqlite import SqliteSaver

memory = SqliteSaver.from_conn_string(DATABASE_URL)
workflow = agent_graph.compile(checkpointer=memory)
# Resume: pass same thread_id
config = {"configurable": {"thread_id": "task-abc-123"}}
result = workflow.invoke({"input": task}, config)
```

Checkpoint every "super-step" (one logical operation, not one tool call), include SHA-256 hashes of all state components, and keep the last 5 checkpoints per task. Verify checkpoint integrity at write time — catch corruption immediately rather than during recovery. When a cascade failure hits, replay from the last verified checkpoint instead of re-running from scratch.

**Layer 3 — Idempotency gates on every side effect.** This is the pattern that separates teams who've had a 2 AM incident from teams who haven't:

- Every state-mutating operation gets an idempotency key
- Before executing (POST, write, send), check "already done" guard
- Transaction log of completed operations; replay skips completed entries
- Example: cron job that posts to Slack gets an `idempotency_key = f"discord-post-{date}-{content_hash}"`; the second concurrent attempt sees the key exists and skips

**Layer 4 — Structured fallback chains.** Don't retry the same failing approach indefinitely:

```python
circuit_breakers = {
    "openai": CircuitBreaker(failure_threshold=5, timeout=60),
    "anthropic": CircuitBreaker(failure_threshold=5, timeout=60),
}

def call_model(prompt):
    for provider in ["openai", "anthropic", "local"]:
        if circuit_breakers[provider].is_open:
            continue
        try:
            return providers[provider].generate(prompt)
        except (RateLimitError, TimeoutError) as e:
            circuit_breakers[provider].record_failure()
            continue
    raise AllProvidersExhausted()
```

**Layer 5 — Uncertainty thresholds and governed escalation.** An agent that doesn't know when to stop is an expensive random number generator. Define explicit confidence thresholds: if the agent's self-reported confidence falls below threshold X, or if the same tool has been called more than N times for the same sub-task, halt and escalate. Escalation is asynchronous-first — use durable state queues with idempotency keys so gateway timeouts and token expiry don't leave actions mid-flight. Teams running 24/7 agents report that 2/3 of escalations are resolvable by a "Senior Agent" (a more capable model reviewing the situation) rather than a human.

## Evidence

- **HN Ask thread (2025):** harperlabs posted a reliability audit framework after observing 7 consistent failure modes across deployments: hallucination under unexpected inputs, edge case collapse (null values, Unicode names like O'Brien or José), loop detection failures, and cascade propagation. Top comments identified the biggest gap: teams test happy paths obsessively and discover failure modes only in production. — [HN discussion](https://news.ycombinator.com/item?id=47325105)

- **GitHub Discussion / Anthropic SDK (April 2026):** A team running 5 autonomous agents 24/7 for 95 days described their "real war story": a cron job hitting a network timeout, retrying, triggering a retry storm, and posting 50 duplicate Discord messages at 22:05. Their fix was idempotency keys plus "already posted" guards. Another contributor described session-based checkpoints every N messages with a shared MEMORY.md file that lets agents replay from the last verified state on cascade failure. — [GitHub Discussion #1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

- **Vectara awesome-agent-failures repo (May 2026):** Community-curated taxonomy of agent failure modes with specific examples. Key entries: *Tool hallucination* (RAG tool returns hallucinated content → agent builds on false premise), *Response hallucination* (tool outputs $26.97B revenue → agent states "$16.3B"), *Goal drift* (user asks for Paris itinerary → agent optimizes for French Riviera instead). — [GitHub: vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)

- **TableFlow engineering post (July 2025):** CTO Eric Ciminelli describes achieving 99.9% reliability through layered retry logic, exponential backoff, and cost-aware error management across multiple LLM providers. Their approach uses a provider fallback chain so a single degraded service doesn't cause an outage. — [TableFlow blog](https://tableflow.com/blog/handling-llm-challenges)

## Gotchas

- **Naive retry without backoff amplifies outages.** A rate-limited service that gets 100 immediate retry requests will stay rate-limited. Always add jitter (`random(0, base * 2^attempt) * 0.7` to `* 1.3`) and a cap.
- **Checkpoint without validation is dangerous.** A corrupted checkpoint is worse than no checkpoint — the agent will silently restore garbage state. Always verify SHA-256 hashes at read time and immediately at write time.
- **Max-step limits are not a substitute for loop detection.** Setting `max_steps=50` stops infinite loops but doesn't tell you *why* the agent is looping. Combine with a reasoning audit trail so you can diagnose whether the loop is caused by a tool returning empty results, a guard condition that never triggers, or a model that keeps re-attempting the same failed approach.
- **Silent failures compound exponentially.** A wrong number at step 3 of a 10-step pipeline looks correct by step 10 because subsequent steps are internally consistent with the wrong premise. Only step-by-step semantic validation catches this early — end-state validation arrives too late.
- **Escalation queues must be durable.** If your escalation mechanism relies on a synchronous gateway confirmation, a token expiry or timeout mid-escalation leaves the system in a half-escalated state. Use persistent queues (Redis, Postgres) with idempotency keys for all escalation paths.
