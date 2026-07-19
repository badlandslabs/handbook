# S-1344 · The Stuck-Loop Ladder — When Your Agent Stops Working But Keeps Spending

An agent that loops infinitely is not crashed — it is billing. Unlike a crashed process that stops consuming resources, a looping agent keeps generating tokens until something external intervenes. The most common fix is `pkill`, which also kills all progress. The better fix is a structured recovery ladder: detect correctly, then apply the cheapest fix first.

## Forces

- **Detection and recovery are separate disciplines.** The cheapest recovery (nudge the agent toward the next step) fails on a wanderer. The heaviest recovery (human handoff) is a poor first choice when a single parameter change would unstick the agent. Treating detection and recovery as one step is why most "loop detection" code either does nothing or escalates too aggressively.
- **Iteration count is a bad proxy for stuck-ness.** A 50-step legitimate research task is not stuck. An agent repeating the same 3 steps is. Iteration count conflates slow work with broken work — the result is either false positives (recovery fires on good work) or false negatives (recovery never fires until massive waste).
- **Recovery without a cap is not recovery.** An unbounded retry-within-recovery can itself loop, burning as many tokens as the original failure. Every recovery action needs its own budget.
- **Most agents don't distinguish failure types.** A rate-limited API call, a tool that returns empty results, and a misunderstood output format all produce a "failed" signal — but they need different fixes. Without an error taxonomy, every failure gets the same retry, which means most retries are wrong.

## The move

**Build a two-stage loop escape system: a precise detector, then a bounded recovery ladder that climbs from cheap to expensive.**

### 1. Define a progress metric (not iteration count)

Track something that only increases when real work is done — failing tests resolved, unique sources gathered, files modified, checklist items completed. This is the signal, not step count. An agent can take 50 legitimate steps and move the needle each time. It can take 3 steps that all produce the same failing test and move nothing.

```
progress_delta = current_progress_score - previous_progress_score
stuck_window = last N steps (e.g., 5)

if progress_delta == 0 for all N steps in stuck_window:
    fire stuck_detector()
```

This distinguishes a deep research spiral (progress moves, just slowly) from a true loop (no progress despite activity).

### 2. Classify the stuck shape

Once stuck is detected, identify which shape you're in before choosing a recovery:

| Shape | Behavior | Root cause |
|-------|----------|------------|
| **Repeater** | Same action, same result, repeated | Tool misfire, output misread, condition never changes |
| **Wanderer** | Different actions but no progress | Bad plan, bad tool selection, goal drift |
| **Oscillator** | Cycles through 2–3 states | Flip-flop between equivalent choices, retry loop in thin disguise |

Classifying before recovering prevents wasting recovery attempts: nudging a repeater works; replanning a wanderer works; neither fixes an oscillator without addressing the flip-flop.

### 3. Climb the recovery ladder

```
Level 1 — Nudge: Inject the next expected step into context. No replanning, no state change.
           Cost: ~1 LLM call. Use when: repeater, early stage.
Level 2 — Replan: Re-invoke the planner with current state, discard the failed branch.
           Cost: ~1 full planning cycle. Use when: wanderer, plan is clearly wrong.
Level 3 — Reset branch: Roll back to the last checkpoint before the stuck sequence.
           Cost: Lost progress on that branch. Use when: oscillator, accumulated bad state.
Level 4 — Switch model: Swap to a model with different sampling (higher temperature, different family).
           Cost: Full re-invocation + different failure mode profile. Use when: tool selection is consistently wrong.
Level 5 — Human handoff: Stop the agent, surface state, request human intervention.
           Cost: Full automation loss. Use when: all above exhausted, or high-stakes domain.
```

Never skip levels — applying a Level 5 fix for a Level 1 problem is as bad as applying a Level 1 fix for a Level 5 problem.

### 4. Bound the recovery itself

```
max_recovery_attempts = 3  # per level
total_recovery_token_budget = initial_task_budget * 0.25
```

If Level 1 fires 3 times and the agent is still stuck, move to Level 2 — don't retry Level 1 indefinitely. If the total tokens spent on recovery exceed 25% of the original task budget, escalate to human handoff regardless of level. An agent that burns recovery tokens faster than task tokens is in a meta-loop.

### 5. Instrument the stuck detector, not just the failure

Log every stuck detection with: shape, iteration count, progress metric snapshot, recovery level applied, recovery outcome. This is the feedback loop that lets you improve tool descriptions, prompt the planner better, or tune the progress metric over time. A stuck detector that fires silently teaches you nothing.

## Evidence

- **AgentPatterns.ai:** Stuck-loop recovery pattern — separates stuck vs. slow-by-converging using a progress metric, classifies three stuck shapes (repeater/wanderer/oscillator), climbs a bounded recovery ladder (nudge → replan → reset branch → switch model → handoff). Cites practitioner adoption. — https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery
- **Show HN / HALO (context-labs, ~1.1k stars):** HALO — Hierarchical Agent Loop Optimizer — RLM-based agent trace debugger that takes OTEL-compliant traces (Langfuse, Arize, JSONL) and recursively analyzes execution patterns to find recurring failure loops. Runs locally via desktop app or Python package. Submitted as Show HN, 27 points, 15 days old. — https://github.com/context-labs/halo — https://news.ycombinator.com/item?id=48649137
- **Show HN / TensorPool Agent:** Autonomous recovery agent for distributed ML training jobs — monitors GPU training runs, auto-recovers from Xid errors and S3 checkpoint failures. 100k+ multinode GPU hours on platform. HN commenters flagged the "silent stall" risk: an agent that nurses a zombie job without detecting progress is worse than no agent. Key lesson: recovery without a progress check is a false safety net. — https://news.ycombinator.com/item?id=46812909
- **LangGraph checkpoint/rollback:** LangGraph's Checkpointers persist graph state at each step. On failure, `command(resume=...)` rewinds to a checkpoint and resumes with new input — enables stateful rollback without losing the thread. Checkpoint storage supports Postgres, Redis, SQLite, or in-memory. — https://github.com/langchain-ai/langgraph/blob/main/libs/checkpoint/README.md
- **AI Engineering Playbook (2026):** The Remote Agent Loop as a five-stage control system (Goal Intake → Planning → Monitoring → Diagnosis → Recovery) with explicit contracts at each boundary. "The reason your remote agent fails is not that the model is not smart enough — it is that the loop has no disciplined path from surprise to repair." — https://aiengineerplaybook.substack.com/p/the-remote-agent-loop-rebuilt-in
- **Zylos Research (Jan 2026):** Layered error handling combining retries → fallbacks → circuit breakers achieves 24%+ improvement in task success rates. Identifies error propagation as the central bottleneck — a single failure cascades through planning, memory, and action modules if not contained at the boundary. — https://zylos.ai/research/2026-01-12-ai-agent-error-handling-recovery
- **AI Agent Error Recovery (Agentbrisk, Mar 2026):** Failure taxonomy: transient (retry), permanent (escalate), ambiguous (classify first). Key insight: a single `except Exception: retry` is worse than no error handling — it retries everything including failures where retrying wastes time and money. — https://agentbrisk.com/blog/ai-agent-error-recovery-2026
- **GitHub / ai-system-design-guide:** Error taxonomy for agents: hallucinated tools, rate limit loops, state corruption, plan divergence. Self-correction loops vs. stateful rollbacks — LangGraph and Microsoft Agent Framework provide native checkpoint/resume primitives. — https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/07-error-handling-and-recovery.md

## Gotchas

- **Progress metrics need maintenance.** A naive metric (files modified) can be gamed — the agent creates and deletes the same file 100 times. Calibrate against actual task outcomes, not activity signals.
- **The stuck detector itself can loop.** If recovery always resets to the same state, the detector fires again, recovery fires again — a meta-loop. Use the token budget cap to break this.
- **Oscillators are the hardest shape.** They look like repeaters but a different recovery approach is needed (state reset, not re-plan). Watch for a cycle length of 2–3 steps — that's the oscillator signature.
- **Recovery state leaks to the next run.** If recovery modified external state (files, API calls) before rolling back, a checkpoint restore won't undo those side effects. Make tool actions idempotent or log them for compensation.
