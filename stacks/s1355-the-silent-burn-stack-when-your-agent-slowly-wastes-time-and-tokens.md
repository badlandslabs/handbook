# S-1355 · The Silent Burn Stack

When you reach for this: Your agent returns HTTP 200 and produces output, but it loops for 20 minutes first, burns $12 on a task that should cost $0.08, and no exception is ever thrown. You've learned that "it didn't crash" and "it didn't fail" are different things.

## Forces

- **Agents fail slowly, not loudly** — unlike a web service that crashes with a stack trace, an agent loops with confidence, accumulates context, and burns budget while appearing healthy from the outside.
- **Traditional error handling doesn't cover agentic failures** — HTTP 200 with hallucinated tool parameters, successful tool calls with wrong semantic meaning, confident nonsense that passes basic assertions.
- **The ReAct loop's own structure creates loop conditions** — each step observes and acts, but without explicit progress checks, the loop continues until it exhausts context or budget.
- **Loop detection is harder than it looks** — agents can make different syntactic choices (varying keywords, reordering steps) while achieving nothing semantically. A pure step-count hard cap stops useful long-horizon tasks too.

## The Move

Three layers of defense, applied in order:

1. **Hard step cap + token budget** — set `max_steps` and `max_tokens` as absolute ceilings. This is your circuit breaker. Typical starting values: 20–50 steps for task agents, per-run token budget of 2–10x expected cost. When the cap hits, stop and surface the partial result.

2. **Soft progress guards inside the loop** — check for real progress at each step, not just step count:
   - **Tool call deduplication**: if the agent calls the same tool with the same arguments within the last 3 turns, flag and break.
   - **Semantic progress check**: compare the last N observations against the task goal. If no new relevant information appeared in the last 2–3 turns, prompt re-plan or break.
   - **State fingerprinting**: hash the agent's recent internal state (last tool calls + key observations). If the same fingerprint repeats, you're looping.

3. **Structured recovery on failure** — when a loop is detected, don't just stop. Capture the run trace, emit structured failure metrics (loop type, step count, cost, last tool called), and attempt one controlled recovery: re-summarize the context, provide an explicit "you are stuck" hint to the model, and restart from step 1 with the hint in context. If recovery fails twice, escalate to human or return partial result.

## Evidence

- **Loop taxonomy (AgentPatterns.tech):** Four distinct loop types — Hard Loop (same action repeating syntactically), Soft Loop (same goal approached different ways but never reached), Retry Storm (same tool called repeatedly on transient errors), Semantic Drift (goal silently changes mid-run). Each requires different detection. — [https://www.agentpatterns.tech/en/failures/infinite-loop](https://www.agentpatterns.tech/en/failures/infinite-loop)
- **Production failure data (Zylos.ai, 2026):** In multi-agent deployments, 42% of failures are specification failures, 37% are coordination breakdowns, 21% are verification gaps. Microsoft's taxonomy identifies six unique failure categories for agents vs. traditional services. A conventional service crashes and logs; an agent may silently loop for 35 minutes, spawn redundant subprocesses, or take irreversible action before human intervention. — [https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery](https://zylos.ai/research/2026-05-06-agent-self-healing-failure-recovery)
- **Real-world case (AgentReviews.dev, 2026):** An email routing agent crashed during peak hours, blocking 47 messages with no exception thrown — the tool returned 200 OK but silently dropped messages. Practical recovery methods in production include: tool call output validation before passing to the model (reject malformed JSON), idempotent saga patterns for multi-step writes, and exponential backoff with jitter for API retries. — [https://agentreviews.dev/blog/ai-agent-failure-recovery-methods](https://agentreviews.dev/blog/ai-agent-failure-recovery-methods)
- **ReAct loop root causes (AIWave, July 2026):** Four root causes of agent loops in production: (1) Ambiguous tool results that the model interprets as "try again", (2) Empty results treated as partial progress rather than failure signal, (3) Missing stop conditions — the model never receives a clear "task is done" signal, (4) Tool degradation where a tool works but returns progressively worse outputs. Fixes: explicit stop tokens in tool descriptions, clear completion criteria in system prompt, step-by-step validation gates. — [https://aiwave.hashnode.dev/why-your-ai-agent-keeps-looping-and-how-to-fix-it-a-deep-dive-into-react-pattern-failures](https://aiwave.hashnode.dev/why-your-ai-agent-keeps-looping-and-how-to-fix-it-a-deep-dive-into-react-pattern-failures)

## Gotchas

- **Hard step caps kill legitimate long-horizon tasks** — a research agent doing 30-step literature review isn't looping. Tune the cap per task type, not globally. Consider a "soft warning" at 70% of cap (emit a log, not a stop).
- **Retrying the same tool with the same args is a different failure than retrying with different args** — naive retry-count limits don't distinguish between retry storms (bad — break) and exploratory iterations (potentially fine). Track both tool identity and argument similarity.
- **The failure is often in the tool, not the agent** — Hallucinated tool parameters, wrong API schemas, and degraded third-party services cause the agent to repeat the wrong thing confidently. Validate tool inputs with schema checks *before* execution, not after.
- **Loops can be invisible until cost hits** — unless you're watching cost per run in real time, you won't know an agent is looping until the bill arrives. Emit token-and-cost metrics on every step, not just on completion.
