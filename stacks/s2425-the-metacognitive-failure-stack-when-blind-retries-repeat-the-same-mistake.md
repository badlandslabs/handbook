# S-2425 · The Metacognitive Failure Stack — When Blind Retries Repeat the Same Mistake

Your agent hits a rate limit, waits 5 seconds, and retries — with the same request, the same parameters, the same rate limit. It hits a tool that returns an empty result, logs "success," and continues building on nothing. It loops through the same three tool calls 30 times because nobody told it that converging was an option. Blind retries are not resilience. They are faster repetition of the same mistake. The teams that break this pattern have built metacognitive failure infrastructure: agents that classify failures, predict their own errors, and act differently on the second attempt.

## Forces

- **Agents need to distinguish failure types before recovering.** A rate limit, a hallucinated parameter, and a missing file require three different responses. Treating them the same is the root cause of repeated failure.
- **Self-prediction is harder than self-correction.** Detecting that you're about to fail is a harder problem than recovering after you fail — but it's also higher leverage, because it prevents cascading consequences.
- **Exactly-once semantics matter for side effects.** Agents that send emails, write records, or mutate state cannot naively retry on failure — the side effect may have already happened. Idempotency is not optional.
- **LLMs are not good critics of their own output.** Multiple practitioner reports find that LLM-as-judge approaches underperform structured eval suites on agent tasks. The agent that generated the failure cannot reliably grade whether it has been fixed.

## The move

Classify failures into domains, predict failures before they happen, enforce exactly-once semantics on side-effecting operations, and route each failure class to its appropriate recovery action.

**Failure classification taxonomy (AgentRx, OpenClaw):**
- `AGENT_LOOP` — repeated tool calls with no state change → break the loop, summarize partial progress, escalate
- `RATE_LIMIT_EXCEEDED` — transient throttle → exponential backoff with jitter, do not retry with same parameters
- `AUTH_FAILURE` → stop and surface credential issue, not retry
- `HALLUCINATED_PARAM` / `HALLUCINATED_VALUE` → the model invented a parameter or value that the tool doesn't recognize → re-plan, don't retry
- `SCHEMA_MISMATCH` → tool output format changed → re-fetch schema, don't retry with same assumptions
- `RESOURCE_MISSING` → file/endpoint doesn't exist → check existence before calling
- `TOOL_DEPRECATED` → tool signature changed → re-generate tool manifest
- `NETWORK_LATENCY` → timeout but operation may have succeeded → check idempotency key before retry
- `EXPLICIT_ERROR` — tool returned error keyword or non-zero exit code → parse error, route to domain-specific recovery
- `SILENT_FAILURE` — exit code 0 but output is empty, truncated, or implausible → validate output shape before continuing

**Preflight checks before risky calls:**
- Does the resource exist? (孔雀 before calling tools on specific files/records)
- Does the auth token still validate? (don't wait for a 401 mid-operation)
- Are the parameters within plausible bounds? (catch hallucinated IDs before the call)

**Exactly-once execution guard (SafeAgent pattern):**
- Wrap side-effecting tool calls in idempotency keys
- On failure, check whether the operation succeeded before retrying — don't re-send an email that already sent
- Log every side effect with a deterministic operation fingerprint

**Structured recovery routing:**
- Transient errors → retry with backoff, capped at N attempts
- Permanent errors → halt, log, surface to operator
- Ambiguous errors → fall back to human-in-the-loop handoff
- Loop detection → after N identical tool-call patterns, break and summarize

**Metacognitive self-correction (arxiv:2509.19783):**
- Agents that predict failure before attempting a tool call catch 30–40% of errors before they cascade
- Two-level architecture: one layer executes tasks, one layer monitors for failure signatures and revises the task-layer's beliefs
- Knowledge base revision: when users flag an error, the agent updates its KB so the mistake doesn't propagate to the next session

## Evidence

- **GitHub repo + blog post:** "Failure Recovery: real agents need more than retries" — proposes the four-category failure taxonomy (explicit, silent, structural, cascading) and the failure-domain map pattern with recovery routing per category — [https://dangroch.com/2026/03/16/failure-recovery-for-ai-agents](https://dangroch.com/2026/03/16/failure-recovery-for-ai-agents) + [https://github.com/dgroch/metacognition](https://github.com/dgroch/metacognition)

- **GitHub repo (AgentRx):** Metacognitive recovery API that classifies tool failures into 10 signatures and returns a plaintext recovery instruction. Integrates with LangChain, CrewAI, and OpenClaw. Failure signatures include `AGENT_LOOP`, `HALLUCINATED_PARAM`, `SCHEMA_MISMATCH`, `TOOL_DEPRECATED`, `NETWORK_LATENCY` — [https://github.com/chainassetslab/agentrx](https://github.com/chainassetslab/agentrx)

- **GitHub repo (Vectara):** awesome-agent-failures — community-curated collection of 7 core failure modes (tool hallucination, response hallucination, goal misinterpretation, infinite loops, context overflow, tool call chaining, security/reliability) with battle-tested mitigations and real-world case studies. 195 stars, 89 commits — [https://github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)

- **HN Show HN:** SafeAgent — exactly-once execution guard for AI agent side effects. Uses idempotency keys and pre-retry state checks to prevent duplicate side effects. Posted 4 months ago — [https://news.ycombinator.com/item?id=47294291](https://news.ycombinator.com/item?id=47294291)

- **arXiv paper:** "Agentic Metacognition: Designing a Self-Aware Low-Code Agent for Failure Prediction and Human Handoff" — proposes two-level metacognitive architecture where a monitoring layer predicts failures before the task layer attempts operations. Benchmarks show 30–40% of cascading errors caught pre-attempt — [https://arxiv.org/html/2509.19783v1](https://arxiv.org/html/2509.19783v1)

- **Blog post:** "Error Handling Strategies for AI Agents" — distinguishes transient (retry with backoff), permanent (halt and surface), and ambiguous errors. Proposes circuit breaker pattern to prevent cascading failures across tool calls — [https://kangclaw.github.io/posts/error-handling-strategies-for-ai-agents](https://kangclaw.github.io/posts/error-handling-strategies-for-ai-agents)

## Gotchas

- **Don't retry with the same parameters.** The most common mistake. If the failure is `HALLUCINATED_PARAM`, retrying with the same invented parameter is guaranteed to fail again. Re-plan, re-generate parameters, then retry.
- **Loop detection requires state tracking, not just call counting.** Counting tool calls is not enough — the agent needs to track whether state is actually changing. Identical tool calls with different parameters may be productive exploration; identical tool calls with identical parameters and no state change is a loop.
- **Exactly-once for agents is harder than for services.** A service call can be wrapped in a transaction. An agent tool call that sends an email cannot be rolled back. The guard must check whether the side effect happened before retrying, not just whether the call returned an error.
- **Human handoff must be frictionless.** When the agent escalates, it must pass not just the failure type but the full context: what it tried, what it observed, what it concluded, and what partial progress was made. A bare "I failed" handoff creates more work than the failure itself.
