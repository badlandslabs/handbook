# S-1193 · The Agent Failure Recovery Stack — When Your Agent Loops Silently and Bills Exponentially

Your agent worked perfectly in staging. In production, it hit a rate limit at step 3 of 8, entered a retry loop, and burned through $800 in API credits before anyone noticed. The monitoring dashboard showed no errors — just smooth, quiet failure. The gap between agent demos and production is where most implementations quietly die.

## Forces

- Agents fail in ways traditional try-catch blocks can't catch: wrong tool called correctly, HTTP 200 with hallucinated output, loops that produce confident nonsense without throwing exceptions
- Loops don't announce themselves — a GPT-4o agent stuck in retry was discovered only because of the bill, not because of any alert
- A single unhandled API timeout in a multi-agent pipeline can cascade into complete system failure across all downstream agents
- LLMs cannot reliably self-correct reasoning errors without external grounding — intrinsic self-correction is systematically fragile
- Agents that pass benchmarks fail under production load: rate limits, malformed responses, and context truncation are not in the training distribution

## The Move

Build a layered failure recovery system that classifies errors before reacting, limits resource consumption explicitly, persists state across interruptions, and degrades gracefully rather than failing catastrophically.

### Error taxonomy first

Categorize every failure before choosing a recovery strategy. Four distinct types, four different responses:

- **Transient** (rate limits 429, timeouts, 503s): retry with backoff — these resolve themselves
- **Semantic** (malformed JSON, wrong tool name, schema violations): re-prompt with corrective context — the LLM needs guidance, not repetition
- **Resource** (token budget, context overflow, spending cap): reduce payload or switch to a smaller model — do not retry the same expensive call
- **Fatal** (auth 401, revoked keys, policy violations): abort immediately, log, alert — no retry will fix this

From: *Neel Mishra — Agent Error Handling: Retries and Fallbacks* — https://neelmishra.github.io/blog/mlops/llm-agents/agent-error-handling.html

### Hard stops on everything

An agent without a stopping condition is a resource leak. Layer three independent stops:

- **Iteration cap**: hard-stop at `max_iterations` — 10–20 steps for most tasks, 30–50 for complex research. Cap at 50 and decompose the task into sub-agents if you need more. The zeroclaw agent framework even had a hardcoded `MAX_TOOL_ITERATIONS = 10` that overrode the config — caught as a bug in 2026
- **Token budget**: track cumulative token spend per task. When the budget is exhausted, halt and return the partial result with a clear `cap_reached` flag — never silently continue or drop output
- **Timeout**: set a wall-clock deadline. For user-facing agents, this is the SLA. After the deadline, return whatever exists and mark it incomplete

From: *Learnixo — Agentic AI Patterns, Lesson 14* — https://learnixo.io/courses/agentic-ai-patterns/ap-max-iterations

### Loop detection is not iteration counting

Simple max-iteration caps miss the expensive failure mode: semantic loops where the agent produces different output each step but makes no progress. Detecting loops requires three strategies:

- **String-hash exact match**: hash each tool-call signature; if the same call appears N times, trip a circuit breaker. O(1) lookup, catches exact repetition
- **Semantic similarity**: embed recent tool-call sequences; if cosine distance between consecutive steps is below a threshold, flag as near-identical looping
- **Frequency analysis**: track tool-call distribution over a sliding window; behavioral loops (different tools, same outcome) show statistical signatures before they become obvious

Three distinct loop types, three detection strategies. A ping-pong loop between two agents in a multi-agent graph is structurally different from a single-agent exact repetition — both need to be caught.

From: *SupraWall — AI Agent Infinite Loop Detection* — https://www.supra-wall.com/learn/ai-agent-infinite-loop-detection

### Circuit breaker with exponential backoff

When a service is failing, stop hammering it. Implement a circuit breaker on every external call:

- Track consecutive failures per endpoint
- Trip the breaker after 5 consecutive failures — stop calling the failing service
- Enter a "half-open" probe phase: allow one test call after a cooldown period
- Re-close or re-open based on the probe result
- Pair with exponential backoff: `base_delay * 2^attempt + jitter` — start at 1s, cap at 60s with 30% jitter

For multi-agent pipelines, a stateful graph circuit breaker catches recursive cycles between agents: when agent A calls agent B which calls agent A within the same turn, the graph itself is in a loop — not the individual agents.

From: *AI Agents Blog — Agent Error Recovery: 5 Patterns for Production Reliability* (Mar 2026) — https://aiagentsblog.com/blog/agent-error-recovery-patterns/
From: *HackerNoon — How to Survive the Multi-Agent Loop of Death* (May 2026) — https://hackernoon.com/how-to-survive-the-multi-agent-loop-of-death-in-production

### Checkpoint-and-resume for long-running tasks

Agents that crash mid-workflow must resume from where they stopped, not from the beginning. The pattern: after each completed step, serialize agent state (current step index, accumulated results, tool-call history) to durable storage. On restart, read the last checkpoint and resume from there.

The `agent-resume` Python library (zero dependencies, 35 tests) implements this with two primitives: a function to save checkpoints and a store to track processed items. For agents running days to weeks, add signal handling (SIGTERM, Ctrl+C) to checkpoint on graceful shutdown, not just on crash.

From: *DEV Community — agent-resume: Checkpoint and Resume Long-Running AI Agent Jobs* — https://dev.to/mukundakatta/agent-resume-checkpoint-and-resume-long-running-ai-agent-jobs-in-python-4n22
From: *Agents for Science — Long-Lived Agent with Checkpoint/Resume* — https://agents4science.github.io/Capabilities/long-lived-agents/AgentsCheckpoint/

### Model fallback chain

Don't rely on a single model as the sole execution path. Build an explicit tier:

- Primary model handles normal requests
- If primary fails with a transient error: retry on the same model
- If primary fails with a capability or availability error: fall back to a tier-2 model (e.g., Opus → Sonnet → Haiku)
- If tier-2 also fails: queue for retry with backoff, alert the operator
- Track which model produced which output so failed outputs can be attributed

This is not just reliability — it's also cost governance. A degraded mode using Haiku is better than a crashed mode using Opus.

From: *GitHub Discussion #1341 — What patterns do you use for AI agent error recovery?* (Apr 2026) — https://github.com/anthropics/anthropic-sdk-python/discussions/1341

### Grounded self-correction, not reflexive self-correction

When the agent makes a mistake, it needs external signal to detect and fix it — not just its own confidence. Intrinsic self-correction (model judging itself) is systematically biased: the model that produced the wrong answer is the same model asked to evaluate it. Grounded self-correction uses:

- **Execution results**: run the code, check the output, feed the error back as corrective context
- **Structured critics**: a separate, smaller model evaluates the primary model's output against a rubric
- **Process Reward Models (PRMs)**: trained to score reasoning steps, not just final answers — catches errors mid-reasoning

Reflexion (NeurIPS 2023) achieved 91% pass@1 on HumanEval with verbal self-critique and memory. But the 2025 consensus is that this only works when the critique is grounded in external feedback — execution traces, test results, or a trained critic — not in the model's own assessment of its reasoning.

From: *Zylos Research — Agent Self-Correction: From Reflexion to Process Reward Models* (May 2026) — https://zylos.ai/research/2026-05-12-agent-self-correction-reflexion-to-prm

### Escalation queue for unresolvable failures

Some failures cannot be recovered automatically. When all retry budgets are exhausted and the agent is still failing, route to a human operator — not into an infinite loop of increasingly desperate retries.

- Maintain a `budget-paused` state: the agent has stopped, the task is queued, an alert is sent
- Include full context: what was attempted, what failed, what the partial result is
- The human decides: retry with modified parameters, abort, or escalate further

## Evidence

- **DEV Community / Hacker News report:** A GPT-4o agent got stuck in a retry loop and ran up a bill before anyone noticed — no alert triggered, no error logged, just smooth silent failure and a credit card statement — https://dev.to/ceaksan/an-ai-agent-got-stuck-in-a-loop-the-monitoring-tools-saw-nothing-1ai
- **GetATeam Blog (Nov 2025):** Woke up to 47 Slack alerts after a single unhandled API timeout cascaded into complete system failure. After deploying hundreds of agents in production: "90% of AI agent implementations fail in production due to preventable issues" — https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/
- **GitHub Discussion #1341 (Apr 2026):** Production teams sharing 4-layer recovery stacks — connection resilience, model fallback chains, tool failure isolation, and escalation queues. Tiered from retry → degraded mode → pause → human — https://github.com/anthropics/anthropic-sdk-python/discussions/1341

## Gotchas

- **Catching exceptions is not enough.** A tool that returns HTTP 200 with a hallucinated payload doesn't throw. You need semantic validation: parse the response schema, check required fields, validate value ranges — not just catch the HTTP error
- **Retry the same call N times is not a strategy.** Retrying without backoff or error classification will hit the same rate limit again. Every retry must be classified: transient errors retry, fatal errors abort
- **The monitoring gap is real.** Standard APM tools (Datadog, New Relic) don't know what a "good" agent step looks like. HTTP 200 on a tool call with hallucinated parameters is indistinguishable from success in most dashboards. You need agent-specific observability: step counts, token budgets, loop detection signals
- **Fallback chains have a cost hierarchy.** Opus → Sonnet → Haiku isn't just a reliability ladder — it's a cost ladder. Track which model handles which requests and why, or you'll get unexpected cost spikes when the primary model starts failing and everything cascades to the fallback
