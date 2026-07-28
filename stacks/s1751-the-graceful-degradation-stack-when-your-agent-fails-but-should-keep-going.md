# S-1751 · The Graceful Degradation Stack — When Your Agent Fails but Should Keep Going

Your agent ran for 47 minutes on a multi-step task, made it through 11 of 14 steps, then hit an API timeout. On restart, it began from step 1 — not step 11. The work of those 47 minutes was discarded. This is not a crash. This is a preventable loss of accumulated progress, and it is the dominant failure mode of long-running agentic workflows.

## Forces

- **Agents fail silently, not loudly.** The most dangerous failure mode returns HTTP 200 with semantically wrong output — a hallucinated tool call, malformed JSON, or an agent that classifies everything as "low priority" and does nothing observable. Traditional try-catch does not catch these. They require semantic verification, not syntax checking.
- **Restart from zero is the worst recovery strategy.** Agents are expensive per-token. Rebuilding 47 minutes of context from scratch is wasteful when the failure was in step 12, not step 1. The recovery strategy must distinguish what succeeded from what failed.
- **Retrying blindly amplifies cost.** A failed step retried identically 3 times in a row burns 3x the token budget and may loop indefinitely if the failure is structural (wrong schema, missing permission, rate limit). Retries need to be informed by what was learned.
- **Graceful degradation vs. escalation.** Some failures should trigger a fallback path (cheaper model, simplified logic, human handoff). Others should halt the agent entirely before irreversible action. The system must classify failure severity before choosing a response.

## The Move

**Design a layered failure recovery architecture.** Instead of a single error-handling block, build three concentric rings:

**Ring 1 — Prevent the blast radius (circuit breakers + timeouts)**
- Wrap every external tool call with a circuit breaker. Open the breaker after 3 consecutive failures, then probe with a lightweight request before resuming. This prevents a rate-limited API from cascading into a full agent stall.
- Set two timeout policies per node: `run_timeout` (wall-clock ceiling — the agent should never run longer than N seconds per attempt) and `idle_timeout` (progress ceiling — reset on every tool call, channel write, or streamed chunk; trips when the agent goes dark without producing output).
- The idle timeout is the Ralph Loop: a watchdog that terminates the agent if it stops emitting progress signals. Named for the Simpsons character who "loses track of time" — the agent isn't crashed, it's just not talking anymore.

**Ring 2 — Recover from failure without restarting from zero (checkpointing + informed retry)**
- After every completed step, write a checkpoint: not just state, but learnings. A checkpoint is `{step: 11, state: {...}, learnings: "API returned paginated results — only page 1 was processed; resume at page 2"}`. The learnings field is what distinguishes a useful checkpoint from a useless snapshot.
- On restart, load the checkpoint and resume at the failed step. The agent should not re-execute steps 1–10.
- Make retries informed: if step 12 failed with a schema mismatch, the retry prompt should include the learning from the checkpoint so the agent does not repeat the same mistake. "The last attempt failed because the `date` field expected ISO 8601 format; you passed 'next Monday.'"

**Ring 3 — Degrade gracefully or escalate to human (action-risk tiers)**
- Classify every agent action into a risk tier before the agent runs. Tier 1: read-only (search, summarize). Tier 2: modify-in-sandbox (draft email, create draft doc). Tier 3: committed change (send email, post to social, move money). Tier 4: irreversible and high-stakes (delete records, execute trades, approve transactions).
- Tier 1 failures: retry with exponential backoff and jitter. Tier 2: retry once with modified parameters, then halt and surface output. Tier 3: checkpoint before execution, require a human-in-the-loop confirmation gate before committing. Tier 4: mandatory HITL checkpoint — the agent pauses, a human reviews and approves, and the agent resumes only on explicit confirmation.
- Escalation is an enforcement layer, not just observability. Observability detects problems after they happened. Escalation design stops irreversible actions before they execute.

**The self-healing cycle (all three rings operating together):**
1. Detection — circuit breaker trips or idle timeout fires
2. Diagnosis — load checkpoint, extract learnings about what failed
3. Containment — open circuit breaker or pause at HITL gate
4. Recovery — informed retry or graceful degradation path
5. Verification — re-check output against ground truth before continuing

## Evidence

- **LangChain fault tolerance primitives (June 2026):** LangGraph exposes `RetryPolicy` (exponential backoff with jitter), `TimeoutPolicy` (dual `run_timeout`/`idle_timeout`), and `ErrorHandler` (routes failures to recovery paths). All three attach directly to nodes via `add_node`, so fault tolerance config lives next to the logic it protects. — [LangChain Blog](https://www.langchain.com/blog/fault-tolerance-in-langgraph)

- **Zylos Research failure taxonomy (May 2026):** Galileo 2025 study of multi-agent systems found specification failures account for ~42% of failures, coordination breakdowns ~37%, and verification gaps ~21%. Without deliberate fault tolerance design, multi-agent systems fail at 41–86.7% rates in production. — [Zylos Research](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)

- **AgentReviews production case study (May 2026):** A customer support ticket routing agent experienced a slow, invisible backlog — no alerts, just unassigned tickets accumulating. Root cause: the agent was silently misclassifying ~15% of tickets as "low priority." The agent was returning HTTP 200 on every call. The failure was semantic, not technical. Diagnosis required semantic output verification (comparing agent classification against ground-truth labels), not log inspection. — [AgentReviews](https://agentreviews.dev/blog/ai-agent-failure-recovery-methods/)

## Gotchas

- **Saving state without learnings is nearly useless.** A checkpoint that only serializes variables will let you resume at step 11, but step 12 will fail the same way step 12 failed before. Capture what the system learned ("the API paginated — page 1 of 3 was all we read") so retries are not just repetitions.
- **LLM API failures are the easiest failures to handle and the most tempting to over-engineer.** A 503 with exponential backoff is a solved problem. A semantic failure — the agent that returns 200 OK but does the wrong thing — requires output verification, not retry logic.
- **The escalation gate must be placed before the irreversible action, not after.** If your agent has already sent the email before the human reviews it, the HITL checkpoint failed at its core purpose. The gate goes at the decision point, not the consequence point.
- **Idle timeout requires heartbeat emissions.** If you use `refresh_on="auto"`, progress signals from tool calls and streamed chunks automatically reset the timer. But for long-running tool calls that don't emit streaming chunks, you must call `runtime.heartbeat()` explicitly — otherwise the idle timeout fires on a tool call that is actively working.
