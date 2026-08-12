# S-2546 · The Escape Hatch Stack — When Your Self-Healing Agent Heals Itself Into an Uncontrollable Loop

Your agent starts failing. Its recovery logic kicks in. The recovery logic also fails. The agent recovers from the recovery failure. The recovery-of-recovery also fails. And now you are paying $12 for a task that should have cost $0.08, with no mechanism to stop it. Self-healing agents have a central paradox: the mechanisms designed to keep agents running are also the mechanisms most likely to run them off a cliff. Every recovery path needs an escape hatch. Every escape hatch needs its own escape hatch.

## Forces

- **Self-healing without bounds is self-destruction** — retry loops, compaction retries, and context-refresh chains have no natural stopping condition. The recovery mechanism must be the first thing bounded, not an afterthought.
- **Activity proxies lie** — API call counts, file edit counts, and log volume all rise during stuck loops just as they do during productive work. Activity is not the same as progress.
- **The stuck vs. slow distinction is hard to automate** — a genuinely converging agent and a looping one look identical from the outside for the first N iterations. Tune N too low and you kill slow legitimate work; too high and you burn resources.
- **Context pollution compounds failure** — each failed attempt adds to context. The later attempts have more noise, making them more likely to fail, creating a compounding degradation spiral.
- **Recovery attempts have cost** — retrying with the same failing parameters generates identical results but bills you again. Every loop iteration is not just time — it is money, tokens, and rate-limit budget.

## The move

**1. Hard stops first, always.** Set cost-budget limits, not just step counts.

```python
# Step count alone is not a ceiling
max_steps = 50  # could still be $500 for a $0.08 task

# Cost-budget ceiling catches price variance
max_cost_usd = 2.00
estimated_cost = count_tokens() * price_per_token
if estimated_cost > max_cost_usd:
    raise BudgetExceededError
```

**2. Retry with parameter modification, not repetition.** The same parameters will produce the same failure. Retry only after changing something meaningful.

```python
# BAD: retries with identical parameters
for attempt in range(5):
    call_api()

# GOOD: retry with exponential backoff + jitter + modified args
for attempt in range(3):
    wait(exponential_backoff(attempt) + random_jitter())
    try:
        result = call_api(modified_args(attempt))
        break
    except TransientError:
        continue
```

**3. Tier failures by type and respond accordingly.**

| Error type | Example | Response |
|---|---|---|
| **Transient** | Network timeout, 429 rate limit | Retry with backoff |
| **Structural** | Bad tool arguments, schema mismatch | Fix args, add type hints, retry once |
| **API/model** | Model refusal, malformed output | Retry with stripped system prompt |
| **Permission** | Auth failure, forbidden operation | Skip task, escalate to human |
| **Compaction/stuck** | Same error N times, no progress signal | Trigger escape hatch |

**4. Progress detection, not just iteration counting.** Track whether the agent's state is actually changing, not just whether it is still running.

```python
# Track semantic state change, not just call count
seen_states = set()
def has_real_progress(state):
    state_hash = hash(state.serialize())
    if state_hash in seen_states:
        return False  # same state = no progress
    seen_states.add(state_hash)
    return True
```

**5. Build a ladder of escape hatches.** Start with the cheapest intervention; escalate only if it fails.

```
Escalation ladder:
1. Retry with modified params (1-3 attempts)
2. Scope reduction — reduce task scope, try smaller chunk
3. Context summarization — compact history, re-prompt from summary
4. Full reset — save partial state, restart with fresh context from checkpoint
5. Human handoff — surface failure, input required to continue
```

Each rung must be independently bounded. Escape hatch #2 must have its own max-attempts and cost ceiling, not inherit from the parent loop.

**6. Observe the recovery system itself.** Monitor retry rates, compaction frequency, escape-hatch trigger rates, and cost-per-task. If the recovery system is working hard, the agent is failing often. A sudden spike in recovery attempts is the leading indicator of an emerging failure mode.

**7. For multi-agent systems:** state must be durable. A five-step workflow that loses context at step four should resume from step four, not restart and rebill. Define failure boundaries at agent handoff points, not just at the outermost loop.

## Evidence

- **Production case study (AgentPatterns.tech):** A task that normally costs ~$0.08 and closes in 3-4 steps spun for 20+ steps, made 60+ tool calls, and cost ~$12 before timing out. The agent was active throughout — API calls, file edits, and logs all indicated running. Progress metrics were flat. The system did not fail; it kept running without converging.
  — https://www.agentpatterns.tech/en/failures/infinite-loop

- **Claude Code compaction bug (GitHub #6004):** Claude Code v1.0.83 entered an infinite loop attempting to "compact" its conversation history, burning through usage limits and preventing task completion. The recovery mechanism (auto-compaction) had no ceiling — it triggered, failed to complete, and triggered again. This is documented as a recurring pattern across multiple open issues.
  — https://github.com/anthropics/claude-code/issues/6004

- **PADISO production data:** Across 50+ production deployments, well-designed retry policies produced 10–50x cost reduction per task compared to ungoverned retry loops. The key variable was retrying with modified parameters vs. identical parameters — same failure, different cost.
  — https://www.padiso.co/blog/tool-errors-retries-claude-recovery/

## Gotchas

- **Max iterations is a ceiling, not a solution.** It stops runaway loops but does not detect progress. Combine with state-change tracking.
- **Retrying with the same failing parameters is not error handling** — it is repeated billing for the same failure. Every retry must change something.
- **Context pollution is invisible until it is catastrophic.** Each failed attempt degrades the context window. Summarize proactively, not reactively.
- **The recovery system itself can loop.** The Claude Code compaction bug is the canonical example: recovery-with-no-ceiling is a self-healing system that made the problem worse.
- **Multi-agent cascade failures are worse than single-agent loops** — one agent failing can propagate to many. Define failure boundaries at every handoff point.
- **Human-in-the-loop is not optional for high-stakes domains.** An escape hatch that only escalates to a log entry is not an escape hatch for a sales agent offering unauthorized discounts.
