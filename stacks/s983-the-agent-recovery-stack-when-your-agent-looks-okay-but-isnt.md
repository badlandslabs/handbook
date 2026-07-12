# S-983 · The Agent Recovery Stack: When Your Agent Looks Okay But Isn't

Your agent returns HTTP 200. The task isn't done. The refund agent just gave away $1.2M. The ticket-router is marking everything "pending." The response looks valid — it isn't. Agentic failures are 200 OKs that are quietly, fundamentally wrong. Loop detection (s979) tells you something is stuck. The recovery stack tells you what to do about it — and it requires a fundamentally different error model than traditional software.

## Forces

- **LLM errors don't throw exceptions.** Hallucinated tool calls, confident nonsense, and semantically wrong JSON all return HTTP 200. Traditional try/catch catches nothing.
- **Failures cascade in multi-step pipelines.** Garbage output from Node A becomes the input to Node B, compounding downstream. One bad step poisons the whole run.
- **Retries without idempotency are dangerous.** Retrying a "give refund" action 3 times costs 3x — and may violate business invariants (no double refunds).
- **The recovery budget is finite.** Every retry burns tokens, API calls, and operator attention. Bounded retry budgets prevent cost explosions, but naive bounds throw away legitimate transient failures.
- **Structural failures won't resolve by retrying.** A hallucinated schema won't fix itself on the 4th attempt. Distinguishing transient from structural failures is the hard part.

## The Move

The recovery stack operates in layers — each addresses a different failure mode in the agent execution graph.

**1. Classify failures before retrying.** Separate transient failures (rate limits, timeouts — resolve on retry) from structural failures (bad schema, hallucinated function names, impossible tasks — will not resolve by retrying). Group exceptions into separate hierarchies and route accordingly. Transient errors get retries. Structural errors escalate immediately.

**2. Wrap each LLM and tool call with its own retry contract.** Do not wrap one generic try/except around the whole run. Each call site gets its own `max_attempts`, `exception_classes`, and `backoff` strategy. Rate limit errors (429) get exponential backoff with jitter. Timeout errors get longer timeouts before retry. Structural parse errors don't retry — they escalate.

**3. Use output validation as a self-healing gate.** Before passing an LLM output downstream, validate it against a schema. If the output is malformed JSON, the validator fails immediately — the agent self-corrects by re-prompting with the error message, rather than propagating garbage. This is safer than setting `output_retries=0` because the validator enables targeted correction rather than blind restart. Use Pydantic models or JSON Schema for structural validation; embed semantic checks (e.g., "did this tool actually produce what was requested?") at higher layers.

**4. Implement circuit breakers for external dependencies.** When an external API is down, a circuit breaker prevents cascading failure by short-circuiting calls to the broken service for a cooldown period. Three states: Closed (normal operation), Open (fail-fast, dependency is down), Half-Open (probe to see if the dependency recovered). This is especially critical for multi-agent systems where one agent's timeout can block a shared resource.

**5. Checkpoint state at recovery boundaries.** Mid-flight interruption — crash at step 9 of 12 — erases all progress without durable execution. For long-running agents, save state (conversation history, intermediate results, tool outputs) to persistent storage (Postgres, DynamoDB) at defined checkpoints. On restart, the agent resumes from the last checkpoint rather than re-executing from step 1. For simple cases, LangGraph's `MemorySaver` works; for production durability, use `PostgresSaver` or move to a durable execution framework like Temporal.

**6. Escalate to human-in-the-loop at decision boundaries.** Some failures cannot be self-corrected: irreversible actions (refunds, deletes, sends), confidence below threshold, repeated structural failures. Define escalation triggers explicitly — not just "on exception" but "on high-stakes action" and "on N consecutive structural failures." The escalation surfaces the full context (what was attempted, what failed, what was produced so far) to a human for a judgment call.

**7. Treat unbounded retry loops as the primary cost risk.** The first failure is recoverable. The expensive part is what happens after — when the system keeps trying, keeps spending, and produces the same outcome because nothing changed. Set per-call retry budgets strictly, implement semantic loop detection (detecting that the agent is attempting the same thing, not just repeating tool calls), and halt with a structured report when the budget is exhausted. The report should include: what was attempted, what failed, what was produced, and what a human needs to know.

## Evidence

- **Incident post-mortem:** A mid-size e-commerce company deployed a customer service agent in Q3 2025 to handle refund requests. Without per-action idempotency guards and output validation, the agent produced multiple refund actions on retry that were each technically valid. Result: $1.2M in erroneous refunds before detection. Post-mortem identified missing action-level idempotency checks and absence of validation gates between the LLM and the refund API. — [Markaicode / AI Agent Disaster Recovery](https://markaicode.com/ai-agent-disaster-recovery-2025)
- **Engineering post-mortem / GitHub tool:** Agent-watchdog (PyPI: `agent-watchdog`, MIT license) implements a circuit breaker for agent runs: loop detection via identical-call and ABAB/ABCABC pattern matching, real-time budget guards in USD, and graceful halts that produce structured reports. Framework-agnostic — works with LangChain, CrewAI, AutoGPT. The creator's thesis: "The frameworks compete on capabilities. The infrastructure for making agents reliable is still building." — [GitHub: woodwater2026/agent-watchdog](https://github.com/woodwater2026/agent-watchdog)
- **Engineering post-mortem / GitHub tool:** ANDON for LLM Agents applies Toyota Production System principles to LLM coding agents. Identifies five structural failure modes: blind retry loops (retry same thing when commands fail), whack-a-mole debugging (fix one error, hit another), volatile learning (debugging knowledge evaporates between sessions), silent spec drift (agents relax requirements to make things pass), and gate gaming (agents optimize for passing checks rather than quality). Solution: real-time quality gates that stop defects immediately and structured feedback loops that capture debugging knowledge. — [GitHub: allnew-llc/andon-for-llm-agents](https://github.com/allnew-llc/andon-for-llm-agents)
- **Research synthesis:** Zylos Research analysis found that in multi-agent systems, ~42% of failures are specification failures (agent was given wrong or incomplete instructions), ~30% are coordination failures (handoffs between agents break down), and the rest are infrastructure (API outages, timeouts). Recovery patterns map to these categories: specification failures require human escalation or re-prompting with better context; coordination failures require explicit handoff contracts and state checkpointing; infrastructure failures require circuit breakers and transient retry with backoff. — [Zylos Research / Supervisor Trees and Fault Tolerance](https://zylos.ai/en/research/2026-03-16-supervisor-trees-fault-tolerance-ai-agent-systems)

## Gotchas

- **Setting `output_retries=0` because retries felt risky.** This doesn't make agents safer — it just makes them fail immediately. Instead, keep the retry budget and use an output validator to catch malformed output. The retry mechanism re-prompts the LLM with the error, which is the actual self-correction mechanism.
- **Using a single generic retry wrapper for the whole run.** This catches nothing useful — a rate-limit error on one tool call shouldn't retry the entire agent pipeline. Each call site needs its own retry contract with the right exception class, attempt count, and backoff strategy.
- **Skipping `thread_id` in LangGraph `configurable` state.** LangGraph silently resumes from the wrong thread, producing unpredictable results. Always set thread identity explicitly.
- **Retrying non-idempotent actions.** If your agent calls a refund API, a retry without idempotency keys produces double-refunds. Wrap every mutating action in idempotency logic before adding retry logic.
- **Not separating transient from structural failures.** Real outages trip circuit breakers correctly, but impossible tasks burn through retry budgets before escalating. Build separate exception hierarchies so the system knows which failures actually resolve on retry.
