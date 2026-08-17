# S-2781 · The Failure Recovery Stack — When Your Agent Returns 200 OK But Everything Is Wrong

Your agent isn't crashing. It's returning HTTP 200 with a confident answer that is subtly, completely wrong — hallucinating a tool call, sending a package to the wrong address, publishing gibberish, or looping silently for 35 minutes. Traditional error handling doesn't catch this. A 10-step pipeline where each step has 85% reliability succeeds end-to-end only ~20% of the time. This is the failure recovery stack — the layered architecture that keeps agents running when the model, the tools, or the network decides to misbehave.

## Forces

- **Agents fail differently than software.** Traditional code throws a `500` with a stack trace. Agents return `200 OK` while being fundamentally wrong. The entire error surface lives inside the output token stream, not the HTTP envelope.
- **Failure compounds.** A 10-step pipeline at 85% per-step reliability → ~20% end-to-end success. Each additional tool call multiplies the failure surface. Per-step: "Galileo 2025, via Zylos Research" — https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/
- **Recovery must be designed in.** Retrofitting idempotency and escalation logic into a live agent means rewriting the parts customers already depend on. — https://agent-works.ai/insights/agent-error-handling-recovery-patterns
- **The four failure types require four different strategies.** A retry loop for a rate-limit error is correct. A retry loop for a hallucinated tool name wastes tokens and deepens the failure. — https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html

## The move

Build a layered failure architecture from four concentric rings. Handle each ring with the right primitive — not the same retry logic applied uniformly.

**Ring 1 — Classify the error type before doing anything.**
Route errors into four buckets with distinct recovery paths:
- **Transient** (rate limit 429, timeout, DNS, 503): retry with backoff. Same request succeeds on repeat.
- **Semantic** (malformed JSON, non-existent tool, schema violation): re-prompt with corrective context. Retrying the same prompt never helps.
- **Resource** (token budget exceeded, context overflow, spending cap): reduce the payload. Summarize history, drop oldest results, switch to a smaller/faster model.
- **Fatal** (auth failure, revoked API key, policy violation): stop, log, escalate. Do not retry.

Source: "Agent Error Handling: Retries and Fallbacks" — https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html

**Ring 2 — Make retries safe with idempotency keys.**
Every tool call that causes state changes must carry a client-generated idempotency key. On retry, if the server has already processed this key, it returns the cached result instead of re-executing. Prevents double-charges, duplicate writes, and corrupted state from safe retries.
Source: "Error Handling and Recovery Patterns for AI Agents" — https://agent-works.ai/insights/agent-error-handling-recovery-patterns

**Ring 3 — Detect loops before the token budget expires.**
Fixed `max_iterations` caps waste money on converged tasks and miss degradation spirals. LoopGain (loopgain-ai/loopgain, Apache-2.0) uses real-time loop-gain measurement (Aβ bands) to detect convergence and rollback to the best-so-far state. Benchmarks: 92.8% less API spend vs `max_iter=20` ($27.05 → $1.94), ~15× faster median wall-clock (30.9s → 2.1s). Supports LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents, and Claude Agent SDK adapters.
Source: GitHub — `loopgain-ai/loopgain` — https://github.com/loopgain-ai/loopgain

**Ring 4 — Checkpoint state and make the workflow resumable.**
Persist agent state at decision points — completed steps, current context, intermediate results. On interruption, the agent queries for incomplete tasks and resumes from the latest checkpoint rather than restarting from scratch.
Source: "How to Implement Checkpoint Recovery for Agents" — https://www.adaptiverecall.com/ai-agent-memory/checkpoint-recovery.php

**Ring 5 — Circuit breakers to prevent cascade failure.**
Track failure rates per operation. When failures exceed a threshold (e.g., 5 failures in 10 calls), open the circuit — block further calls to that operation and route to a fallback (cached data, degraded response, or human escalation). Most teams implement retry logic; far fewer implement circuit breakers. The gap is costly.
Source: "Error Handling and Recovery Patterns for AI Agents" — https://agent-works.ai/insights/agent-error-handling-recovery-patterns

**Ring 6 — Know when to stop and escalate to a human.**
Define a confidence threshold below which the agent stops attempting autonomous recovery. The escalation notification must include: original query, error type, retry count, fallback strategies tried, timestamps, and relevant identifiers (session ID, task ID). The agent hands off the complete execution context, not just the error message.
Source: "Error Handling in AI Agents: Circuit Breakers, Retry & Recovery" — https://preporato.com/blog/error-handling-resilience-patterns-agentic-ai-systems

**Ring 7 — Graceful degradation for partial failures.**
When tools or data are unavailable, agents must continue meaningfully rather than fail completely. Return a fallback response: "CRM unreachable; using last-known contact data." Cache critical tool responses. Operate on partial context rather than crashing.
Source: "Why 90% of AI Agents Fail in Production (And How We Solved It)" — https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/

**Ring 8 — Budget guardrails as a survival requirement.**
Hard USD caps per task and per session. Agents must never silently drift over budget. The resilient-agent reference implementation (`MukundaKatta/resilient-agent`) ships a budget cap module alongside exponential backoff, circuit breaker, and an append-only audit trail.
Source: GitHub — `MukundaKatta/resilient-agent` — https://github.com/MukundaKatta/resilient-agent

## Evidence

- **GitHub + blog post:** LoopGain open-source cost controller with 2,000-paired-trial benchmarks showing 92.8% API spend reduction using loop-gain convergence detection vs fixed `max_iter` caps — https://github.com/loopgain-ai/loopgain
- **Engineering blog:** AgentWorks layered recovery architecture covering idempotency keys, circuit breakers, confidence-based routing, and escalation protocols — https://agent-works.ai/insights/agent-error-handling-recovery-patterns
- **Research synthesis:** Zylos Research taxonomy of AI agent failures — specification (~42% of multi-agent failures), coordination (~37%), verification (~21%) — and the compounding reliability math — https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery/
- **HN discussion (284 points, 117 comments):** Simon Willison's "Designing agentic loops" — consensus that autonomous loops require sandboxing plus constraint enforcement, not just better prompts — https://news.ycombinator.com/item?id=45426680
- **Reference implementation:** Resilient-agent — ~700 lines of Python composing four resilience primitives (retry, breaker, budget, allowlist) around an LLM provider — https://github.com/MukundaKatta/resilient-agent
- **Primary practitioner post:** "Why 90% of AI Agents Fail in Production" — detailed the five critical failure patterns: API rate limits, unexpected input variations, network instability, memory leaks, and cascading failures — https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/

## Gotchas

- **Don't apply retry uniformly.** Retrying a semantic failure (wrong tool name, hallucinated JSON) wastes tokens and deepens the failure. Classify first.
- **Fixed `max_iterations` is not loop detection.** It caps execution at an arbitrary number regardless of whether the agent has converged, degraded, or is still making progress. Use convergence-aware stopping instead.
- **Hard-stops require managed runtimes.** Credential rotation, loop detection, and transparent retry at the infrastructure level (e.g., Hermes Agent managed runtime scored 94/100 on self-healing vs 37–43% for naive implementations) are categories of failure that cannot be solved by recovery code alone.
- **Escalation must include execution context.** Handing a human a bare error message forces them to reproduce the failure. Hand them the full session state, retry history, and diagnosis.
