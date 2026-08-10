# S-2429 · The Escape Ladder Stack — When Your Agent Won't Quit

An agent that runs forever is as broken as one that crashes immediately. You set it a task, it loops. You increase the step limit. It loops faster. You switch the model. Still looping. The real failure: you have no recovery playbook — no way to distinguish "almost done" from "stuck forever," and no ladder of escalation when retry, replan, and retry-again all fail.

## Forces

- **Agents fail silently.** Unlike code that throws errors, agents return `200 OK` with subtly wrong output. No exception bubbles up. No traceback. The damage happens before you notice.
- **Step caps are a blunt instrument.** `max_iterations=12` stops a loop but doesn't recover the task. The agent just dies mid-work with no result and no state.
- **Retries amplify outages.** A circuit-breaker-less retry loop turned a 10-minute API outage into 15,000 avoidable API calls in one team's case.
- **Irreversible actions are the real danger.** A `DROP TABLE`, an S3 delete, a wrong-file rewrite — by the time you detect the loop, the damage is already done.
- **The right fix depends on why it's stuck.** A nudge works for a wanderer. A full replan works for a stale-context agent. A human handoff is the right answer for CAPTCHAs and 2FA — and a poor answer for everything else.

## The move

Build a **recovery ladder**: a bounded sequence of escalating interventions, applied in order, until the agent escapes or a human takes over. Detection is a separate problem from recovery — they need different mechanisms.

### 1. Detect before you recover

Activity proxies (API call count, file edits, log volume) rise during loops too. Track a **progress metric that only increases when real work is done**: unique test cases resolved, checklist items completed, unique sources gathered. Flat across N heartbeats → stuck. Rising → still converging even if slow.

LoopGain (open-source, Apache 2.0) replaces naive step caps with **control theory loop gain** — calculating `Aβ = current_error / previous_error` each iteration. `Aβ < 1` means error is shrinking. `Aβ ≥ 1` means stagnating. This is more precise than `max_iterations=N` because it distinguishes "slow but making progress" from "actually stuck." — [LoopGain — control theory for agent loops](https://github.com/loopgain-ai/loopgain)

### 2. Checkpoint before every side-effect

Before any destructive or stateful tool call (write, patch, rm, DROP, S3 delete), snapshot the affected state. Hermes Agent auto-snapshots via a shadow git store under `~/.hermes/checkpoints/store/`, taking at most one checkpoint per directory per turn. Claude Code does the same via git-checkpoint commits on a shadow branch. — [Hermes Agent — checkpoints and /rollback](https://hermes-agent.nousresearch.com/docs/user-guide/checkpoints-and-rollback)

For sandboxed execution (E2B, etc.), Crab (arxiv 2026) implements semantics-aware checkpoint/restore that captures agent memory, tool state, and filesystem atomically — not just files. — [Crab — semantics-aware checkpoint/restore for agent sandboxes](https://arxiv.org/html/2604.28138v1)

### 3. The recovery ladder

Climb this sequence, not all at once:

| Level | Trigger | Action |
|-------|---------|--------|
| **Nudge** | Loop detected, progress flat < 3 cycles | Inject a prompt nudge: "You're repeating. Original goal: {goal}. Remaining: {remaining}. Suggest a different approach." |
| **Replan** | Nudge didn't work | Re-generate the plan from scratch with current state. Feed the agent its own last 3 tool results and ask: "Given these results, what is the next concrete step?" |
| **Reset context** | Replan failed | Truncate conversation history to last N turns, reload only the most recent checkpoint. Let the agent restart from a known-good state without losing all progress. |
| **Fallback model** | Context reset didn't help | Route to a different model (e.g., GPT-4o → Claude Sonnet). Different reasoning traces break different loop types. |
| **Escalate / Human handoff** | All above failed | Pause the workflow, surface the full trace with error flags to a human, resume with a token the human provides. Never attempt to bypass CAPTCHAs, 2FA, or account attestation — those walls exist on purpose. — [Fabler Labs — human-in-the-loop escalation](https://fablerlabs.com/human-in-the-loop-ai-agents) |

### 4. Budget and cascade guards

- **Cost circuit breaker:** Set a max spend per task. Arize documented a case where an agent made 27 LLM calls in circles before any cap fired. — [The Operator Collective — AI agent error handling](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)
- **Hard step cap as last resort:** `MAX_STEPS = 12` for most agents, `MAX_STEPS = 6` for agents with expensive tool calls. Never set it above 20. Raise `AgentExceededSteps` with the full trace for post-mortem. — [Rajpoot — LLM agent error recovery 2026](https://blog.rajpoot.dev/posts/ai/llm-agent-error-recovery-2026/)
- **Circuit breaker on external calls:** After N consecutive failures on a tool or API, open the breaker. Stop all calls to that service for the cooldown period. One team estimated 60–70% of production incidents are transient failures that a circuit breaker alone would prevent. — [The Operator Collective](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)

### 5. Partial success tracking

For batch operations, process individually and track per-item results. "95 of 100 succeeded" is actionable. "The batch failed" is not. When a batch item fails after N retries, push it to an escalation queue rather than failing the whole batch. — [ai-agent-error-patterns on GitHub](https://github.com/tanayshah11/ai-agent-error-patterns)

## Evidence

- **GitHub repo / research:** AgentPatterns.ai formalizes the recovery ladder as a tool-agnostic technique, distinguishing "stuck" (progress flat, activity continues) from "slow but converging." The key insight: nudge works for wanderers but fails for repeaters; replan works for stale-context agents but is overkill for simple tool errors. — [agentpatterns-ai/website — stuck-loop-recovery.md](https://github.com/agentpatterns-ai/website/blob/main/loop-engineering/stuck-loop-recovery.md)
- **Y Combinator portfolio / engineering post:** The Operator Collective reports 86% of agent failures are recoverable in production — and 40%+ of enterprise agentic projects are cancelled by 2027 not because the AI is bad, but because recovery architecture is missing. The 6 documented failure modes (tool call failures, context overflow, cascading failures, silent wrong outputs, loop traps, budget spirals) each map to a specific recovery pattern. — [The Operator Collective — AI agent error handling](https://theoperatorcollective.org/blog/ai-agent-error-handling-production-guide)
- **Open-source tool:** LoopGain implements loop detection via control theory with `pip install loopgain`. The library's approach — replacing `max_iterations=N` with actual convergence measurement — has 31 HN points as of mid-2026 and is actively maintained. — [LoopGain — HN Show HN](https://news.ycombinator.com/item?id=48919562) / [GitHub](https://github.com/loopgain-ai/loopgain)
- **Market / research:** Gartner projects 40% of enterprise applications will include task-specific agents in 2026 (up from <5% in 2025). AgentMarketCap documents real incidents — agents running `DROP TABLE` before backups exist, deleting S3 partitions by mis-identifying prefixes, corrupting 47 files mid-refactor when context was lost. Checkpoint/rollback engineering has moved from theoretical to standard practice for teams deploying agents against production infrastructure. — [AgentMarketCap — checkpoint and rollback engineering 2026](https://agentmarketcap.ai/blog/2026/04/11/agent-checkpoint-rollback-engineering-2026)

## Gotchas

- **Don't use step count as a progress signal.** Agents can do real work in 3 steps and waste 30 steps on equivalent attempts. Step caps stop loops; they don't complete tasks.
- **Don't retry into the same failure.** If a tool call fails with the same error 3 times, retrying with exponential backoff won't help — the API schema changed, the data is malformed, or the auth token expired. Route to fallback or escalation instead.
- **Don't bypass human-shaped walls.** CAPTCHAs, 2FA, account attestations exist for a reason. Bypassing them violates platform ToS and creates liability. Build the escalation handoff, not the workaround.
- **Don't checkpoint everything.** Checkpointing every tool call creates storage overhead that outweighs the safety benefit. Checkpoint only before destructive or irreversible state changes — writes, deletes, API mutations with side effects.
- **Don't forget the circuit breaker.** Retries without a circuit breaker turn a transient outage into a budget spiral. Pair every retry policy with failure-count tracking and a hard open state.
