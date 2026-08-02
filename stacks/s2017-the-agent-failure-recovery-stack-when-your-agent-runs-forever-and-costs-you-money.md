# S-2017 · The Agent Failure Recovery Stack — When Your Agent Runs Forever and Costs You Money

Your agent entered a loop on Monday morning. A tool returned a schema the model didn't expect. It re-prompted. Retried. Failed again. Spent $47 on API calls before context overflowed and it died mid-task. No circuit breaker fired. No fallback fired. Nobody noticed until the invoice arrived. This is the failure handling gap: agents get deployed with reasoning logic but without the recovery infrastructure that keeps failures bounded, recoverable, and affordable.

## Forces

- **Agents fail differently than software.** Traditional errors are exceptions with stack traces. Agent errors include confident hallucinations returning HTTP 200, tool calls that succeed technically but fail semantically, and reasoning chains producing plausible nonsense. Try-catch doesn't cover it.
- **The naive retry loop amplifies failure.** Hammering a 401 endpoint wastes tokens and triggers rate limit cascades. A retry without error classification just burns money faster.
- **max_iterations is a blunt instrument.** It stops the loop but clips it too early when still improving, or too late after the agent has already degraded past the point of useful output.
- **Per-tool failures are invisible to global budgets.** If your search API degrades but your code executor is fine, a global step cap doesn't protect against a search retry spiral — you need per-tool state.

## The move

Build a layered failure recovery architecture. Classify errors before retrying. Stop loops by convergence, not count. Isolate tool failures with circuit breakers. Fallback to alternatives before escalating.

### Layer 1 — Error classification before retry

```
Transient (HTTP 429, timeout, 503) → retry with backoff
Semantic (malformed JSON, wrong tool schema) → re-prompt with correction
Resource (context overflow, token cap hit) → reduce payload or switch model
Fatal (auth failure, revoked key) → abort immediately
```

Classify before you retry. A retry that hammers a 401 wastes tokens and time.

### Layer 2 — Bounded retry with exponential backoff + jitter

```
delay = min(base × 2^attempt + random(0, jitter), max_delay)
```

Standard formula: base=1s, max_delay=60s, jitter=0.5. Jitter prevents thundering herd across distributed agents hitting a recovering endpoint simultaneously.

### Layer 3 — Per-tool circuit breaker

Each external tool gets its own three-state machine:
- **Closed** (normal): calls pass through
- **Open** (degraded): calls short-circuit with structured failure for cooldown period (e.g., 60s)
- **Half-open** (probing): allows one test call; success → Closed, failure → Open again

Tracks failure count and rate per tool independently. When the search API degrades, the circuit breaker fires while your code executor keeps working.

### Layer 4 — Convergence-based loop termination

Replace fixed `max_iterations=N` with empirical loop gain measurement:

Track error magnitude E(n) per step. Compute loop gain Aβ = E(n) / E(n-1). When Aβ crosses a convergence threshold (e.g., |Aβ| < τ), stop — the loop is no longer improving, not just that it hit N steps.

LoopGain (2025, open-source) benchmarked this against fixed caps: 92.8% less API spend ($27.05 → $1.94 in 2,000 paired trials), ~15× faster wall-clock, quality preserved (judge win-rate 0.50–0.63 on natural workloads).

Limitation: convergence detection confirms the loop has plateaued, not that the answer is correct — pair with output validators.

### Layer 5 — Fallback chain (multi-provider, multi-model)

```
Primary LLM → Fallback LLM → Cached response → Human escalation
Primary Search API → Backup Search API → Local index → Error message
```

Each fallback should provide diminishing capability gracefully, never a hard crash. Cache responses for read-heavy operations so repeated steps don't re-call external services.

### Layer 6 — State checkpointing

Persist agent state at each step boundary. On failure, restart from last checkpoint rather than re-running from scratch. This prevents a 10-step agent from re-spending tokens on steps 1–7 when it fails at step 8.

## Evidence

- **Research paper:** Production agent tool call failure rates are 12–18% — far above SWE-bench's near-zero infrastructure failure assumption. Three primary categories: infrastructure failures (1–5%, transient), schema/interface failures (semi-transient, auth rot, schema drift), and semantic failures (hallucinated tools, wrong tool selection). — [AgentMarketCap, April 2026](https://agentmarketcap.ai/blog/2026/04/10/agent-tool-call-retry-failure-mode-handling-production-2026)
- **Open-source benchmark:** LoopGain (control-theory-based loop termination) reduced agent API spend by 92.8% ($27.05 → $1.94) and wall-clock time by ~15× while preserving output quality across 2,000 paired trials. Framework adapters for LangGraph, CrewAI, AutoGen, LangChain, OpenAI Agents, and Claude Agent SDK. — [LoopGain GitHub / HN Show, ~13 days ago](https://news.ycombinator.com/item?id=48919562)
- **Academic taxonomy:** An Infinite Agentic Loop (IAL) is defined as a structural execution failure where an agentic feedback path repeats without an effective stopping bound. arXiv 2607.01641 (Huazhong University, July 2026) catalogs 12 failure categories across initialization, parameter handling, execution, and result interpretation phases. — [arXiv:2607.01641](https://arxiv.org/abs/2607.01641)
- **Engineering guide:** The Oracle Developers blog (June 2026) documents the three-layer loop model (observe → decide → act) and a four-category error taxonomy (transient, semantic, resource, fatal) with recovery strategies mapped to each. — [Oracle Developers](https://blogs.oracle.com/developers/the-agent-loop-decoded-three-levels-every-agent-engineer-must-know)
- **Open-source pattern catalog:** The AgentPatterns.ai community pattern for circuit breakers documents the three-state machine implementation with per-tool failure tracking, half-open probing, and configurable thresholds. — [AgentPatterns.ai](https://www.agentpatterns.ai/patterns/agent-design/agent-circuit-breaker)
- **Recovery research:** AgentDebug (arXiv 2509.25370, September 2025) uses targeted failure feedback to enable iterative agent recovery, yielding up to 26% relative improvement in task success across ALFWorld, GAIA, and WebShop benchmarks. — [arXiv:2509.25370](https://arxiv.org/abs/2509.25370)

## Gotchas

- **Classifying by HTTP status is not enough.** A 200 response with hallucinated content or a tool call that technically succeeded but returned wrong data needs semantic error handling, not a retry.
- **Circuit breaker state must be per-tool, not global.** A global circuit breaker fires for everything when one tool fails. Per-tool breakers isolate the degraded component.
- **max_iterations is a floor, not a ceiling.** It stops runaway loops but also stops loops still improving. Pair it with convergence detection or output validators, or accept that you're leaving value on the table.
- **Checkpointing adds latency.** Writing state to disk on every step boundary is expensive for latency-sensitive agents. Use it for long-horizon tasks; skip it for single-turn interactions.
- **Fallback chains have ordering risk.** If your fallback is lower quality, it may produce subtly wrong outputs that look successful. Validate fallback outputs, especially for write operations.
