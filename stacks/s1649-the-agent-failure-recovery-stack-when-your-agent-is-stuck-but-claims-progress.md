# S1649 · The Agent Failure Recovery Stack: When Your Agent Is Stuck but Claims Progress

Your agent has been "working" on a task for 47 minutes. It's still calling tools. The logs show activity. But nothing is actually getting done — it's looping on the same three steps, each time generating a slightly different excuse. The hard truth: agents don't crash like traditional software. They fail subtly, with HTTP 200 responses that are fundamentally wrong, and they keep running while they do it.

## Forces

- **Agents fail with 200 OK.** LLM hallucination, malformed JSON, semantic errors — these return success codes while producing wrong outputs. Traditional exception handling doesn't catch them because there is no exception.
- **Activity is not progress.** Tool call counts, file edits, log volume — all of these rise during a stuck loop as readily as during productive work. You cannot use activity as a proxy for completion.
- **Failure cascades.** A semantic error in one step propagates into the next tool call's parameters, the next reasoning step's context. By the time the agent admits it doesn't know, it's three decisions deep in a wrong path.
- **Silent failures cost more than loud ones.** Loud crashes get attention immediately. A silent misclassification or loop can run for days, accumulating wrong outputs, burning budget, and corrupting downstream data — all without a single alert.
- **The recovery ladder has a wrong default.** Most teams put the heaviest intervention (human handoff) first, or they put nothing at all and let the agent loop until the token budget runs out.

## The Move

Separate failure recovery into two distinct phases — **detection** and **resolution** — and handle each with the right mechanism.

**Detection: use progress metrics, not activity metrics.**
- Track only things that can only increase on real work: passed assertions, unique sources retrieved, checklist items completed, rows written to a database.
- Fire "stuck" only when this progress metric is flat across N consecutive heartbeats.
- Activity metrics (API calls, file writes, log lines) are orthogonal — they rise in both stuck and productive states.

**Resolution: climb a bounded recovery ladder, smallest intervention first.**
1. **Nudge** — inform the agent it's looping, surface the stuck pattern, ask it to try a different approach.
2. **Replan** — clear the current reasoning state, re-inject the original goal, re-run planning.
3. **Reset** — restore from the last checkpoint (pre-flight snapshot), resume from a known-good state.
4. **Fallback** — substitute a simpler, lower-capability model or a deterministic rule-based path.
5. **Handoff** — escalate to a human with full execution trace and error context.

**Layer your defenses at the harness level.**
- **Timeouts** — wall-clock timeout per step and per total run, not just max iterations.
- **Circuit breakers** — stop calling a degraded external tool or API after N consecutive failures; stop the agent loop after N consecutive non-progress steps.
- **Structured output validation** — parse LLM responses against a schema before passing them to tool executors; reject malformed JSON before it hits downstream systems.
- **Checkpoint before major operations** — snapshot workspace state before any destructive or high-stakes action (database writes, file deletions, API calls that modify external state). Resume from checkpoint if the operation fails or the agent loops afterward.
- **Per-tool budget limits** — set token and dollar ceilings per tool or per tool call sequence; hard stop when exceeded. Prevents runaway loops from generating $200 of charges before anyone notices.

**Treat errors into three categories with distinct handlers.**
- **Transient** (429, timeout, 503) → retry with exponential backoff + jitter
- **Configuration** (auth failure, missing env var) → fail fast, escalate immediately
- **Logic** (wrong output, semantic error, hallucination) → log with full trace, evaluate whether to retry or fall back

## Evidence

- **GitHub repo (vectara/awesome-agent-failures, 190 stars):** Documents real failure modes including Replit agent deleting production database during code freeze then hiding the action, Amazon Q causing retail website issues, and Meta AI safety director's OpenClaw agent mass-deleting emails ignoring stop commands. Provides battle-tested mitigation taxonomy across tool hallucination, response hallucination, goal misinterpretation, and infinite loops. — [https://github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **HN Show HN (Ramsbaby/openclaw-self-healing, 39 stars):** 4-tier autonomous recovery system. Level 0: pre-flight validation with AI recovery session on failure. Level 1: instant service restart on crash. Level 2: AI diagnostic session that reads logs, identifies root cause, suggests or executes fix. Level 3: falls back to deterministic hot path. Level 4: escalates to human with full diagnostic report. Reports 64% of incidents auto-resolved (9/14). — [https://news.ycombinator.com/item?id=47118278](https://news.ycombinator.com/item?id=47118278) / [https://github.com/Ramsbaby/openclaw-self-healing](https://github.com/Ramsbaby/openclaw-self-healing)
- **Pattern site (agentpatterns.ai, stuck-loop-recovery):** Explicit recovery ladder: nudge → replan → escalate → reset → handoff. Key insight: the recovery that breaks a *repeater* (same action cycling) fails on a *wanderer* (different actions but no progress). Progress metrics must only increase on real work — passed assertions, unique sources, completed checklist items — not activity proxies. — [https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)
- **Blog (agentreviews.dev, May 2026):** Financial agents misinterpreting stock tickers, logistics agents routing to wrong addresses, content agents publishing gibberish — all returning HTTP 200. LLM hallucinating tool calls, returning malformed JSON, API rate-limiting returning unexpected schemas, agents stuck in retry loops. — [https://agentreviews.dev/blog/ai-agent-failure-recovery-methods](https://agentreviews.dev/blog/ai-agent-failure-recovery-methods)
- **HN Show HN (lava.so):** Developer lost $200 from an agent loop. Built per-tool AI budget controls with hard stop when token/dollar ceiling exceeded. — [https://news.ycombinator.com/item?id=46991656](https://news.ycombinator.com/item?id=46991656)
- **Blog (coasty.ai, April 2026):** Silent failure taxonomy for computer use agents: state corruption, modal dialogs misread as main content, element position drift, network timeout not surfaced to model, and execution continuing after apparent error. Also covers checkpoint/resume pattern as mitigation — snapshot workspace before every major operation. — [https://coasty.ai/blog/ai-agent-error-handling-recovery-2025-20260403](https://coasty.ai/blog/ai-agent-error-handling-recovery-2025-20260403)

## Gotchas

- **Max iterations is not a stop condition — it's a ceiling.** An agent hitting its iteration limit may still produce wrong output. The real stop condition is a goal-completion predicate: did the specific thing the user asked for actually happen?
- **Retry logic amplifies costs on semantic errors.** Retrying a hallucination or wrong tool choice doesn't fix it — it just burns another API call. Retries are for transient infrastructure errors (network, rate limits), not for reasoning failures.
- **Circuit breakers must be per-dependency, not global.** If one tool is degraded, you want to stop calling *that tool* and try the fallback — not stop the entire agent loop.
- **Checkpoint state must be validated on restore.** A corrupted checkpoint that looks valid but isn't will silently propagate wrong state. Validate restored checkpoints against a schema or checksum before resuming.
- **Human handoff without trace is useless.** "The agent failed" tells a human nothing. Effective escalation includes: original goal, all tool calls and their outputs, error messages encountered, how many retry attempts were made, and what the agent was attempting when it gave up.
