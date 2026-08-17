# S-2804 · The Structured Failure Recovery Stack

_When your agent hits a transient API error, loops on a bad tool call, or corrupts its own context — and you have no circuit breaker, no rollback, and no way to stop it from burning budget or deleting data_

## Forces

- Agent failures are temporally distributed and non-obvious: a context that drifts over 40 turns looks fine on step 1, catastrophic by step 20 — unlike a crash, there's no clear fault line
- A 10-step pipeline where each step has 85% reliability succeeds end-to-end only ~20% of the time, yet most teams treat each step as independent and never account for compound failure rates
- The three structural failure modes (unauthorized binding agent, over-permissioned agent, unsustainable economics) share one root cause: no structured boundary between what the agent is allowed to do and what it actually does
- Multi-agent systems compound failure surface: ~42% of failures come from specification errors, ~37% from coordination breakdowns, ~21% from verification gaps — and they cascade across agent boundaries
- Agents fail slowly and expensively: a tool-call loop burns budget for 35 minutes before anyone notices; a context corruption silently corrupts every downstream decision

## The move

Build structured failure recovery into the agent loop at three layers: **detect, recover, bound**.

### Detection layer
- **Tool-call circuit breaker:** track calls-per-tool-per-session; trip at 3–5 repeated calls to the same tool and surface the pattern as a loop, not a retry
- **Context drift guard:** monitor token velocity (rate of context growth per step); alert when velocity exceeds 2x the rolling average, signaling accumulation or loops
- **Confidence-weighted output gates:** at each critical step, run a secondary LLM call that scores the primary output on a 1–5 confidence scale; route scores below threshold to human review instead of continuing
- **Idempotency keys on every write action:** tag every state-mutating tool call with a deterministic key; if the agent retries or loops, the system recognizes the duplicate and skips instead of re-executing
- **Structured state checkpointing:** snapshot agent state (context window, tool call history, intermediate outputs) at each major decision point; on failure, replay from the last clean checkpoint instead of re-running from scratch

### Recovery layer
- **Fallback chain, not fallback model:** on LLM failure, route to a deterministic heuristic (rule-based response, cached prior output, escalation template) before escalating — don't just retry the same model
- **Exponential backoff with jitter on API errors:** start at 1s, cap at 32s, add random jitter to avoid thundering-herd on shared LLM endpoints
- **Supervisor-tree architecture for multi-agent systems:** parent agent monitors child agent health via heartbeat; if a child goes silent or loops, the parent kills and reschedules rather than letting the child continue
- **Graceful degradation tiers:** define explicit degradation paths — if real-time data is unavailable, use cached; if agent cannot complete the task, surface partial results with a clear "incomplete" flag and human handoff trigger

### Boundary layer
- **Principle of least privilege on tool permissions:** agents get write access only to the specific resources required for the current task; scope expires after task completion or N minutes, whichever comes first
- **Human-in-the-loop gates at irreversible boundaries:** any tool call that deletes, publishes, sends, or spends gets a mandatory human confirmation step before execution — not a soft suggestion, a hard gate
- **Audit trail on every action:** log tool calls, parameters, responses, and outcomes to an immutable store with timestamps — post-mortems are only possible if the history exists

## Evidence

- **GitHub repo + blog post:** Tanay Shah's open-source library of 4 production reliability patterns (circuit breaker, partial batch retry, idempotency, dead-letter queue) — validated in production, not toy examples — [tanayshah.dev/projects/ai-agent-error-patterns](https://tanayshah.dev/projects/ai-agent-error-patterns)
- **Blog post:** Zylos Research's self-healing failure taxonomy — 10-step pipeline with 85% reliability per step succeeds ~20% of the time; ~42% of multi-agent failures = specification failures, ~37% = coordination, ~21% = verification — [zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)
- **Blog post:** Tanuj Garg's reliability patterns — "AI agent reliability is not primarily a model quality problem, it's a systems engineering problem"; circuit breakers + idempotency + HITL + graceful degradation are the four canonical patterns — [tanujgarg.com/blog/ai-agent-reliability-patterns](https://tanujgarg.com/blog/ai-agent-reliability-patterns)
- **GitHub repo:** Yun1976/ai-agent-incidents — 33 operational lessons from production multi-agent systems in SRE post-mortem format — [github.com/Yun1976/ai-agent-incidents](https://github.com/Yun1976/ai-agent-incidents)
- **Analysis:** Agent Mode AI's six documented failure cases (2024–2025) — Air Canada chatbot, DPD, Replit database deletion, Cursor code deletion, Klarna, NYC MyCity — cluster into three structural modes all covered by OWASP Agentic AI Top 10 controls — [agentmodeai.com/agentic-ai-failure-case-studies](https://agentmodeai.com/agentic-ai-failure-case-studies)
- **Industry framework:** OWASP Top 10 for Agentic Applications 2026 — peer-reviewed by 100+ practitioners, maps failure modes to specific controls including goal hijacking, over-permissioning, and unauthorized action — [genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026](https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026)

## Gotchas

- **"We have retries" is not failure recovery:** naive retries on agent loops just repeat the failure faster and burn more budget — you need loop detection before retry logic
- **Circuit breakers work at the infrastructure level, not just the API level:** a circuit breaker on the LLM API call doesn't help if the agent is looping on a valid tool — you need tool-call-level circuit breakers too
- **Rollback is not just "undo":** agents don't have traditional database transactions; rollback means replaying from a clean state checkpoint, which requires you to actually take checkpoints
- **Human-in-the-loop becomes a bottleneck if it gates every step:** the point is to gate irreversible actions, not to require human sign-off on every token generation — design the tiers explicitly
- **Idempotency keys are only useful if the system recognizes duplicates:** if your tool infrastructure doesn't check the idempotency key before executing, the key is just metadata
