# [S-1179] · The Reasoning-Planning Gap

Your agent decomposes tasks, calls tools in sequence, and explains its logic step by step. It looks smart. Then at step 47 of a 50-step plan it dead-ends — having committed too early to a path that seemed locally optimal but was globally wrong. The agent didn't stop reasoning. It stopped planning.

## Forces

- Chain-of-thought prompting made step-by-step reasoning strong — but reasoning and planning are structurally different
- Step-wise greedy policies are arbitrarily suboptimal on long-horizon tasks: adding more reasoning steps does not fix the problem, it compounds it
- Beam search (wider reasoning) does not close the gap — it finds more locally good paths without improving global coherence
- Task duration doubles every ~4.3 months (AgentMarketCap), meaning the horizon gap widens as agents take on longer work
- METR data: Claude Mythos sustains 80% reliability only to ~3 hours; 50% reliability only to ~16 hours — yet the agent looks competent throughout because each local step *is* competent
- S-357 (planner-worker) and S-357's temporal layers address orchestration but do not resolve the structural mismatch between how LLM reasoning works and what long-horizon planning requires

## The move

### Recognize the failure mode, not the symptoms

Agents failing long-horizon tasks do not announce "I cannot plan globally." They announce:
- Silent commitment: picks one approach path and cannot backtrack even when evidence accumulates against it
- Error cascade: early sub-optimal action creates compounding state that later reasoning cannot recover
- Horizon collapse: performance degrades not at a cliff but as a quadratic function of task length (arXiv:2601.22311)
- Completion cliff: on coding tasks, 64.6% of runs show real partial progress but only 4.3% finish (Long-Horizon-Terminal-Bench)

The symptom is "it got stuck." The disease is reasoning without lookahead.

### The structural diagnosis

LLM reasoning is a step-wise greedy policy:
- At each step, it selects the locally best action given the current state
- It has no mechanism to search the full tree of future consequences
- Even CoT/Scratchpad reasoning is still generated left-to-right, optimizing each next token
- Beam search widens the search but doesn't change the policy class — it finds more greedy paths, not better global paths

This is mathematically different from planning, which requires:
- Evaluating a state-action pair not by immediate reward but by discounted cumulative future reward
- Looking ahead across multiple interaction layers to account for delayed consequences
- Potentially committing to a locally costly action because it unlocks higher-value downstream states

```python
# Step-wise greedy (how LLM reasoning actually works)
def greedy_step(state):
    return argmax(actions, lambda a: immediate_reward(state, a))

# Planning (what long-horizon tasks require)
def planning_value(state, depth=0, gamma=0.9):
    if depth == max_depth:
        return 0
    return max(
        discounted_reward(state, a)
        + gamma * planning_value(transition(state, a), depth + 1)
        for a in actions
    )
```

The gap is not a capability gap — the model *can* reason about consequences. The gap is a *mechanism* gap: step-wise generation does not produce a search over future trajectories. You get one trajectory (the greedy one), not an evaluated portfolio.

### Three structural fixes

**1. Hierarchical task decomposition with independent sub-goals**

Break the task into sub-goals where each sub-goal has its own success criterion that is locally verifiable. This limits the planning horizon at any one level — instead of one 50-step plan, you get 5 ten-step plans evaluated independently.

The key design constraint: sub-goal boundaries must be placed where success/failure of sub-goal N does not fundamentally alter the value of sub-goal N+1. If completing sub-goal 1 changes what sub-goal 2 should be, you've decomposed wrong.

See also: S-357 (planner-worker), S-34 (narrow-scope agent design).

**2. Outcome-verified checkpointing with explicit backtracking gates**

At each major checkpoint, capture the decision state and evaluate whether the current trajectory is converging toward the goal state, not just whether the last tool call succeeded.

```python
checkpoint = {
    "step": n,
    "state": current_state,
    "predicted_outcome": model.predict(goal, current_state),
    "evidence": accumulated_tool_results
}
# External verification — NOT the agent's own reasoning
if not verifier.confirms(checkpoint["predicted_outcome"], checkpoint["evidence"]):
    trigger_replan(checkpoint)
```

This requires the verifier to be structurally separate from the reasoning agent — the same model auditing its own trajectory has the same step-wise greedy bias.

See also: S-439 (confident false success), S-439's state-verification approach.

**3. World-model simulation for lookahead**

Recent work (ProPlay, arXiv:2606.12780; Qwen-AgentWorld, arXiv:2606.09863) proposes explicit world models that simulate the effect of action sequences before execution. Instead of "reason about next step, execute," agents predict "if I take action sequence [A, B, C], the state becomes X, Y, Z — does Z serve the goal?"

This is fundamentally different from CoT because:
- CoT generates one continuation; world-model simulation samples multiple trajectories
- World-model evaluation is against an explicit state representation, not natural language
- The simulation is run before execution, not as a post-hoc explanation

```python
# World-model lookahead (pre-execution simulation)
candidate_sequences = generate_trajectories(current_state, goal, depth=3)
evaluated = [
    (seq, world_model.score(seq, goal))
    for seq in candidate_sequences
]
best = max(evaluated, key=lambda x: x[1])
execute(best[0])
```

### The completion cliff as an eval signal

Dense reward grading reveals what binary pass/fail hides: 60%+ of agent runs make genuine partial progress but never complete. Treat this as a planning-horizon signal:

| R-value (task completion ratio) | Implication |
|---|---|
| R ≥ 0.95 | Task completed (rare — 4.3% on LHTB) |
| 0.75 ≤ R < 0.95 | Agent worked but could not close — classic planning failure |
| 0 < R < 0.75 | Mix of capability and planning failures |
| R = 0 | Capability failure or early mis-commitment |

Track R-value distribution across your production tasks, not just binary success rate. A cohort with R-values clustered below 0.5 but above 0 is a planning-horizon problem, not a capability problem — and the fix is architectural, not model upgrades.

## Receipt

> Verified 2026-07-16 — Research sources: arXiv:2601.22311 "Why Reasoning Fails to Plan" (Wang et al., ICML submission, Jan 2026) — formal proof that step-wise greedy reasoning is arbitrarily suboptimal for long-horizon tasks; arXiv:2604.11978 "The Long-Horizon Task Mirage" (Wang, Bai, Song et al., UW/Berkeley) — HORIZON benchmark across 3100+ trajectories showing horizon-dependent failure; Long-Horizon-Terminal-Bench (Daniel Vaughan, 2026) — 64.6% partial vs 4.3% completion on coding tasks; AgentMarketCap April 2026 — task horizon doubling at 4.3 months; METR capability metrics May 2026 — 3h at 80% reliability, 16h at 50%; ProPlay (arXiv:2606.12780) and Qwen-AgentWorld world-model approaches. Deduplication: No existing handbook entry covers the structural reasoning-vs-planning mismatch, greedy policy suboptimality proof, or world-model simulation as a fix. S-357 covers planner-worker orchestration architecture; S-34 covers narrow-scope design; neither addresses the mechanism-level diagnosis.

## See also

- [S-357 · Long-Running Agent Orchestration: Planner-Worker Temporal Layers](s357-long-running-agent-orchestration-planner-worker-temporal-layers.md) — architectural pattern; complementary to this entry
- [S-1004 · The Agent Eval Stack](s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — eval methodology including dense reward grading
- [S-439 · Confident False Success: The Self-Assessment Failure Mode](s439-confident-false-success-the-self-assessment-failure-mode.md) — why agents can't self-verify their way out of this
- [S-1174 · The Scaffold Convergence Problem](s1174-the-scaffold-convergence-problem-when-frontier-models-cluster-within-1-point-and-the-real-engineering-is-in-the-harness.md) — harness-level engineering leverage
