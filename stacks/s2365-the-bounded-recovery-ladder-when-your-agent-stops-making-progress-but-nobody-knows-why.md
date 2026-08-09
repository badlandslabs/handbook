# S-2365 · The Bounded Recovery Ladder

When your agent has retried the same failing tool 12 times, spent $40 in API credits, and is still nowhere — and there's no gate between "try again" and "keep trying forever."

## Forces
- 86% of agent failures are recoverable (industry research, per The Operator Collective, March 2026), but only 14% of enterprise agentic implementations are production-ready. The gap is recovery infrastructure, not model quality.
- Traditional `try/catch` doesn't cover agentic failures: a tool can return HTTP 200 and still fail semantically (wrong schema, empty result, partial write). The agent doesn't know it failed.
- Iteration caps (`max_iterations`) prevent infinite loops but also kill agents that are making slow-but-real progress. They treat a productive 20-step agent identically to a broken one calling `search("weather NYC")` 20 times.
- Retry logic assumes idempotent steps — but a research pipeline that half-writes a database is not idempotent. Retrying without knowing the state produces corruption, not recovery.
- The failure taxonomy has at least 6 distinct shapes, each demanding a different recovery move. A flat "retry 3 times" policy addresses none of them well.

## The move

Build a **bounded recovery ladder** — an explicit, layered escalation path where each rung costs more and is reached less frequently. Detection is separate from recovery: cheap fixes for repeaters, heavy moves for wanderers.

**Layer 0 — Instrumentation (always running):**
- Log every tool call as `(tool_name, serialized_args, result_hash)` — not just count, but content. Same tool + same args = a potential loop signal.
- Attach a **progress metric** that only increments on real work (tests passed, files created, verified sources gathered). Activity proxies (API call counts, log volume) rise during stuck loops too — they can't distinguish stuck from productive.
- Attach a **semantic verifier** to critical tool outputs: a smaller, faster model checks "does this output actually answer the query?" Returns HTTP 200 but empty array → failure, not success. Pydantic validation alone misses this; schema validation catches type errors, not meaning errors.

**Ladder rung 1 — Retry with exponential backoff + jitter:**
- Classify the error first: transient (rate limit, timeout) vs. terminal (invalid args, missing tool). Transients get retry; terminals don't.
- Add idempotency keys to write operations so retries are safe. If a write lacks an idempotency key and isn't read-safe, skip the retry — the risk of duplicates or overwrites exceeds the recovery value.
- Cap retries at 2–3 with exponential backoff and jitter. Do not let retries compound into runaway cost.

**Ladder rung 2 — Self-correction loop:**
- Surface a structured error message to the model, not just a raw exception. "Tool `search_api` returned 429 rate limit after 2 retries" gives the model enough context to try a different query formulation or wait.
- Reflexion pattern: after a failure, the agent writes a brief "failure note" to a dedicated memory store before retrying. Subsequent attempts read this memory and avoid the previously-failed approach.
- Bounded to 1–2 self-correction attempts. A model that fails to self-correct once will typically fail 10 more times.

**Ladder rung 3 — State rollback to last checkpoint:**
- If the workflow supports checkpointing (LangGraph persistence, custom state snapshots), roll back to the last verified-good state on repeated failure. Don't retry from the corrupted mid-state.
- This requires idempotent step design upfront — steps that can be safely re-entered from a checkpoint.

**Ladder rung 4 — Escalation to human:**
- Trigger when: repeated self-correction fails, confidence score drops below a threshold, a high-risk action (write, delete, payment) fails, or a maximum retry budget is exhausted.
- Send structured context to the human: what was attempted, what failed, what the agent's last good state was, what it was trying to accomplish.
- Route via Slack, email, or a ticketing system. Do not route to a generic inbox — the escalation must be actionable.

**Ladder cap — Stop unconditionally:**
- Set a hard token budget and a hard time budget per task. When either is exhausted, stop. Agents that burn through budgets and produce nothing cost more than agents that stop cleanly.
- The stop must produce a structured artifact: what was completed, what failed, what partial state exists. Don't just return "failed."

## Evidence
- **GitHub Discussion:** LangChain agents calling the same tool with identical arguments in an infinite loop — the recommended fix is tracking `(tool_name, args_hash)` pairs and triggering loop detection when the same pair repeats N times within a window. `max_iterations` alone cannot distinguish this from productive repeated calls. — [github.com/bmdhodl/agent47/discussions/107](https://github.com/bmdhodl/agent47/discussions/107)
- **Engineering Blog:** A LangGraph data ingestion agent silently stopped processing when a vendor API changed from populated arrays to empty arrays — HTTP 200, Pydantic validation passed, zero records processed. Recovery required adding a semantic verifier agent (smaller model) to validate output quality before proceeding. — [agentreviews.dev](https://agentreviews.dev/blog/ai-agent-failure-recovery-strategies)
- **Open-source library:** The `agent-tool-resilience` library (KorahStone, Feb 2026) implements the full stack: exponential backoff with jitter, per-tool circuit breakers, fallback models, and result validation — all as composable decorators wrapping tool calls. — [github.com/KorahStone/agent-tool-resilience](https://github.com/KorahStone/agent-tool-resilience)
- **Architecture reference:** Agentic AI error taxonomy distinguishes transient, client, and semantic errors; the recovery pattern differs for each. Hallucinated tools (model calls a non-existent function) require different handling than rate limits. — [github.com/ombharatiya/ai-system-design-guide](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)
- **Market data:** 62% of enterprises experimenting with agentic AI (McKinsey, late-2025) but only 14% production-ready. Gartner predicts 40%+ of agentic projects cancelled by 2027 — primarily due to failure handling gaps, not model capability. — [The Operator Collective](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)

## Gotchas
- **Don't retry write operations without idempotency keys.** A failed database insert retried without a unique key produces duplicates, not recovery. Design idempotency into the tool contract, not the retry logic.
- **Activity ≠ progress.** A stuck loop generates as much log volume and API calls as a productive one. Only increment a progress metric on verified work output — not on tool calls.
- **Structured errors beat raw exceptions.** Throwing a raw exception to the model loses context (what was attempted, what the downstream system said, what's already been done). Wrap tool errors in structured messages before surfacing them.
- **Circuit breakers belong on tool calls, not LLM calls.** LLM failures are typically transient and benefit from retry. Tool failures (API down, rate limit hit) can cascade — open the circuit after N failures and route to a fallback.
- **The verifier is not the executor.** A semantic verifier checking "does this output answer the query?" runs on a smaller, faster model than the main agent. Don't make the verifier do the agent's work — keep it to a single question.
