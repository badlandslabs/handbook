# S-2504 · The Escalation Ladder Stack — When Your Agent Is Stuck But Refuses to Stop

Your agent is mid-task: it's been running for three minutes, burning $8 in API calls, and producing nothing. It isn't crashing — it keeps calling tools, outputting text, moving forward. But it's not converging either. It's looping: calling the same tool with the same arguments, or bouncing between two actions without ever finishing. You have no circuit breaker. No step cap. No recovery path. The agent will run until it hits your rate limit or your budget is gone.

This is the escalation ladder problem. Most agent frameworks give you no mechanism to detect non-convergence, and even fewer give you a recovery path. You get silence until something breaks badly.

## Forces

- **The agent doesn't know it's lost.** A model outputting the same wrong action will do so with the same confidence as the right one. Activity proxies — API call counts, log volume, token usage — rise during stuck loops too. They cannot distinguish stuck from slow.
- **The cheapest fix is a poor first choice.** A hard step cap (max_turns) stops the bleeding but throws away all partial progress. A context wipe resets the conversation but loses accumulated state. Neither is proportional to the actual problem.
- **The hardest failures are silent.** Tool calls that return 200 with garbage data, rate-limited APIs that return partial responses, JSON parsers that silently return empty objects. The agent sees success and continues. The failure only surfaces downstream, if at all.
- **Multi-agent handoffs create invisible loops.** A cycle between two agents can run for six minutes and $85 before anyone notices — the OpenAI Agents SDK's max_turns counts individual LLM calls, not agent-to-agent handoff cycles. A GitHub issue on the openai-agents-python repo from June 2025 describes exactly this: an author tried to cap turns to force a final answer, found the parameter doesn't cover handoff cycles, and filed it as a limitation.
- **State is ephemeral by default.** A LangGraph workflow returning different answers to the same question across container restarts — same query, different chunks retrieved from the vector store, different fusion result. The agent's "state" lived in memory. On crash, it didn't exist.

## The move

Build a bounded escalation ladder: detect non-convergence first, then climb from least to most disruptive intervention, stopping at the first one that works. This is a separate discipline from loop detection — the cheap fix that breaks a repeater fails on a wanderer, and human handoff is a poor first choice when a nudge would have sufficed.

**Detection first — don't guess the problem:**

- Track a *progress metric* that only rises when real work is done: tests resolved, unique sources gathered, checklist items completed. Activity proxies (file edits, tool calls, log lines) are unreliable — they rise during loops too.
- Use step deduplication: hash the last N tool-call signatures. Same call twice = potential loop. Short cycle detection catches 2-3 action patterns. Both are fast and cheap.

**Then climb the ladder:**

1. **Nudge.** Re-prompt with a directive to try a different approach or produce a final answer now. Zero state loss. Catches the agent that just needed a reminder.
2. **Replan.** Inject a summary of what's been done so far and ask the model to replan from this point. Breaks momentum without losing progress.
3. **Escalate.** Trigger human-in-the-loop: queue the task for human review and pause execution. A Slack message or SMS alert via HITL middleware. The agent stops; a human decides whether to continue, abort, or redirect.
4. **Reset.** Hard cap — wipe context and restart with a fresh session, but preserve checkpoint state from before the loop began. Partial progress is preserved in durable storage, not memory.
5. **Handoff.** Route to a different agent or pipeline. Use when the current agent's context has become too corrupted to recover.

**Durable checkpoints as the foundation:**

- Checkpoint state after every step commit, not just on completion. Use a checksum to detect drift.
- Resume from the last valid checkpoint, not from scratch. A crashed 4-hour agent run should resume at step 47, not step 0.
- LangGraph's built-in checkpointer (SQLite for dev, Postgres for prod) handles this at the graph level. Third-party tools like AgentCheckpoint wrap arbitrary agents with the same pattern.

**Circuit breakers for tool failures:**

- Track failures per tool or API provider. Three consecutive failures within 60 seconds → open (block all calls). Wait 5 minutes → probe once (half-open). Success → closed. This prevents retry storms from cascading across multi-agent pipelines.
- Per-tool budget controls as a hard cost ceiling: an agent loop burning $200 in a single session (documented by a HN Show HN author who built Lava's per-tool AI budget controls after exactly this experience) is a budget control problem, not a detection problem.

**Done signals as the primary fix:**

- The most-cited root cause across primary sources: the agent was never given a clear way to know when it's done. Make success conditions explicit and checkable, not inferred. A verifiable done signal is the difference between an agent that stops and one that loops forever.
- The most reliable agents aren't the smartest ones — they're the ones designed to fail safely and escalate to a human when the done signal isn't reachable.

## Evidence

- **GitHub issue (openai-agents-python, #844):** An author filed a feature request for max_turns control and implemented a hook-based workaround that counts remaining turns and injects a final-answer directive. The issue was closed as not planned — the SDK's built-in max_turns doesn't cover handoff cycles between agents. — [github.com/openai/openai-agents-python/issues/844](https://github.com/openai/openai-agents-python/issues/844)
- **Show HN (Hacker News, 46991656):** Author built per-tool AI budget controls for Lava after losing $200 to a single agent loop. The loop was caused by unbounded tool calls with no per-tool cost ceiling. — [news.ycombinator.com/item?id=46991656](https://news.ycombinator.com/item?id=46991656)
- **Blog post (AgentReviews.dev, May 2026):** Documents the five failure types — hallucinations, auth failures, action loops, state drift, external outages — and maps each to a recovery strategy. Key insight: "When a microservice crashes, you get a 500. When an agent crashes, you get a confident wrong answer." — [agentreviews.dev/blog/ai-agent-failure-recovery-methods](https://agentreviews.dev/blog/ai-agent-failure-recovery-methods)
- **Pattern reference (agentpatterns.ai):** Stuck-loop recovery pattern with the bounded escalation ladder. Explicitly separates detection from recovery — different failure shapes require different interventions. Progress metrics must be semantic (tests resolved, sources gathered), not activity-based. — [agentpatterns.ai/loop-engineering/stuck-loop-recovery](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)
- **GitHub repo (harminsoftware/agentcheckpoint):** Wraps any AI agent with crash recovery and step-by-step replay. On crash, resumes from the exact failed step rather than restarting from scratch. Integrates with LangChain callbacks and LangGraph graph wrapping. — [github.com/harminsoftware/agentcheckpoint](https://github.com/harminsoftware/agentcheckpoint)
- **GitHub issue (openclaw/openclaw, #88870, P1):** Stuck-session recovery aborts long-but-active agent runs at stuckSessionWarnMs × 3 (~6 minutes) with a misleading "Reply operation aborted by user" message. The recovery fires on legitimately long active sessions because the timeout doesn't account for thinking-intensive operations. — [github.com/openclaw/openclaw/issues/88870](https://github.com/openclaw/openclaw/issues/88870)
- **Orchestration pattern (p3nchan/orchestration-playbook):** Three-state circuit breaker (closed/open/half-open) for agent tool calls. Documents the retry storm failure mode: one agent hitting a rate limit retries, a second agent retries simultaneously, both worsen the rate limit, a third agent fails over to an alternative provider which also gets rate-limited. — [github.com/p3nchan/orchestration-playbook/blob/main/patterns/circuit-breaker.md](https://github.com/p3nchan/orchestration-playbook/blob/main/patterns/circuit-breaker.md)
- **Medium article (Isuru Chathuranga, Apr 2026):** Documents a LangGraph workflow returning different answers to the same query across container restarts. Root cause: ephemeral in-memory state, vector store non-determinism, and container restart wiping accumulated workflow state. Proposes write-ahead logging for agent state. — [medium.com/@isuruig](https://isuruig.medium.com/your-agent-has-amnesia-state-persistence-and-crash-recovery-in-production-orchestration-f1edd432d738)

## Gotchas

- **max_turns doesn't cover handoff cycles.** The OpenAI Agents SDK's built-in parameter counts LLM calls from the runner's perspective. It catches one agent looping on itself. It does nothing for agent-to-agent cycle detection, tool-call storms inside a single turn, or context window growth through accumulated handoff messages. You need a separate cycle detection layer for multi-agent architectures.
- **Activity-based detection is a false friend.** Counting tool calls, log lines, or file edits as progress indicators will fire on stuck loops as readily as on legitimate work. Only semantic progress (tests resolved, sources gathered, checklist items completed) can distinguish stuck from slow.
- **Checkpoint drift is silent.** If you checkpoint state but don't verify the checkpoint's integrity (via checksum or hash), a corrupted checkpoint will be loaded on resume and the agent will continue from corrupted state — invisibly, confidently, wrong.
- **Resetting to the last checkpoint throws away more than you think.** If the checkpoint only captures LLM-visible state (conversation history) and not the agent's internal accumulated knowledge (judgments, interpretations, cross-references built over time), restarting from checkpoint loses work that wasn't visible in the prompt anyway. The recovery looks complete but the agent has genuine amnesia about its reasoning.
- **Escalation queues require human availability.** An escalation system that sends Slack messages at 3am with no on-call rotation is a paper escalation — the agent blocks indefinitely, the human never sees it, and the task never completes. Build escalation with realistic human SLA assumptions, or the escalation ladder's top rung is imaginary.
