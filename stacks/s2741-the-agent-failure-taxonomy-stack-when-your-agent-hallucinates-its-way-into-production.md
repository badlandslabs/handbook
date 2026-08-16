# S-2741 · The Agent Failure Taxonomy Stack — When Your Agent Hallucinates Its Way Into Production

Your agent worked perfectly in development. In production, it hallucinates tool parameters, gets stuck in loops, approves flawed outputs, and costs three times budget. The failure is not one thing — it is five distinct failure modes, each requiring a different recovery strategy, and most teams only discover them when users start filing bugs.

## Forces

- **Agents fail non-deterministically.** Unlike standard software, the same input can produce different failure modes on different runs. Try-catch blocks are necessary but nowhere near sufficient.
- **Completion pressure overrides quality pressure.** Agents optimizing for task completion will approve flawed outputs, skip validation steps, and skip retry logic — because finishing feels like succeeding. Production agents at Modelia.ai approved flawed image generations while "optimizing for workflow completion over quality" (Rastogi, 2026).
- **Failure cascades are invisible.** An agent stuck in a loop looks identical to an agent taking longer than expected — until the observability bill arrives. Most teams don't have alerting for "agent is taking too long" until after the first incident.
- **Self-correction is a double-edged sword.** Letting agents retry their own decisions can help, but without guardrails, retries amplify the original error rather than fixing it.

## The Move

Build a layered failure-handling architecture that classifies failures by type and routes each to the appropriate recovery strategy.

### Failure Taxonomy (from production incidents)

1. **Hallucinated Tools** — Agent calls a tool that doesn't exist or invents parameters. Fix: schema-validate tool calls against a strict registry before execution. Never let the model decide which tools exist.
2. **Stuck in a Loop** — Agent repeats the same tool call with identical arguments. Fix: emit a step counter into the agent state; if the same tool+args appear N times, escalate or abort. Common threshold: 3 repeats.
3. **Context Overflow** — Long conversations or large tool responses silently degrade agent reasoning. Fix: stream tool responses into a scratchpad or summary rather than raw history; enforce max context budgets per agent turn.
4. **Quality vs. Completion Trade-off** — Agent declares success before output meets quality bar. Fix: separate "task completed" from "output approved" — introduce a deterministic validation gate before the agent considers a task done.
5. **Cascading Timeout** — One slow tool call freezes the entire pipeline. Fix: per-step timeouts with circuit breakers; failed steps should not block downstream agents.

### Recovery Patterns (from LangGraph, Microsoft Agent Framework, and production teams)

- **Self-correction loop:** After a failed tool call, give the agent the error and let it reformulate — but cap retries at 2. More than 2 retries on the same step almost always amplifies the error.
- **Stateful rollback (checkpointing):** LangGraph and Microsoft Agent Framework both expose native checkpoint/resume primitives. Save state after every meaningful state change. On failure, rehydrate from the last clean checkpoint rather than re-running from scratch.
- **Graceful degradation:** When a non-critical tool fails, continue with degraded capability rather than failing the whole pipeline. For example: if a web search fails, fall back to cached results or a simpler retrieval path. For critical tools, fail fast and alert.
- **Stuck-loop guard:** Track the last 5 (tool, arguments) pairs in agent state. If the current call matches all 5, inject a "you appear to be repeating yourself" system message and force a different approach.
- **Circuit breaker pattern:** For multi-agent pipelines, wrap each agent in a circuit breaker. If an agent fails 3 times consecutively, open the circuit, alert, and route to human review.

## Evidence

- **Blog post (Harsh Rastogi, AI Product Engineer at Modelia.ai/Asynq.ai, March 2026):** Detailed post-mortem of two production incidents — a candidate evaluation agent at Asynq.ai that "hallucinated tool parameters, got stuck in loops, occasionally produced evaluations that contradicted its own reasoning, and cost 3x what we budgeted" and an image generation agent at Modelia.ai that approved flawed outputs while optimizing for workflow completion. Introduces the five failure mode taxonomy. — [URL](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **GitHub (ombharatiya/ai-system-design-guide):** Community-curated guide on agentic system design with a dedicated section on error handling taxonomy and recovery patterns. Notes that error handling has shifted from "Try-Catch blocks to Agentic Self-Correction and Stateful Rollbacks, with frameworks like LangGraph and Microsoft Agent Framework providing native checkpoint/resume primitives." — [URL](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)
- **HN discussion (Ask HN: "How are you scaling AI agents reliably in production?", ~1 year ago):** Practitioner thread where a small team describes production setup with "Python, Kubernetes, MongoDB (state), Redis (queues)" using LangGraph for orchestration. Key finding: use "memory checkpointer after every state change" and implement per-step timeouts. Also notes that "Airflow/Prefect [are] not recommended for agent orchestration — better for batch processing." — [URL](https://news.mcan.sh/item/44909029)
- **Blog post (Markaicode, April 2026):** Describes a production incident where an agent pipeline froze completely after a single timeout — "the process never recovered." Solved by implementing per-step circuit breakers. — [URL](https://markaicode.com/howto/how-to-configure-langgraph-production-setup)
- **Survey (Cleanlab, August 2025, n=95 engineering leaders with agents live in production):** Only 5% of surveyed organizations have agents live in production. Among those, "most are still struggling with basic reliability, not advanced capabilities." — [URL](https://cleanlab.ai/ai-agents-in-production-2025/)

## Gotchas

- **Naming your recovery "retry" is not the same as fixing the failure.** A retry only helps if the failure mode is transient. Persistent failures (wrong tool, hallucinated params) retry into the same error. Diagnose before retrying.
- **Checkpointing state that includes the error is useless.** When saving a checkpoint, save the pre-error state. A checkpoint taken after a hallucinated tool call contains the hallucination — rolling back to it restores the broken reasoning.
- **Observability without alert thresholds is noise.** Teams instrument their agents but forget to set alerts on key signals: step count per task, cost per task, tool call failure rate. Without thresholds, the observability data is only useful for post-mortems, not prevention.
- **LLM-as-judge for quality gating is unreliable for the same reason agents fail.** If your agent approves flawed outputs, a judge powered by the same model may also approve them. Pair LLM-judge with at least one deterministic validation (schema check, rule check, or human spot-check).
- **Timeout values tuned in development are wrong in production.** Network latency, API throttling, and concurrent load all increase timeouts. Set timeouts conservatively and add jitter rather than using fixed values.
