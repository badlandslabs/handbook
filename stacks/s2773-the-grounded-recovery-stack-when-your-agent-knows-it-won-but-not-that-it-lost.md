# S-2773 · The Grounded Recovery Stack — When Your Agent Knows It Won But Not That It Lost

Your agent ran 47 steps, called the API four times, and returned what looks like a complete answer. The pipeline exited with code 0. Your monitoring shows no errors. Three weeks later, an auditor finds the agent silently used stale exchange rates and miscalculated $2.1M in invoices. No exception was raised. No step failed. The agent just produced a confident, plausible wrong answer and moved on. This is **grounded recovery**: the problem is not that the agent crashed — it's that the agent cannot tell when it has produced bad output, so it retries with the same broken logic and compounds the damage.

## Forces

- **LLM errors are semantic, not syntactic.** A 200 OK response with wrong data is harder to catch than a rate-limit error. Traditional try/catch doesn't help — nothing threw.
- **Naive retries reproduce the failure.** The agent that produced the wrong answer doesn't know it was wrong, so a blind retry produces the same wrong answer again. Retries without correction are not recovery.
- **Agents fail non-deterministically.** The same prompt that works once fails the next time due to model drift, token limit truncation, or API behavior changes. Failures are not reproducible by design.
- **Recovery cost compounds.** A 10-step pipeline where each step has 85% reliability succeeds end-to-end only ~20% of the time (Zylos Research, 2026). Without structured recovery, adding steps multiplies failure probability.
- **The 91% failure floor.** AI agents fail in production at rates cited as exceeding 91% (agentguard-llm, GitHub). This is not a model capability problem — it is an operational infrastructure problem.

## The move

Structured failure recovery for agentic systems requires four layers working together. No single layer is sufficient.

**Layer 1 — Classify the failure before choosing a response.** Errors fall into at least four distinct categories that demand different recovery strategies:

- **Transient errors** (network timeouts, rate limits 429/503, DNS failures): retry with exponential backoff and jitter. These self-correct if you wait.
- **Tool errors** (API returns 400, missing permissions, malformed tool response): fix the tool call parameters or schema, then retry. Do not retry the same call.
- **Semantic errors** (LLM returns HTTP 200 with plausible wrong output): the LLM did not fail — it succeeded at the wrong task. Retrying without a corrective signal reproduces the failure. Requires an external validator that tells the agent specifically what was wrong.
- **Deadlock/loop errors** (agent repeats the same tool call or state more than N times): terminate and rollback. Do not retry within the same context.

**Layer 2 — Build self-correction as a generate → validate → critique → repair loop.** This is not a retry — it is a separate feedback channel. The validator (often a smaller, faster model or a rule-based checker) evaluates output against a specification. If validation fails, the critique is passed back to the agent with the specific error. The agent revises. The loop repeats with a bounded retry budget (typically 2–3 iterations). Reflexion (NeurIPS 2023, arXiv:2303.11366) showed this achieves 91% pass@1 on HumanEval vs GPT-4's 80% baseline, but only when the critique is grounded in external feedback, not self-generated confidence.

**Layer 3 — Checkpoint and rollback for durable recovery.** State that survives crashes is not the same as state that survives bad output. Session memory is not durable execution (Zylos Research, 2026-04-24). Checkpointing saves execution boundaries — completed tool calls, approved human decisions, outbound messages — so that recovery continues from the last valid step, not from scratch. On failure, rollback to the last checkpoint rather than replaying the full pipeline. Tools: LangGraph checkpointers, Temporal, Azure Durable Task, Restate. A crash without durable checkpoints is an uncontrolled restart; with checkpoints, recovery is a controlled continuation.

**Layer 4 — Detect loops before they consume resources.** The universal `max_iterations=N` cap is a blunt instrument. LoopGain (open source, Apache-2.0, 122 stars) replaces it with control-theoretic convergence detection based on the Barkhausen criterion: if the loop gain Aβ ≥ 1, the error is not shrinking — the loop is stuck or oscillating. Stop and return the best output seen so far, not the degraded final output. On 2,000 benchmark trials, this stopped loops at the lowest-error iteration rather than the final one. Pre-built adapters exist for LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents SDK, and Claude Agent SDK.

## Evidence

- **GitHub repo:** agentguard-llm — "AI agents fail at 91%+ rates in production" and ships circuit breakers, LLM-aware retry, idempotency enforcement, and loop detection as composable decorators. Pure Python, zero runtime dependencies. — [github.com/maheshmakvana/agentguard-llm](https://github.com/maheshmakvana/agentguard-llm)
- **Research + GitHub demo:** Agent Failure Recovery demo — scanner detects unsafe output → attribution traces to exact tool call/run_id → rollback.py reverts to known-good snapshot → validate.py confirms recovery. Deterministic, no API key required. — [github.com/NassimRahimi/agent-failure-recovery](https://github.com/NassimRahimi/agent-failure-recovery)
- **Open source + HN:** LoopGain — replaces `max_iterations=N` with Barkhausen-criterion convergence detection. 2,000-trial benchmark. Adapters for LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents SDK, Claude Agent SDK. — [github.com/loopgain-ai/loopgain](https://github.com/loopgain-ai/loopgain)
- **Blog post:** LangChain in Production: Five Failure Patterns — documents the specific failure mode where `AgentExecutor` fails to parse LLM output that is neither a valid tool invocation nor a final answer, silently appends an error message, and loops indefinitely past `max_iterations`. — [perun.au/insights/langchain-production](https://perun.au/insights/langchain-production/)
- **Research note:** Zylos Research, "Agent Self-Healing and Failure Recovery" — 10-step pipeline at 85%/step → 20% end-to-end success rate. "An agent may silently loop for 35 minutes, spawn redundant subprocesses, or take an irreversible action before a human can intervene." — [zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)
- **Research note:** Zylos Research, "Agent Self-Correction: From Reflexion to Process Reward Models" — "intrinsic self-correction is fragile; grounded self-correction is where real gains live." — [zylos.ai/research/2026-05-12-agent-self-correction-reflexion-to-prm](https://zylos.ai/research/2026-05-12-agent-self-correction-reflexion-to-prm)
- **Research note:** Zylos Research, "Durable Execution for AI Agent Runtimes" — "session memory is not durable execution. Recovery becomes improvisation without durable boundaries; with them, recovery becomes controlled continuation." — [zylos.ai/research/2026-04-24-durable-execution-agent-runtimes](https://zylos.ai/research/2026-04-24-durable-execution-agent-runtimes)
- **Blog post:** Self-Correcting Agents (sugeerth) — generate → validate → critique → repair loop. Runs locally with no API keys. Documents the silent failure mode: "a JSON object with the right shape, the right field names — and a total that's actually the amount before discount." — [sugeerth.github.io/self-correcting-agents](https://sugeerth.github.io/self-correcting-agents)

## Gotchas

- **Retrying without a corrective signal is not recovery.** If the failure was semantic (wrong output), retrying the same prompt with the same context reproduces the failure. You need a validator that tells the agent what specifically was wrong, not a retry counter.
- **Circuit breakers must handle partial failures, not just binary success/fail.** LLM responses degrade gradually — confidence doesn't drop to zero, it just produces slightly worse reasoning. A circuit breaker that only trips on HTTP 500 misses quality degradation that still produces wrong answers.
- **Checkpointing without idempotency creates duplicate side effects.** If you checkpoint a workflow that sent an email, then crash and replay from checkpoint, you send the email again. Durable execution requires idempotent tool boundaries — each recoverable step must be safe to replay.
- **Attribution is not optional for governance.** When an agent produces unsafe output in production, auditors need to trace the bad output back to the specific tool call, model version, run ID, and timestamp. Without attribution, you can detect failure but not contain it or prove what caused it.
- **`max_iterations` as a termination policy is a cost leak.** The loop either stops too early (shipping degraded output) or too late (wasting compute on oscillations). Replace it with convergence detection that stops at the lowest-error iteration and rolls back to the best result seen.
