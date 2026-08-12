# S-2477 · The Action Threshold Failure Stack: When Your Agent Knows What to Do but Doesn't Do It

Your agent produces thorough, coherent, confident plans. It identifies the right next step. It explains why the step is correct. Then it does nothing — and does nothing again on the next turn. The task never starts, the deadline passes, and the agent logs show no errors. The model isn't broken. It passed every benchmark. Something deeper is broken: the gap between knowing what to do and deciding to do it has become an abyss.

This is the Action Threshold Failure — a distinct failure mode where agents stall not because they lack information, make wrong decisions, or lose context — but because the cost of committing to action exceeds their internal action threshold.

## Forces

- **Inaction has no failure signal.** When an agent takes a wrong action, there's a trace, an error, a measurable deviation. When it does nothing, there's only silence — and silence doesn't trigger retries, alerts, or escalations.
- **Planning is rewarded; action is penalized.** RLHF-trained models learn that articulate, hedged, thorough reasoning is rewarded. Confident single-step action, if wrong, is punished. The rational policy is to keep reasoning indefinitely.
- **Action has irreversible world-effects; reasoning doesn't.** The agent's training treated irreversible consequences as higher-stakes. A model that avoids bad actions also avoids all actions when stakes are ambiguous.
- **The threshold shifts with task complexity.** Simple tasks clear the threshold easily. Multi-step tasks compound perceived risk: each step's potential failure multiplies into the next, making even straightforward plans feel untenable.
- **The failure is invisible to evaluation.** Benchmarks measure whether the agent produces a correct output. They don't measure whether it produces output at all. A perfect reasoning agent that never executes scores 0 in production.

## The move

### Recognize the symptom signature

Action threshold failure has a distinct trace fingerprint, different from goal-drift (S-1036) or context-degradation (S-1000):

```
Step 1:  [REASONING] → "The optimal first action is X"
Step 2:  [REASONING] → "Before X, I should consider Y"
Step 3:  [REASONING] → "However, Y depends on Z, which requires..."
Step 4:  [REASONING] → "Let me reconsider the full plan..."
Step N:  [REASONING] → "The plan requires further analysis..."
```

The agent never reaches `[TOOL_CALL]`. The output is always a re-analysis, never an execution. This is the core diagnostic: reasoning density is high, action density is zero.

### Engineer the threshold down

**1. Break plans into pre-authorized steps.**
Replace "produce the full plan before executing anything" with "produce the next step, then execute it, then produce the next step." Each individual step has lower perceived risk than the full plan. The agent clears the action threshold for one step at a time.

**2. Add execution as its own reasoning class.**
In the system prompt, explicitly separate `REASONING` from `ACT`. Define a distinct token or marker that signals "this turn's purpose is to produce a tool call, not to produce a better plan." Prompt the model: *"If you have identified a concrete next step and you are confident it is correct, switch to ACT mode."*

**3. Use mandatory step commits.**
After N consecutive REASONING turns without an ACT, inject a forced commit: *"You have been reasoning for N steps without acting. Your task is [TASK]. Make one tool call now — even a partial or imperfect action is better than no action."* This is a structural intervention, not a stronger prompt.

**4. Inject execution cost as a signal.**
Counterintuitively: make action the lower-cost signal. Add a token-cost penalty for REASONING turns beyond a threshold. A model that burns tokens reasoning without acting hits a cost wall that forces action. This converts a latent production cost into a behavioral forcing function.

**5. Treat inaction as a first-class failure.**
Add a "zero-action" metric to your SLO: if an agent session produces N+ reasoning tokens without a single tool call within a time budget, fire an alert and trigger escalation. Currently, most teams only alert on bad actions. Inaction is the more common failure.

### Pattern-specific mitigations

**For idle-drift (coherent inaction):**
The model has full situational awareness but has learned that inaction is the safest local optimum. Use contrastive prompting: *"If a human expert faced this situation, what would they do in the next 60 seconds — not what would they think about for the next 60 seconds?"*

**For analysis-paralysis (pre-emptive uncertainty):**
The agent won't act because it can't eliminate uncertainty. Inject a tolerance threshold: *"Acting with 70% confidence is required. 95% confidence is not achievable. Proceed."* Make this explicit in the task framing, not buried in a system prompt.

**For false-inertia (waiting for upstream completion):**
The agent holds action until a condition is met that never triggers. Add a timeout watchdog: if a blocking condition exceeds T seconds, force an alternative path. The agent should have an explicit *"if X hasn't happened by time T, do Y instead"* clause.

## See also
- [S-1036 · The Trajectory Quality Index](/stacks/s1036-the-trajectory-quality-index-when-your-agent-passes-but-the-path-is-broken.md) — measuring process, not just outcomes
- [S-1261 · The Confidence Calibration Stack](/stacks/s1261-the-confidence-calibration-stack-when-your-agent-sounds-sure-and-is-wrong.md) — verbalized confidence as a unreliable signal
- [S-1000 · The Context Exhaustion Stack](/stacks/s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — silent degradation patterns
