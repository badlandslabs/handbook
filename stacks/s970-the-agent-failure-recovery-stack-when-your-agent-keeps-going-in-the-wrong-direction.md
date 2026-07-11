# S-970 · The Agent Failure Recovery Stack — When Your Agent Keeps Going in the Wrong Direction

Your candidate-evaluation agent worked perfectly in development. In production it hallucinated a tool parameter, got stuck trying the same fix, and ran for 23 steps before someone noticed. The trace looked clean. The cost was 3x budget. Every agent that reaches production hits some version of this. The fix isn't better prompts — it's a failure recovery architecture that treats the agent loop like a distributed system: bounded, observable, and recoverable.

## Forces

- Agents fail silently — a bad tool response returns HTTP 200, the agent continues confidently, and the wrong answer ships with no error code
- Infinite loops are budget killers — a loop generating 50 tokens/hr at GPT-4o rates burns $500+/hour, and naive loop detectors that count error types instead of iterations make it worse
- Recovery requires state you don't have — the agent committed a partial write, then crashed; downstream agents now work with corrupted state
- Traditional try/catch doesn't apply — hallucinated schemas, semantically wrong outputs, and valid JSON containing invalid data all look like success
- Retrofitting resilience is 10x harder than designing it in from the start

## The Move

Build failure recovery into the agent loop at the infrastructure level, not in the prompt.

1. **Hard step cap at the runtime loop** — The single most cost-effective guardrail. Enforce a maximum step count in the loop controller, not in the prompt. When the cap hits, return a structured stop reason (`max_steps_reached`, `loop_detected`, `cost_limit_exceeded`) with full state preserved for inspection and resume. Rajpoot recommends starting with `MAX_STEPS = 12` and tuning from production traces.

2. **Semantic loop detection** — Beyond simple step counts, detect when the agent repeats the same or equivalent tool calls. Track the last N (tool, parameters) pairs and compute semantic similarity. A financial services company burned $12,000 in compute and 47,000 failed API calls because their loop detector counted *distinct* error types instead of iterations — it saw three different error messages and concluded the loop was making progress.

3. **Tool output validation before propagation** — Validate every tool response against a Pydantic schema before it reaches the agent's next reasoning step. Catch truncated JSON, error-in-text that looks like success, and type mismatches at the gate, not 12 steps later. Rastogi's production experience: "one unstable tool response" → "repeat of same action" → cascade. Validation breaks the cascade.

4. **Exponential backoff with jitter for retries** — Transient failures (rate limits, network timeouts) should retry with exponential backoff and jitter, not immediate retry. A retry loop without backoff on a rate-limited API makes the problem worse. Separate retryable errors (429, 503, timeout) from non-retryable ones (401, 400 bad parameter) — only retry the former.

5. **Checkpoint state at decision points** — Use framework primitives (LangGraph's `MemorySaver`, Temporal's heartbeat checkpointing) to persist state at meaningful boundaries. On failure, resume from the last checkpoint rather than restarting from scratch. The rule: if removing a field from state wouldn't change any conditional edge, it doesn't belong in state — bin large payloads to external storage (S3, Postgres) and reference by ID.

6. **Graceful degradation chains** — For each tool, define an explicit fallback path: primary API → secondary API → cached response → human-in-the-loop. A research agent that can't reach the vector DB should degrade to cached results with a confidence flag, not fail the entire pipeline. The pipeline should specify what "good enough" looks like at each degradation tier.

7. **Cost circuit breaker** — Separate from step caps: track cumulative cost per run and hard-stop when a threshold is crossed. A runaway agent can generate $X in compute before a step cap catches it if each step is expensive. Set cost limits per task type.

## Evidence

- **Blog post:** "LLM Agent Error Recovery in 2026 — Patterns That Don't Loop Forever" — Hard step caps, tool-level retries, fallback paths, and cost circuit breakers with production code examples — [blog.rajpoot.dev](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026)
- **Engineering post:** "Agentic AI in Production: Error Recovery, Observability, and Scaling Patterns" — Tool parameter hallucination, loop detection, checkpointing, and the 3x budget overrun from a candidate evaluation agent in production at Modelia.ai/Asynq.ai — [harshrastogi.tech](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Engineering post:** "Loop Detection & Breaking: Stop Infinite Agent Loops" — $12,000 loop cost case study, iteration counts vs. error-type counting, token budget controls — [trackai.dev](https://trackai.dev/tracks/observability/debugging-tracing/loop-detection)
- **AI Codex article:** "Multi-agent failure handling: timeouts, partial outputs, and recovery patterns" — Five critical failure modes (timeout mid-pipeline, partial output, cascading failure, silent degradation, state inconsistency), write-ahead logging, idempotency keys — [aicodex.to](https://www.aicodex.to/articles/multi-agent-failure-handling)
- **HN thread:** "Agent-triage – diagnosis of agent failures from production traces" — New open-source tool for classifying agent failures from production traces — [news.ycombinator.com/item?id=47334775](https://news.ycombinator.com/item?id=47334775)
- **AI2 Incubator report:** "State of AI Agents 2025" — 86% of enterprise agent pilots never reach full production; the gap between working demos and reliable production is where projects die — [agentmarketcap.ai](https://agentmarketcap.ai/blog/2026/04/08/ai2-incubator-state-of-ai-agents-2025-deployment-reality)

## Gotchas

- **Prompts don't enforce limits** — Putting "stop after 10 steps" in the system prompt is advisory only. The agent can ignore it. Enforce step caps at the loop controller level where code runs unconditionally.
- **Step caps ≠ loop detection** — A step cap stops the agent after N iterations regardless of progress. A loop detector notices when the agent is stuck on the same problem and stops sooner. You need both: step cap as the floor, loop detection as the smart layer above it.
- **Silent failures look like success** — The hardest class of agent failure. An agent that completes 23 steps on corrupted context returns HTTP 200 and confident output. Only output validation at each tool boundary catches this.
- **Checkpointing without idempotency is dangerous** — A checkpoint taken mid-write can replay a partially-completed operation. Every tool call that has side effects needs idempotency keys to make replay safe.
