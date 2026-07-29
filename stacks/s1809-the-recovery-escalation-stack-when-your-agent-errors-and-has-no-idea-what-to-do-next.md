# S-1809 · The Recovery Escalation Stack — When Your Agent Errors and Has No Idea What to Do Next

Your agent hits a tool failure. The API returned a 503. The agent has two options: retry the same tool forever (loop), or surface the error and crash (lose all work). Neither is good. Most agents default to one of these two, and neither is a strategy — they are the absence of one. You need a recovery escalation hierarchy: a structured decision tree that tells the agent what to do when something breaks.

## Forces

- **Agents fail in shapes single-LLM calls don't.** An LLM API error, a malformed tool response, an auth timeout — these aren't exceptions that a traditional try/catch cleanly handles because the agent's reasoning state may be partially corrupted too.
- **Indifferent retry is the default, and it's expensive.** Without explicit escalation logic, agents retry what just failed because they have no other instruction. A 503 on a non-idempotent operation gets retried 30 times.
- **Context loss on failure is catastrophic for long tasks.** An agent that has spent 20 steps building a report and then errors loses all 20 steps of progress unless something preserved them.
- **Escalation is underused because it's undignified.** Engineers don't want their agent to "give up" — but a graceful handoff with full accumulated state is far better than a runaway loop or a silent partial output.

## The move

A four-level escalation hierarchy that handles every error in sequence. Each level has explicit trigger conditions, bounded attempts, and a defined transition to the next level.

**Level 1 — Self-Correct.** Detect the error class. Retry immediately or with backoff if the error is transient (timeout, 5xx, rate limit). Attempt one alternative tool call if the primary failed for a semantic reason. Cap at 2–3 attempts.

**Level 2 — Fallback.** If self-correction fails, switch to an alternative approach. Same goal, different path. This means having at least two tool strategies for any non-trivial task. Fallback preserves the goal but not the attempted path.

**Level 3 — Graceful Degradation.** Return a partial result with full transparency about what was not achieved. Store the agent's accumulated state to a checkpoint. Do not crash and do not loop. Surface exactly what succeeded, what didn't, and why.

**Level 4 — Escalate.** If the task is critical (not optional) and degraded, hand off to a human with the full checkpoint: conversation history, tool call log, partial outputs, and a summary of what was attempted. The human should be able to resume from the checkpoint, not re-explain the task.

```
Error occurs
    → Self-Correct (2-3 retries, backoff)
        → Fallback (alternative tool/path)
            → Graceful Degradation (checkpoint + partial result)
                → Escalate (human handoff with full state)
```

State checkpointing is the backbone of this hierarchy. After every tool call — successful or not — serialize: the conversation history up to that point, the tool call log, accumulated artifacts, and the agent's current reasoning state. On error at any level, the agent (or its supervisor) can restore from the last checkpoint rather than starting over.

## Evidence

- **Anthropic engineering guidance:** Recommends workflow automation over agents for reliability, but when agents are used, emphasizes explicit checkpoint boundaries and "knowing when to stop" — the article explicitly calls out that the most successful agents have bounded step limits and structured exit paths. — [Anthropic / Building Effective Agents](https://www.anthropic.com/engineering/building-effective-agents)

- **SHIELDA academic framework (2025):** A structured exception-handling framework for LLM agentic workflows that classifies 36 exception types across 12 agent artifacts and maps them to a handling pattern registry with local handling, flow control, and state recovery phases. The paper explicitly links exception handling to root-cause tracing — recovery logic that doesn't trace to the reasoning-phase cause is brittle. — [arXiv:2508.07935](https://arxiv.org/pdf/2508.07935)

- **Statewright (Show HN, 2025):** An open-source tool using formal state machines to constrain AI agent behavior. Core thesis: "Agents are suggestions, states are laws." Demonstrates that deterministic state machine constraints prevent the brittleness that makes error recovery unpredictable — the agent's behavior space is bounded so recovery paths are always defined. — [Hacker News / Show HN: Statewright](https://news.ycombinator.com/item?id=48108778)

- **Zylos research synthesis (2026):** Analysis of production failure distributions across multi-agent systems found ~42% specification failures, ~37% coordination breakdowns, and ~21% verification gaps. Argues fault tolerance for agents is not optional hygiene but "the core engineering challenge of the agentic era." Proposes circuit breakers, supervisor trees, and idempotency guards borrowed from distributed systems. — [Zylos AI Research](https://zylos.ai/zh/research/2026-05-06-agent-self-healing-failure-recovery)

## Gotchas

- **Don't hard-code recovery at the tool level only.** If your tools have try/catch but your orchestration layer doesn't know a failure occurred, escalation never triggers. Recovery must be coordinated at the agent/orchestration level, not inside individual tool wrappers.
- **Partial success is not the same as failure — don't checkpoint after every step.** Checkpointing after every tool call creates overhead; checkpointing only on error means you lose the last step's progress. Checkpoint on every N steps (e.g., every 5) AND on every major state transition, so recovery cost is bounded.
- **Escalation without context is useless.** Handing a human "the agent failed" with no log, no partial output, and no context is worse than crashing. The escalation payload must include the full tool call trace, accumulated artifacts, and the last reasoning summary — not just an error message.
- **Retry logic must be idempotent-aware.** Retrying a non-idempotent tool call (a payment, a DELETE, a send) creates data corruption, not recovery. Classify tool calls as idempotent vs. destructive before applying retry logic.
