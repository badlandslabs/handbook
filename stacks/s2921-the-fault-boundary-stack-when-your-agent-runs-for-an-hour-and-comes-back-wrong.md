# S-2921 · The Fault Boundary Stack — When Your Agent Runs for an Hour and Comes Back Wrong

Your agent just spent 47 minutes writing customer responses, updating records, and filing tickets. It returned a clean status 200. Every step logged "success." It also routed 23% of responses to the wrong customer tier, silently. The problem isn't that the agent crashed — it didn't. The problem is that you gave it no fault boundaries: no way to know it was drifting, no way to stop it mid-run, and no way to recover to a known-good state when something went wrong. A production agent that never fails is not a reliable agent — it's a dangerous one that hides its failures.

## Forces

- **Agents fail non-crashingly.** Unlike a microservice that throws a 500, an agent with a bad plan will happily execute it for an hour and return confident nonsense. Traditional error handling doesn't see it because nothing technically "broke."
- **Recovery windows are narrow.** An agent that takes a destructive action (wrong record update, incorrect email send) has already caused harm by the time the final output is visible. You need to catch drift before the side effect, not after.
- **Retry is not a universal fix.** Retrying a context overflow with the same bloated context fails identically. Retrying a hallucinated tool call reproduces the hallucination. Classifying the error before deciding the recovery is the actual engineering work.
- **Long-horizon tasks amplify failure surface area.** A 10-step pipeline where each step has 85% reliability has ~20% end-to-end success — but the failures aren't random; they're correlated and cascading. One bad tool call in step 3 corrupts everything downstream.
- **State loss is catastrophic at scale.** Without checkpointing, a pod restart mid-run loses the entire trajectory. Without interruptible execution, you can't pause for human review before irreversible actions.

## The move

Build explicit fault boundaries into every agent execution layer: classify errors before retrying, interrupt before irreversible actions, checkpoint state at decision points, and degrade gracefully when capabilities are unavailable.

**Classify before you retry.** Route recovery strategy to error type, not error presence:

| Error category | Symptoms | Correct recovery |
|---|---|---|
| Transient API | 429, 500, 503, timeout | Retry with exponential backoff |
| Context overflow | Token limit exceeded | Compress context, truncate history, not retry |
| Hallucinated tool | Tool not found, wrong params | Re-fetch tool catalog, not retry same call |
| Reasoning collapse | Loop, repetition, max steps hit | Restart from checkpoint, not continue |
| Specification drift | Output diverges from intent | Interrupt + human review |
| Side-effect failure | Write fails, external API rejects | Rollback + retry from last checkpoint |

**Interrupt before irreversible actions.** Wrap every side-effecting node — writes, emails, API mutations, database commits — in a pre-commit checkpoint. On interrupt, the agent saves its full state (tool call history, intermediate outputs, memory) and waits. A human approves or corrects before the node resumes.

**Use circuit breakers for downstream dependencies.** When a tool or API fails N times consecutively, stop calling it and route to fallback. Track failure rate per tool endpoint, not just per agent run. A single degraded dependency that takes 30s to timeout will serialize your entire pipeline.

**Implement graceful degradation, not brittle fallback.** When a capability is unavailable, the agent should still produce a useful output — escalate with full context, use a slower/more-expensive model as fallback, or surface the uncertainty to the user. Do not return silent failure.

**Checkpoint at decision points, not just on errors.** Save state snapshots at every branch: before a multi-way routing decision, before calling an external tool, before updating memory. This enables replay, debugging, and rollback without re-executing the entire run.

**Detect drift, not just failure.** Session-level metrics catch crashes but miss drift. Track trajectory-level signals: tool selection consistency across similar inputs, output distribution shift, and step count anomalies. A sudden jump from 8 steps to 40 steps is a failure signal even if every individual step logged "success."

## Evidence

- **Survey:** SAP Labs KDD 2025 paper "Evaluation and Benchmarking of LLM Agents" (arXiv:2507.21504) — identifies four evaluation objectives (task completion, output quality, latency/cost, capability) and four evaluation processes (static, dynamic, judge-based, human review). Notably frames evaluation as a two-dimensional taxonomy rather than a single benchmark.
- **Engineering post:** Keats AI "Error Recovery Patterns for Production AI Agents" (keats-ai.dev) — documents seven error categories with distinct recovery strategies. Key finding: generic retry logic works only for transient errors; for all other categories it wastes tokens and compounds problems. The core principle: classify before retry.
- **Research synthesis:** Zylos AI "AI Agent Self-Healing and Failure Recovery" (zylos.ai, 2026) — draws on Galileo's 2025 production analysis showing specification failures (42%), coordination breakdowns (37%), and verification gaps (21%) as the dominant failure distribution in multi-agent systems. Introduces circuit breakers, supervisor trees, and idempotency guards borrowed from distributed systems engineering.
- **Engineering post:** ActiveWizards "LangGraph State Management: Checkpointing & Recovery" (activewizards.com, 2026) — provides a checkpointer decision matrix: `MemorySaver` for local dev, `SqliteSaver` for single-process servers, `PostgresSaver` for multi-process/containerized production. Key gotcha: teams shipping to production on `MemorySaver` experience state loss on pod restarts and spend sprints reverse-engineering database schemas.
- **Blog post:** Subodh Jena "Persistence and Checkpointing: Time Travel and Recovery for LLM Agents" (subodhjena.com, April 2026) — frames checkpointing as the unifying capability for four production requirements: surviving process restarts, supporting human approvals mid-run, enabling execution replay for debugging, and continuing from the last successful step after error. LangGraph checkpointers, OpenAI Assistants API thread state, and Temporal workflows all implement the same primitive at different granularities.

## Gotchas

- **Retrying non-transient errors compounds the problem.** A context overflow retried with the same bloated context fails identically. A hallucinated tool call retried with the same tool definition reproduces the same hallucination. Log the error classification, then route to the correct recovery path.
- **`MemorySaver` is not production-ready.** State is lost on every process restart. If you're using it in production because "it was just for testing," a single pod restart will lose every in-flight agent thread. Migrate to `PostgresSaver` or equivalent before you have 50 active threads to recover manually.
- **Max-step limits catch loops but not drift.** A step limit prevents infinite loops, but an agent can silently execute 40 steps of subtly wrong logic without repeating itself. Combine step limits with trajectory validation — check intermediate outputs against expected output structure, not just final answers.
- **Circuit breakers must be per-tool, not per-agent.** If you track circuit breaker state at the agent level, one failing tool will open the breaker for all tools, even healthy ones. Track failure rate per tool endpoint.
- **Checkpoint state includes more than you think.** A checkpoint must capture tool call history, intermediate outputs, memory state, and thread identifiers — not just the last LLM response. Partial state saves will corrupt your recovery path.
