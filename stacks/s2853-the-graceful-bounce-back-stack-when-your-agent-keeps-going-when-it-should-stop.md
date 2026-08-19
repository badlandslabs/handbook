# S-2853 · The Graceful Bounce-Back Stack

When your agent keeps going when it should stop — retrying a dead API, looping through the same failed plan, or silently burning $700 overnight while nobody watches.

## Forces

- Agents fail in shapes single LLM calls don't — loops, reasoning spirals, and irreversible side-effects that accumulate before a human notices.
- The cost of a runaway agent dwarfs the cost of building recovery logic; one $30k incident justifies a dozen guardrails.
- Classifying errors by type matters more than retrying everything — hammering a 401 endpoint wastes tokens and delays the real response.
- Multi-agent systems inherit classic distributed-systems failures (deadlock, race conditions) with the added wrinkle that one "resource" is a human's attention.
- Recovery is not optional engineering hygiene — it is the core engineering challenge of production agentic systems.

## The Move

Layer three distinct failure-handling systems around every agent, from innermost to outermost:

**1. Error taxonomy drives recovery strategy — classify before retrying.**
- **Transient** (rate limits 429, timeouts, 503s, DNS): retry with back-off.
- **Semantic** (malformed JSON, wrong tool name, schema violation): re-prompt with corrective context.
- **Resource** (token budget, context overflow, spending cap): reduce payload, summarize history, switch to smaller model.
- **Fatal** (auth 401, revoked keys, policy violations): abort immediately, log, alert.
- *Design principle from Neel Mishra: classify before you retry. A retry loop against a 401 endpoint wastes tokens and time.* [1]

**2. Hard step caps are the single most important guardrail.**
```python
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    raise AgentExceededSteps(f"didn't finish in {MAX_STEPS}")
```
- In LangGraph: `recursion_limit=12` on the compiled graph.
- Step caps prevent reasoning loops where the agent keeps re-planning after each failure — a fundamentally different failure mode than a retry storm.
- Pair with a wall-clock timeout and a token budget cap. These three cover 90% of runaway scenarios. [2]

**3. Circuit breaker — stop the retry storm.**
- Three states: **Closed** (normal), **Open** (fail-fast, no calls), **Half-open** (probe for recovery).
- For agents: timeouts treated as "try different approach" rather than "stop" are the primary cost driver. A circuit breaker prevents the agent from re-routing around a dead endpoint indefinitely.
- FailWatch (open-source Python SDK) intercepts dangerous tool calls *before* execution using deterministic policy checks — hard blocks on numeric limits and regex patterns, no LLM involved. [3]
- Emit circuit-breaker state transitions as observability spans so trips are visible in dashboards. [2]

**4. Checkpoint and rollback — undo before you can't.**
- Save a "known good state" snapshot at defined boundaries (e.g., after each significant tool-call batch).
- LangGraph `interrupt()` pauses the graph mid-run for human approval; state persists via a checkpointer (AsyncPostgresSaver or MongoDBSaver in production, InMemorySaver for dev). The agent resumes from disk without re-running LLM calls. [4]
- Compensation logic: for agents that mutate external state (DB writes, API calls), build compensating actions alongside the forward logic — rollback is rarely a clean undo, it's a set of counter-actions.

**5. Deadlock detection in multi-agent systems.**
- Classic Coffman conditions (1971) are satisfied by default in multi-agent systems with human-in-the-loop approval queues: Agent A waits for B → B waits for A → both requests pile up in separate human queues → system hangs silently for 19 hours. [5]
- Fix: explicit state ownership — one agent owns the shared state; all others read-only. No agent calls another agent's output without a polling timeout and a defined escalation path.
- A `call_chain` registry that tracks which agent types are currently running prevents circular wait chains: "no agent runs at greater depth than the designer intended." [6]

**6. Observability is the last layer.**
- A circuit breaker that nobody sees is barely better than no circuit breaker. Emit: step count, token usage, tool call latency, error type per step, circuit-breaker state transitions.
- Spending alerts: set a per-run budget (e.g., $5) and alert before it's exceeded. The $200 agent-loop from HN and the $30k production incident both went unnoticed until billing alerts fired. [7][8]

## Evidence

- **Engineering blog:** Fault tolerance taxonomy — transient/semantic/resource/fatal — with recovery strategy per type; argues fault tolerance is "the core engineering challenge of the agentic era." — [Zylos Research, 2026-05-06](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery/)
- **Engineering blog:** Step cap + wall-clock timeout + token budget covers 90% of runaway scenarios; $700/night agent incident from cascading retries where timeouts were not treated as stop signals. — [BuildMVPFast, 2026-04-02](https://www.buildmvpfast.com/blog/agent-timeout-circuit-breaker-patterns-runaway-ai-workflows-2026)
- **Show HN post:** Developer lost $200 from an agent loop, built per-tool AI budget controls as a result. — [Hacker News, 2026-02](https://news.ycombinator.com/item?id=46991656)
- **Open-source repo:** Four production error-handling patterns (circuit breaker, partial success, HITL, graceful degradation) with tests, built on Trigger.dev v4. — [tanayshah11/ai-agent-error-patterns](https://github.com/tanayshah11/ai-agent-error-patterns) [Tanay Shah engineering notes](https://tanayshah.dev/projects/ai-agent-error-patterns/)
- **Open-source repo:** FailWatch — Python circuit-breaker SDK that intercepts tool calls before execution with deterministic policy checks (no LLM in the safety path). — [Ludwig1827/FailWatch](https://github.com/Ludwig1827/FailWatch)
- **Engineering blog:** Human-in-the-loop approval queues in multi-agent systems create circular wait chains satisfying all four Coffman conditions; liveness now depends on human response time. — [tianpan.co, 2026-06-01](https://tianpan.co/blog/2026-06-01-the-multi-agent-deadlock-that-hangs-on-two-calendars)
- **GitHub issue + design:** OpenClaw `recursion_limit` feature request — documents three loop types: tool repetition, reasoning repetition, and replan loops; proposes `call_chain` registry to bound nesting depth. — [openclaw/openclaw#37022](https://github.com/openclaw/openclaw/issues/37022)
- **LangGraph docs:** `interrupt()` requires checkpointing; production requires persistent checkpointer (AsyncPostgresSaver or MongoDBSaver) to resume agent state from disk after human approval. — [LangGraph docs](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)

## Gotchas

- Step caps and circuit breakers address *different* failure modes: a step cap stops a reasoning loop; a circuit breaker stops a retry storm. Treat timeouts as "try different approach" is the failure that bypasses both.
- Checkpointing alone is not rollback — it only saves state. You still need compensating actions for agents that wrote to external systems. The "undo" assumption is dangerous.
- Human-in-the-loop sounds safe but creates a new failure surface: if two agents both hit HITL queues on two different humans who don't know they're paired, you have deadlock. HITL reduces risk but doesn't eliminate it.
- Observability is not optional. Every pattern above (circuit breakers, step caps, checkpoints) is invisible in production unless it emits spans and state transitions. Build alerts, not just logs.
- Per-run spending caps catch cost overruns but don't prevent them in real time. For high-risk agents, use pre-execution policy checks (like FailWatch) that block before the token is spent, not after.
