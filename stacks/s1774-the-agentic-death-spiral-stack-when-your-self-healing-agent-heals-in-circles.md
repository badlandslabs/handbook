# S-1774 · The Agentic Death Spiral Stack — When Your Self-Healing Agent Heals in Circles

Your agent hits a transient API error. It retries. Fails again. Retries with exponential backoff. Fails. Tries a fallback model. The fallback returns a slightly malformed JSON that crashes the parser. The agent treats the parse error as a new failure and retries the whole chain from scratch. You now have an agent that runs 47 times and charges your account $340, producing nothing. This is not a bug in the agent — it is a structural failure in how self-healing logic is designed.

## Forces

- **Self-healing and self-destruction use the same mechanism** — retry loops, recovery paths, and fallback chains are indistinguishable from infinite loops unless bounded
- **Agents fail non-deterministically** — a retry may produce a different output, which means "try again until success" can never converge
- **Traditional fault-tolerance patterns break in the agentic layer** — exponential backoff works for HTTP 503s but not for model hallucinations that look like successes
- **Failure classification is harder than failure recovery** — knowing *that* something failed is easy; knowing *whether* retrying will produce a different result requires understanding the failure mode
- **Compounding blast radius** — a single agent in a multi-agent pipeline that loops can corrupt shared state, trigger cascading failures, and burn budget at every node

## The Move

Frame failure handling as a **classification + routing problem**, not a retry problem. Before every recovery action, the agent (or its orchestrator) must identify the failure type and route accordingly.

**Layer 1 — Classify before you act.** Route every failure to exactly one handler:

| Failure class | Handler | Key constraint |
|---|---|---|
| Transient (429, 500, timeout) | Retry with backoff | Max 3 attempts; budget-gated |
| Permanent (auth failure, bad input, schema change) | Fail fast, route to DLQ | Never retry — waste is 100% |
| Semantic (malformed output, wrong format) | Re-prompt or validator agent | Do not retry the same model with the same prompt |
| Quality (correct format, wrong answer) | Escalate to human or multi-model consensus | No automatic retry loop |
| Looping (same tool called N times) | Hard interrupt + state snapshot | Ceiling on tool-call count per session |

**Layer 2 — Budget everything.** Every recovery path has a token and dollar ceiling. The ceiling is enforced by the execution layer, not the agent. Supergood Solutions (2026) documents the compounding math: *98% per-agent success × 5 sequential agents = ~90% end-to-end reliability*. Budget gates prevent the tail from consuming disproportionate resources.

**Layer 3 — Dead letter queue for permanent failures.** When all retries exhaust, persist partial state to a DLQ — conversation history, tool outputs, error classification, and what the agent was attempting. This is not the same as a failed task. The DLQ enables a human or a scheduled replay process to resume from the snapshot, not from scratch. (Brandon Lincoln Hendricks, "Dead Letter Queues and Retry Policies for Production AI Agent Systems," 2026-03-31)

**Layer 4 — Supervisor tree for multi-agent recovery.** Borrowing from Erlang/OTP's "let it crash" philosophy, wrap each sub-agent in a supervisor that decides what happens on failure: restart (for transient), escalate (for semantic), or terminate (for loops). The supervisor is the orchestrator — the agent itself should not own its own recovery logic. (Zylos Research, "Supervisor Trees and Fault Tolerance Patterns for AI Agent Systems," 2026-03-16)

**Layer 5 — Checkpoint on durable storage.** LangGraph's checkpointing, Temporal's workflow state, or a custom SQLite/Postgres store — every meaningful step snapshots state to durable storage. If the process crashes, the agent resumes from the last checkpoint, not from the beginning. (Markaicode, "Production Multi-Agent System with LangGraph," 2026-03-04)

**Layer 6 — Tool-call ceilings.** A hard cap on how many times any single tool can be called in one session. This is the only reliable guard against infinite loops. The Claude Code compaction loop bug (GitHub Issue #6004, reported 2025-08-18) burned API usage limits because there was no ceiling on compaction attempts — the recovery mechanism fed the failure it was trying to recover from.

## Evidence

- **arXiv paper:** "Evaluating Agentic AI in the Wild: Failure Modes, Drift Patterns, and a Production Evaluation Framework" (2605.01604, 2025) — Standard metrics fail to detect 4 of 7 production failure modes entirely. The paper presents a taxonomy of production failure modes at billion-event scale, noting that tool failure cascades and compounding decision errors are the dominant modes in long-horizon tasks.
- **Engineering post:** Brandon Lincoln Hendricks, "Circuit Breaker Patterns for AI Agent Reliability" (2026-03-25) — Documents that AI circuit breakers must handle *partial failures and quality degradation*, not just binary success/fail. A circuit breaker that only reacts to HTTP errors misses the most expensive failure mode: a model that succeeds at calling tools but produces semantically wrong results.
- **Bug report:** Claude Code Issue #6004, "MAJOR BUG: Claude Code Stuck in Infinite Compaction Loop" (GitHub/anthropics/claude-code, 2025-08-18) — Agent stuck attempting compaction repeatedly, burning usage limits. Closed "not_planned." The root cause: no ceiling on compaction attempts; the recovery logic (compact when context is full) re-triggered when compaction produced output the API marked as near-limit, creating a feedback loop.
- **Engineering post:** Supergood Solutions, "When Agents Fail: Retry Logic, Circuit Breakers, and Dead Letter Queues" (2026-03-08) — Documents that per-agent 98% success rate compounds to 90% across 5 sequential agents, framing fault tolerance as the primary engineering challenge for multi-agent pipelines.

## Gotchas

- **Retry-without-budget is a denial-of-service on your own API key.** A retry loop with no ceiling will run until rate limits, budget limits, or context limits force it to stop — and none of those stops are clean.
- **Treating semantic errors as transient errors wastes the most resources.** A malformed JSON response from an LLM is not fixed by retrying the same prompt with the same model. You need a different approach — different prompt, different model, or a validation agent.
- **The agent's own recovery logic is the most dangerous attack surface.** If the recovery path re-triggers the condition that caused the failure, you get a death spiral. Validate at every layer that recovery is not feeding the failure.
- **Checkpointing without a ceiling is incomplete.** Saving state every N steps helps resume, but if the agent loops on step 3, checkpointing just saves "I am looping on step 3" repeatedly. Ceilings and checkpoints work together.
- **Fallback chains must be pre-validated, not discovered at runtime.** If your OpenAI → Anthropic fallback hasn't been tested under the exact failure mode you're experiencing, the fallback may fail for a different reason and produce a misleading error.
