# S-2307 · The Escape Ladder Stack — When Your Agent Loops Forever and Everyone Is Stuck

Your agent enters a loop: it calls the same tool five times with the same arguments, then calls it five more. The context window fills with its own outputs. The cost meter climbs. The task never completes. Nobody is paged. Nobody knows. This is the Infinite Agentic Loop (IAL) — and it's not a hypothetical edge case. A static analysis of 6,549 repositories found 68 confirmed IAL failures across 47 projects, with 91.9% precision. Your agent framework has no systematic recovery path.

## Forces

- **Agents are designed to iterate.** Planning, tool use, reflection, and multi-agent handoffs all require loops. The same mechanism that makes agents useful is the mechanism that makes them unbundle in production.
- **Activity is not progress.** A looped agent is active — it makes API calls, edits files, sends messages. Activity metrics like call counts and log volume rise during a stuck loop, making naive circuit breakers fire on legitimate work.
- **The fix hierarchy is inverted.** Most teams start with the heaviest option (human handoff) or the bluntest (hard timeout) because no one built the ladder. This wastes human attention on nudgable problems and leaves genuinely stuck agents running until the budget runs out.
- **IALs are structurally invisible.** They arise from the interaction between agent logic, framework semantics, runtime observations, and termination mechanisms — not from a single bad line of code. Traditional testing misses them.

## The move

**Build a bounded recovery ladder.** When loop detection fires, climb a structured escalation path from cheapest to heaviest — but only fire when a genuine progress metric is flat, not when activity alone is high.

### The recovery ladder (4 rungs, in order)

1. **Nudge.** Inject a targeted prompt variation — clear last N turns of context, append a redirect instruction, or swap the tool's argument schema. Effective against: agent fixated on a wrong approach but still capable.
2. **Replan.** Request a full replan from the LLM with explicit termination criteria surfaced. Feed it the trajectory log so it can see what was tried. Effective against: agent stuck in a local optimum it could escape with a new plan.
3. **Reset.** Clear the agent's working memory but preserve trajectory log and task state. Reinitialize from the last known good checkpoint. Effective against: context window pollution, tool-call argument drift, or corrupted state.
4. **Handoff.** Route to human reviewer with the full trajectory, error classification, and accumulated state attached. This is the last rung — human attention is expensive and slow. Effective against: anything that couldn't be fixed by 1–3. Log it as a signal for step 0 improvements.

### The detection discipline: progress metrics, not activity metrics

The clean separator between "stuck" and "slow":

| State | Progress metric | Activity |
|-------|----------------|----------|
| **Stuck** | Flat across N heartbeats | Continues |
| **Converging slowly** | Rising (even by small increments) | Any level |

A progress metric only increases when real work is done — failing tests resolved, unique sources gathered, valid records written, checklist items completed. API call counts, file edit operations, and log volume rise during stuck loops too and cannot distinguish them from legitimate work.

### Supporting infrastructure

- **Circuit breakers** at configurable thresholds (steps, tokens, time) that flank the recovery ladder — they halt execution if the ladder itself fails to converge. Hard stops, not soft suggestions.
- **Trajectory logging** before any reset. The recovery ladder destroys working state; the trajectory log is immutable and captures the full execution path so the next run (or human) doesn't repeat the same failure. Store: tool calls with arguments, model outputs, state snapshots at each step.
- **Telemetry on the ladder itself.** Log which rung fired, how many times each rung was attempted, and whether the task completed. Patterns in rung usage reveal whether your agent needs better tool design (nudge keeps firing) or a better planner (replan keeps firing).

## Evidence

- **arXiv (formal study):** "When Agents Do Not Stop: Uncovering Infinite Agentic Loops in LLM Agents" — IAL-Scan detected 68 confirmed IAL failures across 47 projects from a corpus of 6,549 repositories, with 91.9% precision. Authors identify IALs as distinct from ordinary programming loops: they arise from the interaction between agent logic, framework semantics, runtime observations, and termination mechanisms. — [arXiv:2607.01641](https://arxiv.org/abs/2607.01641)
- **Open-source pattern catalog:** "Stuck-Loop Recovery" on agentpatterns.ai — defines the escape ladder with the key constraint that recovery must not fire on slow legitimate work, and proposes progress metrics that only increment on real work completion as the detection discriminator. — [agentpatterns.ai](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)
- **Benchmark study:** Hermes Agent Reviews Lab tested 6 failure categories across production agent runtimes in June 2026. Found that recovery rate (did it detect and recover without human intervention?) was the most variable dimension across platforms, with recovery latency varying by 3–8x depending on strategy quality. Platforms with explicit loop-detection scored 40–60% higher on the Self-Healing composite. — [hermes-agent.reviews](https://hermes-agent.reviews/error-recovery-patterns.html)

## Gotchas

- **Hard timeouts are not loop detection.** Setting a 5-minute execution limit stops a runaway but provides no recovery path, no context preservation, and no signal about what went wrong. Timeouts are a circuit breaker, not a recovery strategy.
- **Clearing context is not the same as a reset.** Simply removing the last N turns from context doesn't reset tool-call state, accumulated variables, or the agent's internal plan. A proper reset requires reinitializing from the last checkpoint, not just truncating the window.
- **The ladder rung count is a tuning parameter, not a design constraint.** Some teams need 6 rungs; others need 2. The discipline is the escalation order (cheap before expensive) and the progress-metric gate (don't fire on legitimate work). Start with 2 rungs (nudge + handoff) and add rungs as you collect data on what the nudge rung resolves.
