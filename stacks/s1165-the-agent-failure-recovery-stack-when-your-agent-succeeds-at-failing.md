# S-1165 · The Agent Failure Recovery Stack — When Your Agent Succeeds at Failing

[Your agent returns HTTP 200 with the wrong answer, loops forever calling the same broken tool, or hangs waiting for an API that went down an hour ago. No exception was thrown. No alert fired. You're burning budget and your queue is piling up. The fix isn't better prompts — it's a layered failure architecture that detects, contains, and recovers from agent failures without human babysitting every edge case.]

## Forces

- **HTTP 200 doesn't mean success.** Agents produce plausible-but-wrong outputs with no error signal. Traditional exception handling misses this class of failure entirely.
- **Self-correction loops can fail.** An agent that tries to fix itself can fail again, creating nested failure that compounds cost and context.
- **State is fragile mid-failure.** When an agent crashes partway through a multi-step task, you need to know what completed, what didn't, and where to resume — not restart from scratch.
- **Not all errors are retryable.** Retrying auth failures wastes budget; not retrying rate limits drops requests. Error classification is prerequisite to recovery strategy.

## The Move

Build a layered failure architecture: **detect → classify → contain → recover → log**.

**1. Hard stopping conditions — always.** An agent without a hard stop is a resource leak. Layer at least three:
- Max iterations (e.g., 20 turns) — the universal circuit breaker
- Token budget (e.g., 50k tokens/session) — prevents runaway cost
- Wall-clock timeout (e.g., 5 min) — enforces latency SLA for user-facing agents
Source: every production incident and every framework docs.

**2. Error classification before retry.** The first action on any failure must be classifying the error type:

| Error Type | HTTP | Action |
|---|---|---|
| Rate limit | 429 | Exponential backoff + jitter, then retry |
| Server error | 500/503 | Retry with backoff, then fall back |
| Timeout | — | Increase timeout or simplify the request |
| Auth failure | 401/403 | Do NOT retry; alert immediately |
| Invalid output | — | Retry with stricter prompt; validate structurally |
| Hallucinated tool | — | Validate tool existence before call |

Source: OpenHelm (https://openhelm.ai/blog/ai-agent-retry-strategies-exponential-backoff), AImade Tools (https://www.aimadetools.com/blog/ai-agent-error-handling/).

**3. Exponential backoff with jitter.** Base delay × 2^attempt + random jitter (0–1s). Cap at 60s. Prevents thundering herd when a service recovers.

**4. Tool-call guardrails.** Before executing any tool — especially destructive ones — validate: (a) the tool exists in your registry, (b) the output schema matches expectations, (c) run a second cheaper model ("LLM-as-judge") for high-stakes outputs. This catches hallucinated tool calls before they cause damage.

**5. Loop detection with forced escape.** Track the last N agent actions. If the same action repeats M times (e.g., 3x identical tool call), inject a "selective amnesia" signal: clear recent history and re-prompt with corrective context. If escape attempts exceed a threshold, escalate to human review or dead-letter queue. Source: Dev.to "Self-Healing AI Agents" (https://dev.to/techfind777/building-self-healing-ai-agents-7-error-handling-patterns-that-keep-your-agent-running-at-3-am-5h81).

**6. Checkpointing for resumable state.** Use framework-native checkpointers (LangGraph's persistent checkpointer backed by Redis/SQL, or Hermes Agent's shadow git repos) so that mid-failure resume works from a known-good snapshot rather than restarting from scratch. Source: ai-system-design-guide (https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md), LangGraph docs (https://activewizards.com/blog/a-deep-dive-into-langgraph-for-self-correcting-ai-agents).

**7. Grounded self-correction over intrinsic.** The Reflexion approach (store verbal self-critiques in memory and retry) achieved 91% pass@1 on HumanEval vs GPT-4's 80% baseline. But grounded self-correction — anchored in actual execution results, structured critics, or process reward models — is more reliable than the model judging itself. Intrinsic self-correction fails on reasoning errors without external signals. Source: Zylos Research (https://zylos.ai/zh/research/2026-05-12-agent-self-correction-reflexion-to-prm).

**8. Fallback chain for graceful degradation.** Define an explicit fallback cascade: primary model → cheaper model → cached response → graceful error message. Never let a model failure surface as a raw 500 to the user.

**9. Dead-letter queue for failed tasks.** Every unrecoverable failure goes to a DLQ with full execution context (step count, token spend, tool calls made, error type, truncated context). This is your post-incident audit trail and the input for improving your recovery logic.

## Evidence

- **Production incident:** Geta Team's email gateway agent crashed during high volume — a single unhandled API timeout cascaded into 47 Slack alerts, blocked customer emails, and response times going from seconds to hours. Recovery required circuit breakers on API calls, exponential backoff, and a DLQ so failed tasks didn't silently disappear. — https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it

- **Stuck-agent problem:** AxmeAI's agent-timeout-and-escalation repo addresses the specific failure mode where an agent calls a tool and waits indefinitely — adding configurable timeouts with automatic escalation chains, so a 30-minute hang becomes a timed-out call with a defined retry/escalate path. — https://github.com/AxmeAI/agent-timeout-and-escalation

- **Research validation:** Reflexion (NeurIPS 2023) showed verbal self-critique in memory achieves 91% pass@1 on HumanEval vs GPT-4's 80%. But Zylos Research's 2026 analysis confirms: LLMs cannot reliably correct reasoning errors without external signals. Intrinsic self-correction is fragile; grounded self-correction (execution results, structured critics, PRMs) is the reliable pattern. — https://zylos.ai/zh/research/2026-05-12-agent-self-correction-reflexion-to-prm

- **Framework consensus:** Learnixo's agentic patterns course (2025) states the consensus: "Every agent loop needs at least one hard stopping condition and ideally two or three layered stops." — https://learnixo.io/courses/agentic-ai-patterns/ap-max-iterations

## Gotchas

- **Retrying everything is the most common mistake.** Auth failures (401/403) should never retry — they waste budget and extend failure time. Classify first, then act.
- **HTTP 200 is not a success signal for agents.** Agents produce valid JSON that is wrong. Every consequential tool call needs output validation, not just exception handling.
- **Max iterations alone is not enough.** Without token budget and wall-clock timeout, you still have cost leaks and latency SLA violations hiding in production.
- **Without a DLQ, you can't improve.** Failed tasks that disappear silently leave no trace for post-incident analysis. Every unrecoverable failure should be captured with full context.
