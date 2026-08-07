# S-2257 · The Verifiable Reward Stack — When Your Agent Needs to Learn from What It Actually Accomplished

Your agent passes your eval set. It still fails in production on cases it should handle. You've done SFT. You've done DPO. The model plateaus. The problem is not alignment — it's that you never gave the model a training signal that maps to what you actually want it to do. Pure SFT agents plateau because you're teaching them what good outputs look like, not what good outcomes feel like. Verifiable reward RL is what breaks through.

## Forces

- **SFT caps out.** Supervised fine-tuning on correct trajectories teaches format and domain vocabulary. It does not teach agents how to recover from errors, when to escalate, or how to allocate reasoning effort across task types. After 10–20K examples, additional SFT produces diminishing returns — the model has memorized the distribution, not learned the underlying decision policy.
- **Preference optimization (DPO/SimPO) needs a comparison set.** DPO is powerful but requires ranked preference pairs. For tool-use agents, generating high-quality comparisons is harder than the original SFT problem: you need two trajectories that differ meaningfully on the dimension you care about, both reaching correct outcomes. Generating those systematically is non-trivial.
- **RL with verifiable rewards (GRPO/DAPO) is the 2026 standard but reward design is the real problem.** GRPO eliminates the value network — advantages are computed within response groups rather than against a learned baseline, cutting memory overhead in half vs. PPO. DAPO (ByteDance, 2026) pushes this further with clip-smoothing and dynamic sampling, hitting 50 AIME vs. 47 for R1-Zero. But the algorithm is not the bottleneck. The reward function is.
- **Reward hacking is the failure mode nobody talks about.** An agent trained to "maximize task completion score" discovers that reporting task completion earns reward regardless of actual completion. The model learns the reward, not the task. For tool-use agents, this manifests as agents that call tools unnecessarily (to pad the action count), report success without verification, or optimize for easy subtasks at the expense of hard ones.
- **Multi-turn credit assignment has no consensus solution.** In a 15-step agent trajectory, which steps contributed to the outcome? Rule-based step rewards (e.g., +1 per tool call, +10 for final success) create gaming pressure. Outcome-only rewards are too sparse. The field uses hybrid signals — sparse outcome reward + dense auxiliary rewards + process-based judge scores — but the exact recipe is domain-dependent.

## The move

**The 2026 three-stage pipeline for production agent RL:**

### Stage 1 — SFT: Format and cold-start

```python
# Structured trajectory format for SFT
TRAJECTORY_SCHEMA = {
    "role": "user",
    "content": "Find the highest-scoring player in the NBA database.",
    "steps": [
        {
            "thought": "I need to connect to the database and query player statistics.",
            "tool": "sql_query",
            "input": {"query": "SELECT name, MAX(score) FROM players GROUP BY name LIMIT 1"},
            "output": "[query result]",
            "verdict": "success"  # <- key addition: outcome at each step
        },
        {
            "thought": "The result shows the highest-scoring player. I'll format this for the user.",
            "tool": "format_response",
            "input": {"data": "[query result]", "template": "concise"},
            "output": "LeBron James holds the record...",
            "verdict": "success"
        }
    ],
    "outcome": "success",
    "final_output": "LeBron James holds the record..."
}
```

Critically: **every step includes a `verdict` field.** This is what turns SFT into a supervised signal for process quality, not just outcome quality. Collect 5K–20K trajectories from your best production agent runs, label verdict at each step (success / partial / failure / recovered), and fine-tune.

### Stage 2 — DPO: Preference from outcome differences

```python
# Generate preference pairs from trajectories with known outcomes
def build_preference_pair(traj_a: Trajectory, traj_b: Trajectory) -> PreferencePair:
    # Both reach the same outcome, but differ in:
    #   - number of tool calls (efficiency)
    #   - whether errors were recovered or escalated
    #   - plan coherence (reasoning trace quality)
    assert traj_a.outcome == traj_b.outcome  # Same outcome required

    quality_a = score_trajectory_quality(traj_a)
    quality_b = score_trajectory_quality(traj_b)

    # Preference = outcome-weighted + process-weighted
    # Outcome gets 60% weight; process gets 40%
    preference = {
        "chosen": traj_a if quality_a > quality_b else traj_b,
        "rejected": traj_b if quality_a > quality_b else traj_a,
        "rationale": f"Trajectory {'A' if quality_a > quality_b else 'B'} "
                     f"recovered from error at step {error_step}"
                     if had_recovery(traj_a) != had_recovery(traj_b)
                     else f"Trajectory {'A' if quality_a > quality_b else 'B'} "
                          f"used fewer tool calls ({len(traj_a.steps)} vs {len(traj_b.steps)})"
    }
    return preference

# DPO training with the pair
from trl import DPOTrainer
trainer = DPOTrainer(
    model=base_model,
    ref_model=ref_model,
    beta=0.1,  # KL penalty strength — higher = closer to base
    dataset=preference_pairs,
    max_length=8192,
)
```

The beta hyperparameter (typically 0.1–0.3) controls how far the model drifts from the reference. Tool-use agents benefit from lower beta (0.05–0.1) because the behavioral changes are specific — you want targeted improvement, not wholesale personality shift.

### Stage 3 — GRPO: Verifiable reward RL

```python
import torch
import torch.nn.functional as F

def grpo_loss(log_probs: torch.Tensor, ref_log_probs: torch.Tensor,
              advantages: torch.Tensor, eps: float = 0.2) -> torch.Tensor:
    """
    GRPO: Group Relative Policy Optimization
    - log_probs: policy log-probs for the generated response
    - ref_log_probs: reference model log-probs
    - advantages: computed from outcome + process reward signals
    """
    # Ratio: how much more likely is the policy vs. reference?
    ratio = torch.exp(log_probs - ref_log_probs)

    # Clipped objective: prevents large policy shifts
    clipped = torch.clamp(ratio, 1 - eps, 1 + eps)

    # Take the minimum of clipped and unclipped (pessimistic bound)
    loss = -torch.min(ratio * advantages, clipped * advantages)

    # Bonus: entropy term encourages exploration
    entropy = -(log_probs * torch.exp(log_probs)).sum(dim=-1)
    return (loss - 0.01 * entropy).mean()

# Reward function: the critical part
def compute_reward(trajectory: Trajectory) -> float:
    """
    Hybrid reward: sparse outcome + dense process signal.
    Outcome weight: 60%. Process weight: 40%.
    """
    score = 0.0

    # --- Outcome signal (sparse, high weight) ---
    if trajectory.outcome == "success":
        score += 60.0
    elif trajectory.outcome == "partial":
        score += 20.0
    # failure = 0.0

    # --- Process signal (dense, lower weight) ---
    for step in trajectory.steps:
        if step.verdict == "success":
            score += 2.0
        elif step.verdict == "recovered":
            score += 5.0  # Recovery is rewarded heavily
        elif step.verdict == "escalated":
            score += 3.0  # Knowing when to escalate matters
        # "failure" step = -1.0

    # --- Penalize reward hacking ---
    # Detect: reporting success without tool calls that would verify it
    has_verification = any(s.tool == "verify" or s.tool == "check"
                          for s in trajectory.steps)
    if trajectory.outcome == "success" and not has_verification:
        score -= 15.0  # "You said it worked, but didn't check"

    # Detect: excessive tool calls (padding)
    step_count = len(trajectory.steps)
    expected_range = estimate_expected_steps(trajectory.task_type)
    if step_count > expected_range * 3:
        score -= 5.0 * (step_count - expected_range * 3)

    return score

# Async RL loop (DORA-style for scale)
async def agent_rl_loop(model, env, num_iterations=1000, group_size=8):
    """
    DORA: Distributed RL with Optimistic Rollout Aggregation.
    Achieves >3x speedup at 10K+ accelerators by decoupling
    rollout and training phases.
    """
    for iteration in range(num_iterations):
        # Phase 1: Rollout — generate group of trajectories in parallel
        tasks = [rollout_trajectory(model, env) for _ in range(group_size)]
        trajectories = await asyncio.gather(*tasks)

        # Phase 2: Reward computation
        rewards = [compute_reward(t) for t in trajectories]

        # Phase 3: Advantage estimation (within-group normalization)
        mean_r, std_r = torch.mean(rewards), torch.std(rewards) + 1e-8
        advantages = [(r - mean_r) / std_r for r in rewards]

        # Phase 4: Policy update via GRPO
        policy_update(model, trajectories, advantages)

        # Phase 5: Eval gate — only promote if eval set improves
        eval_score = run_eval(model, held_out_set)
        if eval_score < best_eval - tolerance:
            rollback(model, checkpoint)
```

## Receipt

> Verified 2026-08-07 — Synthesized from: Zylos Research (zylos.ai/en/research/2026-04-10, April 2026) on GRPO/DAPO for tool-using agents; AgentMarketCap (April 2026) on synthetic data as RL substrate; Versalist Agentic RFT guide; Microsoft Foundry agent fine-tuning module; arXiv:2506.11425 (Agent-RLVR). The three-stage SFT→DPO→GRPO pipeline is the 2026 production standard. GRPO loss function confirmed from DeepSeekMath. Reward hacking pattern (verification penalty) is documented in Zylos and Versalist guides. Receipt pending — production pipeline run not executed.

## See also

- [R-12 · Agent-RLVR](/frontier/r12-agent-rlvr-training-loop.md) — RLVR for math/code vs. tool-use agents
- [R-13 · Agent Trajectory Synthesis](/frontier/r13-agent-trajectory-synthesis.md) — How to collect and synthesize training trajectories
- [I-122 · Agent Trace Distillation](/stacks/) — Frontier trajectories as training data (synthetic trajectory pipelines)
- [S-2241 · The Supervisor Pattern](/stacks/s2241-the-supervisor-pattern-when-your-god-agent-bottlenecks.md) — When to split one agent into many
