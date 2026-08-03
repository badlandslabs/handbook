# S-2009 · The Token Spiral Stack — When Your Agent Isn't Broken, It's Just Expensive

Your monitoring dashboard is green. Latency is normal. Error rate is 0%. But your AI budget is burning at $700/hour and nobody noticed for four hours. The agent is returning HTTP 200 on every call. It's executing different tools, producing different outputs, reasoning through different paths. It's also getting nowhere — and every iteration costs more than the last. This is not a loop. This is a spiral.

## Forces

- **Traditional observability is blind to semantic failure.** Token spirals produce perfect-looking metrics: all calls return success, latency is within SLO, no exceptions are thrown. The agent's behavior is structurally identical to correct execution. You cannot detect it with latency, traffic, error, and saturation — the four golden signals — because it generates none of the failure signals those signals are designed to catch.

- **Each iteration is more expensive than the last.** LLM API pricing is billed on accumulated context. As the agent's context window fills with tool calls, tool responses, reasoning traces, and intermediate results, the cost of the next iteration grows. A spiral doesn't burn tokens at a constant rate — it accelerates. The first 10 iterations might cost $0.50; the next 10 might cost $5. The cumulative cost curve looks exponential even when the per-call behavior looks rational.

- **Individual iterations are individually defensible.** Unlike a syntactic loop (calling the same function with the same arguments repeatedly, which existing loop detectors catch), a token spiral involves semantically different tool calls, different reasoning chains, different intermediate states. The agent is not stuck — it is active, producing novel outputs, appearing to make progress. Loop detectors that check for repeated tool names or identical arguments miss this entirely. The failure is not behavioral repetition — it is semantic non-convergence.

- **Convergence is not a natural property of agentic loops.** Agents are designed to continue until a terminal condition is met. For task-completion agents, the natural terminal condition is "the task is done." But "task done" is a semantic judgment that the agent makes about its own output. An agent that has produced a plausible-looking but incorrect result will self-verify against that result, pass, and terminate — having produced the wrong answer at great expense. An agent that is genuinely stuck but producing varied outputs has no mechanism to detect this without an external convergence check.

## The Move

**1. Semantic convergence checking — the loop detector that actually detects spirals.**

Track the semantic similarity of agent outputs across iterations, not just tool call patterns. Store a compressed representation of each output (embedding, structured state diff, or goal-progress score) and compare consecutive iterations. A semantic drift score that falls below a threshold — meaning outputs are changing without making measurable progress toward the goal — triggers escalation or termination. This catches the spiral that loop detectors miss: one where the agent is active but not converging.

Implementation options, simplest to most robust:
- **Output embedding similarity:** Encode each tool output or final response into a vector. If cosine similarity between consecutive outputs stays above 0.95 (i.e., outputs keep saying the same thing in different words) for N iterations, trigger a breaker.
- **Goal-progress scoring:** After each iteration, query the agent itself (or a lightweight judge model) with: "On a 0–10 scale, how much closer is the current state to the task goal than it was at the start?" If the score doesn't improve for M consecutive iterations, terminate.
- **Structural state diffing:** For agents producing structured outputs (JSON, table rows, code), track schema-level changes. If the output structure stabilizes but the agent keeps calling tools, that stability is a convergence signal — not a loop, but a completion signal.

**2. Layered cost circuit breakers — not just budgets, but velocity and acceleration.**

Hard token budgets (total spend ceiling per task) are necessary but insufficient for spirals. A budget stops the agent after the damage is done; a velocity breaker stops it when the burn rate itself becomes the warning signal.

Three distinct layers:

- **Hard budget cap:** Set an absolute ceiling on total spend per task instance. Use your LLM provider's native `max_tokens` or `max_total_tokens` parameter. When hit, the run terminates with a clear status code. This is your last line of defense.
- **Cost velocity breaker:** Track spend rate ($/minute or tokens/minute) over a sliding window. If the rate exceeds a threshold (e.g., 2× the expected rate for this task type), pause execution and alert. A velocity spike before a budget hit gives you time to investigate rather than just terminate.
- **Context acceleration detector:** Track the growth rate of the context window across iterations. If the context is growing faster than the agent is producing useful output, the spiral is accelerating. Calculate: `(context_tokens_at_iteration_n - context_tokens_at_iteration_1) / n`. A rising ratio across iterations is a leading indicator of spiral conditions.

**3. The green-dashboard problem — instrument what actually matters.**

Traditional APM (Datadog, New Relic, Grafana) cannot detect token spirals because they monitor system behavior, not agent behavior. You need agent-native instrumentation layered on top:

- **Token spend per task instance** with real-time accumulation, not end-of-day billing reports.
- **Output novelty score** — a rolling metric of how semantically different each new output is from the previous one. Low novelty + high tool call count = spiral.
- **Goal proximity metric** — a lightweight checkpoint at fixed iteration intervals that asks: "Is the agent closer to the goal than it was at iteration 0?" If no, flag for human review.
- **Cost-per-progress-unit** — the cost divided by a measurable progress indicator (rows processed, files generated, steps completed). A rising cost-per-unit is a spiral in progress, even if the absolute spend looks reasonable.

**4. Spiral-resistant agent design — make convergence the default.**

Design agents to have explicit convergence semantics baked in, not bolted on:

- **Define terminal conditions declaratively, not procedurally.** Instead of "keep going until you feel done," specify what "done" looks like: a schema that the output must match, a predicate that must be true, a number of items that must be produced. The agent's self-verification step checks against this declaration, not its own confidence.
- **Task complexity bucketing.** Route tasks into complexity tiers (simple/medium/complex) and set per-tier iteration limits and cost budgets at routing time. A "find and summarize 3 files" task gets 10 iterations and $0.50. A "research this topic thoroughly" task gets different limits with explicit escalation at threshold.
- **Checkpoint-based recovery.** Save agent state at regular intervals. If a spiral is detected and terminated, the last checkpoint provides a recovery point — you don't lose all the work, just the spiraling tail.

## Tradeoffs

- **Semantic similarity checks add latency and cost.** Computing embeddings or calling a judge model at each iteration has its own token cost. This is acceptable: a 1% overhead to detect a $2,000/hour spiral is a net win. Keep the check lightweight — a small embedding model or a 3-shot judge prompt, not a full evaluation run.
- **Velocity breakers create false positives on legitimate high-complexity tasks.** A task that legitimately requires exponential exploration (e.g., a complex code debugging session) will naturally show increasing context. Tune thresholds by task type, not globally. Use task-complexity bucketing to set appropriate baselines.
- **Terminal condition declarations can be wrong.** If you define "done" incorrectly, the agent will confidently produce the wrong output and stop. Treat terminal conditions as living specifications — log cases where the agent reported completion but a downstream check failed, and refine the conditions.
- **Budget caps sacrifice work.** A hard cap terminates a spiraling agent mid-task, losing all accumulated progress. The checkpoint strategy mitigates this — but checkpoint granularity is a tradeoff between storage cost and work loss.

## Receipt

> Verified 2026-08-02 — Research sources: TrustGate AI (Jun 20, 2026) on token spiral taxonomy and $2,847/4-hour incident; n1n.ai (May 25, 2026) on why traditional monitoring fails token spirals (HTTP 200 + green dashboards); OpenLegion (July 2026) on layered circuit breakers; Velocity Software (May 22, 2026) on multi-agent orchestration failure taxonomy; arXiv 2511.22729 on context window overflow solutions. The token spiral is distinct from S-979 (syntactic loop detection) and S-1311 (infinite bill/budget ceiling) in that it captures the specific failure mode of semantic non-convergence with multiplicative context cost growth, invisible to traditional APM. New contribution: semantic convergence checking via embedding similarity, goal-progress scoring, and context acceleration detection — none covered by existing entries.

## See also

- [S-979 · The Loop Detector Stack](s979-the-loop-detector-stack-when-your-agent-runs-all-night-draining-your-budget.md) — syntactic loop detection (same tool, same arguments)
- [S-1311 · The Infinite Bill Stack](s1311-the-infinite-bill-stack-when-your-agent-runs-until-it-runs-out-of-money.md) — hard budget enforcement
- [S-2008 · The Trajectory Watch Stack](s2008-the-trajectory-watch-stack-when-your-agent-answers-correctly-but-got-there-completely-wrong.md) — output correctness vs. reasoning path validation
