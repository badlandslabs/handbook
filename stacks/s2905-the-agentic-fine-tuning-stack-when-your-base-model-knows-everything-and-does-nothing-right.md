# S-2905 · The Agentic Fine-Tuning Stack

You fine-tuned your base model on your domain data. It gets worse at agentic tasks — slower tool-use accuracy, worse multi-step reasoning, more loops. The base model knew how to use tools; your fine-tune forgot. The problem is that standard fine-tuning recipes destroy agentic behaviors that were never in your training data to begin with.

## Forces

- **Agentic behaviors live in the post-training stack, not the base model.** Tool use, trajectory following, planning loops, and failure recovery are learned through RLHF and harness-based training — not raw SFT on domain text.
- **Standard SFT degrades generalization.** Fine-tuning on domain examples collapses the model's learned tool-calling distribution toward your training distribution, causing accuracy regression on unseen tool schemas.
- **Reward signals for agents are harder to define than for chat.** Unlike text quality, "good agent behavior" requires process rewards (did it check its work?) not just outcome rewards (did it succeed?).
- **Closed-loop tool interaction during training is expensive.** Naive RLHF requires running the full agent loop at scale — every training step needs tool calls, state updates, and reward computation.
- **Synthetic trajectories amplify the generator's biases.** The model that generates your training data has its own failure modes. Without diversity filtering, you're training copies of a flawed teacher.
- **LoRA rank and dataset size interact nonlinearly for agentic tasks.** What works for style transfer (small data, high rank) does not work for tool-use (needs diversity, may need lower rank to preserve pre-trained behaviors).

## The move

**The core principle: agentic fine-tuning is not about the data — it's about the training loop.**

### 1. Choose the right algorithm for the behavior class

| Behavior | Algorithm | Why |
|---|---|---|
| Tool-use accuracy | SFT + curated trajectories | Outcome is verifiable; process is short |
| Failure recovery | RLHF / GRPO | Outcome is noisy; process quality matters |
| Planning / reasoning | Process Reward Model (PRM) + RL | Steps must be evaluated mid-trajectory |
| Style / persona | LoRA / DPO | Low-stakes; preference data sufficient |
| Generalization preservation | Lower LoRA rank (32 or below) + diverse data | Higher rank erodes pre-trained behaviors |

### 2. Build trajectories, not completions

```python
# Bad: fine-tune on (prompt, completion) pairs
dataset = [{"prompt": q, "completion": a} for q, a in domain_qas]

# Good: fine-tune on trajectories — (state, action, result) chains
dataset = []
for task in env.run_episodes(n=5000):
    traj = {
        "messages": task.transcript,       # full context window
        "trajectory": task.actions,          # [tool_call_1, tool_call_2, ..., final_answer]
        "reward": task.ground_truth_score,  # 0.0–1.0
        "process_rewards": task.step_scores, # per-step signals
    }
    dataset.append(traj)

# Key: include FAILED trajectories with negative rewards
# A model that only sees success is fragile under perturbations
```

### 3. Use a custom reward function for agents (don't rely on outcome alone)

```python
def agent_reward(trajectory: Trajectory, env: ToolEnv) -> float:
    outcome_score = float(env.is_correct(trajectory.final_answer))
    
    # Process reward: did it verify its work?
    verified = any("verify" in step.tool_name or "check" in step.tool_name 
                   for step in trajectory.steps)
    
    # Tool call diversity: did it use multiple tools, not just one repeatedly?
    tool_diversity = len(set(step.tool_name for step in trajectory.steps))
    
    # Efficiency: penalize excessive loops
    efficiency = 1.0 / (1.0 + 0.1 * max(0, len(trajectory.steps) - 10))
    
    return (
        0.5 * outcome_score +
        0.2 * float(verified) +
        0.15 * min(tool_diversity / 3.0, 1.0) +
        0.15 * efficiency
    )
```

### 4. Preserve tool-use generalization with schema augmentation

```python
# Train on your schema, evaluate on HELD-OUT schemas
# This tests whether the model learned "call tools correctly" 
# vs "call these specific tools correctly"

HELD_OUT_TOOLS = [
    ToolSchema("query_database", {...}),
    ToolSchema("send_email", {...}),
    # Never appear in training data
]

def evaluate_generalization(model, held_out_tools):
    accuracy = model.bulk_eval(
        tasks=generate_tasks_for_tools(held_out_tools),
        metric="exact_tool_match"
    )
    return accuracy  # If <70%, your fine-tune collapsed tool generalization
```

### 5. The dataset size rule of thumb

- **< 500 trajectories**: Use DPO or KTO (no reward model needed). High risk of overfitting.
- **500–5,000 trajectories**: SFT with curated positive examples + filtered negatives.
- **> 5,000 trajectories**: Full RLHF with learned reward model (OpenRLHF, TRL).
- **Unsloth for speed**: 2–5× speedup, 50–70% memory reduction — use for iteration cycles under 10K examples.

## Receipt

> Verified 2026-08-20 — Research synthesis from: arXiv:2512.08769 (production agentic workflows guide), OpenAI Agent RFT (tool call latency -18%, accuracy +5–23%), Presenc AI RLHF Toolchain 2026 (TRL, Unsloth, OpenRLHF, GRPO comparison), Stanford Agentic AI curriculum (Math-Shepherd PRM, process vs outcome rewards). Key finding confirmed across multiple sources: standard SFT degrades agentic generalization unless trajectories include diversity and failed examples.

## See also

- [S-194 · Synthetic Data Generation for Fine-Tuning](s194-synthetic-data-fine-tuning-pipeline.md) — data generation pipeline (this entry focuses on the training loop)
- [S-2811 · The State-Grounded Synthetic Data Stack](s2811-the-state-grounded-synthetic-data-stack-when-your-training-data-has-more-tool-call-hallucinations-than-your-agent.md) — training data quality for agent fine-tuning
- [S-998 · The Capability Ceiling Stack](s998-the-capability-ceiling-stack-when-your-agent-ships-but-stalls-on-hard-tasks.md) — when prompting stops working and training becomes necessary
