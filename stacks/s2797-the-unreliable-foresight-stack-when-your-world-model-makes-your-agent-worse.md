# [S-2797] · The Unreliable Foresight Stack

Your agent has a world model now. It predicts the consequences of actions before executing them. It runs simulations. It thinks ahead. You shipped it because foresight should make decisions better. Six months in, your long-horizon task reliability has dropped by 23%. The agent is confidently wrong more often than it was without the world model. Nobody can explain why.

## Forces

- World models are the natural evolution of planning for long-horizon agents — predicting consequences before execution should dominate naive step-by-step reasoning
- The field assumed unreliable foresight would be ignored (agents would fall back to reactive behavior) — it is not; agents use it, and it actively degrades decisions
- Selective trust is harder than full trust: agents cannot distinguish between high-confidence and hallucinated predictions without the very world model they're evaluating
- Frozen world models (pre-trained, not updated at deployment) accumulate prediction-observation mismatches that compound silently over long task horizons
- Even self-evolving world models that revise their context can introduce new errors if the revision mechanism itself is unreliable

## The move

The core move: **do not give your agent a world model without a confidence gate on its output, and do not assume bad foresight is harmless.**

### WorldEvolver architecture (NUS/SUTD/SMU, arXiv:2606.30639, Jun 2026)

The three-module self-evolving framework addresses unreliable foresight directly:

1. **Episodic Memory** — exploit real action→observation transitions through retrieval-based simulation. Only simulate from confirmed past trajectories, not imagined ones.
2. **Semantic Memory** — extract persistent heuristic rules from prediction-observation mismatches. When the world model is wrong, extract *why* it was wrong and encode that as a filter rule.
3. **Selective Foresight** — filter low-confidence predictions before integrating them into agent reasoning context. The world model is only consulted for predictions above a confidence threshold; below threshold, fall back to reactive execution.

Key insight: all three modules operate with the downstream agent and model parameters *frozen*. No fine-tuning required. The world model evolves its context, not the model.

### SR²AM architecture (Deng et al., arXiv:2605.22138, May 2026)

Three-system decomposition for efficient agentic reasoning:

1. **Simulative Reasoning (System II)** — grounds deliberation in future-state prediction using a world model. Not unconstrained chain-of-thought; action→consequence→evaluate→choose.
2. **Self-Regulation (System III)** — learned configurator that decides *when* and *how deeply* to invoke the simulative planner at each turn. Avoids always-on planning (wasteful) and never-on planning (misses long-horizon tasks).
3. **Reactive Execution (System I)** — handles fine-grained reasoning and action for routine steps. Fast, low-token, no world model overhead.

The configurator is the critical component: it is the confidence gate that prevents unreliable foresight from contaminating decisions.

### Practical checklist

```
[ ] World model output is gated by confidence score
[ ] Predictions below threshold → reactive execution path (no world model)
[ ] Episodic Memory uses only confirmed action-observation pairs (not hallucinations)
[ ] Prediction-observation mismatches are logged and fed to Semantic Memory as filter rules
[ ] Self-regulation configurator has a minimum-confidence threshold tunable per task type
[ ] World model context is revised at deployment time (frozen ≠ static)
[ ] Long-horizon tasks (>1 hour) have explicit world-model sanity checks on critical branches
[ ] Unreliable foresight degradation is measured: compare task success with and without foresight
```

### Diagnostic signal

If your world-model-equipped agent is outperforming a reactive baseline on *short* tasks but underperforming on *long* tasks, unreliable foresight contamination is likely. The fix is not a better world model — it is selective use of the world model you have.

## See also

- [S-1179 · The Reasoning-Planning Gap](s1179-the-reasoning-planning-gap-when-your-agent-reasons-well-but-plans-poorly.md) — structural difference between reasoning and planning; this entry adds the world-model dimension
- [S-561 · The Self-Correction Gap](s561-the-self-correction-gap-when-agents-cant-self-heal.md) — agents can't self-heal from their own errors; unreliable foresight is a specific case where self-correction by the world model introduces new errors
- [S-447 · The Three-Store Memory Architecture](s447-the-three-store-memory-architecture.md) — episodic/semantic/procedential stores; WorldEvolver's Episodic and Semantic Memory modules build on this architecture
