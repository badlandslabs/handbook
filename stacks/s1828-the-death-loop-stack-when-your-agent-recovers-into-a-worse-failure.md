# S-1828 · The Death Loop Stack — When Your Agent Recovers Into a Worse Failure

Your agent hits a rate limit. It retries — same call, same error. Retries again. By the time you notice, it has burned through $1,500 in API credits on a single stuck task, produced nothing, and locked up the queue. This is not a model failure. It is an architecture failure: the retry contract was never defined, the circuit breaker was never installed, and the escalation path was never written. The death loop stack fixes all three.

## Forces

- **Probabilistic retry logic.** LLMs are trained on next-token prediction, not retry semantics. When a tool fails, the model's next step gravitates back to the same action — the one that "almost worked." Without structural intervention, retry loops are the default outcome, not the exception.
- **Retries amplify outages.** A cascading failure with naive retry can turn a 10-minute dependency outage into platform-wide queue pressure. 500 jobs/min × 3 extra attempts × 10 minutes = 15,000 avoidable API calls.
- **Silent quality failures don't look like failures.** 40%+ of agent failures arrive with HTTP 200 and a confident tone. A tool call succeeds but returns semantically wrong data. An agent approves an obviously flawed result because it optimized for completion, not quality.
- **Checkpoint granularity vs. recovery speed.** Fine-grained checkpoints give precise recovery but cost storage and slow resume. Coarse checkpoints are fast but re-do significant work on failure.

## The move

Design a **layered failure architecture** before the first tool call. The three layers stack — each addresses a different failure class, and each must be explicit, bounded, and observable.

**Layer 1 — Bounded retry with exponential backoff + jitter:**
- Set `max_attempts` per node, not globally. A search node gets 2 attempts. An API write node gets 1.
- Never retry deterministic failures (401 auth, 404 not found, 422 bad request). Only retry transient failures (429 rate limit, 500 server error, timeout).
- Add jitter to retry delays so concurrent failures don't thundering-herd onto the same backoff window.
- Never let retry delay exceed a hard ceiling — agents will stall waiting for a backoff that never resolves.

**Layer 2 — Fallback chain for provider-level failures:**
- Design tool calls as provider-agnostic where possible. If the primary LLM fails, route to a secondary model. If a search API fails, fall back to a cached result or a different provider.
- The fallback chain is a **directed acyclic graph**, not a linear sequence — model → model → cached → human, with branching based on error type.
- Multi-provider fallback reduces outage risk: "60% of LLM API errors are rate limits" (ValuestreamAI, Feb 2026), not model outages.

**Layer 3 — Circuit breaker at the provider and workflow level:**
- Trip the breaker when error rate exceeds a threshold (e.g., Cordum opens at 3 consecutive failures for 30 seconds on the safety-client).
- Share circuit state via Redis so multiple agent instances stay synchronized.
- Configure explicit fail modes: `closed` (default — requeue) vs `open` (allow through with bypass signal). The fail mode is a governance decision, not a technical one.
- Breaker must monitor four dimensions: same tool + same params (loop detection), same error type (cascading failure), token burn rate (cost explosion), and context window velocity (memory pressure).

**Checkpoint + interrupt for long-running workflows:**
- LangGraph's checkpointer saves state after each node. On crash, the graph resumes from the last checkpoint — not from scratch.
- Place `interrupt()` before high-stakes nodes (writes, approvals, external calls). The graph pauses and awaits `Command(resume=...)` from a human or downstream process.
- Recovery granularity is determined by checkpoint frequency: every node gives precise recovery, every N steps trades precision for speed.
- The checkpointer must be durable (PostgresSaver with ACID guarantees, not SQLite for production).

**Verification gates and bounded autonomy:**
- Every tool call result gets a validation gate before the agent acts on it. VIGIL (ACL 2026) intercepts tool responses before passing them to the agent — catching injection and parameter errors in <2ms.
- Structured reflection loops: OuroLoop (GitHub, 2026) implements 5 verification gates and 3-layer self-reflection before autonomous remediation. Without structured gates, "reflection" devolves into the agent re-confirming its wrong conclusion.
- Set hard budgets: max total tool calls per session, max total cost per run, max context window fill percentage. When a budget triggers, the agent must escalate — not attempt one more call.

## Evidence

- **LangGraph fault tolerance docs:** Per-node `RetryPolicy(max_attempts=3)` with configurable `retry_on` exception types. Error handlers run after all retries are exhausted. Timeout wraps individual node execution — the entire node gets one timeout budget, not per-call. — https://docs.langchain.com/oss/python/langgraph/fault-tolerance
- **Cordum production circuit breaker:** "At 500 jobs per minute, three extra attempts per job adds 15,000 avoidable calls over 10 minutes." Safety-client breaker opens at 3 failures for 30 seconds, shared state via Redis. Fail modes: `POLICY_CHECK_FAIL_MODE=closed` requeues, `open` allows through with bypass signals. — https://cordum.io/blog/ai-agent-circuit-breaker-pattern
- **HN — LangGraph research automation:** "We always put a human in the loop checkpoint after each critical step, might be annoying now but I think it will save us long-term." ( commenter on HN thread about LangGraph production deployments, 2025) — https://news.ycombinator.com/item?id=46734370
- **LambdaFlux loop taxonomy:** Three loop patterns — Tool Hammering (same tool + same params), Logic Shuffling (alternating tools without refining), and Hallucination spirals (agent invents new parameters each loop). Each requires a different intervention. — https://lambdaflux.substack.com/p/the-ai-engineers-guide-to-agentic
- **Living AI — crash recovery runtime:** Open-source production runtime for LangGraph, CrewAI, and OpenAI Agents that adds crash recovery, time-travel replay, and execution history across frameworks. — https://github.com/likkisamarthreddy/livingai

## Gotchas

- **Retry storm masquerading as resilience.** Adding retry logic without a circuit breaker amplifies cascading failures. The breaker must trip before retry pressure overwhelms the recovering dependency. Retries + breakers is the combination, not retries instead of breakers.
- **Checkpointing unvalidated state.** If you checkpoint after a node that returned a wrong answer, you resume from a wrong answer. The checkpoint captures state, not correctness. Pair checkpoints with validation gates — validate the output before checkpointing.
- **interrupt() without a resumption plan.** Pausing the graph without a defined consumer for the `Command(resume=...)` call leaves the workflow orphaned. The interrupt point is coupled to a human review queue, a webhook, or a downstream process that will actually resume the graph.
- **Hard-coding max_retries as a magic number.** The right retry budget depends on the operation type — reads are idempotent and cheap, writes are dangerous and expensive. Treat retry policy as a per-node configuration, not a global constant.
- **Silent quality failures pass through all three layers.** HTTP 200, valid JSON, confident tone. The breaker doesn't trip. The retry doesn't fire. The agent acts on the wrong data. This requires L4/L5 observability (output quality monitors, semantic validators) that most teams don't build until after their first incident.
