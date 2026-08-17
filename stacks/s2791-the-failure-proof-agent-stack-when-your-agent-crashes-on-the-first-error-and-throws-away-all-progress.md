# S-2791 · The Failure-Proof Agent Stack — When Your Agent Crashes on the First Error and Throws Away All Progress

Your agent worked perfectly in development. In production, a single API timeout cascaded into a complete system failure, 47 Slack alerts, and three hours of lost work. The agent had no error recovery and no state preservation — every intermediate result was gone. The fix isn't a bigger try/catch. It's a layered resilience architecture.

## Forces

- **Agents fail non-deterministically.** A prompt that works once fails the next time due to model drift, token limit changes, or a tool returning an unexpected schema. Unlike conventional software, the failure surface isn't just network calls — it's LLM output itself (hallucinated tool arguments, refusals, schema violations).
- **The loop problem is asymmetric.** `max_iterations=N` caps are wrong in both directions: they stop agents still making progress, or let them burn tokens indefinitely after they're stuck. Neither outcome is acceptable at production scale where each run costs real money.
- **State loss is the silent killer.** When an agent crashes mid-workflow, most implementations lose every intermediate result. Teams then build manual recovery processes or — worse — just re-run from scratch, burning budget and time.
- **Error classification matters.** Not all errors are equal: a transient network blip and a permanent auth failure require completely different recovery strategies. Treating them the same either over-retries permanent failures or gives up too early on transient ones.

## The Move

Layer five concentric safeguards. Each one handles a different failure mode. Together they make agent failures predictable and recoverable instead of catastrophic.

**1. Classify errors before retrying.** Sort every error into one of three buckets on contact:
- **Transient** (network blip, rate limit, 5xx): retry with backoff
- **Permanent** (auth failure, invalid params, 404): fail fast, escalate immediately
- **Ambiguous** (timeout with no response, 429): verify state, then retry once

```python
def classify_error(error, context={}):
    if error.status in (408, 429, 500, 502, 503, 504):
        return "transient"  # retry with backoff
    if error.status in (401, 403, 404):
        return "permanent"  # fail fast, escalate
    return "ambiguous"  # verify, then retry once
```

**2. Exponential backoff with jitter for retries.** Never retry immediately — back off and add randomness to avoid thundering herd:

```python
delay = min(base_delay * (2 ** attempt) + random.uniform(0, 1), max_delay)
```

Typical starting config: base=1s, max=60s, max_attempts=3–5. This handles the majority of transient failures without hammering your provider or getting yourself rate-limited.

**3. Tool-level validation before execution.** The most common agent failure mode isn't the tool failing — it's the agent hallucinating tool parameters (non-existent IDs, wrong date formats, invalid enum values). Validate every tool call against its schema *before* execution. Return a structured hint on failure, not just "invalid input":

```typescript
function createSafeToolExecutor(tool: Tool) {
  return async function validatedExecute(args: unknown) {
    const result = tool.schema.parse(args)
    if (!result.success) {
      return {
        error: "invalid_params",
        hint: result.issues[0].message,  // tells agent what went wrong
        received: args
      }
    }
    return tool.execute(result.data)
  }
}
```

**4. Control-theory loop detection instead of step caps.** Replace `max_iterations=N` with empirical convergence detection. LoopGain (open-source, Apache 2.0) computes a "loop gain ratio" (current_error / previous_error) each iteration. Below 1.0 means the error is shrinking — keep going. Above 1.0 means the agent is stuck or making things worse — exit:

| Loop State | Aβ Ratio | Action |
|---|---|---|
| FAST_CONVERGE | < 0.5 | Continue |
| CONVERGING | 0.5–0.9 | Continue |
| STALLING | 0.9–1.1 | Warn, consider exit |
| OSCILLATING | > 1.1 | Exit, trigger checkpoint recovery |
| DIVERGING | >> 1.1 | Exit immediately |

**5. State checkpointing with framework-native persistence.** Checkpoint after every successful step — not just on completion. LangGraph's checkpointing system uses this pattern:
- **Dev:** `MemorySaver` (in-process, zero config)
- **Single-server prod:** `SqliteSaver` (file-based, ACID transactions)
- **Multi-instance prod:** `PostgresSaver` (shared state across replicas)

Resume from checkpoint, not from scratch:

```python
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph

checkpointer = PostgresSaver.from_conn_string(os.environ["DATABASE_URL"])
graph = StateGraph(AgentState).compile(checkpointer=checkpointer)

# Resume after interruption — picks up exactly where it stopped
result = graph.invoke(None, config={"configurable": {"thread_id": "task-123"}})
```

**6. Fallback chain for model/tool failures.** Never rely on a single model or single tool. Chain fallbacks in priority order:

```python
fallback_chain = [
    ("gpt-4o", primary_toolset),
    ("gpt-4o-mini", fallback_toolset),  # cheaper fallback
    ("claude-3-5-sonnet", recovery_toolset),  # different provider
]
```

**7. Circuit breaker for cascading failures.** Open the circuit after N consecutive failures on the same endpoint, stop all requests for a cooldown period, then test recovery in half-open state:

```python
# Pseudocode — real impl in agent-circuit-breaker (PyPI)
circuit.state = CLOSED
if circuit.failure_count >= threshold:
    circuit.state = OPEN
    schedule(coat_down_period, circuit.half_open_test)
```

## Evidence

- **Engineering blog — 90% of agents fail in production:** GetATeam identified 5 critical failure patterns from deploying hundreds of agents: API rate limits, unexpected input variations, network instability, hallucinated tool calls, and context window exhaustion. Their fix: exponential backoff retry, graceful degradation, and cost circuit breakers. — [https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/) (November 2025)

- **Real incident — $200 silent loop:** Markaicode documented the production reality: "Your LangGraph agent works perfectly in testing. In production it loops silently for 20 minutes, consuming $200 in API calls before you notice." Their solution: typed state schemas, Postgres checkpointing, per-step error recovery, and LangSmith trace inspection. — [https://markaicode.com/langgraph-production-agent](https://markaicode.com/langgraph-production-agent) (March 2026)

- **HN Show HN — control theory vs step caps:** Dave built LoopGain after noticing that agent feedback loop diagrams resemble electrical circuit diagrams. His key insight: `max_iterations=N` is wrong in both directions — stops improving agents early, lets stuck agents burn. LoopGain replaces it with convergence detection. Open-source at [github.com/loopgain-ai/loopgain](https://github.com/loopgain-ai/loopgain). — [https://news.ycombinator.com/item?id=48919562](https://news.ycombinator.com/item?id=48919562) (HN score: 31)

- **AI engineer post-mortem — five failure modes at scale:** Harshrastogi at Modelia.ai and Asynq.ai documented real production failures: a candidate evaluation agent hallucinated tool parameters and got stuck in loops costing 3x budget; an image generation agent approved obviously flawed outputs. Fix: tool-level schema validation, stall detection (same tool call 3x without progress), and quality-vs-completion tradeoff monitoring. — [https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns) (March 2026)

- **LangGraph production guide — checkpoint persistence tiers:** Kalvium Labs shipped 5 production LangGraph agents and documented the persistence decision: MemorySaver for dev, SqliteSaver for single-server, PostgresSaver for multi-instance. Key insight: use `Annotated` reducers for accumulating fields to prevent silent overwrites across parallel branches. — [https://www.kalviumlabs.ai/blog/langgraph-in-production-stateful-multi-step-agents/](https://www.kalviumlabs.ai/blog/langgraph-in-production-stateful-multi-step-agents/)

## Gotchas

- **Tool descriptions cause loops more than tool execution does.** Rajpoot (May 2026) documented that the #1 reason agents loop on tools is ambiguous tool descriptions — the model doesn't know when to stop retrying or which parameters are required. Write tool descriptions with the same precision as API docs: expected types, required vs optional, error semantics, and valid value ranges.
- **`max_iterations=15` is cargo-culted.** Framework defaults vary wildly (OpenAI Agents SDK: 10, CrewAI: 20, arbitrary configs: 50–100) and no one has validated them against actual task characteristics. Treat them as a floor safety net, not a performance knob.
- **Checkpointing state grows unbounded.** Every field in your state schema gets serialized on every checkpoint write. Large state (long conversation histories, accumulated artifacts) balloons storage and slows recovery. Prune aggressively — store only what you need to resume.
- **Circuit breaker state must survive restarts.** If your circuit breaker state is in-memory, a pod restart resets it to closed and you'll immediately re-flood a failing downstream. Persist state externally or use a shared store.
- **Retrying with the same prompt on the same input is often futile.** If the agent failed because of a bad plan or hallucinated parameters, retrying 3x with backoff just burns budget. The retry should either use a different model, a different tool, or an explicit re-plan instruction — not the same context.
