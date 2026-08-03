# S-2049 · The Agent Recovery Ladder Stack — When Your Agent Is Stuck But Still Running

Your agent is on its 47th loop. It is consuming tokens, calling APIs, writing log lines — it looks active. But the progress metric is flat. No tests resolved. No unique sources added. No checklist items completed. It is stuck, and it does not know it. You need the recovery ladder: a bounded escalation sequence that gets agents unstuck or hands them to a human — without burning more resources.

## Forces

- **Activity is not progress.** API call counts, file edit volumes, and log output rise during stuck loops just as they do during productive work. Detectors that fire on activity will either false-trigger constantly or miss real deadlocks.
- **The wrong fix for the wrong stuck.** A nudge (rephrase the last instruction) unblocks a wanderer. It does nothing for a repeater running the same failed approach. Human handoff fixes everything — but costs everything. Escalate too fast and you defeat the purpose of automation.
- **Agents fail without exceptions.** The agent's reasoning layer is the failure surface. It can return a plausible but wrong next action with no error signal. Recovery cannot wait for a traceback.
- **State is fragile.** A 10-step pipeline with 85% step reliability succeeds end-to-end only 20% of the time (0.85^10). Losing state on failure means re-running from step one, burning more cost and context.

## The move

The recovery ladder is an ordered escalation sequence, each rung with a bounded attempt budget. Climb from cheap to expensive:

- **Nudge.** Re-inject the current goal with a slightly different framing. Breaks simple orientation errors where the agent lost track of the objective. Budget: 1 extra LLM call.
- **Replan.** Clear the current strategy and regenerate from the last confirmed good state. Use the progress metric as the replan anchor. Budget: 1 full planning cycle.
- **Reset.** Return to the last checkpoint and try a different approach branch. Do not replay the same strategy that got you stuck. Budget: 1 full branch from checkpoint.
- **Escalate.** Surface full agent state (context, tool history, last action, confidence signals) to a human reviewer. Budget: human time + full context packaging.
- **Terminate.** Hard stop with a structured error report. Log the failure mode for post-mortem. Budget: no further cost.

Key supporting patterns:

- **Circuit breaker per tool.** Each external dependency (API, search, code executor) gets its own three-state breaker (closed/open/half-open). Failures above a threshold open the breaker and route to fallback — the agent keeps working with degraded capability instead of burning tokens on retry loops. FailWatch (Ludwig1827, 2025) implements this as a fail-closed design: when in doubt, stop.
- **Checkpoint before every tool call.** State snapshot (current goal, completed steps, tool results so far) written to durable storage before the call fires. On crash, timeout, or intervention, resume from the last checkpoint — not from scratch. `MemorySaver` works in local dev only; production needs `PostgresSaver` or equivalent for multi-process/containerized deployments.
- **Confidence-threshold escalation.** For high-stakes operations (financial transactions, irreversible writes, external communications), the agent outputs a confidence signal. Below threshold, the workflow halts and surfaces a structured approval request to a human with full context — not a vague "something went wrong" message.
- **Hard iteration cap.** Set a maximum step count per conversation (e.g., 50–200 depending on task complexity). When the cap fires, run the termination rung. This is the backstop that catches every other failure mode.

## Evidence

- **GitHub repo + blog post:** Stuck-loop recovery requires a separate playbook from detection. A valid progress metric (tests resolved, unique sources gathered, checklist items completed) is the only reliable separator between "stuck" and "slowly converging." Activity-based proxies (API calls, file edits, log volume) fail because they rise in both states. The recovery ladder (nudge → replan → reset → escalate → terminate) orders fixes from cheapest to most expensive. — [agentpatterns.ai: Stuck-Loop Recovery](https://github.com/agentpatterns-ai/website/blob/main/loop-engineering/stuck-loop-recovery.md)
- **Research synthesis:** The dominant multi-agent failure distribution (Galileo 2025): ~42% specification failures, ~37% coordination breakdowns, ~21% verification gaps. A 10-step pipeline at 85% per-step reliability succeeds end-to-end only ~20% of the time — making stateful recovery non-negotiable for any multi-step agent. A context-monitor spawned duplicate sessions at 6-minute intervals when a downstream tool degraded, demonstrating that silent resource contention (not crash) is a primary failure mode. — [Zylos Research: AI Agent Self-Healing and Failure Recovery (2026)](https://zylos.ai/en/research/2026-05-06-agent-self-healing-failure-recovery/)
- **Blog post + GitHub:** Production agents fail on OpenAI API timeouts (2–5% of requests during peak), rate limits (429s), invalid JSON, downstream API outages, and network instability. Proper error handling with retry + backoff + circuit breaker + fallback increased agent reliability from 87% to 99.2% (14× fewer failures) in one deployment. FailWatch implements per-tool circuit breakers as a fail-closed system — when the breaker opens, the agent stops calling the degraded tool rather than continuing to generate error-bound responses. — [OpenHelm Blog: Error Handling for Production AI Agents](https://openhelm.ai/blog/error-handling-reliability-patterns-production-ai-agents) + [HN Show: FailWatch](https://news.ycombinator.com/item?id=46529092)

## Gotchas

- **Never use `MemorySaver` in production.** Container restarts, pod evictions, and process crashes wipe in-memory checkpoints. Teams discover this the hard way after losing twenty in-flight agent threads at once. Use `PostgresSaver` or equivalent for durability and queryability.
- **SQLite serialization kills concurrency.** `SqliteSaver` is fine for single-process dev but write-locks serialize concurrent threads. In multi-process or containerized deployments, this creates a bottleneck that defeats the purpose of checkpointing.
- **Structural interrupts beat self-reported confidence.** An agent that self-determines whether to escalate can be prompt-injected into skipping the gate. Approval interrupts must be enforced by the orchestration runtime — placed in the workflow graph before the irreversible action executes, not called by the agent's reasoning.
- **The iteration cap is your cost ceiling.** Without it, a stuck agent in a long conversation burns tokens until the context window fills. Set it, test it under failure conditions, and verify it fires before you deploy.
