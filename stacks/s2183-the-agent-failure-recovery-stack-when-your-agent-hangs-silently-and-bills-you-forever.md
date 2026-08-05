# S2183 · The Agent Failure Recovery Stack

When your agent hangs at step 3 of a workflow, makes no progress, and bills you for 20 minutes of context inflation — and there's no error, no exception, no signal.

## Forces

- Agents fail *without raising exceptions*. The LLM returns valid output every time; the system has no crash to catch. You discover the failure only when the customer complains or the bill arrives.
- Multi-step agents accumulate partial state across steps. When a step fails mid-execution, you lose not just that step but the context built on top of it. There's no stack trace, no rollback.
- Conventional software patterns (try/catch, circuit breakers) were designed for deterministic code. Agent failures are semantic — wrong tool chosen, plausible but incorrect plan, or a loop that just keeps going. The same code path that worked yesterday fails today with no exception.
- The gap between test and production is wider for agents than any other system class: agents encounter inputs the developer never imagined, take paths no one designed for, and hit failure modes no one named.

## The Move

Layer failure handling into the agent architecture at four levels:

**1. Hard limits at the orchestration layer** — never rely on the LLM to decide when to stop. Set a maximum number of steps per task, a per-task cost ceiling, and a timeout budget. Treat these as safety fences, not suggestions.

**2. Loop detection via step fingerprinting** — track a rolling window of recent tool calls and their arguments. Flag when the same (tool, args) pair repeats N times, or when consecutive steps produce near-identical outputs. This catches both hard loops (same call repeated verbatim) and soft loops (different words, same outcome).

**3. Structured recovery patterns, not blind retries:**
- *Exponential backoff with jitter* — for transient failures (rate limits, network blips). Double the wait on each retry, cap at a maximum, add random jitter to prevent thundering herds.
- *Circuit breaker* — after N consecutive failures on a tool or dependency, stop calling it and return a fallback. Reset after a cooldown window.
- *Checkpoint-and-resume* — after each successful step, serialize the agent's state (context window, working memory, step count, tool call history) to durable storage. On failure, restart from the last checkpoint rather than from scratch.
- *Fallback chain* — if tool A fails, try tool B; if tool B fails, return a graceful degradation response. Never leave the user with an empty screen.
- *Escalation queue* — when recovery patterns are exhausted, route to human review rather than returning a potentially wrong answer.

**4. Supervisor architecture for multi-agent systems** — a single supervisor agent owns communication with the user, decomposes tasks, assigns to worker agents, and monitors progress. The supervisor maintains a task graph and can detect when a worker is looping, stalled, or taking an unacceptably long time. This prevents hallucination loops that plague flat peer-to-peer agent architectures.

## Evidence

- **HN Ask thread (2025):** Following incidents like the DataTalks database wipe by Claude Code and a Replit agent deleting data during code freeze, practitioners reported that the primary gap was no observability into step-by-step agent actions, no cost tracking per task, and no way to interrupt before irreversible actions. AgentShield emerged as a community response — an observability SDK providing execution tracing, risk detection on outputs, and human-in-the-loop approval for high-risk actions. — [https://news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)

- **Agent Patterns catalog (2025):** Documents four loop types that plague production agents: *hard loops* (same tool call repeated verbatim), *soft loops* (same tool, slightly varied arguments), *semantic loops* (different reasoning, same output), and *retry storms* (a failed tool triggers repeated retries that all fail identically). The recommended fix is step fingerprinting with a sliding window — flag when the last N steps match or overlap, then inject a "try a different approach" redirect into the context. — [https://www.agentpatterns.tech/en/failures/infinite-loop](https://www.agentpatterns.tech/en/failures/infinite-loop)

- **AI Agents Blog (March 2026):** Details five recovery patterns implemented with the Anthropic SDK: exponential backoff with jitter for rate limits, circuit breakers that trip after sustained tool failures, checkpoint-and-resume for preserving partial progress in long tasks, fallback chains that try alternative approaches before degrading, and escalation queues for cases where automated recovery is exhausted. — [https://aiagentsblog.com/blog/agent-error-recovery-patterns](https://aiagentsblog.com/blog/agent-error-recovery-patterns)

- **Databricks / BASF Coatings (October 2025):** Deployed a supervisor agent pattern for 11,000+ employees across 70+ global sites. A central supervisor decomposes complex queries, routes to specialized Genie agents and function-calling agents, monitors execution, and aggregates results. The supervisor maintains the task graph and prevents workers from diverging into unverified territory. — [https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)

- **JetThoughts (2026):** Surveyed the multi-agent framework landscape. LangGraph dominates production deployments for its graph-based state machines with fine-grained control; CrewAI for rapid prototyping via role-based crews; AutoGen entered maintenance mode October 2025 with Microsoft Agent Framework as the successor. — [https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025/](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025/)

- **Zylos Research (2026):** Categorizes six agent failure types requiring different recovery approaches: infinite loops (progress-halted), deadlocks (mutual waiting between agents), resource contention (multiple agents fighting shared resources), context overflow (context grows until the model halts), semantic errors (valid output, wrong answer), and cascading failures (one slow step blocks the entire reasoning loop). — [https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery/](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery/)

## Gotchas

- **Don't rely on LLM self-correction alone.** Telling the agent "if you're stuck, try a different approach" on every loop is a common pattern that works for simple cases but has no guarantee. Some agents will rephrase the same wrong plan 15 times rather than truly pivot. Hard limits are more reliable than self-awareness.
- **Soft failures are harder to catch than hard failures.** A tool that returns a valid-looking but incorrect result will pass every try/catch. You need output validation — either a critic agent, a structural schema check, or an LLM-as-judge evaluating the semantic correctness of tool results — not just a non-error status code.
- **Checkpointing without a test restore is decoration.** Many teams implement checkpoint-and-resume but never actually test whether the serialized state reproduces the agent's behavior when deserialized. In practice, deserialization bugs are common and frequently missed until a real failure forces a restore.
- **The supervisor can become a bottleneck.** A single supervisor that all workers must report to can create its own deadlock if the supervisor's context window fills up or its own LLM call times out. Production implementations typically give supervisors a bounded queue with timeout, not a blocking channel.
- **Circuit breakers on LLM calls require careful threshold tuning.** An LLM API returning 429s might recover in 30 seconds; setting the circuit breaker to trip after 3 failures and stay open for 60 seconds might be too conservative for short-burst tasks but too aggressive for sustained rate limiting. Test under realistic load patterns, not unit tests.
