# S-2653 · The Autonomous Recovery Stack — When Your Agent Retries the Same Mistake 11 Times

Your agent is retrying. Third attempt, same error. Then fifth. Then eleventh. This is not resilience — this is a loop with a counter. Real autonomous recovery classifies the error, picks the right response, and either succeeds or fails cleanly. Most production agent code has retry logic and nothing else.

## Forces

- **Retry logic is the default, not the solution.** Teams implement `try N times with exponential backoff` and call it error handling. But retry addresses exactly one failure class: transient infrastructure hiccups. A hallucinated tool argument, a budget ceiling hit, and a missing permission all fail retry differently — and retrying a hallucinated argument 11 times wastes money and burns the context window.
- **Agentic failures cascade silently.** Unlike traditional software where errors surface as exceptions, agentic errors return HTTP 200, produce valid JSON, and look like success. The agent moves on from a failed API call having stored partial state, leaving the next step operating on corrupted context.
- **State loss is the real killer.** A 20-step agent workflow that fails at step 15 has already sent emails, written to databases, and called external APIs. If you replay from step 1 to recover, you get duplicate actions with real-world consequences. If you can't replay, the session is dead.
- **The budget-paused state is missing from most frameworks.** When an agent hits its token or cost ceiling mid-task, the naive response is crash or loop. The right response is `budget-paused` → notify orchestrator → await top-up → resume. Almost nobody implements this.

## The move

Implement a layered recovery stack where each layer handles a distinct failure class. Error classification precedes all recovery decisions. State is checkpointed before any side-effectful operation so recovery is deterministic replay, not LLM reasoning about what went wrong.

**Layer 0 — Classify before acting.** Every error routes through a classifier before triggering a response. The classifier tags it as `transient`, `budget`, `capability`, `semantic`, or `fatal`. This tag drives all downstream decisions.

**Layer 1 — Retry transient infrastructure errors.** Use exponential backoff with jitter (1s → 60s, ±30%). AWS research found this reduces retry storms by 60–80% vs. fixed-interval. Configure per-tool: a payment API trips the circuit breaker after 1 consecutive failure; a search API tolerates 3.

**Layer 2 — Route non-transient errors to targeted handlers.** `budget` errors enter `budget-paused` state and signal the orchestrator. `capability` errors escalate to the parent agent. `semantic` errors (LLM output failed validation) retry with an explicit format correction injected into the next system prompt. `fatal` errors mark the task failed, return partial results with an error receipt, and stop — no more LLM calls.

**Layer 3 — Checkpoint state before side-effectful steps.** Use an append-only checkpoint store (DynamoDB, Redis, or a LangGraph `MemorySaver`) before any step that calls external APIs, writes data, or sends messages. Never mutate persisted state — append-only semantics enable both replay and audit.

**Layer 4 — Deterministic recovery, not LLM recovery.** When a step fails, the system replays from the last checkpoint using a pre-validated recovery workflow. The LLM does not reason about recovery paths — it executes a stored recovery plan.

**Layer 5 — Circuit breakers per tool.** Each tool gets its own circuit breaker with failure threshold and recovery timeout tuned to the tool's criticality. Critical tools (payment processing) trip on 1 failure; tolerant tools (search) tolerate 3.

## Evidence

- **GitHub Discussion (Anthropic SDK):** A practitioner running 5 AI agents 24/7 for 95+ days at miaoquai.com reported 97.8% autonomous recovery using a 4-layer error recovery stack: connection resilience (exponential backoff + circuit breaker after 5 consecutive failures), model fallback chain (Opus → Sonnet → Haiku → queue), tool failure isolation (30-second tool timeout, degraded continuation), and semantic correction with tool self-testing (openclaw-skill-validator achieves 100% self-test score). — [github.com/anthropics/anthropic-sdk-python/discussions/1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

- **AWS Database Blog (Jan 2026):** AWS publishes `DynamoDBSaver`, a LangGraph checkpoint library that persists agent state to DynamoDB with S3 offload for large payloads. Demonstrates checkpoint-then-act pattern: save state before every tool call, resume from any checkpoint. The thread model tracks conversation history and arbitrary custom state across distributed, long-running agent sessions. — [aws.amazon.com/blogs/database/build-durable-ai-agents-with-langgraph-and-amazon-dynamodb](https://aws.amazon.com/blogs/database/build-durable-ai-agents-with-langgraph-and-amazon-dynamodb)

- **Code Worm (May 2026):** Production patterns piece identifies six non-negotiables for agent workflow state management: checkpoint immutability (append-only, never mutate), memory scope isolation (phase-scoped, not global), deterministic recovery (pre-validated workflows, not LLM reasoning), loop detection (count tool-call attempts per step, hard cap), rollback (compensating actions in reverse order), and human escalation (every automated recovery layer has an exit gate to a human). — [codewormdev.blogspot.com/2026/05/agent-workflow-state-management.html](https://codewormdev.blogspot.com/2026/05/agent-workflow-state-management.html)

- **Cleanlab Enterprise Survey (2025):** Only 95 of 1,837 surveyed organizations (≈5%) had AI agents live in production. Among those, the top failure mode was observability gaps — teams could see that agents were failing but couldn't determine the failure class or recover autonomously. — [cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)

## Gotchas

- **Hard cap your retry loops, or you'll burn budget on hallucinated arguments.** A model that produces invalid JSON will likely produce invalid JSON again. After 2–3 retries with the same prompt, inject a format correction or escalate — don't loop forever.
- **Append-only checkpoints are only useful if you replay them.** Teams persist state correctly but never implement the replay path. Test recovery by killing an agent mid-step and verifying it resumes correctly from the last checkpoint — not just that state was saved.
- **Model fallbacks are not the same as error recovery.** Swapping from GPT-5 to Sonnet when the primary model errors is useful for availability, but it does not address `semantic` or `budget` failures. Model fallback is Layer 2 availability; error classification and routing is what makes recovery autonomous.
- **Silent failures are the worst failures.** An agent can return HTTP 200 with hallucinated data, or an MCP server can go dark for 3 days without erroring. Instrument every tool call with a 30-second timeout and a health check that pings each tool's endpoint independently.
