# S-2280 · The Defensive Descent Stack — When Your Agent Fails in the Middle and No One Notices

Your agent is 4 steps into a 6-step workflow when the API returns a 429. It freezes. The user sees no error — just a spinning cursor that eventually times out at 10 minutes. Nothing was saved, nothing was retried, nothing was rolled back. The agent left the session in an undefined state and the on-call engineer has no idea it happened. The defensive descent stack is how teams build agents that lose gracefully: detecting failures fast, recovering intelligently, and failing in ways that leave the system better than they found it.

## Forces

- **Agents fail silently in ways traditional software doesn't.** A conventional microservice crashes at a boundary and generates a stack trace. An agent mid-step might call a tool that partially succeeds, silently skips an intermediate result, or restarts from scratch and loses all prior progress — with no error code, no exception, and no log line. Without explicit detection, you won't know.
- **Loop cost is non-obvious until it's catastrophic.** A task that costs $0.08 and completes in 3 steps can spin to 60+ steps, $12, and 15 minutes when the agent enters a repetition cycle. The cost doesn't spike a PagerDuty alert — it accrues in API bills and user frustration. Simple iteration caps (`max_iterations=N`) stop too early or too late, not when the agent has actually finished improving.
- **Every recovery strategy is context-dependent.** Retrying a 503 is cheap and correct. Retrying a malformed tool call with the same arguments is waste. Retrying indefinitely on a permanent failure is a denial-of-service attack on your own infrastructure. Classifying the error type before choosing the recovery path is the first line of defense.
- **Partial results are better than zero results.** A degraded agent that resolves 70% of queries correctly during an outage delivers more value than one that errors out completely. But in safety-critical contexts (medical, financial, legal), graceful degradation is the wrong call — you want hard failure, not a lower-quality guess.

## The move

Build a layered failure-handling system that classifies errors on entry, contains cascades at the tool boundary, and preserves enough state to recover without starting over.

**Step 1 — Classify before you retry.** Every error that reaches your recovery layer must be inspected and categorized before any retry logic fires. Four categories, each with a distinct path:

| Category | Signals | Recovery |
|---|---|---|
| **Transient** | HTTP 429, 503, timeout, DNS failure | Retry with backoff — the same request will likely succeed |
| **Semantic** | Malformed JSON, schema violation, non-existent tool | Re-prompt with corrective context — the request was wrong |
| **Resource** | Token budget exceeded, context overflow, spending cap | Reduce payload — summarize, paginate, or paginate the input |
| **Agentic** | Hallucination, confident wrong answer, tool returns technically valid but factually wrong data | Inject verification step or human handoff — the agent cannot self-correct without external grounding |

**Step 2 — Replace `max_iterations` with convergence detection.** LoopGain (Show HN, fitz2882) uses control theory: calculate the ratio of current error to previous error (loop gain, Aβ) on each iteration. Aβ ≥ 1 means the loop is stuck or making things worse. A trajectory classifier labels each run as FAST_CONVERGE / CONVERGING / STALLING / OSCILLATING / DIVERGING and decides whether to continue, stop here, or roll back to the best output seen so far. This stops loops when they're genuinely done improving, not when a fixed cap is reached.

**Step 3 — Instrument each tool with its own circuit breaker.** Different tools have different failure profiles. A vector search might tolerate 3 consecutive failures before you should stop hitting it; a payment API might tolerate 5. Configure per-tool circuit breakers with independent failure thresholds and recovery timeouts. When a tool's breaker opens, either route to a fallback tool (e.g., swap vector DB providers) or degrade gracefully.

**Step 4 — Checkpoint after every successful step.** Preserve agent state (memory contents, conversation history, intermediate outputs, progress markers) at natural step boundaries — not just at the end. A document analysis agent that times out after 58 minutes of processing can resume from the last checkpoint instead of starting over. For financial services, legal review, and medical data tasks, this is not optional — re-processing or losing partial results has real consequences.

**Step 5 — Return partial results by default.** When a multi-step workflow has completed steps 1–3 and step 4 fails, surface what you have with a clear indication of what is missing. "Found 3 flights and 12 hotels in Paris. Weather data is currently unavailable — check back shortly" is the correct response, not a 500. This is a first-class architectural decision, not an afterthought: design your workflow output schema to distinguish complete, partial, and degraded states.

**Step 6 — Define explicit stop conditions, not just iteration counts.** Oracle's agent loop guide defines seven distinct exit criteria: (1) model produces final response with no pending tool calls, (2) goal-completion predicate returns true, (3) max iterations reached, (4) wall-clock timeout expired, (5) unrecoverable error, (6) harness detects a failure mode, (7) agent explicitly invokes exit. Only conditions 3 and 4 are time-based; the rest are semantic.

## Evidence

- **Show HN (LoopGain):** LoopGain library replaces arbitrary `max_iterations=N` with empirical convergence detection using control theory loop gain (Aβ). Returns best-output-so-far on divergence, not final-output. — [https://news.ycombinator.com/item?id=48919562](https://news.ycombinator.com/item?id=48919562)
- **Agent Patterns / FailureModes.ai:** Taxonomy of four loop failure patterns — hard loop (same tool+args repeated), soft loop (same action pattern with variation), retry storm (agent keeps retrying a failed tool), semantic loop (agent "understands" the task differently each iteration). Detection via tool call fingerprinting, token pattern similarity, and progress predicates. — [https://www.agentpatterns.tech/en/failures/infinite-loop](https://www.agentpatterns.tech/en/failures/infinite-loop), [https://failuremodes.ai/failure-modes-library/infinite-loop](https://failuremodes.ai/failure-modes-library/infinite-loop)
- **AgentixForce (2026):** Financial services client processing regulatory filings — a single Cloud Run timeout after 58 minutes of processing meant starting from scratch without checkpointing. With per-step state preservation, the same failure resumes 14 minutes behind schedule instead of from zero. — [https://agentixforce.ai/blog/graceful-degradation-strategies-agents](https://agentixforce.ai/blog/graceful-degradation-strategies-agents)
- **Vectara awesome-agent-failures (Apache-2.0, 89 commits since Aug 2025):** Failure taxonomy including tool hallucination (RAG returns hallucinated source), response hallucination (agent combines tool outputs into factually inconsistent answer), context overflow (agent loses track of early steps), and infinite loops. — [https://github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **Preporato (NCP-AAI):** Semantic errors return HTTP 200 — the agent produces a confident, fluent wrong answer. Traditional error-handling sees no exception. Requires a validation layer that checks output against ground truth, not just error codes. — [https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems](https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems)
- **Oracle Developers Blog (2026):** Agent loop exit criteria: seven distinct stop conditions beyond time-based caps. Goal-completion predicates (semantic checks) outperform iteration counts because they measure actual task completion, not time spent. — [https://blogs.oracle.com/developers/the-agent-loop-decoded-three-levels-every-agent-engineer-must-know](https://blogs.oracle.com/developers/the-agent-loop-decoded-three-levels-every-agent-engineer-must-know)

## Gotchas

- **Retry without classification hammers the wrong endpoint.** A retry loop that hammers a 401 endpoint wastes tokens, time, and rate-limit budget. Inspect the error type or HTTP status code first, then branch.
- **Checkpointing every step creates storage pressure on long-running agents.** Store checkpoints at natural step boundaries (post-tool-call, not mid-call), and implement checkpoint expiry to avoid unbounded storage growth.
- **Graceful degradation is not appropriate for safety-critical paths.** Medical diagnosis, financial trading, and legal review should hard-fail with a clear "unavailable" message rather than serve a degraded lower-quality answer. Exclude these paths from your degradation layer explicitly.
- **`max_iterations` is a false friend.** It prevents runaway loops but clips improving ones and returns the final (sometimes worse) attempt rather than the best one seen. Treat it as a safety net, not a convergence signal.
- **Semantic errors need a validation layer, not a retry loop.** An agent producing a confident wrong answer won't self-correct by trying again with the same context. You need external ground truth (test suite, verification query, human-in-the-loop) to detect and break the pattern.
