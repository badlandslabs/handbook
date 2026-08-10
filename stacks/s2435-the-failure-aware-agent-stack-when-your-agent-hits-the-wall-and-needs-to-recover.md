# S-2435 · The Failure-Aware Agent Stack — When Your Agent Hits the Wall and Needs to Recover

Your agent works perfectly in the demo. It handles the happy path flawlessly. Then in production it loops on an unexpected input, double-charges a customer on retry, leaves a half-written ticket in the system, and has no recovery path when a tool goes down. You've added better prompts. You've added more tools. What you haven't done is design the agent to fail — explicitly, safely, and recoverable.

Agents are not reliable by default. They are non-deterministic, they act through fallible tools and services, and small errors compound across every step of a task. A 10-step pipeline where each step has 85% reliability succeeds only ~20% of the time. Failure handling is not optional hygiene — it is the core engineering challenge of the agentic era.

## Forces

- **Retries without idempotency cause double effects.** When a tool call times out, the agent retries. If the tool succeeded on the first try, the retry creates a duplicate side effect — a second charge, a duplicate ticket, a double-sent email. Most agents retry blind.
- **Loop detection is not built-in.** LLMs can and do loop — repeating the same tool call with slightly different arguments, chasing the same failed state. Without explicit loop detection, agents burn tokens until someone notices.
- **Failure modes are categorically different.** A rate-limit retry needs different handling than a malformed JSON response, which needs different handling than a context overflow, which needs different handling than a capability gap. Treating all errors the same — retry or abort — misses the recovery landscape.
- **Progress is lost on crash.** Long-horizon agents that crash mid-task restart from scratch unless state was checkpointed. The cost compounds with task length.
- **Standard evaluation misses failure.** Standard metrics (ROUGE, BERTScore, accuracy) fail to detect four of seven production failure modes entirely, and detect the other three only with multi-cycle lag. You cannot improve what you cannot measure.

## The move

Build the agent to expect failure and handle it at four layers:

**Layer 1 — Classify before you act.** Every error must be classified before choosing a recovery strategy. Retrying a 401 wastes tokens and delays real recovery. Retrying a 400 produces the same 400 five times.

| Error type | Examples | Recovery |
|---|---|---|
| Transient | Rate limits (429), 503, DNS timeout, network hiccup | Retry with exponential backoff + jitter |
| Semantic | Malformed JSON, invalid tool call, schema violation | Re-prompt with corrective context in next turn |
| Resource | Token budget exceeded, context overflow, spending cap | Reduce payload (summarize, drop old results) or switch model |
| Capability | Agent requested unavailable tool | Escalate to parent agent or supervisor |
| Fatal | Auth failure, revoked key, policy violation | Abort immediately; notify human |

**Layer 2 — Idempotency keys on every side-effecting tool.** Every tool that creates, modifies, or deletes external state must accept and respect an idempotency key. On retry, the tool checks the key and deduplicates — returning the original result instead of re-executing. Use deterministic content-derived keys (UUIDv5 or sha256-hex) derived from task inputs, so any retry carries the same key.

**Layer 3 — Loop detection with explicit budget.** Set a maximum iteration count (10–20 is common: OpenAI Agents SDK defaults to `max_turns=10`, CrewAI defaults to `max_iter=20`). Track a rolling window of recent actions and flag repetition. On detection, break and report — do not loop into the budget. Combine with heartbeat monitoring: for long-running agents, detect silence, not just repetition.

**Layer 4 — Checkpoint state at decision boundaries.** Serialize agent state (conversation history, tool results, mid-task progress) at each decision point. On crash, resume from the last checkpoint — not from scratch. The Temporal heartbeat checkpointing pattern (per-step state snapshots inside durable workflow activities) is one proven approach. LangGraph's built-in checkpointing covers single-agent state; Temporal covers cross-service crash recovery.

**Layer 5 — Progressive escalation hierarchy.** Self-correct first (retry with correction), then fallback (switch strategy or model), then degrade gracefully (deliver partial results rather than nothing), then escalate to human. High-stakes or low-confidence actions (irreversible writes, payments, deletions) should require human confirmation before execution — not as a rubber stamp but as a genuine decision checkpoint.

**Layer 6 — Circuit breaker per tool.** Set per-tool timeouts (30s is common for external API calls). If a tool fails N consecutive times, open the circuit — stop calling it and switch to fallback behavior. Reset the circuit after a recovery timeout. This prevents cascading failure from a degraded dependency.

## Evidence

- **arXiv research paper (May 2026):** Seven production-specific failure modes for agentic AI, grounded in systems operating at billion-event scale. Key finding: standard evaluation metrics fail to detect four of seven failure modes entirely. Introduces PAEF (Production Agentic Evaluation Framework) — a five-dimension evaluation framework for continuous production monitoring. — [arXiv:2605.01604](https://arxiv.org/abs/2605.01604)

- **GitHub Discussion (Anthropic, Apr 2026):** Production engineers sharing battle-tested patterns from systems running 5+ autonomous agents 24/7. Reported 97.8% autonomous recovery rate using a three-layer strategy: error classification, retry budgets with circuit breakers, and human escalation for capability gaps. 30-second timeout per tool call. Learned during the Nov 2025 outage. — [anthropics/anthropic-sdk-python#1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)

- **GitHub repo (Jan 2026):** `steveandroulakis/temporal-langgraph-checkpoint-recovery` — LangGraph research agent running inside Temporal activities with dual heartbeat pattern (background heartbeats + immediate superstep checkpoints). Activity resumes from last checkpoint on worker failure. Demonstrates checkpoint-at-every-decision-boundary pattern in production use. — [temporal-langgraph-checkpoint-recovery](https://github.com/steveandroulakis/temporal-langgraph-checkpoint-recovery)

- **GitHub repo (Feb 2026):** `KorahStone/agent-loop-detector` — Lightweight Python library for identifying when AI agents get stuck in repetitive patterns. Tracks rolling window of actions, flags repetition above a similarity threshold, provides full execution tracing for debugging. Zero external dependencies. — [agent-loop-detector](https://github.com/KorahStone/agent-loop-detector)

- **Engineering blog (2026):** Agent Reliability Handbook — 18 patterns for production agent systems including per-step retry budgets, checkpoint recovery, human-in-the-loop escalation, and guardrails that prevent runaway token costs on duplicate operations. — [AgentsInProduction.dev](https://agentsinproduction.dev/)

- **GitHub repos (May 2026):** `agentidemp-py` and `agentidemp-rs` — Idempotency key libraries for LLM agent retries. Deterministic content-derived keys (UUIDv5 or sha256-hex) so retries deduplicate at the provider layer, preventing double-bill and double-dispatch from retrying side-effecting operations. — [MukundaKatta/agentidemp-py](https://github.com/MukundaKatta/agentidemp-py)

- **Research blog (May 2026):** Analysis of multi-agent failure statistics: specification failures at 42% of failures, coordination breakdowns at 37%, verification gaps at 21%. Central thesis: fault tolerance for AI agents is not optional engineering hygiene — it is the core engineering challenge. — [Zylos Research: AI Agent Self-Healing](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery)

## Gotchas

- **Treating all errors as retryable is the most expensive mistake.** A `BadRequestError` (HTTP 400) retried five times wastes five LLM calls and five tool executions against a rate limit quota. Classify first, retry only transient errors.
- **Adding jitter to backoff is non-negotiable.** Exponential backoff without jitter causes thundering herd — all retrying clients wake up simultaneously and re-destabilize the same endpoint. Add random jitter (typically ±25% of the backoff window).
- **Loop detection catches repetition but not stalls.** An agent that calls different tools each turn can still be stuck in a dead end. Pair loop detection with heartbeat monitoring (detect silence, not just repetition) and explicit success conditions (define what "done" looks like so the agent can self-terminate).
- **Checkpointing is only useful if state is resumable.** Saving checkpoint data that cannot be deserialized and executed from is not checkpointing — it is logging. Test recovery paths, not just the happy path.
- **Human-in-the-loop degrades to bottleneck if the human cannot meaningfully evaluate the decision.** A reviewer approving a reasoning path they did not personally travel cannot verify intent — only surface plausibility. Design escalation to ask for specific judgment, not general approval.
