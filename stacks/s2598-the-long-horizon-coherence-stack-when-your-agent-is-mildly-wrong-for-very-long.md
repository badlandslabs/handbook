# S-2598 · The Long-Horizon Coherence Stack — When Your Agent Is Mildly Wrong for Very Long

Your agent completes a 60-step task in two hours. Every individual step looks reasonable. No errors. No crashes. HTTP 200 on every call. The final output is wrong — subtly, comprehensively, and expensively wrong. The problem isn't a bad tool call, a failed API, or a context overflow. The problem is that your agent's implicit model of the task drifted — one degree per step, accumulating to 60 degrees of wrong by the end. You had no way to know until the bill arrived.

This is the long-horizon coherence problem: agents that are individually reasonable at every step but collectively wrong over the full trajectory. It is the hardest failure mode to catch, because it never triggers a single alert.

## Forces

- **Semantic drift compounds before it saturates.** Each summary, each tool call result fed back into context, each reformulation of the task adds a small distortion. The distortions are individually imperceptible. The aggregate is catastrophic. This is not the "lost in the middle" context degradation — it's degradation that happens even at 10% context fill, caused by summarization artifacts and confirmation-driven retrieval, not by capacity limits.
- **Agents anchor on their own recent output.** Once an agent produces a wrong intermediate result, subsequent steps treat it as ground truth. The agent builds on itself. Each wrong step makes the next wrong step more plausible. By step 30, the agent is confidently wrong about facts it generated in step 15.
- **Standard evals measure outcome, not trajectory.** Your eval suite passes because the final output matches expected answers on held-out tasks. It has no signal on whether the agent took a coherent path to get there. Two agents can score identically on the benchmark while one cohered to the answer and the other stumbled into it sideways.
- **The goal itself gets reformulated.** As the task context grows, the agent's implicit restatement of the goal drifts from the original. "Summarize customer complaints by product category" becomes "count total tickets" becomes "find the most mentioned word." Each step is locally rational. The aggregate is off-mission.
- **Confirmation bias in retrieval amplifies drift.** External memory retrieval returns results that match the agent's current framing, not the original goal. The agent's evolving context shapes what it retrieves, which shapes its next action, which shapes its context further. The feedback loop is self-reinforcing.

## The move

**1. Trajectory coherence checkpoints — not just task success.**
At every N steps (tune N to your task length; 10–15 is a good starting point), insert a coherence probe: ask the agent to re-state the current goal and the last three key decisions. Compare against the original goal. If the re-statement has drifted beyond a threshold, halt and surface the divergence.

```python
COHERENCE_STEP_INTERVAL = 12  # steps between coherence checks

def run_with_coherence_checkpoint(task: str, max_steps: int = 200):
    goal = task
    history = []
    for step in range(max_steps):
        result = agent.step(history)
        history.append(result)
        if step > 0 and step % COHERENCE_STEP_INTERVAL == 0:
            drift = measure_drift(
                original_goal=goal,
                current_goal=agent.restate_goal(history[-COHERENCE_STEP_INTERVAL:]),
                recent_decisions=agent.summarize_decisions(history[-COHERENCE_STEP_INTERVAL:])
            )
            if drift > DRIFT_THRESHOLD:
                logger.warning(f"Coherence drift detected at step {step}: {drift:.2f}")
                # Surface to human or escalation handler
                pause_and_await_review(history, drift=drift)
        if agent.is_done(history):
            break
```

**2. Anchor everything on immutable task facts.**
Capture 3–5 immutable facts from the original task at session start: the specific output format required, the key constraints, the success criteria. Store these separately from the evolving context. At coherence checkpoints, verify that the agent's current context is consistent with these anchors. Do not let the agent overwrite its own task facts.

**3. Counterfactual rewind sampling.**
Periodically (every 25–30 steps on long tasks), have the agent produce a counterfactual: "If I started this task over with only the final output so far, what would I do differently?" If the counterfactual diverges significantly from the current trajectory, the agent has drifted. This catches drift that goal-re-statement alone might miss, because it forces re-evaluation rather than reframing.

**4. Divergence-weighted tracing.**
Instrument tool calls and memory retrievals with a divergence flag: is this tool call's output consistent with the original task framing, or is it responding to the agent's evolved context? Tool calls that retrieve or act against the original goal (not the current framing) are strong drift indicators. Log these as first-class signals, not just as part of the trace.

**5. Outcome prediction at step boundaries.**
Before each step, have a lightweight model predict the next step's expected output. After execution, compare actual vs. predicted. Large deviations at step boundaries — even if the step itself "succeeded" — are early warning signals of drift. Accumulate these into a trajectory anomaly score.

## Receipt

> Receipt pending — [2026-08-13]

## See also

- [S-872](s872-the-silent-failure-stack-when-your-agent-returns-200-ok-and-wrong.md) — Silent failure: when 200 OK and wrong are the same problem
- [S-1000](s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — Context exhaustion: when the window fills before the agent finishes
- [S-1023](s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — Recovery ladder: when the agent thinks it succeeded but didn't
- [S-1030](s1030-the-forgetting-stack-when-your-agent-remembers-everything-and-knows-nothing.md) — Forgetting stack: when external memory retrieval fails
