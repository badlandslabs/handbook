# S-1073 · The Agent Distillation Stack — When Your Frontier Agent Becomes Your Production Cost

Your agent works beautifully. Every workflow completes. Every edge case handled. The catch: it runs on a frontier model at $2–15 per 1,000 completions, and you have 50,000 completions per day. The business case collapses the moment finance sees the invoice. You can't ship the small model because it fumbles on hard cases. You can't afford the frontier model at volume. The answer is neither — you distill the frontier agent's behavioral essence into a specialized student that costs 10–100x less and performs within 2–5% on your specific task distribution.

## Forces

- **Frontier cost is structurally incompatible with volume production.** A frontier model agent that costs $0.50 per task is fine at 1,000 tasks/day ($500/day). At 50,000 tasks/day ($25,000/day), the economics break. The solution is not negotiation — it's compression.
- **Agent distillation is harder than text distillation.** Agents produce trajectories: chains of reasoning, tool calls, observations, corrections. You can't just distill the final answer. You have to distill the *process* — and processes have variable length, branching, and failure recovery that text doesn't.
- **Behavioral collapse is the silent failure of distillation.** Fine-tuning a small model on teacher trajectories risks mode collapse: the student learns to reproduce the teacher's outputs but not the teacher's *competence*. It passes the eval it was trained on and fails on anything slightly new.
- **Trajectory quality varies with task difficulty.** Teacher agents produce high-quality trajectories on simple tasks (near-perfect tool selection, clean reasoning). On hard tasks, trajectories contain retries, backtracking, and failed attempts. The student that learns from all of this uniformly treats every trajectory as equally worth mimicking.

## The move

### Step 1 — Collect Teacher Trajectories at Scale

Run your frontier-agent pipeline on your production workload. Capture complete traces: reasoning steps, tool calls with arguments, tool responses, final outputs. The goal is 1,000–10,000 high-quality trajectories covering your task distribution. Filter aggressively:

```python
# Trajectory quality scoring
def score_trajectory(trajectory: dict) -> float:
    """Score a trajectory for distillation quality."""
    score = 0.0

    # Reward: task completed successfully
    if trajectory["outcome"] == "success":
        score += 0.4

    # Reward: efficient (within 2x of optimal step count)
    optimal_steps = estimate_optimal_steps(trajectory["task_type"])
    if trajectory["step_count"] <= optimal_steps * 2:
        score += 0.2

    # Penalize: excessive retries or backtracking (shows the teacher struggled)
    retry_ratio = trajectory["retries"] / max(trajectory["step_count"], 1)
    if retry_ratio > 0.3:
        score -= 0.2

    # Penalize: tool calls with null/empty arguments (hallucinated args)
    hallucinated_args = sum(
        1 for tc in trajectory["tool_calls"]
        if null_args_in_call(tc)
    )
    if hallucinated_args > 0:
        score -= 0.15 * hallucinated_args

    return max(0.0, min(1.0, score))

# Only distill from trajectories scoring above 0.7
distill_set = [t for t in trajectories if score_trajectory(t) >= 0.7]
```

### Step 2 — Segment Trajectories by Reasoning vs. Action

Separate the reasoning trace (chain-of-thought, planning, tool selection) from the action trace (tool calls, API results, state mutations). Each type requires different distillation signals:

- **Reasoning spans**: Use a Chain-of-Thought Policy Alignment loss — penalize the student when its reasoning diverges from the teacher's logical sequence on the same state.
- **Action spans**: Use an Action Consistency loss — penalize tool selection deviations and argument structure differences, even when final outcomes match.

```python
from transformers import Trainer, TrainingArguments
from torch import nn

class AgentDistillationLoss(nn.Module):
    """Two-component distillation loss for agent trajectories."""

    def __init__(self, cot_weight=0.4, action_weight=0.6):
        super().__init__()
        self.cot_weight = cot_weight
        self.action_weight = action_weight
        self.ce = nn.CrossEntropyLoss(ignore_index=-100)

    def forward(self, student_logits, teacher_logits, labels, segment_mask):
        # Component 1: Reasoning spans (segment_mask == "reasoning")
        reasoning_mask = (segment_mask == "reasoning")
        if reasoning_mask.any():
            cot_loss = self.ce(
                student_logits[reasoning_mask],
                labels[reasoning_mask]
            )
        else:
            cot_loss = 0.0

        # Component 2: Action spans (segment_mask == "action")
        action_mask = (segment_mask == "action")
        if action_mask.any():
            action_loss = self.ce(
                student_logits[action_mask],
                labels[action_mask]
            )
        else:
            action_loss = 0.0

        return self.cot_weight * cot_loss + self.action_weight * action_loss
```

### Step 3 — Use Curriculum Learning to Prevent Brittle Habits

Order training examples from simple to complex. Exposing the student to hard cases too early teaches it to mimic failure patterns. A curriculum prevents the student from learning "retry 5 times on simple task X" as a habit.

```python
# Sort by task complexity, not trajectory quality
trajectories_by_complexity = sorted(
    distill_set,
    key=lambda t: t["complexity_score"]  #: number of tools, context length, hop count
)

# Feed in waves: simple → medium → hard
batch_waves = [
    trajectories_by_complexity[0:1000],      # Wave 1: simple tasks
    trajectories_by_complexity[1000:3000],    # Wave 2: moderate complexity
    trajectories_by_complexity[3000:],        # Wave 3: hard edge cases
]
```

### Step 4 — Distillation with a Different Judge

Train a separate evaluation model (a judge) to score student outputs against a rubric (helpfulness, safety, tool adherence, response accuracy). The judge must be a *different* model than the student — using the same model as judge and student produces mode collapse (self-preference inflation). Target Expected Calibration Error (ECE) below 5%.

### Step 5 — Shadow Deploy Before Cutover

Run the distilled student in shadow mode alongside the teacher: same inputs, teacher decides, student observes. Compare outcomes for 2 weeks. Measure: task success rate, tool call accuracy, retry rate, user satisfaction. Only cut over when student is within 3% of teacher on all metrics.

## Receipt

> Verified 2026-07-13 — Production pipeline components drawn from Zylos Research "Distilling AI Agents: Frontier to Specialized" (Apr 2026) and Perea.ai "Knowledge Distillation in Production: The 2026 Pipeline" (May 2026). Cost-reduction benchmarks (10–100x) from Zylos Research. Curriculum learning ordering pattern from Zylos SAD technique. SCoRe correction approach noted as orthogonal addition. Receipt pending — pipeline not instantiated end-to-end.

## See also

- [S-1039 · The Specialist Router Stack](s1039-the-specialist-router-stack-when-your-agent-runs-everything-through-opus-and-bills-you-for-it.md) — model selection as routing problem, complementary to distillation
- [S-1028 · Synthetic Trajectory Degeneration](s1028-synthetic-trajectory-degeneration-when-recursive-fine-tuning-narrows-your-agent.md) — failure mode when distillation ignores distribution anchoring
- [S-998 · The Capability Ceiling Stack](s998-the-capability-ceiling-stack-when-your-agent-ships-but-stalls-on-hard-tasks.md) — eval design for measuring whether distilled student meets production bar
