# S-1422 · The Agent Failure Recovery Stack — When Your Agent Fails Silently and Wastes Your Budget

Your agent spent 47 minutes and $23 in API credits retrying a query that was structurally impossible to answer. It never raised an error. It never stopped. It just kept calling the search tool with the same broken parameters, accumulating context until the model refused to generate further. By the time you noticed, it had consumed a week's budget and accomplished nothing. You weren't watching. Nobody was.

## Forces

- **Multi-step compounding failure.** A 10-step pipeline where each step has 85% reliability succeeds ~20% of the time overall. Each step is a new opportunity for a failure that wasn't there before. Standard error handling assumes a step either works or it doesn't — agents add steps that "work" but produce wrong outputs (Galileo, 2025; Zylos Research, 2026)
- **Traditional error handling doesn't protect against agent failures.** Try-catch catches exceptions, not hallucinations returning HTTP 200. Tool calls that succeed technically can fail semantically. Reasoning chains that produce confident nonsense have no stack trace (Preporato / NCP-AAI, May 2026)
- **Agents fail silently.** Unlike a crashed microservice that pages an SRE, an agent may loop for 35 minutes, spawn redundant subprocesses, or take irreversible actions before a human notices. Standard monitoring detects none of this by default (Zylos Research, 2026; arXiv 2605.01604, May 2026)
- **Cascade failures in multi-agent systems.** One agent's bad output becomes another agent's input. By the time the error is visible at the output layer, the root cause is three hops away. Specification failures account for 42% of incidents, coordination breakdowns for 37%, and verification gaps for 21% (Galileo 2025, cited in Zylos Research)

## The Move

Build a layered failure-recovery architecture that treats agent errors as a first-class engineering concern. The layers, from innermost to outermost:

1. **Hard limits with early stopping.** Set `max_iterations` (LangChain recommendation: 10) with `early_stopping_method='generate'` — this stops the agent when it appears stuck, not just when it hits the ceiling. Reduces token waste by up to 92% versus letting agents hit natural context limits (Markaicode, May 2026). Pair with a step-count guard that surfaces a warning before the limit triggers.

2. **Layered retry strategy.** Not all errors are equal. Transient network errors: simple retry. Rate limits (429): exponential backoff with jitter (AWS research shows jitter prevents thundering-herd re-requests). Tool failures: retry once with the same tool, then route to an alternate tool or fallback. Never retry hallucinated content — it won't self-correct (kangclaw.github.io, Feb 2026).

3. **Stateful checkpoints with rollback.** Frameworks like LangGraph and Microsoft Agent Framework provide native checkpoint/resume primitives. On each step boundary, snapshot agent state (context window, tool results, intermediate outputs). When recovery fails, roll back to the last clean checkpoint instead of re-executing from the user prompt. For destructive operations, use shadow git repos with automatic snapshots before mutations (fast.io; Hermes Agent docs, mudrii/hermes-agent-docs).

4. **Supervisor tree for multi-agent systems.** Inspired by Erlang/OTP, treat each agent as an actor with isolated private state and a mailbox for async messages. A supervisor agent monitors child agents and applies a restart policy: restart on recoverable failure, escalate to a human on unrecoverable failure, and terminate if a child exceeds restart frequency thresholds. Theater framework (GitHub: colinrozzi/theater) implements this as WebAssembly components with hierarchical supervision (Theater Docs, actor model page).

5. **Graceful degradation.** When a step fails and retry is exhausted, don't propagate the failure — degrade to a partial result. If a search tool fails, fall back to a cached result or a simpler retrieval path. The goal is "done enough" rather than "perfect or nothing." Circuit breakers prevent a failing subsystem from taking the whole agent down (Preporato, May 2026; kangclaw.github.io).

6. **Silent-failure detection as observability.** Standard metrics fail to detect 4 of 7 agent failure modes entirely (arXiv 2605.01604, May 2026). Instrument with OpenTelemetry semantic conventions for LLM agents. Track: step count per turn (high count = possible loop), context window utilization (approaching limit = possible drift), tool call success rate per tool (low rate = bad tool definition), and cost per task (spike = possible runaway). WhyLabs LangKit and Hazel.js observability both provide LLM-specific monitoring with hallucination detection.

7. **Idempotency guards.** Make every agent action safe to retry. Use idempotency keys on write operations, version vectors on state, and confirmation prompts before irreversible actions (ARF: petterjuan/agentic-reliability-framework).

## Evidence

- **Blog post:** "Agentic AI in Production: Error Recovery, Observability, and Scaling Patterns" — A candidate evaluation agent at Asynq.ai hallucinated tool parameters and got stuck in loops; an image generation pipeline at Modelia.ai approved flawed outputs. Setting max_iterations=10 with early stopping cut token costs by 92%. — [URL](https://www.harshrastogi.tech/blog/agentic-ai-error-recovery-observability-patterns)
- **Research synthesis:** Zylos Research (2026) — A 10-step pipeline at 85% per-step reliability succeeds ~20% of the time. Galileo's 2025 analysis of agent incidents: specification failures (42%), coordination breakdowns (37%), verification gaps (21%). Agents may silently loop for 35 minutes, spawn redundant subprocesses, or take irreversible actions before detection. — [URL](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)
- **arXiv paper:** "Evaluating Agentic AI in the Wild" (Pandey, arXiv:2605.01604, May 2026) — Standard evaluation frameworks (HELM, MT-Bench, AgentBench) fail to detect 4 of 7 production failure modes entirely. Key production challenge: sequential decisions with compounding errors where each step's bad output becomes the next step's input. — [URL](https://arxiv.org/html/2605.01604)
- **GitHub framework:** Theater — Agent framework implementing Erlang-style hierarchical supervisor trees where parent agents monitor child agents with per-child restart policies (restart, escalate, terminate). Each agent is a WebAssembly component with isolated private state. — [URL](https://colinrozzi.github.io/theater/guide/core-concepts/actor-model.html)
- **GitHub repo:** Agentic Reliability Framework (petterjuan/agentic-reliability-framework, v3.3.9) — Graph-native reliability platform treating incidents as memory and reasoning problems. Captures operational experience, reasons over it with AI agents, enforces execution boundaries. — [URL](https://github.com/petterjuan/agentic-reliability-framework)
- **Guide:** "Error Handling and Recovery" in ai-system-design-guide — Checkpoint/resume in LangGraph and Microsoft Agent Framework; agent self-correction loops; "stuck in loop" fixes using max iterations. — [URL](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md)

## Gotchas

- **Setting max_iterations too high defeats the purpose.** The point isn't to let the agent run longer — it's to fail fast with a trace when stuck, so you can fix the root cause. 10 is a reasonable starting point; tune based on your average task complexity.
- **Retry logic applied to the wrong error class.** Don't retry hallucinated or logically wrong outputs — the LLM won't self-correct the same way it won't self-correct a null pointer. Only retry transient errors (network, rate limits, timeouts).
- **Rollback doesn't undo side effects.** If your agent wrote to an external system (sent an email, modified a DB record, pushed code) before crashing, rolling back the agent state doesn't roll back the external state. Idempotency guards and confirmation gates before mutating operations are the real solution.
- **Multi-agent cascade failures look like single-agent failures.** When a downstream agent fails, you may diagnose and fix the downstream agent repeatedly without realizing the real problem is a bad output from an upstream agent that you never fixed. Trace the error to its origin, not its symptom.
- **Observability tooling lags the problem.** Most existing monitoring stacks aren't instrumented for LLM-native failure modes. Without OpenTelemetry spans for tool calls, context window markers, and cost-per-step tracking, you'll discover failures the way this stack's opening scenario describes — after the damage is done.
