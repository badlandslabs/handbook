# S-1233 · The Agent Comes Back Alive Stack — When Your Agent Fails But Shows No Sign It Did

You deployed an agent. It returns HTTP 200. The monitoring dashboard is green. But the agent got stuck in a loop at step 3, hallucinated a tool parameter, and burned $400 of API credits before someone filed a complaint. Standard observability doesn't catch this class of failure.

## Forces

- **Monitoring lies differently than code.** Classic APM catches crashes, timeouts, HTTP errors — all the things agents don't do when they fail. Agents fail by succeeding at the wrong thing, or looping forever while returning 200.
- **Retrying is dangerous, not safe.** In traditional software, retry until it works is fine. In agents, a replayed tool call can create a second ticket, send a duplicate email, or push a config change twice. Idempotency can't be assumed.
- **Silent failures have no floor.** A crashed microservice fails loudly. An agent that silently degrades can cost thousands before anyone notices.
- **The failure taxonomy is different.** Agents fail in five modes that standard error handling doesn't cover: tool-call loops, semantic failures (technically correct, contextually wrong), hallucinations, non-deterministic output that breaks parsers, and token limit violations.
- **73% of AI agent projects fail** due to unpredictability, lack of memory, and unsafe execution — not because the model was wrong.

## The Move

Design for failure detection, cost containment, and safe recovery as first-class concerns — not afterthoughts.

**Detect before it costs:**
- Set hard iteration caps (`max_iterations=10` in LangChain, or equivalent guard in your framework) to break loops. The most common cause: ambiguous tool descriptions or missing stop conditions that cause the agent to retry the same failed action indefinitely.
- Instrument loop detection at the call-site level — track identical action sequences within a session window. If the agent tries the same tool with the same parameters N times in a row, break.
- Add cost guards that halt execution at a daily budget ceiling. AgentFuse uses SQLite WAL mode to track spend across concurrent agents and tabs, halting execution before credit is exhausted.

**Classify failures by type, not just presence:**
- Distinguish transient errors (rate limit, timeout) from semantic errors (hallucinated params, wrong output shape) from architectural errors (loop, token limit). Each class has a different recovery path.
- Use structured reason codes on every failure — not just "failed" but `"max_scheduling_retries"`, `"llm_hallucination_detected"`, `"output_parse_failed"`. These codes drive downstream retry policy and DLQ routing.

**Route failures to the right destination:**
- **Exponential backoff with jitter** for transient errors (rate limits, brief API outages). Start with a 1-second delay, multiply by 2, cap at 5 minutes, add random jitter to avoid thundering herd.
- **Circuit breaker** for downstream services that are genuinely down. After N failures in a window, stop calling the service for a cooldown period. This prevents cascading failures when a dependency is unavailable.
- **Escalation queue / dead letter queue** for failures that can't be auto-resolved. Emit structured metadata (reason code, step number, idempotency key, attempt count) to a DLQ with a human review gate. Cordum caps scheduling retries at ~50 attempts (~25 minutes), then emits to DLQ with a `replay_status: pending_review` flag.
- **Checkpoint-and-resume** for long-running workflows. Save state at each step boundary. If the agent crashes, resume from the last checkpoint rather than restarting from scratch. Critical for workflows that span hours.

**Diagnose after the fact:**
- agent-triage (converra/agent-triage) extracts behavioral policies from system prompts, replays traces step-by-step with an LLM-as-judge, and identifies which turn broke things, which agent caused it, and how failures cascade across routing and handoffs.
- Aggregate root causes across all conversations — e.g., "24 out of 51 failures are missing escalation logic" — to target systemic fixes rather than per-case patching.

## Evidence

- **DEV Community post:** An agent got stuck in a retry loop and burned API credits — the monitoring tools showed nothing. LangSmith, LangFuse, Arize, and Helicone all show latency and token counts but don't answer "is my agent actually reliable right now." The author found the failure from a billing alert, not an alert. — [dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing](https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai)
- **Cordum DLQ analysis:** DLQ replay without idempotency key checks can cause duplicate side effects. A replayed tool call in a ticket-creation workflow creates a second ticket. Reason-code quality is a hard dependency — vague errors turn replay into guesswork. — [cordum.io/blog/ai-agent-dlq-replay-patterns](https://cordum.io/blog/ai-agent-dlq-replay-patterns)
- **AgentFuse GitHub:** A developer fell asleep while a script was running and woke to a drained OpenAI balance. AgentFuse wraps the OpenAI client as a drop-in shim (supports LangChain), uses SQLite WAL mode for persistence, and enforces hard daily budget limits to prevent runaway costs. — [github.com/AgentFuse](https://github.com/jetspidee/agent-fuse) (via [jetspidee.blogspot.com](https://jetspidee.blogspot.com/2025/12/show-hn-agentfuse-local-circuit-breaker.html))
- **AI Agents Blog:** Five production patterns with implementations: exponential backoff with jitter, circuit breaker, checkpoint-and-resume, fallback strategies, and escalation queue — all built on the Anthropic SDK. — [aiagentsblog.com/blog/agent-error-recovery-patterns](https://aiagentsblog.com/blog/agent-error-recovery-patterns/)
- **agent-triage GitHub:** Diagnoses agent failures from production traces by extracting policies from prompts, evaluating traces step-by-step, and aggregating root causes across conversations. — [github.com/converra/agent-triage](https://github.com/converra/agent-triage)
- **Agentic Reliability Framework (ARF):** Reports 73% of AI agent projects fail due to unpredictability and unsafe execution. Provides multi-agent self-healing with advisory AI + enterprise execution. — [github.com/petterjuan/agentic-reliability-framework](https://github.com/petterjuan/agentic-reliability-framework)

## Gotchas

- **The DLQ is not a trash can.** A DLQ record with no reason code and no idempotency key is un-actionable. Emit structured metadata on every failure or you won't be able to safely replay.
- **Max iterations without early stopping method is a blunt instrument.** LangChain's `early_stopping_method='generate'` lets the model self-evaluate whether to continue, which cuts token waste more intelligently than a hard cap alone.
- **Cost guards need to survive restarts.** If you only track spend in-memory, a crash loses the budget state. Use a persistent store (SQLite WAL, Redis, a database) that survives process restarts.
- **Auto-replay lowers pager load but can hide systemic defects.** If the same job keeps landing in the DLQ and replaying successfully, you have a flaky dependency — not a transient failure. Monitor DLQ depth per reason code, not just total DLQ volume.
- **Monitoring tools optimized for LLMs (LangSmith, LangFuse) answer "what happened" but not "is it working."** Build business-level assertions — is the agent routing tickets correctly? approving the right images? — as a layer above trace observability.
