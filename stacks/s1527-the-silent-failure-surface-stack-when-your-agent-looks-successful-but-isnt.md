# S-1527 · The Silent Failure Surface Stack — When Your Agent Looks Successful But Isn't

You have monitoring, error logs, and retry logic. Your agent returns HTTP 200. Everything looks fine. Three weeks later you discover it was hallucinating API calls and corrupting a document pipeline since day three. The agent never crashed. It never logged an error. It just quietly failed.

## Forces

- **The silent-majority problem** — Research from production AI teams (AlgeriaTech, April 2026) finds 5% of production requests fail, and the dangerous failures are the silent ones: context degradation, orchestration drift, and wrong-but-200 responses. No exception means no alert.
- **Compounding accuracy** — Pass@1 drops from ~76% on short tasks to ~50% on long-horizon tasks (AgentMarketCap, April 2026). With per-step accuracy of 97%, a 10-step pipeline only delivers 72% end-to-end. At 99% per-step, you're still at 90%. Each step is a coin flip for failure propagation.
- **The detection-recovery gap** — Most teams add retries. Fewer teams instrument to detect that the agent completed but produced wrong output. Observability and recovery are different capabilities that need separate builds.
- **The loop problem** — Agents retry the same tool with the same arguments because the failure was in parsing, not the tool itself. YOLO mode (auto-approve-all) amplifies this into credit-burning runaway loops.

## The Move

Separate failure modes into a classification hierarchy before choosing a recovery strategy. Layer detection and recovery as independent systems.

### Error Classification Taxonomy

| Type | Detection | Recovery |
|------|-----------|---------|
| **Transient** — API timeout, rate limit, network blip | Error code | Exponential backoff + retry |
| **Semantic** — Agent completes but output fails validation | Output validator | Retry with correction in system prompt |
| **Loop** — Same tool called N times with same arguments | Tool call fingerprint | Hard limit + state reset |
| **Context overflow** — History grows until model halts | Token budget | Truncate + re-inject summary |
| **Cascading** — One agent's failure propagates to downstream agents | Step-level trace analysis | Circuit breaker + partial result return |
| **Silent quality** — HTTP 200 with wrong answer | Behavioral telemetry / LLM judge | Fallback chain + human escalation |

### Detection Layer

- **Output validators** — Not just try-catch. Validate schema, value ranges, and semantic correctness before returning. The agent finishing without an exception is not evidence of success.
- **Tool call fingerprinting** — Track the last N tool calls with their arguments. Flag when the same call repeats with identical arguments more than 2–3 times.
- **Token budget monitors** — Alert when context grows past 70% of the model's limit. Truncate and re-inject a summary before overflow.
- **Behavioral telemetry** — Instrument not just errors but observable behavior: did the agent's output change the expected state? Was the API actually called? Did the file actually get written?
- **LLM-as-judge on sampled outputs** — Run a separate model on 5–10% of production outputs to score correctness. Catch degradation that no error code would surface.

### Recovery Layer

- **Exponential backoff with jitter** — Never retry immediately after a rate-limit error. Double the wait per attempt, add random jitter to avoid thundering herd.
- **Hard guardrails** — Set maximum iterations, maximum tool calls per task, maximum cost per session, and maximum context size. These are walls, not suggestions.
- **Fallback chains** — When primary model fails, try a smaller/faster model as fallback. When all models fail, return a structured partial result with a `status: degraded` flag — never return nothing.
- **Circuit breakers** — If a downstream service fails N times, stop calling it for a cooldown period. Prevent cascading failures from compounding.
- **Checkpoint + resume** — For long-running tasks, checkpoint state after each successful step. On failure, resume from the last checkpoint rather than re-running from scratch.
- **Human escalation with active notification** — Writing to a log file is not escalation. Page the on-call engineer when all automated recovery is exhausted. Include the full trace, what was tried, and the partial result.

### Production Hardening

- **Sandbox the environment** — Run agent tool execution in isolated containers (bubblewrap, Docker) with read-only binds except for explicit work directories. Limit blast radius of destructive commands.
- **Approval tiers** — Distinguish YOLO mode (auto-approve-all) from per-step approval. Use YOLO for bounded, reversible tasks; require approval for filesystem/network/destructive operations.
- **Cost governors** — Set per-task and per-session spend limits. Agents burning API credits in loops are a real production failure mode.

## Evidence

- **Engineering post:** Simon Willison's "Designing agentic loops" (September 2025, 284 HN points, 117 comments) — coins the framing: "An AI agent is an LLM wrecking its environment in a loop." Details sandboxing with bubblewrap, per-step approval vs YOLO mode, and hard loop limits. — https://simonwillison.net/2025/Sep/30/designing-agentic-loops/
- **HN discussion:** Zenflow Show HN — tooling specifically built to solve agents "getting stuck in 'you're right' loops, apologizing, and wasting time." Cross-model verification pattern (run multiple models to review each other's outputs) emerged as a recovery technique. — https://news.ycombinator.com/item?id=46290617
- **GitHub repo:** agent-triage (Converra) — diagnoses agent failures at the step level in production traces. Pinpoints the first root-cause failure vs downstream consequences, specifically designed for multi-agent cascading failure scenarios. — https://github.com/converra/agent-triage
- **GitHub discussion:** Anthropic SDK community discussion on error recovery patterns (April 2026) — practitioner's error classification framework with 5 error types and distinct recovery strategies per type. — https://github.com/anthropics/anthropic-sdk-python/discussions/1341
- **Research synthesis:** AgentMarketCap analysis (April 2026) — 40% of multi-agent pilots fail within 6 months of production deployment; mean pass@1 drops from 76.3% on short tasks to 50.5% on long-horizon tasks. — https://agentmarketcap.ai/blog/2026/04/06/agent-failure-diagnosis-production-silent-failures-braintrust-arize-langsmith

## Gotchas

- **Adding retries is not error handling.** Retries handle transient errors. Semantic errors (agent completes but is wrong) require output validation, not a retry loop. Most teams conflate the two.
- **Error handling is not observability.** A retry loop can run for weeks without a single trace proving it fired. Recovery and the record of recovery are separate builds.
- **YOLO mode is not the problem — YOLO mode without cost governors and sandboxing is.** The failure mode is runaway execution amplified by unlimited API calls, not the auto-approve setting itself.
- **Single-pass success rate is the wrong metric.** A 99% pass@1 rate on 10-step tasks means only 90% of tasks complete correctly. Measure end-to-end task completion, not per-step accuracy.
- **The cascade is invisible without step-level tracing.** When Agent B fails because Agent A gave it bad context, your monitoring shows Agent B failed. You need trace-level causality to find Agent A.
