# S-2716 · The Agent Failure-Interruption Stack — When Your Agent Silently Burns $47K in a Loop

Your multi-agent system worked in staging. In production it ran for 11 days straight, two agents caught in an infinite conversation loop, compounding costs with no circuit breaker to stop it. $47,000 later, you pull the plug. The agent never told you it was stuck — it just kept calling the model, accumulating context, and re-trying. The problem is not that agents fail. The problem is that their failure modes are silent, expensive, and cascading.

## Forces

- **Agents fail non-deterministically.** Unlike a service that crashes with a stack trace, an agent can return HTTP 200 with hallucinated tool arguments. A tool call that succeeds technically can fail semantically. Traditional try-catch blocks don't cover these failure modes.
- **Error propagation cascades.** A single tool failure ripples through planning, memory, and action modules. The agent's state degrades progressively until it's pursuing the wrong goal entirely — with no error code to flag it.
- **Loops are the #1 cost sink.** Single agents consume ~4x the tokens of a single chat; multi-agent systems ~15x. Each loop cycle re-sends accumulated history. An agent stuck in a loop on a single task can match the token cost of a full SWE-bench run (~1,000x a single call). Most agents don't self-report when they're looping.
- **Context rot compounds inaccuracy.** As context window fills with loop iterations, the agent's outputs degrade. It spends more tokens producing worse decisions — the exact opposite of what you'd expect from more computation.

## The move

Build layered failure-interruption infrastructure: detect loops before they cost, checkpoint state so recovery doesn't require restart, cascade gracefully when tools fail, and give the agent an explicit escape handoff.

### Loop detection: counter-based intervention

Track the `(Tool, Args)` tuple per session. If the same tuple appears 3 times in one session, inject a mandatory pivot instruction: *"You have tried this N times. This path is dead. Try a different tool or admit you are stuck."* This is what the `agent-watchdog` and `agentguard` libraries implement as their core primitive.

### Budget guards: per-tool spend limits

Set token and dollar spend limits per tool call before the agent runs. When a threshold is breached, halt execution. One developer on HN built exactly this after losing $200 to an agent loop overnight — per-tool AI spend controls that stop execution before runaway costs accumulate. Tools like `lava.so` and `agent-watchdog` surface real-time spend versus budget as the agent runs.

### Stateful checkpointing: save after every tool call

After every successful tool call, save a state snapshot to durable storage (Redis, Postgres). If the agent enters a logical stall, the supervisor resets to the last safe checkpoint and forces a different execution path. LangGraph's built-in checkpointing primitives make this straightforward; the pattern applies to any graph-based orchestrator. High-reliability agent deployments treat checkpoints as non-optional — the cost of replaying one step is always less than the cost of a full restart.

### Graceful degradation: partial results over complete failure

When a tool fails in a multi-step workflow, return what succeeded with a clear indication of what is missing. Do not fail the entire run. A partial "here are 3 travel options, weather data unavailable" is more useful than an error page. The NCP-AAI certification exam frames this as the correct answer in nearly every multi-tool failure scenario. Partial results preserve user trust and give the next recovery attempt a meaningful starting state.

### Fallback chain and supervisor escalation

Route through a fallback chain: primary agent → simplified agent with fewer tools → supervisor agent that can escalate to human-in-the-loop. The supervisor pattern (used by 62% of enterprise teams with agents in production) provides a single accountability point, clean failure isolation, and a natural handoff surface for the agent to hand off ambiguous cases. Build the supervisor as a separate, smaller model that monitors worker agent outputs and decides when to intervene versus retry.

### Circuit breakers for external calls

Wrap external API calls and LLM invocations in circuit breaker patterns: closed (normal) → open (failing fast, after N consecutive failures) → half-open (probe to see if service recovered). `agentguard` implements this natively with LLM-aware retry logic — when the circuit is open, it raises `CircuitOpenError` rather than retrying into a degraded service. FailWatch implements fail-closed circuit breakers that block dangerous tool calls before execution based on logic rules and budget limits.

## Evidence

- **Engineering post / HN:** A team deployed a four-agent LangChain system coordinating via A2A for market research. Two agents entered an infinite loop for 11 days. Costs escalated from $127/week to $18,400/week, totaling $47,000 before detection. The infrastructure layer for production multi-agent failure handling "doesn't exist yet." — [Towards AI on Medium](https://pub.towardsai.net/we-spent-47-000-running-ai-agents-in-production-heres-what-nobody-tells-you-about-a2a-and-mcp-5f845848de33), October 2025

- **Engineering blog:** Agents consume ~4x the tokens of a single chat; multi-agent systems ~15x; SWE-bench runs ~1,000x. Token usage explains ~80% of performance variance. The mechanism: each loop cycle re-sends accumulated history, so agent cost = useful work × number of passes + re-reading overhead. — [GetUnblocked](https://getunblocked.com/blog/agent-auto-loop-token-cost), June 2026, citing [Anthropic Engineering multi-agent research system (2025)](https://www.anthropic.com/engineering/multi-agent-research-system)

- **GitHub / HN launch:** A developer launched FailWatch on HN after losing $200 to an agent loop. The tool implements fail-closed circuit breakers for AI agents — blocking dangerous tool calls (database writes, payment API calls, email sends) before execution based on logic rules and budget limits. — [HN Show: FailWatch](https://news.ycombinator.com/item?id=46529092)

- **GitHub / production library:** `agentguard` (PyPI, MIT license) — "AI agents fail at 91%+ rates in production." Implements circuit breakers, LLM-aware retry with exponential backoff + jitter, idempotency guards, loop detection (same LLM output N times), and timeout enforcement. Framework-agnostic: works with LangChain, AutoGen, CrewAI, or custom pipelines. Zero dependencies. — [agentguard on GitHub](https://github.com/maheshmakvana/agentguard-llm), April 2026

- **GitHub / production library:** `agent-watchdog` — "A circuit breaker for AI agent runs." Loop detection, real-time budget guards, graceful halts. Framework-agnostic. — [agent-watchdog on GitHub](https://github.com/woodwater2026/agent-watchdog), March 2026

- **Multi-agent research / engineering guide:** Error propagation is the central bottleneck to robust agents — a single failure cascades through planning, memory, and action modules. Modern approaches combining layered defenses, self-healing runtimes, and explicit error taxonomies achieve 24%+ improvement in task success rates. — [Zylos Research](https://zylos.ai/research/2026-01-12-ai-agent-error-handling-recovery), January 2026

- **Microsoft reference architecture:** Supervisor/worker pattern is the most widely deployed multi-agent topology in production, used by 62% of enterprise teams with agents in production. Provides single accountability point, clean failure isolation, and maps naturally to LangGraph graph primitives. — [Microsoft Multi-Agent Reference Architecture](https://github.com/microsoft/multi-agent-reference-architecture/blob/main/docs/reference-architecture/Patterns.md), May 2025

## Gotchas

- **Loop detection by output similarity, not just tool+args.** A sophisticated loop may call different tools with different args but converge on the same output. Track semantic output similarity (e.g., embedding cosine distance) in addition to exact `(tool, args)` tuples.
- **Circuit breakers must not retry into a dead service.** When a circuit is open, immediately fail-fasthumb do not retry. Retrying into a degraded external API or a rate-limited model just widens the blast radius. `CircuitOpenError` is not retryable by design.
- **Checkpoint granularity matters.** Saving state after every node transition in a LangGraph is cheap and safe. Saving only at "milestones" leaves a large rollback window. Default to per-step checkpointing in high-stakes or long-running agent runs.
- **Human-in-the-loop must be genuinely reachable.** A supervisor that escalates to a human who gets a Slack notification 3 hours later is not a working fallback for a production agent running unattended. Define expected response time SLAs and instrument escalation channels before deploying.
- **Budget guards need to account for token costs, not just API call counts.** An agent can make few API calls but generate enormous outputs. Real-time dollar-denominated spend tracking is more meaningful than call-count limits.
