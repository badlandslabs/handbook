# S-1439 · The Self-Bounding Agent Stack — When Your Recovery Logic Costs More Than the Bug

Your agent hit a failure. The recovery loop kicked in. The recovery loop kicked in again. And again. Three days later you find your agent has burned through 250,000 API calls executing recovery logic that had no ceiling. The agent was never broken in any obvious sense — it was executing exactly the recovery behavior it was given. The logic just had no stop condition.

This is the self-healing paradox: the mechanisms designed to keep agents running are also the mechanisms most likely to run them off a cliff. Every retry is an opportunity to retry wrong. Every self-correction is an opportunity to compound the error.

## Forces

- **Recovery logic has no natural stopping point.** Unlike exceptions in deterministic code, agent recovery decisions are made by the LLM itself, which may retry a failing strategy indefinitely — especially when the retry prompt says "try again."
- **Silent failures outnumber crashes.** Agents return HTTP 200 with subtly wrong outputs far more often than they throw errors. A task that "succeeded" and produced a confident, polished, completely wrong answer is harder to detect than a crash.
- **Self-correction is fragile unless grounded.** The model judging its own work is unreliable across reasoning errors. The field has converged: intrinsic self-correction (Reflexion-style verbal critique) is a research baseline; grounded self-correction (anchored in execution results, structured critics, or process reward models) is the production standard.
- **The budget you allocate for recovery is also the budget available for runaway loops.** A recovery system with no ceiling will find it.

## The move

1. **Hard ceilings on every recovery loop as non-negotiable infrastructure, not configuration.** Set `max_retry_attempts`, `max_loop_iterations`, and per-step token budgets as hard limits enforced at the infrastructure layer — not soft guidelines passed to the LLM. Use control-theoretic termination (loop-gain analysis) instead of fixed `max_iterations` caps: stop when the system is actually converging, not when a counter hits zero. LoopGain benchmarks show 92.8% API cost reduction ($27.05 → $1.94) with quality preserved, ~15× wall-clock speedup over `max_iter=20`.

2. **Grounded self-correction over intrinsic.** Route corrections through external signals: verify outputs against structured schemas before accepting them; execute tool calls to confirm parameter validity before committing; use process reward models (PRMs) rather than letting the agent declare its own correctness. The distinction matters: a model that says "I should try again" is not the same as a system that confirms "the previous output failed validation."

3. **Stateful rollback as a first-class primitive.** Use framework checkpointing (LangGraph's `MemorySaver` or `PostgresSaver`) to snapshot state before every risky operation. On failure, rewind to the last known-good checkpoint — do not re-execute from the beginning. LangGraph's pattern: `checkpointer = PostgresSaver(conn)` → `graph.invoke(inputs, config={"configurable": {"thread_id": "..."}})`. On resume, LangGraph rehydrates state and continues from the next queued node. Postgres for durable production checkpoints; Redis for low-latency session resume.

4. **Failure triage with tool-call attribution.** When a failure occurs, attribute it to the specific tool call that produced the corrupt state — not to the downstream step that surfaced the error. The NassimRahimi/agent-failure-recovery pattern separates five explicit stages: detect → attribute → quarantine bad state → rollback to snapshot → validate restored state is actually safe.

5. **Selective retry by exception class.** Never apply a uniform retry policy. Rate-limit errors (HTTP 429) → exponential backoff (1s, 2s, 4s, 8s, 16s). Transient network errors → immediate retry. Auth failures (InvalidAPIKeyError) → hard stop, alert, do not retry. Policy/content violations → quarantine, escalate. Hallucinated tool calls → do not retry the same tool, substitute or escalate.

6. **Escalation at semantic boundaries, not just crashes.** Define escalation triggers that have nothing to do with HTTP status codes: confidence score drops below threshold, agent explicitly signals uncertainty, a pre-defined edge-case pattern fires, or a specific tool category (destructive operations, financial actions) is invoked. A "pause and ask" function that the agent can call is more surgical than a blanket escalation policy.

## Evidence

- **arXiv research paper:** "Evaluating Agentic AI in the Wild: Failure Modes, Drift Patterns, and a Production Evaluation Framework" (Pandey, May 2026) — taxonomy of 7 production failure modes; standard metrics (accuracy, pass rate) fail to detect 4/7 entirely in continuous operation; introduces PAEF (Production Agentic Evaluation Framework) — [arxiv.org/html/2605.01604](https://arxiv.org/html/2605.01604)

- **Engineering blog:** Harsh Rastogi (Modelia.ai / Asynq.ai, March 2026) — candidate evaluation agent hallucinated tool parameters, got stuck in loops, produced contradictory evaluations, cost 3× budget in production before detection; image generation pipeline agent approved obviously flawed images while optimizing for workflow completion over quality — [harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)

- **HN / GitHub:** LoopGain — open-source cost controller for agent loops using control-theoretic termination (loop-gain bands + best-so-far rollback); adapters for LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents, Claude Agent SDK; 92.8% cost reduction vs fixed `max_iter=20` on comparable tasks — [github.com/loopgain-ai/loopgain](https://github.com/loopgain-ai/loopgain) | [HN discussion: news.ycombinator.com/item?id=48919562](https://news.ycombinator.com/item?id=48919562)

- **HN / GitHub:** Agent-triage — diagnosis of agent failures from production traces, attributing failures to the specific tool call that produced them — [news.ycombinator.com/item?id=47334775](https://news.ycombinator.com/item?id=47334775) | [github.com/converra/agent-triage](https://github.com/converra/agent-triage)

- **GitHub:** NassimRahimi/agent-failure-recovery — deterministic, no-API-key demo of detect → attribute → quarantine → rollback → validate pipeline for agentic workflows — [github.com/NassimRahimi/agent-failure-recovery](https://github.com/NassimRahimi/agent-failure-recovery)

- **Engineering post:** AI Dev Day — "Roll Back a Failing Agent in 3 Lines: LangGraph Pattern" — Postgres vs Redis checkpointer decision for production, automated rollback on external API failure — [aidevdayindia.org](https://aidevdayindia.org/blogs/ai-agent-observability-agentops-playbook/ai-agent-rollback-checkpoint-pattern-langgraph-production.html)

- **Research synthesis:** Zylos Research — "Agent Self-Correction: From Reflexion to Process Reward Models" (May 2026) — intrinsic self-correction (verbal critique) achieves ~91% pass@1 on HumanEval in research; grounded correction with execution feedback and PRMs is the production standard — [zylos.ai/en/research/2026-05-12-agent-self-correction-reflexion-to-prm](https://zylos.ai/en/research/2026-05-12-agent-self-correction-reflexion-to-prm)

## Gotchas

- **Control-theoretic termination beats fixed caps.** If you're using `max_iterations=20`, you're spending budget on every task that converges at iteration 3. The loop-gain approach (monitoring whether error is decreasing per iteration) stops at actual convergence — not at an arbitrary ceiling.

- **Verify the rollback, not just the re-execution.** After rewinding to a checkpoint, confirm the restored state is actually safe and consistent. State corruption can survive a rollback if the snapshot was taken after the corruption occurred, or if the rollback mechanism doesn't properly isolate side effects (database writes, external API calls).

- **Intrinsic self-correction is a demo artifact, not a production guarantee.** The Reflexion pattern (store verbal critiques, retry with context) works in controlled settings. In production, a model that confidently says "I'll try a different approach" after producing wrong output is still producing wrong output. Require external verification before accepting any self-corrected result.

- **The Claude Code compaction bug is the canonical example.** An agent's recovery logic had no ceiling on compacting context. It ran 250,000 API calls in a day before the team noticed — not because the agent was malfunctioning, but because its recovery behavior had no upper bound. Every agent system has an equivalent bug waiting to happen.
