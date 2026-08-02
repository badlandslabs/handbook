# S-1993 · The Agent Failure Ladder Stack

*When your agent loops 40 times, burns $200 in API credits, and produces nothing — or worse, produces a confidently wrong result that ships. The failure wasn't a crash. It was silence followed by damage. You need a layered recovery system that distinguishes stuck from slow, costs from catastrophic, and retryable from terminal.*

## Forces

- **Agents fail non-deterministically, not just via crashes.** A traditional microservice fails obviously — a stack trace, a 500, a timeout you can catch. An agent fails silently: it keeps looping, keeps calling tools with hallucinated parameters, keeps reasoning over empty context. No exception thrown. No error surfaced. Just wrong behavior wearing a normal exit code.
- **Activity is not progress.** API call counts, log volume, and token consumption all rise during stuck loops the same as during productive ones. You cannot distinguish stuck from slow by watching activity — you need a progress metric that only increases when real work is done.
- **Every layer of autonomy removes a safety signal.** The more an agent can do without stopping, the fewer natural breakpoints exist to catch failure. Demos exploit this: a 10-step agent that works 95% of the time in the demo environment fails silently when the 5% case hits production data.
- **Cost accumulates faster than observability.** An unchecked agent loop at $0.01 per turn becomes $200 in an hour. By the time you notice, the damage is done. Budget controls need to be per-tool, not global, because different tools have vastly different cost profiles.
- **Context window exhaustion is invisible.** The agent doesn't error when context fills — it just starts dropping early context and reasoning on a partial view. 95% of users see correct results; 5% get confidently wrong answers with no error signal.

## The move

A layered failure recovery system built from five interlocking layers, executed in order when something goes wrong:

### Layer 1 — Classify the failure class before retrying

Not all failures are equal. Separate transient errors (timeout, rate limit, network blip) from terminal errors (invalid parameters, auth revocation, resource permanently gone). Only retry the transient class. Terminal errors escalate immediately. Returning structured error metadata — `{ type, retryable, fallback_hint }` — to the model lets it self-correct on retryable failures without human intervention.

### Layer 2 — Make every retry safe with idempotency keys

Tool calls that modify state must carry an idempotency key so that a retry after failure doesn't double-apply the side effect. This is not optional — it is the foundation that makes retries safe at all. Without it, you get duplicate emails, double-charges, double-commits.

### Layer 3 — Detect stuck loops before cost accumulates

Define a progress metric specific to your task: test suite pass rate, document count produced, search result relevance score. Track it per heartbeat window. When the metric is flat for N consecutive windows, the agent is stuck — not slow. Fire recovery before cost accumulates. Set per-tool budget caps so a single tool can't bleed unlimited credits in a loop.

### Layer 4 — Execute a bounded recovery ladder

When stuck-loop detection fires, climb the ladder in order:

1. **Nudge** — provide a direct hint about what failed and how to correct it (e.g., "last search returned 0 results, try different query terms"). This resolves ~60% of stuck loops.
2. **Replan** — regenerate the task plan from scratch, discarding the failing path. Replans cost an extra LLM call but are cheap compared to continued looping.
3. **Reset** — checkpoint-and-resume from the last known-good state, then re-execute from a different starting point.
4. **Escalate** — hand off to human review. This is not failure — it is the designed boundary of autonomous operation. Define escalation thresholds in advance: dollar amounts, compliance triggers, external communications.

### Layer 5 — Degrade gracefully, never fail silently

For each tool, define a degraded-mode fallback: cached data, skipped optional enrichments, partial results. Never return a blank error to the user when you can return a partial answer with a caveat. Never continue silently when the agent's confidence drops below a threshold — surface the uncertainty.

## Evidence

- **Engineering blog — Spacetime Agents:** 85% of AI agent production failures stem from system design flaws, not model failures. The three highest-leverage fixes: add a real evaluation suite, force the agent to self-verify, and monitor outcomes — not just latency. — [spacetimeagents.com](https://spacetimeagents.com/blog/ai-agent-production-failures-fix)
- **Hacker News / Show HN:** Developer lost $200 in API credits from a single unchecked agent loop. Built per-tool budget controls as a result. OpenClaw (120k+ GitHub stars) documents that stuck-session recovery defaults to `warnMs × 3` (~6 minutes) before aborting active agent runs — meaning long-turn tasks are silently capped without operator awareness. — [HN #46991656](https://news.ycombinator.com/item?id=46991656), [OpenClaw Issue #88870](https://github.com/openclaw/openclaw/issues/88870)
- **Research / Enterprise:** A hierarchical planner-worker architecture showed only 5.5% performance degradation under failure conditions versus 40%+ for flat agent swarms. The planner detects worker failures and reassigns, preventing cascading breakdowns. — [Spacetime Agents](https://spacetimeagents.com/blog/ai-agent-production-failures-fix), cross-referenced with [OpenReview — LLM Multi-Agent Fault Tolerance](https://openreview.net/forum?id=bkiM54QftZ)
- **Enterprise ops — Cordum:** Stuck-job recovery requires both a timeout reconciler (marks stale jobs TIMEOUT) and a pending replayer (re-submits via normal dispatch with distributed Redis locks to prevent duplicate execution). Queue-level ack deadlines alone do not cover persisted scheduler-state recovery after failures. — [cordum.io](https://cordum.io/blog/ai-agent-stuck-job-recovery-pending-replayer)
- **HITL taxonomy — Redis.io:** Three oversight models in production use: HITL (synchronous interrupt-and-resume for high-risk), HOTL (asynchronous monitoring with veto for medium-risk), and HOOF (human-on-the-flow for fully autonomous). The right model depends on the action's reversibility and consequence severity. — [redis.io](https://redis.io/blog/ai-human-in-the-loop/)
- **Recovery ladder pattern — agentpatterns.ai:** Recovery must be separate from detection — a nudge fixes a repeater but not a wanderer, and human handoff is a poor first choice when a single hint would suffice. Progress metrics (test pass rate, document count) distinguish stuck from slow; activity proxies (call counts, log volume) do not. — [agentpatterns.ai](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery/)

## Gotchas

- **Activity monitoring is a false signal.** If you watch API call counts to detect stuck loops, you'll get false positives on legitimate long tasks. Build task-specific progress metrics — ones that only advance when real work is done.
- **Idempotency keys are often the missing piece.** Teams implement retries but forget to make tool calls idempotent. The retry succeeds but the side effect double-applies. Fix the tool, not the retry logic.
- **Context window exhaustion is invisible.** The model doesn't signal when context fills — it just starts reasoning on truncated context. You need to monitor context position and surface a warning (or trigger a checkpoint/summarize) before the window caps out.
- **Degraded mode must be intentional.** "Just use cached data" sounds simple but cached data can be stale. Each tool's fallback needs explicit definition of what degraded means, how stale is acceptable, and what the user experience should be.
- **Escalation thresholds need to be defined before deployment, not during.** When a $50k fraud slips through because nobody had defined the escalation threshold, it's too late. Define dollar amounts, compliance triggers, and confidence-score cutoffs in the design phase.
