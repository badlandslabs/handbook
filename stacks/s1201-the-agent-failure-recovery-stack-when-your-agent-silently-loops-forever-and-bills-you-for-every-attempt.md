# S-1201 · The Agent Failure Recovery Stack — When Your Agent Silently Loops Forever and Bills You for Every Attempt

Agents fail in shapes single-LLM calls don't. The API returns a 429 at the worst moment. A tool call times out mid-workflow. The model hallucinates a function that doesn't exist. The response is valid JSON but semantically wrong. Or the agent enters an infinite tool-call loop and burns through your entire monthly budget before anyone notices. Traditional try/catch doesn't cover these failure modes — you need layered defenses at every level.

## Forces

- **Agents can fail silently.** Unlike a crashed web service with a stack trace, an agent may behave incorrectly while returning HTTP 200 — confident nonsense, a loop that looks productive, a tool result that's technically valid but wrong.
- **Retry is non-deterministic.** Re-running the same agent step with the same inputs does not guarantee the same output. Unlike an HTTP handler, the agent's state (context, tool history, accumulated results) changes with every attempt.
- **Side effects make retries dangerous.** A tool call that sends an email, writes a record, or triggers a payment cannot be blindly retried. You need idempotency before you can retry safely.
- **Cost spirals are real.** A misconfigured agent looping without a step cap can accumulate thousands of dollars in API calls in a single session. The billing shock arrives before the error log does.
- **Cascading failures compound.** A single downstream service outage can corrupt an entire multi-step agent workflow — and if there's no checkpointing, recovery means starting from scratch.

## The Move

Build layered failure handling where each layer has a distinct purpose and scope.

**Layer 1 — Hard step caps (the circuit breaker for loops):**

The single most important guardrail. Cap the maximum number of agent steps and stop unconditionally when reached.

```python
MAX_STEPS = 12
for step in range(MAX_STEPS):
    response = await llm.invoke(state)
    if response.is_done:
        return response
    state = await execute_tools(response.tool_calls)
else:
    raise AgentExceededSteps(f"Did not finish in {MAX_STEPS} steps")
```

In LangGraph: `recursion_limit=12`. The cap prevents runaway loops and forces explicit escalation.

**Layer 2 — Error classification before retry:**

Not all errors are equal. Classify each failure before deciding what to do:

| Error Type | Example | Retry? | Fix |
|---|---|---|---|
| Transient | Rate limit (429), timeout, 500/503 | Yes — with backoff | Retry |
| Permanent | Auth failure, missing field, bad input | No | Fallback or escalate |
| Semantic | Valid JSON, wrong answer | No | Re-prompt or escalate |
| Cascading | Tool consistently failing | No | Circuit breaker |

**Layer 3 — Retry at the step level, not the agent level:**

Identify the smallest retriable unit. A full agent restart discards accumulated state. A step-level retry preserves context and only re-executes the failed tool call.

For tools with side effects, enforce idempotency before retrying. Add an idempotency key to prevent duplicate writes on re-execution:

```python
@tool
def send_email(to: str, subject: str, body: str, idempotency_key: str):
    # Check if key was already processed
    if db.idempotency_keys.exists(idempotency_key):
        return db.emails.find_by_key(idempotency_key)
    result = email_provider.send(to, subject, body)
    db.idempotency_keys.insert(idempotency_key, result.id)
    return result
```

**Layer 4 — Circuit breakers per tool:**

Track failure rates per tool. When failures exceed a threshold within a time window, open the circuit and fail-fast rather than continuing to call a degraded service:

```python
class CircuitBreaker:
    def __init__(self, threshold=5, window=60):
        self.failures = deque(maxlen=threshold)
        self.threshold = threshold
        self.window = window

    def record(self, success: bool):
        self.failures.append((time.time(), success))
        self._cleanup()

    def is_open(self) -> bool:
        self._cleanup()
        recent = [s for ts, s in self.failures if time.time() - ts < self.window]
        return len(recent) >= self.threshold and not any(recent)

    def _cleanup(self):
        cutoff = time.time() - self.window
        self.failures = deque([f for f in self.failures if f[0] > cutoff], maxlen=self.threshold)
```

**Layer 5 — Checkpointing for long-running tasks:**

Save agent state at defined intervals (every N steps, or at task boundaries). On failure, resume from the last checkpoint instead of starting from scratch. LangGraph, Temporal, and Dagster all ship first-class checkpoint primitives. Without checkpointing, a single API timeout can wipe out hours of agent work — production agents lose an estimated 30% of work hours without it.

```python
def checkpoint(state: AgentState, step: int, path: str):
    with open(f"{path}/checkpoint_{step}.json", "w") as f:
        json.dump({"step": step, "messages": state.messages, "results": state.results}, f)

def restore(path: str) -> AgentState:
    checkpoints = sorted(glob(f"{path}/checkpoint_*.json"))
    with open(checkpoints[-1]) as f:
        data = json.load(f)
    return AgentState(messages=data["messages"], results=data["results"], step=data["step"])
```

**Layer 6 — Dead letter queue for failed tasks:**

Failed agent tasks that can't be retried (permanent failures, step-cap exceeded, semantic errors) go to a DLQ for human review. Track: user ID, task description, failure reason, agent state at failure, timestamp. This is where you catch the $47,000 fraudulent refund before it becomes an incident.

**Layer 7 — Explicit escalation for high-stakes actions:**

For irreversible operations (payments, data deletion, external communications), require a confidence threshold. Below the threshold, surface the decision to a human reviewer rather than making the call autonomously. Human-in-the-loop is not a fallback — it is a first-class architectural component for production agents.

## Evidence

- **Blog post (Manvendra Rajpoot, May 2026):** "Hard step caps" are identified as the single most important guardrail — if an agent doesn't finish in 12 steps, stop, document, and escalate. Covers tool error semantics, tool-level retries, fallback paths, whole-agent retries, cost circuit breakers, state checkpointing, and the specific loop patterns to watch for (loop on missing field, loop on stale data, loop on auth, hallucinated tool, cost spiral). — [blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)

- **OpenHelm Blog (Max Beech, 2024, canonical):** Proper error handling increased agent reliability from 87% to 99.2% — a 14× reduction in failures. Recommends 3-5 retries for most cases (transient errors), 10+ for critical operations (payments, data loss). Distinguishes between retryable (timeout, rate limit, 503) and permanent (auth, malformed input) errors. — [openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents](https://www.openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents)

- **Hacker News (Ask HN, harperlabs, 2025):** Gartner predicted over 40% of AI agent projects will fail by 2027. A January 2026 prompt injection in a customer support agent processed a $47,000 fraudulent refund. The 7 core failure modes identified: hallucination under unexpected inputs, edge case collapse (null/Unicode/empty fields), prompt injection, context limit surprises (silent misbehavior), cascade failures (tool #1 fails → tools 2-6 fail compounding), tool call loops without exit conditions, and context window overflow. — [news.ycombinator.com/item?id=47325105](https://news.ycombinator.com/item?id=47325105)

- **GitHub (converra/agent-triage, 2026):** Open-source tool that diagnoses AI agents in production by extracting behavioral rules from system prompts, replaying conversation steps with an LLM-as-judge, and flagging the exact step and agent where failure occurred. 197 commits, MIT license. — [github.com/converra/agent-triage](https://github.com/converra/agent-triage)

- **Zylos Research (May 2026):** Synthesizes 6 failure categories: Deadlock & Resource Contention, Silent Degradation, Hallucinated Tool Calls, Context Overflow, Irreversible Action Taken Prematurely, and Context-Dependent Non-Determinism. Distinguishes agent failures from conventional software failures (agents can behave incorrectly without raising any exception). — [zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery)

## Gotchas

- **Don't retry at the agent level.** Re-running the full agent discards all accumulated state and re-spends tokens on every prior step. Retry the specific failed step instead.
- **Don't retry side-effectful tools without idempotency.** An email sent twice, a record written twice, a payment processed twice — these are worse than a clean failure. Add idempotency keys or check-before-write logic before any retry on a tool with external effects.
- **Don't retry on semantic errors.** A valid JSON response with the wrong answer will return the same wrong answer on retry. Detect semantic failure through output validation, not HTTP status codes.
- **Don't set step caps too high.** 50-step caps are common in tutorials but hide runaway loops, not prevent them. Start at 8-12 steps; raise only when you have evidence the domain genuinely needs more.
- **Don't skip the DLQ.** If failed tasks disappear into a void, you have no audit trail and no recovery path. Route every permanent failure to a queue with enough state for a human to understand what happened and retry manually if needed.
