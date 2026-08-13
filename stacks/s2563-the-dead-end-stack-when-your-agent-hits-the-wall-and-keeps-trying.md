# S-2563 · The Dead-End Stack: When Your Agent Hits the Wall and Keeps Trying

Your agent hit something it can't solve. The right response is to stop, report, and escalate. The wrong response — the one it defaults to — is to retry the same failing call 47 more times. This is the stack for making agents know when to quit.

## Forces

- **Agents are trained to persist.** LLM-based agents are trained to keep trying. A human would recognize "this has failed 12 times and won't fix itself." An agent doesn't — it just knows it hasn't succeeded yet.
- **Loops are the most expensive failure mode.** One team documented a single fullstack agent burning 58,000 tokens over 2 hours 28 minutes, zero progress, because nothing told it to stop. Another team's agent ran ~50,000 requests before anyone noticed — and took down the prod database.
- **The failure is invisible from the outside.** No exception. No crash. No log line screaming. Just the agent looking busy while burning money and time.
- **max_iterations is not enough.** A hard cap on total steps doesn't catch behavioral loops — an agent can be stuck on step 5 of 60, repeating the same call pattern, burning iterations without making progress.
- **Classical error handling doesn't translate.** Agents plan their own call sequences at runtime. The same tool might be called once, three times, or zero times depending on the task. Try-catch alone can't distinguish "retry this transient failure" from "you are trapped in a loop."

## The Move

**Treat every failure as an observation, not a crash — then build structured awareness of when observation becomes compulsion.**

### Detect before you defend

- **Payload hash sliding window.** Hash each tool call signature (`SHA256(tool_name + serialized_args)`) in a 60-second rolling window. After 3–5 identical calls in the window, inject a warning into context. After 5+ with no success signal, hard-stop. The 60-second window matters more than the repeat threshold — agents that loop typically do so rapidly. (LangChain issue #36139, OpenFang `loop_guard.rs`)
- **Banded escalation.** Not binary — warn first, then block. Level 1: inject a self-correction prompt ("you've called this tool N times without success — consider a different approach"). Level 2: force a planning step before retry. Level 3: hard-stop with a BLOCKED status and specific reason.

### Classify errors, then decide

- **Transient (retry):** timeout, rate limit, network hiccup — safe to retry with exponential backoff (1s → 2s → 4s, capped at 60s, 30% jitter). Separate retry configs for idempotent vs. non-idempotent operations.
- **Terminal (stop):** resource doesn't exist, permission denied, schema mismatch, validation error — retry won't fix it. Log the error, surface it as structured feedback, and stop.
- **Structured error feedback.** Pass errors back to the model as structured objects (`{"type": "terminal", "reason": "resource_missing", "detail": "..."}`) so the model can reason about recovery rather than blindly retrying.

### Make stopping safe

- **Idempotency keys.** Wrap every write operation in an idempotency key so that if a retry does happen, it doesn't create duplicate side effects. This makes "stop on first real failure" safe.
- **Snapshot before actions.** Log a before-state snapshot for every file write, DB mutation, or API call. On failure, a rollback hook can restore state. This decouples "stop retrying" from "lose work."
- **Human escalation path.** When retries are exhausted and fallbacks have failed, escalate — not with a vague "failed" message, but with: what was attempted, what failed, what was tried, what the agent recommends. This is especially critical for compliance-critical operations (finance, healthcare, legal).

### Design the fallback chain

- **Model-level:** Anthropic (primary) → OpenAI (secondary) → Cohere (tertiary) → local model (last resort). Not just for outages — for cost management and latency spikes.
- **Tool-level:** When a primary tool fails, have a structurally equivalent fallback. Search API down → cached results with a staleness warning. Database write fails → queue to a dead-letter table.
- **Intent-level:** If the full plan can't complete, can a partial result be delivered? A degraded response that answers "what changed, what still works, what happens next" is far better than silent failure.

## Evidence

- **GitHub Discussion:** Anthropic SDK Python issue #1341 — practitioners from miaoquai.com's production agent team describe exponential backoff with jitter (1s→60s, 30% jitter), circuit breakers (5 consecutive failures trips for 30s), separate retry configs for idempotent vs. non-idempotent operations, rollback hooks for file changes, and before-state snapshots. — [URL](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **r/AI_Agents post (79 points):** "Our AI agent got stuck in a loop and brought down production." Community discussion identifies root cause: the agent received responses it didn't like, modified parameters slightly, and retried repeatedly with no stopping condition. Commenters note "the retry loop is the classic failure mode for autonomous agents. LLMs often hallucinate that tweaking one parameter will fix a hard error." — [URL](https://old.reddit.com/r/AI_Agents/comments/1r9cj81/our_ai_agent_got_stuck_in_a_loop_and_brought_down/)
- **Agent.ceo blog (GenBrain AI):** Documents a fullstack agent burning 58,000 tokens over 2h 28m stuck in a single thinking/tool-call cycle. Rule implemented: same action repeated 5+ times with no success → STOP. Recommends decompose into smaller steps, mark BLOCKED with specific reason, or escalate. — [URL](https://agent.ceo/blog/detect-break-agent-retry-loops-production)
- **HN discussion "The Coming Loop" (435 points):** Armin Ronacher's essay on continuous AI-assisted development loops. Commenter notes: "I so far see very little progress [in models improving at this]. The model will just go in circles." Multiple practitioners report agents defaulting to infinite TODO updates or continuous extra-test-writing when tasks complete. — [URL](https://news.ycombinator.com/item?id=48643180)
- **LangChain issue #36139:** Production open-source implementation of SHA-256 fingerprint tracking in a 60-second sliding window, with HTTP 429 after 5 identical requests. Finding: "the 60-second window matters more than the repeat threshold." — [URL](https://github.com/langchain-ai/langchain/issues/36139)

## Gotchas

- **Don't rely solely on max_iterations.** An agent stuck on step 5 of 60 is burning budget and making zero progress. Behavioral loop detection (payload hashing) and step counting are complementary, not substitutes.
- **Don't retry everything blindly.** Transient errors (network, rate limits) deserve retries. Terminal errors (missing resource, permission denied) don't. Conflating the two wastes budget and can create the loop condition you're trying to prevent.
- **Silent failure is worse than visible failure.** A degraded response — "live AI review is temporarily unavailable, your draft is saved, deep analysis is queued" — costs less than a runaway agent and maintains user trust.
- **Rollback hooks must be designed before the agent runs wild.** You can't add them after the database is already wiped. Build state snapshotting into the tool layer from day one.
