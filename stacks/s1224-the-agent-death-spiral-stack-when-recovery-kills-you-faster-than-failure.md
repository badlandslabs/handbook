# S-1224 · The Agent Death Spiral Stack — When Recovery Kills You Faster Than Failure

Your agent hit an error. It retried. Failed again. Retried differently. Now it's burning $400/hour, has spawned four redundant subprocesses, and nobody has noticed because the error logging is buried in a language-model output. The original failure was recoverable. The recovery logic killed the production system. This is the death spiral pattern: the most dangerous failure mode in agentic AI isn't the crash — it's the cure.

## Forces

- **Recovery logic has no ceiling by default.** The mechanisms designed to keep agents running (retries, fallback models, re-prompting) are also the mechanisms most likely to accumulate unbounded cost and context. A recovery loop without a hard stop condition will run until the billing stops.
- **Agents fail silently in ways software doesn't.** A conventional web service crashes and logs a stack trace. An agent may silently loop for 35 minutes, spawn redundant subprocesses, accumulate context until the model halts, or take an irreversible action before human intervention. The failure modes are qualitatively different from traditional software.
- **Naive agent loops compound costs at O(N²).** LLM APIs bill the entire conversation history on every call. A 20-step loop can consume over 10x the tokens a linear per-step estimate suggests. The cost isn't in the prompts — it's in the loop mechanics.
- **Detection latency is measured in thousands of dollars.** By the time a human notices an agent is looping, the damage is already done. The incident that burned 250,000 API calls in a single day was not caught by any monitoring — it was discovered during a billing review.

## The Move

The death spiral isn't a bug in your agent. It's a gap in your recovery governance. Fix it at three layers:

- **Hard circuit breakers on every recovery path.** Every retry, re-prompt, and fallback branch must have: a maximum attempt count, a per-attempt timeout, an exponential backoff schedule, and a hard fallback to human escalation when the ceiling is hit. The circuit breaker trips before the agent can compound the failure.
- **Supervisor hierarchy, not flat parallelism.** Every agent that can spawn sub-agents needs a parent that monitors it. The supervisor watches for: iteration counts exceeding a threshold, context accumulation exceeding a budget, cost accumulation exceeding a per-task cap, and tool-call patterns that indicate looping. The supervisor can kill and restart the child without human intervention.
- **Checkpoint state, not conversation state.** Save a serializable task state (not the full LLM context) at each step boundary. On failure, recover from the last checkpoint rather than replaying from the beginning. This reduces both cost and latency on recovery, and makes the recovery path auditable.
- **Cost and iteration telemetry as first-class signals.** Log cost-per-step, iteration count, and context size on every loop iteration. Alert on anomalies. A $2,000/month agent that suddenly costs $14,000 should page someone before it reaches $40,000.
- **Recovery logic needs its own tests.** Test that the recovery path has a ceiling. Test that the ceiling triggers. Test that the fallback to human escalation fires correctly. The recovery path is the most critical code in your agent system and the least tested.
- **Graceful degradation over heroic recovery.** When an agent can't complete a task, the right behavior is often to return a partial result with confidence level, not to keep trying. Degraded output is better than a runaway process.

## Evidence

- **Incident post-mortem (Zylos Research):** An agent's compaction logic had a bug where each failure triggered a deeper compaction attempt. No maximum depth was set. Before the engineering team noticed, the bug burned roughly 250,000 API calls in a single day. The agent was executing exactly the recovery logic it had been given — the logic just had no ceiling. The post-mortem notes this is the central paradox of self-healing agent systems. — [https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)

- **Production pattern analysis (Open Empower, June 2026):** 2026 enterprise deployments revealed systematic failure patterns: runaway loops (agent retries error, creates new error, loops), tool misuse (agent uses a tool incorrectly and compounds), context window exhaustion (context fills, model halts mid-task), hallucinated tool arguments (agent invents parameters that fail), and cost explosions (no per-task cost cap). Recommended pattern: circuit breaker per tool, iteration cap per task, and cost alerting. — [https://www.openempower.com/blog/ai-agent-production-failures-enterprise-lessons-2026](https://www.openempower.com/blog/ai-agent-production-failures-enterprise-lessons-2026)

- **Cost analysis (Augment Code):** Naive agent loops rebill the entire conversation history on every call. A 20-step loop can consume over 10x the tokens a simple per-step estimate suggests. Coordinator-specialist architectures that scope each step's context narrowly reduce that waste. The agent loop cost equation is: Tasks × Attempts × AgentTurns × ContextSize × ModelPrice × Parallelism — the highest-leverage term is Attempts (retries and re-prompts), which is directly controlled by recovery logic design. — [https://www.augmentcode.com/guides/ai-agent-loop-token-cost-context-constraints](https://www.augmentcode.com/guides/ai-agent-loop-token-cost-context-constraints)

## Gotchas

- **Max iteration limits are necessary but not sufficient.** An agent hitting its iteration limit may still have burned 50,000 tokens getting there. The limit is a ceiling, not a governor. You also need cost-per-step tracking and alerting before the ceiling is hit.
- **Backoff without a ceiling is still a death spiral.** Exponential backoff slows the spiral — it doesn't stop it. Add a maximum retry count and a hard escalation trigger, or the backoff just makes the billing slower and more painful.
- **Agents can't reliably detect their own failure modes.** An agent in a loop may confidently continue producing output that looks correct but is actually degrading. Human-out-the-loop is not the same as unsupervised. Build a separate monitoring process that watches the agent's behavior, not just its outputs.
- **Idempotency is a prerequisite for safe recovery.** If your agent's tool calls have side effects (write, send, execute), retrying them on failure may cause duplicate operations. Design tool interfaces so that repeated calls with the same parameters are safe. The agent-triage tool (GitHub) surfaces which recovery paths lack idempotency guards by analyzing production traces against system prompt policies.
- **Supervisor agents can also spiral.** A supervisor that monitors a misbehaving agent may itself enter a loop of kill-and-restart. The hierarchy needs monitoring at every level. The TensorPool Agent's production deployment notes highlight this: even the monitoring agent needs a monitoring agent for long-running autonomous tasks.
