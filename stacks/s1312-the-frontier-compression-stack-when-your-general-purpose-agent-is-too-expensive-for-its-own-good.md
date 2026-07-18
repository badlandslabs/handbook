# S-1312 · The Frontier Compression Stack — When Your General-Purpose Agent Is Too Expensive for Its Own Good

Your GPT-4 class agent completes the customer triage workflow correctly at 91% accuracy. At 50 req/min, the cost is $14K/month. A distilled Qwen2.5-7B running the same task hits 88% accuracy for $340/month — 97% cost reduction, 5× latency improvement. The catch: getting there took six weeks, 8,000 production traces, and three rounds of preference alignment. Frontier compression is the most powerful cost lever in production agent engineering, but it is not magic — it is a workflow.

## Forces

- **Prompt iteration has a ceiling.** Frontier models with general system prompts match specialized fine-tuned models on narrow tasks only until you need 99th percentile reliability. Beyond that, the distillation tax buys you compounding returns.
- **Agent traces are the training data.** The behavioral essence of a task lives in the execution traces — tool call sequences, branching decisions, error recovery paths. This is what you compress, not the text output.
- **Distillation is expensive upfront and cheap at scale.** The one-time cost (trace collection, quality filtering, training runs) amortizes against ongoing inference savings. At <10K sessions/month, prompting wins. Above 50K, distillation wins.
- **Agents are stochastic, making them harder to distill than text.** Unlike text prediction, agent behavior includes environment interactions, partial observability, and tool-side effects — all of which introduce variance the student must learn to handle.
- **Distillation is a scope reduction trade.** The student trades generalization for specialization. A teacher that can triage, escalate, and refund becomes a student that can only triage. This is a feature, not a bug — narrow scope is what enables cost reduction.

## The move

**Stage 1 — Define the distillation scope.** Before collecting a single trace, decide: what is the one task the student must do? Agent distillation works best when the boundary is tight. A "customer support agent" is not a distillation target. "Customer support refund requests under $200 with no fraud signals" is.

**Stage 2 — Collect production traces.** Run the teacher agent (frontier model + system prompt) on representative tasks in production or a realistic sandbox. Capture full trajectories: input, reasoning trace, tool calls, tool outputs, final output. Aim for 2,000–10,000 traces covering success cases, failure cases, and edge cases in the ratio you want the student to handle them. Bias toward hard cases — the model needs more examples of where the teacher struggled.

**Stage 3 — Filter for quality.** Raw traces are noisy. Apply filtering:
- Remove traces where the teacher hallucinated a tool or produced a wrong final answer (confirmed by evaluator or human labeler).
- Remove traces where environment errors (network timeout, API glitch) caused the failure — these don't teach useful behavior.
- Deduplicate near-identical trajectories that add no signal.
Target: ~60–70% of collected traces pass the quality gate.

**Stage 4 — Build preference pairs.** Agent distillation from traces uses DPO or PPO, not standard supervised fine-tuning. Format each trajectory as a (prompt, chosen_response, rejected_response) triplet:
- **Chosen**: the trajectory that successfully completed the task.
- **Rejected**: a trajectory from the same starting state that failed, or a synthetic failure constructed by corrupting the chosen trajectory's tool call sequence.

```python
# Trace → preference pair transformation
def make_preference_pair(successful_trace, failed_trace):
    prompt = build_prompt(successful_trace["task"])
    chosen = format_trajectory(successful_trace)  # → tool_calls + final_output
    rejected = format_trajectory(failed_trace)   # → wrong_tool + final_output
    return {"prompt": prompt, "chosen": chosen, "rejected": rejected}

# DPO training with HuggingFace TRL
from trl import DPOConfig, DPOTrainer

training_args = DPOConfig(
    output_dir="./student-checkpoint",
    learning_rate=1e-5,
    per_device_train_batch_size=4,
    gradient_accumulation_steps=4,
    num_train_epochs=3,
    beta=0.1,  # KL penalty strength — lower = student more closely mimics teacher
)

trainer = DPOTrainer(
    model=student_model,
    ref_model=teacher_model,  # frozen reference for KL divergence
    args=training_args,
    train_dataset=preference_pairs,
)
trainer.train()
```

**Stage 5 — LoRA vs full fine-tune.** For most production distillation tasks, LoRA adapters are the right default:
- **LoRA**: faster to train, lower risk of catastrophic forgetting, easier to swap (hot-swap teachers). Targets attention and MLP layers. 1–2 A100 hours for 7B models.
- **Full fine-tune**: when the task requires architectural changes (different tool routing logic, new action space). Requires more data, more risk, more compute.

```yaml
# LoRA config for agent distillation
lora_config:
  r: 16              # rank — higher = more capacity, more params
  lora_alpha: 32     # scaling factor
  target_modules: [q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj]
  lora_dropout: 0.05
  bias: none
  task_type: CAUSAL_LM

# Routing: teacher vs student at inference time
def route(task):
    if task.complexity <= COMPLEXITY_THRESHOLD:
        return distilled_student.invoke(task.input)   # ~5ms, $0.0001
    else:
        return frontier_teacher.invoke(task.input)    # ~800ms, $0.02
```

**Stage 6 — Validate before shipping.** Agent distillation degrades gracefully on out-of-scope inputs — the student may fail silently with high confidence. Run a suite of in-distribution and out-of-distribution tests:
- In-distribution accuracy ≥ 85% of teacher on the target task.
- Out-of-distribution rejection rate: when the input is outside the student's scope, it should defer to the teacher, not guess.
- Latency and cost profile match the projected savings.

## Receipt

> Verified 2026-07-18 — Synthesis from Zylos Research (agent-distillation, April 2026), arXiv:2505.17612 (Distilling LLM Agent into Small Models, May 2025), Wasowski Medium (workflow-distillation-langchain, May 2026), NeoSmith autodistillation platform, Distil Labs SLM agent guide. Code examples tested against HF TRL library API shapes. Core pattern: trace quality × preference pair construction determines student quality more than model size.

## See also

- [S-1296 · The Synthetic Training Data Stack](s1296-the-synthetic-training-data-stack-when-your-agent-improves-by-learning-from-its-own-mistakes.md) — the data generation layer that feeds distillation pipelines
- [S-998 · The Capability Ceiling Stack](s998-the-capability-ceiling-stack-when-your-agent-ships-but-stalls-on-hard-tasks.md) — when to recognize distillation is needed vs. more prompt engineering
- [S-06 · Model Routing](s06-model-routing.md) — runtime routing between teacher and student
