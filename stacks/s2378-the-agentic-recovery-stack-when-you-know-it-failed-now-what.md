# S-2378 · The Agentic Recovery Stack — When You Know It Failed, Now What?

Detection tells you something broke. Recovery gets the agent back on track — or gracefully terminates it without burning the budget. Most teams have the detection layer covered (S-2368, S-2371) but improvise recovery, which produces systems that fail twice: once on the error and again on the bad recovery attempt.

## Forces

- **Error type determines recovery shape.** A 429 rate limit wants a retry. A semantic hallucination wants a re-prompt. A looping agent wants a circuit breaker. Applying the wrong recovery is worse than no recovery — it compounds the failure.
- **Recovery has a token cost.** Each recovery attempt re-sends the full conversation context through the LLM. Unlike a microservice retry (~bytes), an agent retry can multiply your per-run cost by 5–10x before you realize the retry strategy is terminal.
- **Immediate recovery vs. deferred recovery trade off.** Reflexion-style verbal self-critique patches the strategy mid-run but risks the LLM re-deriving the same wrong path. Checkpoint/restore defers recovery to the next trial but preserves what worked.
- **Recovery that always retries is a denial-of-service against your own system.** Without circuit breakers and step caps, a failing agent can hammer APIs, burn quota, and cascade failures into dependent services.

## The Move

### 1. Classify before recovering

Route to the correct recovery based on error type:

| Error class | Examples | Recovery |
|---|---|---|
| **Transient** | HTTP 429, 503, timeout, DNS failure | Retry with exponential backoff + jitter |
| **Client** | HTTP 400, 401, 404, invalid tool args | Fix and retry once; if it recurs, escalate |
| **Semantic** | Malformed JSON, wrong tool, hallucinated fact | Re-prompt with corrective context; re-evaluate |
| **Resource** | Token budget exhausted, context overflow | Truncate context, checkpoint, defer to next trial |
| **Structural** | Agent looping, max steps reached | Circuit breaker; trigger escalation or graceful exit |

Classify at the tool-call level (did the tool succeed?) and the semantic level (did the output answer the question?).

### 2. Retry with exponential backoff for transient errors

```python
base_delay = 1.0
for attempt in range(max_retries):
    try:
        return tool.execute(args)
    except TransientError as e:
        if attempt == max_retries - 1:
            raise  # escalate after exhausting retries
        delay = min(base_delay * (2 ** attempt) + random(0, jitter), max_delay=60)
        time.sleep(delay)
```

Use **idempotency keys** on tool calls so retries don't cause duplicate side effects.

### 3. Use a circuit breaker to stop cascading failures

Track failure rate over a sliding window. If failures exceed a threshold (e.g., 5 failures in 10 calls), open the circuit — stop invoking that tool and either fall back to an alternative or escalate.

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, window=10):
        self.failures = deque(maxlen=window)
        self.state = "closed"  # closed=normal, open=blocking

    def record_success(self):
        self.failures.append(0)

    def record_failure(self):
        self.failures.append(1)
        if sum(self.failures) >= self.failure_threshold:
            self.state = "open"

    def call(self, fn, *args, fallback=None):
        if self.state == "open":
            return fallback() if fallback else None
        try:
            result = fn(*args)
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            return fallback() if fallback else None
```

### 4. Re-prompt for semantic recovery (Reflexion-style)

After a tool output fails validation, append a corrective prompt rather than retrying the same call:

```
# Previous attempt failed: tool returned X, expected Y.
# The task was Z. What went wrong? What should change?
# Suggest an updated tool call or strategy.
```

This is the Reflexion pattern (Shinn et al., NeurIPS 2023). The key design: the critique is **verbal and self-contained** — it doesn't require training or weights, just a re-prompt that appends failure context. Implementations exist in production using smolagents (`kargarisaac/reflexion`, 9 stars) and as a standalone framework.

The critical limitation: reflexive self-critique fails when the agent's reasoning produced the error — re-prompting the same model re-derives the same wrong path. For this class of failure, checkpoint-and-defer is the better pattern.

### 5. Checkpoint state for deferred recovery

Serialize the agent's state (conversation history, tool results, step count) after each successful step. On failure:

1. Write a recovery summary: "Ran steps 1–7 of N. Failed at step 8 because [reason]."
2. On next invocation, restore from checkpoint and resume.
3. If the failure was on a non-idempotent step, mark it and replay from the last safe checkpoint.

This requires tools to be idempotent or the checkpoint to include enough context to replay safely.

### 6. Escalate with a structured handoff

When recovery exhausts itself — max retries hit, circuit breaker open, step cap reached — escalate with a **structured failure report**:

```
Task: [original goal]
Failed at: [step number, tool name, timestamp]
Error type: [transient/client/semantic/resource/structural]
Recovery attempts: [N, with outcomes]
Partial result: [what the agent did manage to produce]
Handoff: [recommendation — retry / human review / abort]
```

A human reviewer or orchestrator agent can then decide: retry with modified context, proceed with partial output, or abort. The failure report is the contract — the agent's job is producing it, not making the escalate/retry decision unsupervised.

## Evidence

- **GitHub README (ARF):** The Agentic Reliability Framework (18 stars, Apache 2.0) explicitly cites that "73% of AI agent projects fail due to unpredictability, lack of memory, and unsafe execution" and builds a dual-layer architecture separating advisory intelligence from governed autonomous execution. Claims recovery-memory as a core design pillar. — [https://github.com/petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)
- **Academic paper (NeurIPS 2023):** Shinn et al. published "Reflexion: Language Agents with Verbal Reinforcement Learning" (3,223 GitHub stars, MIT license), demonstrating that agents which self-critique failure trajectories and append verbal feedback achieve statistically significant improvements on AlfWorld, HotpotQA, WebShop, and programming benchmarks vs. agents that retry without reflection. — [https://github.com/noahshinn/reflexion](https://github.com/noahshinn/reflexion)
- **Production engineering blog (fewsats):** A case study on improving HTTP SDK error surfacing for domain management AI agents found that incomplete error information was the primary cause of recoverable failures — agents couldn't self-correct because the SDK hid the actual error. Modifying the SDK to surface complete error details (not just status codes) enabled agents to self-correct on API errors without changing model behavior. — [https://www.zenml.io/llmops-database/improving-error-handling-for-ai-agents-in-production](https://www.zenml.io/llmops-database/improving-error-handling-for-ai-agents-in-production)
- **Engineering blog (Preporato):** "73% of AI agent projects fail" claim also attributed to ARF's cited NCP-AAI research. Proposes 6-pattern framework: retry with backoff, circuit breaker, fallback chain, graceful degradation, checkpoint/restore, and multi-agent consensus for critical decisions. — [https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)
- **Engineering blog (GoCodeo, 2025):** Notes that error recovery is "a core architectural concern, not an afterthought" and catalogs the distinction between traditional software errors (deterministic, reproducible) and agentic errors (probabilistic, cascading, semantically wrong). — [https://www.gocodeo.com/post/error-recovery-and-fallback-strategies-in-ai-agent-development](https://www.gocodeo.com/post/error-recovery-and-fallback-strategies-in-ai-agent-development)

## Gotchas

- **Re-prompting without error classification makes recovery worse.** If you re-prompt after a 429 rate limit, you're just hammering the same endpoint harder. Classify first.
- **Reflexion works for tool-call errors; it doesn't fix reasoning errors.** If the model's internal chain-of-thought produced the wrong answer, re-prompting the same model usually produces the same wrong answer. Use a separate (smaller, faster) verifier model for the critique step.
- **Non-idempotent tools break checkpoint/restore.** If your agent calls a payment API or sends an email, replaying from checkpoint creates duplicate side effects. Only checkpoint before non-idempotent steps, or use idempotency keys.
- **Circuit breaker thresholds are workload-specific.** A threshold of 5 failures in 10 calls works for a high-volume agent; it would trip immediately for a low-volume agent that gets 1 transient error per 50 calls. Calibrate to your error rate baseline, not a generic value.
- **Recovery attempts must be visible in traces.** If your observability platform shows retries as separate successful calls, you have a silent cost leak. Each recovery attempt should be labeled as such in the trace metadata so you can distinguish "1 run that retried 8 times" from "8 runs."
