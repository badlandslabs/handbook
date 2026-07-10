# S-905 · The Silent Green Exit Stack — When Your Agent Says Done and Did Nothing

Your agent ran last night. The log says success. The work didn't happen. The emails didn't send, the database didn't update, the report wasn't generated. The agent reached what it thought was a conclusion, returned a clean exit, and moved on — leaving nothing behind while reporting everything complete. You don't find out for a week. By then, the audit trail is cold and the downstream damage is done.

This is the silent green exit: the most common production failure mode in agentic systems, and the least discussed.

## Forces

- **Verification lives inside the agent that produced the work.** The same system that generated the false positive is trusted to detect it. This is circular.
- **Agents fail quietly, not loudly.** Traditional software throws exceptions. Agents generate fluent text that explains away the absence of output.
- **Logs say success. Reality says nothing.** A task that never ran, a tool that returned empty because it wasn't properly invoked, an API that was called with wrong parameters — all look like success when the agent writes "completed successfully."
- **Schedule drift compounds silently.** An agent that misses one scheduled run drifts further from ground truth each cycle, with no mechanism catching the gap.
- **The production gap in observability.** Less than 1 in 3 teams are satisfied with their observability and guardrails for agents. Most find out about failures the way they always have: a user tells them.

## The move

**Verification lives outside the agent.** The fix is architectural, not prompt-engineered.

- **Side-effect attestation.** After any agent action that produces an external effect (email sent, record updated, file written, API called), a separate verification step — running as an independent process — confirms the effect occurred. The agent checks its own work only as a fallback.
- **State checkpointing instead of conversation replay.** Store *facts* (goal, completed steps, results) rather than conversation history. On recovery, reconstruct agent context from the checkpoint. Conversation replay fails because LLM responses are non-deterministic — the same history can produce different tool calls on replay, and stale tool outputs from earlier runs no longer reflect current system state.
- **Three-layer memory persistence.** Redis for hot/session state → PostgreSQL for warm/durable state → Vector DB for cold/semantic memory. Checkpoints written after each critical node; recovery from nearest checkpoint on crash. All state mutations must be idempotent.
- **Circuit breakers on loops.** Cap iteration count and time budgets per task. Agents that loop for 35 minutes with no progress should trigger a circuit break and escalate, not accumulate cost and context until the model halts.
- **Golden set + tolerance bands for CI evals.** Pin the judge model, use tolerance bands instead of exact thresholds, and sample a stable golden test set so non-deterministic LLM output doesn't break pipelines. Run at least two frameworks in parallel — one for dev-time evaluation (DeepEval or Promptfoo), one for production monitoring (Arize Phoenix, W&B Weave, or Braintrust).
- **Human approval gates on irreversible actions.** Until production data justifies automation, require human confirmation for deletions, financial transactions, and external communications. The cost of a pause is low; the cost of an irreversible action that can't be undone is not.

## Evidence

- **OperatorIQ field report:** Silent green exits are the most expensive failure mode in 2026 agentic production. Operators caught agents reporting success while producing zero output for weeks at a time. The fix requires verification processes that run independently of the agent that produced the work — verification must be structurally external. — [OperatorIQ](https://operatoriq.io/blog/agentic-ai-failure-modes-silent-green-exits/)
- **Zylos Research taxonomy:** Production agents fail in ways traditional software does not: silent loops, redundant subprocesses contending for shared resources, context accumulation until model halts, irreversible actions taken before human intervention. Fault tolerance is not optional hygiene — it is the core engineering challenge of the agentic era. — [Zylos Research](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery)
- **Adaptive Recall on recovery:** Conversation replay fails on three grounds: non-deterministic LLM responses produce different tool calls on replay; stale cached outputs reflect old system state; and intermediate reasoning accumulates noise in the context window. Checkpoint-based recovery stores facts, not conversations. — [Adaptive Recall](https://www.adaptiverecall.com/ai-agent-memory/checkpoint-recovery.php)
- **Anthropic engineering blog:** Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks. Default to the simplest solution, only increase complexity when evidence demands it. — [Anthropic](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- **Confidence ≠ correctness.** Agents generate fluent responses even with incomplete or incorrect context. A confident tone is not a correctness signal — it is a failure mode.
- **Benchmarks can be gamed.** UC Berkeley found all eight prominent AI agent benchmarks could be gamed to near-perfect scores without solving underlying tasks. One team gamed 890 tasks with a single character change. SWE-bench scores rose while real-world code quality declined. Static task-completion scores fail to capture reliability, cost efficiency, and safety.
- **LLM-as-judge has calibration drift.** Judge models are updated over time, causing evaluation scores to shift even when the evaluated agent hasn't changed. Pin judge model versions in production evals.
- **Most agent deployments are over-engineered.** Analysis of 47 agent deployments found 68% would have achieved equivalent or better outcomes with a well-designed single-agent system. The multi-agent tax — higher latency, compounding failure modes, operational complexity — often eats the gains before they reach users.
