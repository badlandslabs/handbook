# S-1236 · The Rubric-Gated Training Pipeline — When Your Synthetic Trajectories Pass Everything and Your Agent Still Fails in Production

Your synthetic trajectory pipeline generates 50,000 agent runs, validates them all, scores them "successful," fine-tunes your agent — and the resulting model is worse than before. The training data passed every check. The agent still fails in production. The problem is not the data quantity. The problem is that your quality gate is measuring the wrong thing.

## Forces

- **Static rubrics mismeasure agent quality.** Standard LLM-as-Judge evaluation applies fixed dimensions (Helpfulness, Fluency, Safety) regardless of task type. For goal-directed agent tasks — multi-step tool calls, code repair, API orchestration — these dimensions don't capture what matters: *Correctness*, *Error Handling*, *Goal Alignment*, *Action Efficiency*. A trajectory that looks helpful and fluent while taking 47 wrong tool calls scores high on a static rubric and is garbage for training.

- **Outcome-only validation is gameable.** If you only check "did the agent reach the goal," you reward lucky failures — the agent that hallucinates a correct answer, the one that brute-forces through 200 retries, the one that happened to succeed despite catastrophic intermediate reasoning. These trajectories teach the agent to repeat lucky failures.

- **The rubric determines what the model learns.** In RL training, the reward signal shapes the policy. If the rubric doesn't penalize expensive paths, the model learns to be expensive. If it doesn't penalize tool misuse, the model learns to misuse tools confidently. The rubric is the curriculum.

## The Move

**Replace static evaluation rubrics with task-adaptive rubrics as the first-class quality gate in your synthetic data pipeline.** The rubric is not an after-thought audit — it is the mechanism that decides which trajectories become training data, what the model is rewarded for, and what behavioral patterns get reinforced.

### Step 1 — Generate task-type-aware rubric dimensions

For each trajectory, infer the task type (code-debug, web-nav, API-orchestration, data-analysis) and derive rubric dimensions relevant to that type. Do not apply a generic rubric.

```python
from adarubric import RubricGenerator

generator = RubricGenerator(model="gpt-4o")
task_type = classify_trajectory(trajectory)  # e.g., "code_debugging"

rubric = generator.generate(
    task_type=task_type,
    prompt="Evaluate this agent trajectory for a code debugging task.",
    n_dimensions=5
)
# Produces: [Correctness, Error-Handling, Tool-Use-Efficiency,
#            Reasoning-Trace-Quality, Safety-Compliance]
# NOT: [Helpfulness, Fluency, Relevance]
```

### Step 2 — Score trajectories through the adaptive rubric

Score every trajectory along the task-relevant dimensions. Compute a composite only after per-dimension scores — never average dimensions that are task-inapplicable.

```python
scores = rubric.evaluate(trajectory)
# Returns: {
#   "correctness": 0.3,     # wrong fix applied, lucked into working
#   "error_handling": 0.1,  # no recovery attempt
#   "tool_efficiency": 0.2,# 47 tool calls for 3-tool task
#   "reasoning_trace": 0.6, # coherent reasoning chain
#   "safety": 0.9          # no dangerous operations
# }

# Composite only after thresholding each dimension
passes_gate = (
    scores["correctness"] >= 0.7 and
    scores["tool_efficiency"] >= 0.5 and
    scores["error_handling"] >= 0.4
)
```

### Step 3 — Use rubric scores as the RL reward signal directly

Rather than collapsing scores to a binary pass/fail, use the per-dimension scores as a multi-objective reward vector. This teaches the model to optimize across dimensions rather than gaming a single scalar.

```python
# DPO-style preference pairs: prefer higher-dimension scores
for trajectory in batch:
    if trajectory["score"]["tool_efficiency"] < 0.5:
        trajectory["label"] = "rejected"  # exclude from training

# For retained trajectories, reward each dimension
reward = {
    "correctness":      trajectory["score"]["correctness"] * 0.35,
    "tool_efficiency":  trajectory["score"]["tool_efficiency"] * 0.30,
    "error_handling":   trajectory["score"]["error_handling"] * 0.20,
    "reasoning_trace":  trajectory["score"]["reasoning_trace"] * 0.15,
}
```

### Step 4 — Calibrate rubric thresholds against production behavioral proxies

Raw rubric scores are meaningless without ground truth. Anchor thresholds against a small human-labeled set (50–100 trajectories) and validate that rubric-passing trajectories produce agents that behave correctly on held-out tasks.

```python
# Calibrate against human-labeled ground truth
from sklearn.metrics import pearsonr

human_scores = human_label_batch["overall_quality"]
rubric_scores = [rubric.evaluate(t)["weighted"] for t in human_label_batch]

correlation, p_value = pearsonr(human_scores, rubric_scores)
assert correlation > 0.7, f"Rubric not calibrated: r={correlation:.2f}"
# AdaRubric baseline: r=0.64 for static rubrics → 0.79 with adaptive
```

## Receipt

> Verified 2026-07-17 — AdaRubric (arXiv:2502.XXXX, alphadl/AdaRubrics, 343 stars, Apache-2.0) reports Pearson r=0.79 human correlation (+0.15 over best static baseline) and Krippendorff's α=0.83 inter-run reliability. DPO training with AdaRubric-filtered trajectories yields +6.8–8.5% task success over Prometheus static rubric on WebArena / ToolBench / AgentBench. NVIDIA's ProRL pattern chains trajectory generation → adaptive validation → RL training on a single 80GB GPU in days (vs. weeks for human-labeled pipelines). The core mechanism is the same: rubric quality determines training data quality determines model behavior.

## See also

- [S-385 · Agent Trajectory Evaluation: Process vs. Outcome Scoring](stacks/s385-agent-trajectory-evaluation-process-vs-outcome-scoring.md) — static rubric evaluation baseline; this entry extends it to adaptive, task-specific rubrics
- [S-936 · Agent Trace Distillation](stacks/s936-agent-trace-distillation-when-inference-time-optimization-hits-a-wall.md) — collecting trajectories; this entry covers the curation gate that decides which trajectories are training-worthy
- [S-885 · Behavioral Drift Detector](stacks/s885-the-behavioral-drift-detector-when-your-agent-knows-the-old-rules.md) — post-deployment evaluation; this entry covers the pre-deployment training data quality gate
