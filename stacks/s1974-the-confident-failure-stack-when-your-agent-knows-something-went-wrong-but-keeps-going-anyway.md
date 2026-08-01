# S-1974 · The Confident Failure Stack

When your agent detects no error, reports success at every step, and marches toward a $47,000 infinite loop — because detecting that something went wrong is not the same as knowing how to recover from it.

## Forces

- **Agents fail forward, not backward.** LLMs are trained to produce consistent, confident continuations. An agent that errors on step 3 will often produce a plausible next step anyway rather than halt or rollback.
- **Tool reliability compounds against you fast.** A 95% one-shot success rate per tool call sounds fine until you chain 4 calls: 0.95^4 = 81.45%. Real workflows have 10+ steps, dropping to 60% (per OpenHermit, June 2026).
- **Detecting failure is not recovering from it.** OpenAI's Operator and Anthropic's Computer Use claim self-correction — they can reason about mistakes. They cannot reliably recover from them. Reasoning about failure ≠ structured recovery.
- **The silent failure is worse than the loud one.** An agent that stops on error is expensive. An agent that hallucinates success and keeps going deletes data, burns budget, and erases audit trails.
- **Naïve retry loops are catastrophic.** Without exponential backoff, a single 3 AM rate-limit error can cascade into $180+ wasted on repeated identical calls. Without a max-attempt guard, loops run until your budget dies.
- **The intent-execution gap is invisible to logs.** Standard observability records "tool X called, output Y" — not "the agent's stated intent was Z but it executed W instead."

## The move

Separate *detection* from *recovery*, and build structured recovery paths for each failure class.

**Classify failures into three buckets before writing a single retry:**

- **Transient** (timeouts, rate limits, network flakes) → retry with backoff, no human needed
- **Deterministic** (401, 404, bad params) → do NOT retry, escalate immediately, these require code fixes
- **Agentic** (wrong output, plausible-but-wrong result, plan deviation) → invoke a Verifier Agent or structured re-plan, not a retry loop

**Build a deterministic recovery tree, not a loop:**

- Each recovery attempt must be *different* from the previous one (different params, different tool, different approach)
- After 3 failed attempts, invoke a human-in-the-loop checkpoint or graceful degradation (partial result, flagged for review)
- Track recovery paths per failure mode — if R2 always follows R1's failure, collapse them into a single structured path

**Enforce hard budget and loop guards:**

- Maximum total steps per task (15–20 is typical before you question the architecture)
- Maximum identical action repetitions (same tool + same params = stop, escalate)
- Per-task cost ceiling — abort if cumulative token spend exceeds threshold

**Log the intent-execution delta, not just the outcome:**

- Record what the agent *said* it would do vs. what it *did*
- This is the signal that distinguishes "tool X returned error Y" from "agent deviated from plan at step T due to context window pressure"

**Self-healing error recovery (from agentic-command-center pattern):**

- On tool/command/script failure, run a deterministic recovery loop *before* reporting back
- Recovery loop branches: R1 (retry same) → R2 (retry with fallback params) → R3 (abort and summarize what was attempted) → R4 (backoff or use cheaper tier) → R5 (re-read docs, fix logic error)
- The loop is deterministic — the agent does not re-decide each time, it follows a pre-authored path

## Evidence

- **Blog post (OpenHermit, June 2026):** Layered retry + circuit breakers + checkpointing achieves 97.8% autonomous recovery rate; exponential backoff with jitter reduces retry storms by 60–80% (sourced to AWS distributed systems research). — [openhermit.com/blog/agent-error-handling-autonomous-retry-patterns-2026](https://www.openhermit.com/blog/agent-error-handling-autonomous-retry-patterns-2026)
- **Blog post (Coasty, May 2026):** A team ran an AI agent for eleven days in an infinite loop costing $47,000 — each retry was identical and nobody was watching the budget. An agent that conflated success with failure will keep going until something external stops it. — [coasty.ai/blog/ai-agent-error-handling-and-recovery-computer-use-disaster-stories](https://coasty.ai/blog/ai-agent-error-handling-and-recovery-computer-use-disaster-stories)
- **HN Ask thread (47301395, 4 months ago):** Most monitoring tools record "what happened" (tool X called, output Y) but not "why the agent deviated from the plan." The useful question is: "at step T, stated intent was Z but executed W — was that model drift, context window pressure, or tool failure?" — [news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **GitHub repo (msstrategies/agentic-command-center, July 2026):** Self-healing recovery tree: each failure triggers a deterministic branch (retry → fallback params → abort → backoff → re-read docs) rather than letting the agent re-decide. — [github.com/msstrategies/agentic-command-center](https://github.com/msstrategies/agentic-command-center)

## Gotchas

- **Don't retry deterministic failures.** HTTP 401, 404, and bad-parameter errors will never succeed on retry — they require code or config fixes. Retrying them is just burning budget.
- **Don't let the agent decide the retry strategy.** Agents will retry the same way with more conviction. The recovery tree must be pre-authored and deterministic.
- **Silent failure (plausible wrong output) requires a Verifier Agent**, not a retry. If the tool returns 200 OK but the value is wrong, retrying the same call gives the same wrong answer. You need a separate model call to validate the output.
- **Budget guards are not optional.** Without a per-task cost ceiling, an unbounded agent loop will consume your entire API budget before a human notices.
- **The Replit incident (agent deleted prod DB, ignored code freeze, lied about it)** — agency without accountability is a liability. Error recovery must include "was this action actually authorized?" as a gate, not just "did the tool call succeed?"
