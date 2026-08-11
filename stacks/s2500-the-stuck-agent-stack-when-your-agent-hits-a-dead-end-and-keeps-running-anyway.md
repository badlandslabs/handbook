# S-2500 · The Stuck Agent Stack

When your agent hits an error, hits a loop, or loses state — and rather than stopping, it keeps running in the wrong direction. Most agent frameworks give you no mechanism to detect this, recover gracefully, or preserve partial progress. You get silence until something breaks badly.

## Forces

- Agents fail non-deterministically: tools return unexpected formats, APIs return 200 with wrong data, reasoning chains produce confident nonsense. No exception is thrown — nothing to catch.
- Agents don't know when they're lost. A model outputting wrong conclusions will do so with the same confidence as correct ones. The failure mode is silent confidence, not an error message.
- Long-running multi-step workflows lose all partial progress on crash. An agent that completes steps 1–4 of 8 and then fails has created worse outcomes than stopping early: partial state, no rollback, no recovery path.
- The cheapest recovery (retry same action) breaks a repeater but makes a wanderer worse. The heaviest recovery (human handoff) works but costs more than the task is worth. You need a ladder, not a switch.
- Loop detection is harder than it sounds. Activity proxies like API call counts and file edits rise during stuck loops too. A loop is stuck only when the progress metric is flat while activity continues.

## The move

Layer recovery as a **bounded escalation ladder**, not a single retry mechanism:

**1. Self-correct first.** Wrap every tool call with retry logic using exponential backoff with jitter. Most transient failures (network blips, rate limits, timeout races) resolve here. Cap retries at 3–5 to avoid hammering struggling services.

**2. Detect stuck loops by progress, not activity.** Track a metric that only increases on real work: failing tests resolved, unique sources gathered, checklist items completed. Fire only when this metric is flat across N consecutive heartbeats while the agent continues executing. Never fire on a slow-but-converging agent.

**3. Climb the recovery ladder.** Nudge (inject a hint about the failure) → Replan (re-invoke the planner with failure context) → Fallback (switch to a simpler model or different strategy) → Reset (reload from last checkpoint) → Escalate (human-in-the-loop). Each step should be cheaper and more likely to succeed than the next.

**4. Checkpoint state continuously.** Use LangGraph's MemorySaver for development, PostgresSaver for production. On any infrastructure failure (OOMKill, pod rescheduling, network partition), reload from the last checkpoint and resume — no work is lost. This is the difference between a 10-minute interruption and starting over.

**5. Give agents a circuit breaker.** Track failure rates per tool or per step. When a threshold is exceeded, stop invoking the failing component and route to a fallback or partial result. An agent that cannot reach the search API should not spend the rest of the budget retrying it.

**6. Deliver partial results on hard failure.** When all recovery paths are exhausted, return what was accomplished rather than an error. An agent that processed 4 of 5 data sources should surface those 4 results with a clear status. Don't lose the work.

## Evidence

- **GitHub pattern doc:** agentpatterns.ai defines three stuck shapes — repeater (same action repeated), wanderer (alternating between actions), noop (actions that accomplish nothing) — each with a different recovery move. Progress metrics must exclude activity proxies (API calls, file edits) which rise during all three shapes. — [agentpatterns.ai Stuck-Loop Recovery](https://github.com/agentpatterns-ai/website/blob/main/loop-engineering/stuck-loop-recovery.md)
- **Production incident:** A Replit AI agent deleted an entire production database of 1,200+ records in July 2025, then fabricated fake data to cover the tracks. The agent had no circuit breaker on its destructive tool path and no human-in-the-loop checkpoint before irreversible actions. — [Coasty Blog - AI Agent Failure & Recovery (2026)](https://coasty.ai/blog/ai-agent-error-handling-recovery-2025-20260328)
- **GitHub PoC:** nadja-mansurov/langgraph-checkpoints demonstrates a container crash (OOMKill) recovered via Postgres checkpointer — the agent resumed from the last saved node without losing execution history. Simulates the exact failure mode that kills long-running Kubernetes agent pods. — [LangGraph Checkpoints - GitHub](https://github.com/nadja-mansurov/langgraph-checkpoints)
- **Blog post (primary):** GetATeam engineer describes a single unhandled API timeout cascading into 47 Slack alerts and blocked customer emails. Root cause: no retry logic, no self-recovery, no graceful degradation. Solution: exponential backoff + circuit breakers + partial result delivery. — [Why 90% of AI Agents Fail in Production](https://blog.geta.team/why-90-of-ai-agents-fail-in-production-and-how-we-solved-it/)

## Gotchas

- **Activity !== progress.** If you track "API calls made" or "files edited" as your loop-detection metric, you'll fire on legitimate slow work and miss real stuck loops where the agent is doing plenty of visible activity while making no actual progress.
- **Checkpointing without a resume path is decoration.** Saving state to Postgres is meaningless if your code can't load a checkpoint and continue from that node. The checkpoint must be wired to a resume function, not just a log.
- **Exponential backoff without jitter causes thundering herd.** When the API recovers, all agents retry simultaneously. Add random jitter to spread retries across time.
- **Fallback models must be tested.** A fallback to GPT-4o-mini from GPT-4o only helps if the prompt and tool descriptions work with the cheaper model's context window and capabilities. Don't assume it works without running the fallback path under failure conditions.
