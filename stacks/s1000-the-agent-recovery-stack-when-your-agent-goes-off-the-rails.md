# S-1000 · The Agent Recovery Stack — When Your Agent Goes Off the Rails

Your agent has been running for 22 minutes. You didn't ask it to take 22 minutes. It hasn't errored — it hasn't done anything at all except keep calling the same tool with minor variations, waiting for an output that never arrives. The process is still running. The logs show nothing wrong. This is not a crash. This is the worst kind of failure: a silent, resource-consuming loop with no exit signal.

Agents fail differently than regular software. A web service crashes and tells you. An agent can degrade silently, loop forever, duplicate side effects, or take irreversible actions before anyone notices. The same tooling that keeps web services reliable — retry loops, circuit breakers, dead letter queues — works for agents, but only if you treat agent failures as a first-class architectural concern, not an afterthought.

## Forces

- **The multiplicative failure curve.** 85% per-step accuracy sounds good. Ten steps in a workflow means the end-to-end success rate is 0.85¹⁰ ≈ 20%. At 95% per-step — still impressive — a 10-step workflow succeeds only ~60% of the time. Better models don't fix this. Only durable execution infrastructure does.
- **Silent failures are worse than loud ones.** A tool timeout, rate limit, or malformed JSON is recoverable. An agent that loops for 35 minutes accumulating context, duplicating side effects, and producing nothing is not obviously broken — it exits cleanly with no error code.
- **Retry logic is not one-size-fits-all.** Retrying a transient network error is correct. Retrying a prompt that consistently produces malformed JSON will loop forever. The recovery strategy must match the error category.
- **Checkpointing is load-bearing.** Without it, every failure restarts from scratch. With a 10-step workflow at 85% per-step accuracy, that means ~80% of runs restart at least once, losing all progress.
- **Escalation is under-designed.** Most teams build evals and observability to detect problems. Fewer build the enforcement layer — human review at decision points — that prevents irreversible outcomes.

## The Move

Build a layered recovery stack. Each layer handles a distinct failure category. Layers closer to the infrastructure (retries, circuit breakers) are automated. Layers closer to the business logic (checkpointing, escalation) are designed.

### Layer 1 — Error taxonomy before retry logic

Classify every failure before deciding what to do with it. Four categories, four responses:

| Error Type | Cause | Response |
|---|---|---|
| **Transient** | Rate limits (HTTP 429), timeouts, 503s, DNS failures | Retry with exponential backoff + jitter |
| **Semantic** | Malformed JSON, wrong tool names, schema violations | Re-prompt with corrective context (don't retry the same call) |
| **Resource** | Token budget exceeded, context overflow, spending cap | Reduce payload: summarize, drop older results, switch model |
| **Fatal** | Auth failures, revoked keys, policy violations | **Abort immediately**, log, alert, escalate |

The most common mistake is treating semantic errors as transient and looping the same bad prompt.

### Layer 2 — Hard step caps

The single most cost-effective guardrail. If the agent doesn't complete in N steps, stop and surface the partial result.

```python
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    raise AgentExceededSteps(f"did not finish in {MAX_STEPS}")
```

Without this, there is no upper bound on runtime, cost, or context accumulation. With it, every failure is bounded.

### Layer 3 — Circuit breakers

Monitor failure rates per tool and per model call. When a threshold is exceeded, stop calling the failing component before it poisons downstream steps.

```
failure_threshold = 5
recovery_timeout = 60 seconds
state = CLOSED (normal)

on failure:
    failure_count++
    if failure_count >= failure_threshold:
        state = OPEN
        start recovery_timer

on recovery_timer expires:
    state = HALF_OPEN
    allow 1 probe call
    if probe succeeds: state = CLOSED; failure_count = 0
    if probe fails: state = OPEN; reset timer
```

This prevents a single degraded tool (rate-limited API, failing sandbox) from cascading into a complete workflow failure.

### Layer 4 — Durable checkpointing

Save state at every step boundary. When the process restarts, resume from the last checkpoint — not the beginning.

LangGraph's checkpointing model is the canonical implementation: every graph state transition is persisted to a backend store (PostgreSQL, Redis, or SQLite). When a workflow resumes, it replays from the last saved state.

```
from langgraph.checkpoint.postgres import PostgresSaver

checkpointer = PostgresSaver.from_conn_string(conn_string)
graph.compile(checkpointer=checkpointer)
```

The critical property: checkpointing is not backup — it is the load-bearing mechanism for any workflow longer than a single API call round-trip.

### Layer 5 — Human-in-the-loop escalation

Escalation is the final safety valve, not the first. It should trigger only after automated recovery is exhausted.

Four reliable escalation triggers — not verbal model confidence, which is systematically miscalibrated (RLHF-trained models often express highest confidence on incorrect outputs):

- **Novelty trigger:** Task type not seen in training data or eval suite
- **Reversibility trigger:** Action has irreversible side effects (writes, deletes, sends)
- **Confidence trigger:** Auxiliary confidence score (not verbal) below calibrated threshold
- **Policy trigger:** Action conflicts with defined business rules or compliance constraints

Escalation requires active notification — not just a log entry. PagerDuty, Slack, or a ticketing system. The reviewer needs the full decision context: what the agent saw, what it chose, and why it stopped.

## Evidence

- **Engineering specification:** Error taxonomy, retry/fallback contracts, and checkpointing as the core persistence layer — treating every LLM call as a network call that can fail. — *[Best AI Web: Retry, Fallback & Self-Correction Loops in AI Agents, 2026](https://www.bestaiweb.ai/how-to-implement-retry-fallback-and-self-correction-loops-in-ai-agents-in-2026)*

- **Primary source — durable execution:** "Most AI agents are built as a single process holding state in memory. That holds up until the workflow has to outlive the process that started it — and in production it always does." LangGraph checkpointing passes 30,000 GitHub stars; teams building long-running agents reach for durable execution as the solution, not better models. — *[Vadim Nicolai: Durable Execution in LangGraph, June 2026](https://vadim.blog/durable-execution-agents-that-survive-failure-and-resume-where-they-left-off/)*

- **Primary source — failure distribution:** Analysis of production multi-agent deployments finds: specification failures account for ~42% of failures, coordination breakdowns ~37%, verification gaps ~21%. The majority of failures are design and orchestration problems, not model quality. — *[Zylos Research: AI Agent Self-Healing and Failure Recovery, May 2026](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)*

- **Primary source — escalation design:** "RLHF-trained models tend to express highest confidence on incorrect outputs; a claimed 90% confidence can correspond to roughly 75% real-world accuracy." Escalation signals must be calibrated against auxiliary metrics, not verbal model confidence. — *[Digital Applied: Human-in-the-Loop Escalation Design for AI Agents, June 2026](https://www.digitalapplied.com/blog/human-in-the-loop-escalation-design-ai-agents-2026)*

- **Primary source — step caps:** Hard step caps prevent runaway loops. Combined with checkpointing, they make every failure bounded and recoverable. — *[Manvendra Rajpoot: LLM Agent Error Recovery in 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)*

## Gotchas

- **Retrying semantic errors loops forever.** If the prompt consistently produces malformed output, re-prompting with the same structure will produce the same bad output. You need a different prompt or a schema validation layer in the tool definition, not a retry loop.
- **Circuit breakers at the wrong granularity miss cascading failures.** A circuit breaker on the overall agent call will not catch a single degraded tool that other steps still depend on. Instrument per-tool, not just per-agent.
- **Checkpointing without explicit commit points is fragile.** LangGraph checkpoints at every node transition by default, but custom pipelines need manual save calls at safe boundaries — after reads, before writes. Without this, a mid-write crash can leave state inconsistent.
- **Escalation without context is useless.** Routing a "please review" message to a human reviewer with no context generates a queue of ignored tickets. The escalation payload must include: what the agent saw, what it decided, what action it would take, and what the uncertainty is.
- **Hard step caps without partial-result capture leave you with nothing on failure.** If the agent exhausts its step budget, the last checkpoint must contain enough state to either resume manually or produce a meaningful "could not complete" report to the user.
