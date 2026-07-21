# S-1410 · The Agent Distillation Stack — When Your Frontier Teacher Agent Costs a Fortune and You Need a Student

Your production agent runs on GPT-4o-class infrastructure. It costs $60K/month and p99 latency is 8 seconds. A team using SCoRe-style reinforced distillation trained a 7B student that matches it on your specific task distribution — at 1/10th the cost and 1/5th the latency. You've been prompt-engineering around the ceiling instead of compressing the solution. This is the agent distillation stack: how to extract your teacher agent's behavioral essence into a specialized student that lives where you need it to.

## Forces

- **Trajectories, not tokens.** An agent produces chains of reasoning, tool calls, observations, and corrections — not a single output. Naive token-level imitation misses the structural patterns that make agents succeed. You can't distill an agent like you'd distill a chatbot.
- **Teacher-student reasoning gaps compound.** The smaller student's logical decomposition differs from the teacher's. Full-trajectory imitation trains on perfect runs the student would never produce, creating a distributional mismatch that degrades at inference time.
- **Synthetic data quality is uneven.** Real agent traces are expensive; synthetic ones are cheap but noisy. Without curation, you train the student on failures that teach it to fail.
- **Degeneration risk.** Recursive distillation without anchoring to ground truth narrows capability over cycles — the student becomes a specialist in your training distribution and collapses on novel inputs. See: S-1028 (Synthetic Trajectory Degeneration).
- **Tool integration is the hard part.** The student must not only reason well — it must call the right tools, handle failures, and know when to stop. Tool behavior doesn't compress as easily as reasoning text.

## The move

### 1. Define the task boundary before collecting anything

Agent distillation only makes sense for bounded, well-scoped tasks. Before you collect a single trajectory:

```
# Task boundary checklist before distillation
TASK_BOUNDARY = {
    "input_space": "Is the input distribution enumerable? (e.g., N intent categories)",
    "success_metric": "Can you automatically verify success? (not LLM-as-judge)",
    "step_count": "Median trajectory length? (>15 steps → high failure rate on small models)",
    "tool_count": "How many tools does the agent use? (>5 → harder to compress)",
    "failure_recoverability": "Can the agent self-correct, or does it fail irreversibly?",
}
# Only distill if: bounded inputs + verifiable success + tractable tool count
```

### 2. Generate teacher trajectories with error seeding

The core insight from SCoRe (Lyu et al., ICLR 2026): the student learns best when the teacher corrects *its own* failures, not when it demonstrates perfection. Run the teacher through your task set twice:

1. **Pass-1**: Run teacher → collect successful trajectories
2. **Fail-seed**: Inject perturbations (wrong tool order, truncated context) → let teacher self-correct → collect corrected trajectories

The second pass reveals *how the teacher recovers* — this is the most compressible, most valuable behavior for the student.

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import LoraConfig, get_peft_model
import torch

def collect_score_trajectories(teacher, task_set, perturbation_rate=0.3):
    """SCoRe-style trajectory collection with self-correction.
    
    Key: let the student (during RL phase) generate from its own prefix,
    then teacher corrects only the earliest error.
    """
    trajectories = []
    for task in task_set:
        # First pass: baseline trajectory
        baseline = teacher.run(task)
        
        # Perturb: randomly swap tool order or truncate context
        perturbed = perturb_trajectory(baseline, rate=perturbation_rate)
        
        # Second pass: teacher corrects from perturbed state
        corrected = teacher.recover(perturbed)
        
        if corrected.success:
            trajectories.append({
                "task": task,
                "initial_state": perturbed,
                "corrected_trajectory": corrected.steps,
                "first_error_step": corrected.first_error_step,  # Crucial for SCoRe RL
                "reward": corrected.reward
            })
    
    return trajectories

def train_student_with_score(student_model, trajectories, earliest_error_steps):
    """Two-phase SCoRe training.
    
    Phase 1: SFT on corrected trajectories (warm start)
    Phase 2: RL from student's own generated prefix, teacher corrects only
             the step BEFORE the earliest error (verified prefix).
    """
    # Phase 1: standard SFT on corrected full trajectories
    phase1_ds = build_sft_dataset(trajectories)
    train_sft(student_model, phase1_ds, epochs=3)
    
    # Phase 2: RL from verified prefix
    # Student generates; if it reaches step k-1 correctly, 
    # assign reward at step k (the error step teacher fixed)
    phase2_ds = build_rl_dataset(trajectories, earliest_error_steps)
    train_grpo(student_model, phase2_ds)
    
    return student_model
```

### 3. Retain tools via externalized cognition — don't distill tool behavior

The most reliable compression strategy: distill *reasoning* into the student, externalize *tool execution*. The student learns the *decision* to call a tool; the tool execution layer stays on the teacher or moves to a deterministic function.

```
┌─────────────────────────────────────────────────────────┐
│  Student (7B)                                          │
│  "Given the user query and retrieved context,          │
│   decide: call search, call calculator, or respond?"  │
└─────────────────────────────────────────────────────────┘
                         │ decision
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Tool Execution Layer (deterministic, hosted)          │
│  - search(query) → results                             │
│  - calculate(expr) → result                            │
│  - No model inference here                             │
└─────────────────────────────────────────────────────────┘
                         │ tool result
                         ▼
┌─────────────────────────────────────────────────────────┐
│  Student (7B) — synthesizes tool results into answer   │
└─────────────────────────────────────────────────────────┘
```

This is the "first-thought prefix" (FTP) trick from Agent Distillation (Kang et al., NeurIPS 2025): prepend the student's reasoning prefix to the teacher's tool-call demonstrations, so the student learns the *when* of tool use, not the *how*.

### 4. Build an anchor set — and freeze it

The degeneration risk is real: without anchoring to ground truth, every distillation cycle pulls the student further from the original capability frontier. Maintain a frozen anchor set of 200-500 cases with known correct answers, and measure:

```python
def measure_degeneration(student, anchor_set, base_model):
    """KL divergence on anchor set — detect narrowing before it kills you."""
    student_probs = get_token_probs(student, anchor_set)
    base_probs = get_token_probs(base_model, anchor_set)
    
    kl_div = mean_kl_divergence(student_probs, base_probs)
    base_wins_pct = fraction(base_model.outperforms(student, anchor_set))
    
    degenerate = kl_div > 0.3 or base_wins_pct > 0.10
    if degenerate:
        print("⚠️  Degeneration detected — halt distillation, re-anchor")
    return {"kl_divergence": kl_div, "base_wins_pct": base_wins_pct, "degenerate": degenerate}
```

If degenerate: roll back to the previous checkpoint, tighten the task boundary, or inject fresh teacher data from the degenerate region.

### 5. Deploy with a fallback cascade

No student is universally better than its teacher. Deploy with explicit fallback:

```python
class DistilledAgent:
    def __init__(self, student, teacher, fallback_threshold=0.85):
        self.student = student
        self.teacher = teacher
        self.fallback_threshold = fallback_threshold
    
    def run(self, task):
        # Fast path: student
        student_conf = self.student.confidence(task)
        
        if student_conf >= self.fallback_threshold:
            return self.student.execute(task)
        
        # Quality path: teacher (async, background)
        teacher_result = self.teacher.execute(task)
        
        # Log the gap for future distillation rounds
        if teacher_result.better_than(student_result):
            self.distillation_buffer.append(
                {"task": task, "teacher_trace": teacher_result}
            )
        
        return teacher_result
    
    def periodic_distill(self, buffer_size=500):
        """Every N new cases: retrain student on new teacher demonstrations."""
        if len(self.distillation_buffer) >= buffer_size:
            new_trajectories = self.distillation_buffer
            self.student = train_student_with_score(
                self.student, new_trajectories
            )
            self.distillation_buffer.clear()
```

## Receipt

> Verified 2026-07-20 — SCoRe paper (arXiv:2509.14257, ICLR 2026) demonstrates 7B student matching 72B teacher on 12 benchmarks via self-correction RL. Agent Distillation paper (arXiv:2505.17612, NeurIPS 2025 Spotlight) provides FTP + tool externalization pattern. Zylos Research (2026-04-06) synthesizes production pipeline for teams paying $50K+/month on frontier APIs. Tianpan's six-stage distillation cycle provides operational framework. Receipt pending — code not run in this environment.

## See also

- [S-1028 · Synthetic Trajectory Degeneration](s1028-synthetic-trajectory-degeneration-when-recursive-fine-tuning-narrows-your-agent.md) — the failure mode this pattern avoids
- [S-998 · The Capability Ceiling Stack](s998-the-capability-ceiling-stack-when-your-agent-ships-but-stalls-on-hard-tasks.md) — what you're compressing past
- [S-06 · Model Routing](s06-model-routing.md) — when to route to teacher vs. student
