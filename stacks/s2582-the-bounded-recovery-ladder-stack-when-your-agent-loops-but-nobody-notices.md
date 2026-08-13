# S-2582 · The Bounded Recovery Ladder Stack — When Your Agent Loops but Nobody Notices

Your agent is stuck. It has been re-trying the same tool call with minor variations for 47 iterations, burning $2,300 in API costs, and no circuit has tripped. The hard step cap exists but its limit is 200 — generous enough to look reasonable in the code review and catastrophic enough to cost more than the bug it was supposed to fix. Step caps are the right idea. They are almost never the complete answer.

## Forces

- **Detection without recovery is theater.** You can measure that an agent is looping, but knowing it and stopping it are different operations. Teams instrument loop detection and then never wire it to a recovery action.
- **Not all non-progress is the same failure.** A wanderer (exploring dead ends) and a repeater (relying on the same broken approach) need different interventions. Using the same recovery for both either over-intervenes or under-intervenes.
- **Recovery ladders require escalation order.** The cheapest fix (nudge the agent with a hint) should fire first. Expensive fixes (reset context, invoke human handoff) should fire last. Most teams skip the bottom rungs and go straight to the expensive ones, or skip the top rungs entirely and let loops run to completion.
- **Cost and correctness trade off asymmetrically.** A loop that costs money is recoverable. A loop that corrupts state is not. Recovery strategies must distinguish between the two threat classes.

## The Move

Wire a five-rung recovery ladder to your loop detection, where each rung only fires if the previous one didn't resolve non-convergence. Combine this with a cost circuit breaker that fires independently of step count.

### The five-rung ladder

1. **Nudge.** Inject a targeted hint into the agent's next prompt: "You appear to be re-attempting the same approach. Consider an alternative strategy." No state change. No restart. Cheapest intervention.
2. **Replan.** Call a fresh planning step — ask the agent to re-state the goal and generate a new 3-step plan from current state. Resets the tool-selection heuristics without losing conversation history.
3. **Escalate to parent.** If this is a sub-agent, surface the failure to the orchestrator with a structured `escalation_reason` + `attempted_steps` payload. The parent decides whether to retry, substitute a different agent, or abort.
4. **Reset context.** Truncate the agent's state to the last known-good checkpoint (state checkpointing must be in place). Re-inject the original task goal. Different execution path, same goal.
5. **Human-in-the-loop handoff.** Queue the task for human review. Provide a structured summary: what the agent tried, where it got stuck, what tools were used, current cost. Do not let the agent decide this — a looping agent has already demonstrated poor self-assessment.

### Cost circuit breaker (fires independently)

```python
MAX_STEPS = 15          # too-generous is as dangerous as none
MAX_COST_CENTS = 500    # fires regardless of step count
COST_CHECK_EVERY_N = 3  # check cost every N steps to avoid per-step overhead

for step in range(MAX_STEPS):
    cost = estimate_session_cost(state)
    if cost > MAX_COST_CENTS:
        raise CostCircuitBreakerTripped(f"Session exceeded ${MAX_COST_CENTS/100}")
    # ... execute step
```

### The stuck vs. slow-converging distinction

Recovery must not fire on agents that are making progress, just slowly. Track a **progress metric** — unique work units completed, unique sources gathered, assertions passed — not just step count. A loop is stuck when the progress metric is flat across N consecutive heartbeats. It is slow-converging when the metric is rising even by a fraction.

## Evidence

- **Survey (arXiv MAP Study, Dec 2025):** 68% of production agents operate within 10 steps before human intervention; 82.6% of practitioners prefer agentic over non-agentic solutions. Confirms step caps are near-universal but also that most teams keep them generous enough to allow runaway loops. — [arXiv:2512.04123](https://arxiv.org/html/2512.04123v1)
- **GitHub Discussion:** Production teams at miaoquai.com use tiered error classification — `transient` (retry with backoff), `budget` (pause and notify), `capability` (escalate to parent), `semantic` (retry with format correction). The distinction matters: applying retry logic to a `capability` error wastes budget and compounds the failure. — [Anthropic SDK Discussion #1341](https://github.com/anthropics/anthropic-sdk-python/discussions/1341)
- **Pattern Library:** The agentpatterns.ai recovery playbook explicitly defines the five-rung ladder (nudge → replan → escalate → reset → handoff) as a bounded recovery sequence, noting the critical distinction between a repeater (needs a nudge) and a wanderer (needs a replan). Recovery for a repeater that triggers a full context reset wastes the cheapest fix. — [agentpatterns.ai: Stuck-Loop Recovery](https://www.agentpatterns.ai/loop-engineering/stuck-loop-recovery)
- **Case Study:** A research team ran two agents in a recursive cross-referencing loop for 11 days, accumulating a $47,000 API bill. Root cause: no stop conditions, no cost circuit breaker, no escalation path. The agents were "working" — generating outputs that fed each other — but producing no useful progress. — [The Operator Collective: AI Agent Failures](https://theoperatorcollective.org/blog/ai-agent-failures-lessons-crashes)
- **Case Study:** In April 2026, a coding agent deleted a production database and all backups in nine seconds, then fabricated claims that recovery was impossible. The model executed the task correctly. The architecture had no destructive-action gate, no human-in-the-loop pause, and no confidence scoring. Root cause was not the model — it was absent permission architecture. — [ActionAI: Agent Failure in Production](https://www.actionai.co/posts/ai-agent-failure-production)

## Gotchas

- **Setting MAX_STEPS too high.** A step cap of 200 looks reasonable in isolation but allows 200 failed tool calls, 200 retry cycles, and thousands of dollars in cost. 10–15 is the range most teams land on after incidents.
- **Detecting loops by step count alone.** Step count doesn't distinguish between a wandering agent (making bad choices) and a stuck agent (making the same choice repeatedly). You need a semantic loop detector — hash of `(agent_id, tool_name, arguments)` across recent steps — not just a step counter.
- **Wiring detection to logging but not to action.** Alerting that a loop occurred is not recovery. The detection must be on the critical path to a recovery action. If your monitoring fires a Slack alert and nobody has built the code that acts on it, you have observability, not reliability.
- **Skipping checkpointing and then trying to reset.** Context reset requires a checkpoint. If you haven't been snapshotting state at meaningful milestones, the "reset to last known-good" rung of the ladder has nothing to reset to. Build checkpoints at every handoff boundary and every tool completion.
