# S-880 · The Circuit Breaker Stack — When Your Agent Loops for 35 Minutes and Prints a Smile

Your agent returns HTTP 200. The workflow "completed." Three CRM records were created. The agent called the wrong endpoint each time. The API silently accepted the malformed payloads. Your agent didn't loop — it succeeded at the wrong thing, over and over, until someone noticed the duplicate records. The failure modes that kill agentic systems don't look like failures. They look like success with wrong content.

## Forces

- **Agents fail silently.** Unlike traditional software that crashes with stack traces, an agent may produce a confident wrong answer, loop indefinitely, or spawn redundant subprocesses — all while returning a 200 status code. You have no idea anything is wrong until a user reports it.
- **Reliability compounds poorly across steps.** A 98% success rate per step sounds great. Five sequential agent steps gives you 90% end-to-end reliability. Ten steps gives you 82%. Multi-agent pipelines (41–86.7% failure rate per Galileo 2025 data) amplify this further.
- **Traditional error handling doesn't map.** Catch/throw doesn't catch "the agent reasoned confidently about wrong tool parameters" or "the agent is stuck in a reasoning loop." You need infrastructure-level reliability patterns borrowed from distributed systems.
- **Retry amplifies outages.** Naive retry logic — retry on failure, retry on timeout — without idempotency keys or circuit breakers turns a transient API blip into a thundering-herd cascade.

## The Move

Wrap every agent workflow with a layered fault-tolerance system. Treat failure as an engineering primitive, not an exception.

**1. Three-layer retry with different rules at each layer.** Most agent code retries at one layer and calls it done. Production needs three: (a) **Transport layer** — HTTP retry with exponential backoff + jitter for network failures (AWS Architecture Blog best practice: `wait = min(base * 2^attempt + random_jitter, max_delay)`); (b) **Tool layer** — idempotent tool calls using idempotency keys (Stripe's pattern: include a UUID per logical operation so retries don't duplicate writes); (c) **Model layer** — model cascade fallback (primary model → fast cheap fallback → final degradation response).

**2. Idempotency keys for every write operation.** Never retry a write without one. A non-idempotent retry of a "create CRM record" call will create three records. Generate a stable UUID per logical operation, store it in the request metadata, and have the downstream system deduplicate.

**3. Circuit breakers that open on quality degradation, not just HTTP errors.** Standard circuit breakers trip on 5xx responses. For agents, also trip on: (a) tool-call failure rate above threshold, (b) consecutive self-correction failures (agent keeps failing to correct itself), (c) context exhaustion approaching token limits. Open circuit = fail fast, return degraded response, don't keep spending tokens.

**4. Budget guardrails and step caps.** Hard cap on total steps (e.g., 20 tool calls max per task). Hard cap on total tokens spent per workflow. Budget guardrails alone reduce token waste in complex agent loops by ~40% (ValueStreamAI 2026). These aren't error responses — they're resource governors that prevent runaway agents.

**5. Validation gates before execution.** Don't wait for a tool call to fail. Validate inputs *before* sending them: schema validation on tool arguments, referential integrity checks on IDs/foreign keys, enum range checks. ~70% of hallucinated outputs are caught pre-execution with validation gates (ValueStreamAI 2026). This catches wrong tool parameters (fabricated IDs, invalid enum values, bad date formats) before the API call.

**6. Dead letter queues for unrecoverable failures.** When retries exhaust, don't log and drop. Route to a DLQ with full context: original prompt, agent trajectory, error type, step count at failure. Enables replay, post-mortem analysis, and downstream human review.

**7. Checkpointing for long-running workflows.** Capture a snapshot of agent state at decision points. On failure, restore from checkpoint rather than re-executing from scratch. Critical for workflows that run longer than a single API call cycle. Branch-scoped context keys (e.g., ctxbin's git-inferred keys) enable reliable handoffs between agent sessions without losing state.

**8. Deadlock prevention with supervisor trees.** For multi-agent pipelines, assign a supervisor agent that monitors child agents: detects when a child loops, stalls, or deadlocks, then kills and restarts from the last checkpoint. Don't let agents wait on each other indefinitely.

## Evidence

- **Blog post — Harsh Rastogi (AI Product Engineer at Asynq.ai/Modelia.ai):** "Agentic AI in Production" — documents five concrete failure modes: tool parameter hallucination, infinite loops, contradictory reasoning, multi-agent deadlocks, and budget overruns. Their candidate evaluation agent hallucinated tool parameters in production (not in dev). The fix: validate ALL tool inputs with schema validation AND referential integrity checks before execution. — [harshrastogi.tech](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **Engineering guide — ValueStreamAI (2026):** Production benchmarks showing LLM API error rate is 5% of all spans (60% from rate limits), agent task failure reaches 75% across repeated runs, and multi-agent system failure ranges 41–86.7%. Documents validation gates catching ~70% of hallucinated outputs pre-execution and budget guardrails reducing token waste by 40%. — [valuestreamai.com](https://valuestreamai.com/blog/ai-error-handling-patterns-2026)

- **Show HN — theredsix / Agent Browser Protocol:** Built a forked Chromium (ABP) after finding that most browser-agent failures aren't about model misunderstanding — they're about stale state. After each action (click, type), the browser freezes JavaScript execution and rendering, captures the resulting state, and serves it back to the agent. Achieved 90.5% on Mind2Web benchmark vs standard browser automation. HN commenter confirmed: "The single biggest source of failures is acting on stale screenshots — autocomplete dropdowns, loading spinners, modals that appeared 200ms after the last capture. Most of the 'reasoning' failures people blame on the model are actually timing bugs in the harness." — [HN #47336171](https://news.ycombinator.com/item?id=47336171)

- **Research — Zylos Research (2026-05-06):** Self-healing failure taxonomy: specification failures account for 42% of multi-agent failures, coordination breakdowns for 37%, verification gaps for 21%. Introduces five-stage Agentic SRE cycle: Detection → Diagnosis → Repair → Validation → Adaptation. Synthesizes circuit breakers, supervisor trees, idempotency guards, and graceful degradation strategies. — [zylos.ai](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery)

- **Engineering blog — Gravity (2026-05-27):** "AI Agent Fallback and Retry" playbook documenting three retry layers with different rules. Recommends 10% of normal QPS as the SRE-book default for system-level retry budgets. Cites AWS Architecture Blog (2015) and Stripe API (2024) as canonical references for exponential backoff + jitter and idempotency key patterns. — [gravity.fast](https://gravity.fast/blog/ai-agent-fallback-and-retry)

## Gotchas

- **Don't retry writes without idempotency keys.** This is the #1 way teams silently corrupt data. A "successful" retry that the server accepted but didn't process creates duplicate records, duplicate charges, duplicate tickets — all invisible until someone audits.
- **Circuit breakers that only check HTTP status miss the real failures.** An agent calling a tool with fabricated parameters gets a 200 response — the tool accepted the garbage. Trip breakers on tool-call failure rates, not just HTTP codes. The silent failures are the ones that look like success.
- **Step/step-counting loops are not the same as reasoning loops.** An agent can call the same tool 15 times without being in a loop — it might genuinely be paginating through results. But 15 calls to the same tool in 5 seconds with no state change = loop. Track state change, not just call count.
- **Graceful degradation means returning *something*, not returning nothing.** When a circuit opens or budget exhausts, returning an empty response passes the failure downstream. Return a structured degraded response with what was completed, what failed, and a flag indicating degraded mode so the calling system can handle it.
