# S-2829 · The Dead Letter Queue Stack — When Your Agent Fails Silently and Costs You Money

[Your agent ran for 11 days straight. It never crashed. It never raised an exception. It just silently looped between two other agents, each one treating the other's output as input, until the bill hit $47,000. No alert fired. No human checked. The system was, by every technical measure, running fine.]

## Forces

- **Agents fail semantically, not structurally.** Unlike a crashed microservice, an agentic failure is often a confident wrong answer, a hallucinated tool argument, or a looping plan — all returning HTTP 200. Traditional error budgets don't see this.
- **Retry logic has no ceiling.** A message queue retry count prevents infinite redelivery. An agent retry loop has no natural stopping condition — it runs until the context window fills, the budget drains, or a human notices.
- **Checkpointing ≠ durable execution.** Persisting state after each step protects against crashes but does nothing for semantic loops — the agent is perfectly state-consistent while being completely wrong.
- **Escalation is opt-in, not default.** Every agent framework lets you build an escalation path. Nearly none of them make it the default behavior when task completion genuinely cannot be achieved.

## The move

The DLQ (Dead Letter Queue) pattern from message-queue engineering translates to agentic systems with a key modification: agent failures are semantic, not structural, so the queue entry must carry the full execution context, not just a retry count.

**Layer 1 — Error classification before retry.** Not all failures are equal. Classify into: transient (429, timeout → retry), semantic (malformed output → re-prompt with correction), resource (token budget → checkpoint and defer), and fatal (401, revoked key → abort immediately). Only transient errors get automatic retry; everything else needs a human decision.

**Layer 2 — Per-tool circuit breakers.** Track failure counts per tool. When a tool crosses a threshold (e.g., 5 consecutive failures), trip the circuit and fail fast on all calls to it. This stops agents from burning tokens retrying a degraded external API. The AgentCircuit library (GitHub, MIT) implements this as a decorator — it detects loops, auto-repairs outputs, and enforces a configurable budget cap per run.

**Layer 3 — Checkpoint state at transition points.** Save minimal checkpoint state before every expensive, irreversible, or user-visible step. The checkpoint captures: run_id, completed_steps, pending_step, fallback_status, and next_safe_action. This isn't a full memory dump — it's the recovery payload. If the run crashes or loops, a supervisor can read this and determine whether to resume, reroute, or escalate.

**Layer 4 — Escalation budget per task.** Set a maximum token spend and step count per task. When both are exhausted without completion, route to a human-in-the-loop queue instead of retrying. The DLQ entry includes the full conversation history, all tool outputs, the failure classification, and a suggested next action. CrewAI v0.5 and LangGraph both support interruption points at designated graph nodes for this.

**Layer 5 — DLQ inspection and replay.** Failed tasks sit in the queue with metadata. Operators triage: fix the root cause (tool broken? prompt drifted? model degraded?), then replay from the last checkpoint. The replay is idempotent — the checkpoint makes it so. The vinod-mishra/langgraph-dead-letter-queue repo demonstrates this pattern with Pydantic v2 and LangGraph.

## Evidence

- **Blog post (Tian Pan, formerly Uber/Brex/IoTeX):** A multi-agent research tool ran 11 days with two agents cross-referencing each other's outputs in a loop — $47,000 in charges before discovery. No alert fired. Pan uses this as the anchor case for why DLQ semantics are essential for agents, not just messages. — [tianpan.co/blog/2026-05-05-dead-letter-queues-agent-task-failures](https://tianpan.co/blog/2026-05-05-dead-letter-queues-agent-task-failures)
- **GitHub repo (tanayshah11/ai-agent-error-patterns, MIT):** Production error-handling patterns for Trigger.dev v4 including circuit breaker, partial success, human-in-the-loop escalation, and graceful degradation — all with CLI tests that run in ~3ms for CI/CD. — [github.com/tanayshah11/ai-agent-error-patterns](https://github.com/tanayshah11/ai-agent-error-patterns)
- **GitHub repo (vinod-mishra/langgraph-dead-letter-queue):** LangGraph + Pydantic v2 implementation of a defensive orchestration pattern that isolates runtime agent failures by routing them to a DLQ for inspection and replay. — [github.com/vinod-mishra/langgraph-dead-letter-queue](https://github.com/vinod-mishra/langgraph-dead-letter-queue)
- **LangChain blog (Fault Tolerance in LangGraph, June 2026):** Documents error handlers, retry policies, and timeout handling as first-class LangGraph primitives — including per-step interruptibility for human review. — [langchain.com/blog/fault-tolerance-in-langgraph](https://www.langchain.com/blog/fault-tolerance-in-langgraph)
- **Research blog (Neel Mishra):** Four-category agent error taxonomy (transient, semantic, resource, fatal) with distinct recovery strategies per category. Recommends adaptive retry combining exponential backoff with circuit breaker state transitions. — [neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)

## Gotchas

- **A retry count alone is not a DLQ.** The message-queue DLQ pattern uses retry count as the termination condition. For agents, retry count is necessary but not sufficient — you also need semantic failure classification and a human decision for resource/fatal categories.
- **Checkpointing prevents crashes but not loops.** The most expensive agent failures (semantic loops) are perfectly state-consistent. You need a step-count ceiling and a plan-change detector, not just persistence.
- **Failing fast at the circuit breaker is the hard part.** It's tempting to keep retrying a degraded tool "just in case." Don't. A 20% fallback rate is a signal that your primary strategy has a systemic issue, not a resilience one.
- **DLQ replay must be idempotent.** If your agent wrote side effects before failing (sent an email, posted to Slack), replaying the task will duplicate them. Design idempotent action boundaries — or gate replay behind a human approval step.
