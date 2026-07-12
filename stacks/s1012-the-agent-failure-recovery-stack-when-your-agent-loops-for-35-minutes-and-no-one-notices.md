# S-1012 · The Agent Failure Recovery Stack — When Your Agent Loops for 35 Minutes and No One Notices

A conventional service crashes and logs a stack trace. An agent may silently loop for 35 minutes, burn 250,000 API calls in a day, or confidently execute a destructive action based on corrupted state passed from an upstream agent. Traditional try-catch doesn't cover these failure modes. The agents aren't broken — they're doing exactly what they were prompted to do. Recovery requires deliberate, systemic design.

## Forces

- **Agents fail with HTTP 200.** The most dangerous errors return success codes while being fundamentally wrong — hallucinated tool calls, valid JSON with wrong schema, semantically incorrect reasoning. A crash you notice beats a success you trust.
- **Recovery mechanisms run away.** The mechanisms designed to keep agents running are the mechanisms most likely to run them off a cliff. A compaction routine with no retry ceiling burned 250,000 API calls in a production incident.
- **State propagates faster than failures.** In a multi-agent chain, Agent A passes slightly malformed state to Agent B, which confidently executes a destructive action. The root cause is three steps up the chain and invisible by the time the error surfaces.
- **Turn limits feel like defeating the agent.** Developers resist capping reasoning steps because it feels like second-guessing the model. In practice, uncapped agents are a liability.

## The move

Layer four distinct protections — from cheapest to most expensive — so a single failure doesn't cascade:

**1. Hard turn/step limits (always first).**
Cap the maximum LLM reasoning steps per task (e.g., 50-100 turns). This is the single highest-leverage guardrail. Without it, agents can loop indefinitely on any task that doesn't produce an explicit stop signal. Pair with a semantic loop detector: if the last N tool calls are semantically identical (same tool, similar arguments), terminate even before the hard limit.

**2. Tool-level circuit breakers.**
Track failure rates per tool in a rolling window. When failures exceed a threshold (e.g., 5 failures in 2 minutes), open the circuit — return a fast fallback immediately instead of making the network call. Three states: CLOSED (normal), OPEN (fast-fail, cooldown), HALF-OPEN (probe one request). This prevents retry amplification from killing a degraded dependency.

**3. Saga pattern with compensating actions for multi-step workflows.**
Register a rollback function alongside each step. When a downstream step fails, execute compensations in reverse order. Example: `reserve_flight → reserve_hotel → charge_card`. On `charge_card` failure, execute `cancel_hotel → cancel_flight`. Don't try to undo; explicitly define what "undo" means for each step.

**4. Checkpoint state persistence for long-running tasks.**
Serialize agent state (memory contents, conversation history, intermediate results, progress markers) at defined checkpoints. On interruption (timeout, crash, manual restart), restore from the last checkpoint instead of restarting from scratch. Critical for tasks exceeding context-window timeouts or running on ephemeral infrastructure.

**5. Human-in-the-loop escalation for high-stakes actions.**
Define confidence thresholds below which the agent surfaces the decision rather than proceeding. For irreversible actions (sending emails, executing code, financial transactions), queue the output for operator review. Build a clear operator interface to view agent state and approve/reject/correct.

## Evidence

- **Hacker News discussion (Ask HN):** "The hardest failure mode we've had to debug isn't a single agent hallucinating; it's Agent A correctly doing its job, but passing slightly malformed state to Agent B, which then confidently executes a destructive action based on that bad state." Cross-agent state corruption propagates faster than it surfaces. — [HN #47358618](https://news.ycombinator.com/item?id=47358618)
- **Hacker News discussion:** "The #1 production failure I've seen in multi-agent systems: state collision. Two agents read shared context at nearly the same time, process independently, then one overwrites the other's changes." — [HN #47358618](https://news.ycombinator.com/item?id=47358618)
- **Autonomous AI agent architect (Brandon Lincoln Hendricks):** A document analysis agent for a financial services client had no checkpointing. A single Cloud Run timeout after 58 minutes of processing meant starting from scratch. A compaction routine with no retry ceiling burned 250,000 API calls in one day. — [BLH Research: Checkpointing](https://brandonlincolnhendricks.com/research/implementing-agent-checkpointing-recovery-patterns-long-running-ai-tasks) and [BLH Research: Circuit Breakers](https://brandonlincolnhendricks.com/research/circuit-breaker-patterns-ai-agent-reliability)
- **Odea Works (Connor O'Dea, April 2026):** Built ClawdHub (13K+ line orchestration platform) and AgentAgent (multi-agent coordinator). Key finding: traditional try-catch is insufficient because errors return HTTP 200 — the failure is semantic, not syntactic. — [Odea Works](https://odeaworks.com/blog/2026-04-05-ai-agent-error-handling-best-practices)
- **Neel Mishra (MLOps: LLM Agents):** Agent errors divide into four categories requiring different recovery: transient (retry with backoff), semantic (re-prompt with corrective context), resource (checkpoint and resume), and integration (circuit breaker). — [Agent Error Handling](https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html)
- **Agentic Patterns catalog (March 2026):** Circuit breaker pattern status: "maturing." Tracks per-tool failure rates. On cascade: token waste, latency amplification, cascading failures into dependent components. — [Agentic Patterns: Circuit Breaker](https://www.agentic-patterns.com/patterns/agent-circuit-breaker)
- **DEV Community (Alessandro Pignati, 2025):** Infinite loops in agents aren't explicit code — they emerge from how agents interact. Foundational guardrails: hard turn limits, clear termination functions, mandatory final states, circuit breakers. Advanced: semantic similarity analysis of recent tool calls to detect subtle loops. — [DEV Community](https://dev.to/alessandro_pignati/stop-the-loop-how-to-prevent-infinite-conversations-in-your-ai-agents-ekj)

## Gotchas

- **Retry identical prompts for semantic errors.** Transient errors (rate limits, timeouts) respond to retry. Semantic errors (wrong schema, hallucinated tool) do not — re-prompting with the parse error as context is the fix. Retrying without correction just reproduces the same wrong output.
- **Circuit breakers applied to LLM calls must handle non-deterministic responses.** Unlike a binary health check on a microservice, an LLM that returns a semantically degraded response isn't "down" — it's still serving traffic. Track quality degradation (repetitive output, falling confidence scores), not just failure counts.
- **Compensating actions can themselves fail.** Design saga rollbacks to be idempotent and log failures without throwing. A compensation that fails silently leaves the system in an inconsistent state.
- **Checkpointing adds latency if done synchronously.** Flush checkpoints asynchronously and on explicit progress milestones (not every step). Store checkpoints in durable storage (S3, Redis) — in-memory checkpoints survive process crashes but not infrastructure failures.
