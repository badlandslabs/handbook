# S-1784 · The Compounding Failure Stack — When Your Agent Succeeds into a Mess and Nobody Notices

Your agent completed 4 of 8 steps. No error was raised. The final output looks plausible. The exit code was 0. Three hours later, a customer reports the data in the report is from last month. Step 4 called an API that started returning stale cached data. The API returned HTTP 200. The agent interpreted the stale payload as valid and proceeded. No exception fired. No retry fired. The failure cascaded silently through steps 5–8, each building on the previous wrong assumption. This is how agents fail — not by crashing, but by producing confident wrong output that looks like success until it isn't.

## Forces

- Agents fail non-deterministically in ways that standard try/catch cannot catch — wrong plans, stale data, semantic misinterpretation, and confident hallucination all look like HTTP 200
- Self-correction only works when the agent has an accurate signal that something went wrong; an agent asked "did that work?" will almost always say yes
- Retries on hard errors (network timeout, rate limit) are straightforward, but retries on semantic errors (agent misunderstood a tool response) can make things worse
- Every failed attempt burns compute and context; naive retry loops without convergence detection can cost 14× more than necessary
- The failure modes are categorically different: hard errors (catchable), soft errors (validated away), and compounding errors (each step makes diagnosis harder)

## The Move

Layer five distinct recovery mechanisms matched to the failure type:

**1. External-signal retry — the only reliable self-correction.** When a test fails, a schema check fails, or an API returns a non-zero exit code, the agent has an objective signal. Retry with that signal as context. This is the only type of self-correction that reliably improves outcomes — the evaluation is not self-referential.

**2. Semantic self-correction with Observe-Plan-Act-Reflect (OPAR).** The agent produces output, then an independent verifier evaluates it against observable criteria (not the agent's own assessment). If verification fails, the verifier's diagnosis feeds back into the next planning cycle. Crucially, the verifier is a separate concern from the actor — never ask the agent "did you succeed?" — build a separate evaluation path.

**3. Stateful rollback via checkpointing.** Before each significant step, save the execution state (tool call inputs, intermediate results, LLM reasoning). On failure, rewind to the last valid checkpoint instead of restarting from scratch. LangGraph's `MemorySaver` or Postgres checkpointer enables this with 3 lines of config. Research agents running multi-step web scrape → code → API pipelines benefit most — recovering from a rate limit error by resuming from step 2 instead of re-running steps 1–2 is the key win.

**4. Bounded convergence detection — not max_iterations.** Agents oscillating or degrading after convergence is common. LoopGain's research across 2,000 paired trials found that naive `max_iterations=20` burns $27.05 in API spend vs. $1.94 with convergence-based termination — a 92.8% reduction — while preserving output quality. The pattern: track the rate of output change between iterations; when delta drops below a threshold, stop. LoopGain implements this as real-time loop-gain (Aβ) bands with best-so-far rollback, available as adapters for LangGraph, CrewAI, AutoGen, and the Claude Agent SDK.

**5. Graceful degradation with defined minimum viable output.** For steps that cannot be recovered, define what the agent must return rather than failing silently. A partial report with a data freshness timestamp is better than a stale report with no timestamp. The acceptance criteria should be defined *before* the run, not negotiated after the failure.

**Separation of concerns is the structural key.** Detection (what went wrong), diagnosis (why), and acceptance (is the result good enough) must be handled by separate mechanisms. A single agent handling all three will almost always pass acceptance — confidence is not a reliable signal of correctness.

## Evidence

- **GitHub/LangGraph:** Research agents recover from rate limit errors by resuming from the last successful checkpoint, skipping already-completed nodes. A single `NodeInterrupt` raised on `RateLimitError`, combined with LangGraph's checkpointing, allows a 12-step run to continue from step 3 rather than restarting — [markaicode.com/usecases/langgraph-use-cases-production-workflows](https://markaicode.com/usecases/langgraph-use-cases-production-workflows)
- **Show HN / GitHub (LoopGain):** 2,000 paired trials across 10 workload cells. `max_iterations=20` baseline: $27.05 spend, median 30.9s. LoopGain convergence detection: $1.94 spend, median 2.1s. Quality preserved (judge win-rate 0.50–0.63 on natural workloads, 0.92–0.95 on engineered-failure workloads). Open-source, Apache 2.0, adapters for LangGraph/CrewAI/AutoGen/Claude Agent SDK — [github.com/loopgain-ai/loopgain](https://github.com/loopgain-ai/loopgain)
- **Atlas of Agent Design Patterns (danielcanfly.com):** "A model saying it verified an output is not the same as the system producing verifiable evidence." The five-responsibility table (Detection / Diagnosis / Acceptance / Recovery / Reporting) as separate architectural concerns. Critically, Reflexion-style patterns (persistent reflection memory guiding future attempts) apply to complex problem-solving; simple retry applies to external-signal failures — [danielcanfly.com/en/blog/the-atlas-of-agent-design-patterns-part-5](https://danielcanfly.com/en/blog/the-atlas-of-agent-design-patterns-part-5)

## Gotchas

- **Self-correction can degrade outputs.** On GSM8K math, naive self-correction consistently *hurt* results — changing correct answers to wrong ones. Self-correction only reliably helps when external validation exists. If the task has no test and no schema, do not assume the agent can correct itself.
- **Cascading failures hide the root cause.** Step N fails because step N−1 returned stale data. By the time the failure is visible, the original cause is buried in the trace. Log tool call inputs and outputs at each step, not just final state, so diagnosis can work backward.
- **`max_iterations` is a budget guard, not a convergence signal.** It stops the loop when the budget runs out, not when the agent has converged. Agents that have converged will continue burning tokens; agents that need more iterations will be cut off. Treat it as a cost ceiling, not a quality signal.
- **Soft failures have no error code.** The API returned 200. The JSON is valid. The content is wrong. This is the failure mode that requires the most architectural investment — schema validation catches structural errors, not semantic ones. You need output sampling, ground-truth comparison, or a verifier agent for these.
