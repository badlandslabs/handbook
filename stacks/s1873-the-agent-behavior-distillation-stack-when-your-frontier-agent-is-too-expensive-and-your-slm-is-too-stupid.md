# S-1873 · The Agent Behavior Distillation Stack — When Your Frontier Agent Is Too Expensive and Your SLM Is Too Stupid

Your production customer-service agent handles 10,000 conversations daily at $0.04 per conversation using GPT-4o. The economics work at 10K — but your roadmap calls for 500K. You look at a 3B SLM and shudder: it can't hold a tool-call loop for more than two turns without hallucinating the API schema. The solution is not prompt engineering. It's distillation: extracting the frontier agent's behavioral policy — planning, tool selection, error recovery, knowing when to stop — and compressing it into a student that costs 50× less and responds in 200ms instead of 2 seconds.

## Forces

- **Agents are trajectories, not tokens.** Standard LLM distillation (teacher generates text → student mimics tokens) fails for agents because the output is a *chain* of reasoning → decision → tool call → observation → reasoning again. Distilling just the final answer loses the policy. Distilling the full trajectory is what SWiRL (Step-Wise Reinforcement Learning) and Agent Distillation (Kang et al., KAIST 2025, arXiv:2505.17612) do differently.
- **Small models hallucinate schemas and tool names.** The core failure mode of ≤3B models as agents: they confidently call `get_customer_by_id(id="CUST_1234")` when the actual schema is `GET /customers?id={customer_id}`. The fix is not prompting — it's giving the student model *permanent access to the same retrieval and code-execution tools* that the teacher used, so the student doesn't need to memorize API shapes.
- **Trajectory quality is the bottleneck.** If your teacher agent produces 1,000 trajectories but 400 of them succeed for the wrong reason (a lucky hallucination), your student learns the wrong policy. The first-thought prefix technique (Kang et al.) re-prompts the teacher to generate more deliberate trajectories, improving trajectory quality before any fine-tuning begins.
- **You still need a frontier model — just less of it.** Distillation does not eliminate the frontier model. It makes the frontier model the *author* of training data, not the *runtime* inference engine. You pay frontier costs during the distillation pipeline; you run student inference in production.

## The move

### Step 1 — Build a Verified Trajectory Collector

Attach a lightweight logging layer to your teacher agent that captures complete trajectories: every LLM call (prompt + full chat history), every tool call (input + output), every intermediate reasoning step. Label each trajectory with an *outcome tag* — success, failure, or partial. Filter aggressively: only use trajectories where the outcome is verifiable (e.g., the downstream database shows the correct record was updated, the flight was booked, the ticket was created).

```[python]
import json
from dataclasses import dataclass, asdict
from typing import Optional

@dataclass
class ToolCall:
    tool_name: str
    input_args: dict
    output: str  # truncated at 2000 chars
    status: str  # "success" | "error" | "retry"

@dataclass
class TrajectoryStep:
    model_reasoning: str       # full CoT or thinking block
    tool_calls: list[ToolCall]
    observation: str          # aggregated tool outputs

@dataclass
class AgentTrajectory:
    session_id: str
    outcome: str              # "success" | "failure" | "partial"
    outcome_verified: bool    # external system confirmed
    steps: list[TrajectoryStep]
    token_count: int

    def to_training_example(self, student_prompt: str) -> dict:
        """Format verified trajectory as a student training example.
        Uses first-thought prefix: student learns the teacher's deliberate
        reasoning pattern, not just the output.
        """
        reasoning_chain = "\n\n".join(
            f"[Step {i+1}]\n{s.reasoning}"
            for i, s in enumerate(self.steps)
        )
        return {
            "system": student_prompt,
            "messages": [
                {"role": "user", "content": "Solve this task step by step."},
                {"role": "assistant", "content": reasoning_chain},
            ],
            "outcome": self.outcome,
            "verified": self.outcome_verified,
        }
```

### Step 2 — Curate with First-Thought Prefix

Before fine-tuning, re-pass candidate trajectories through the teacher with a "think step-by-step first" prefix. This causes the teacher to generate more deliberate reasoning chains rather than fast Pattern-Matched solutions. Filter out any trajectory where the teacher's re-generated trajectory differs from the original — inconsistency signals a lucky success.

```[python]
import anthropic

def curate_trajectories(
    raw_trajectories: list[AgentTrajectory],
    teacher_client: anthropic.Anthropic,
    teacher_model: str = "claude-sonnet-4-20250514",
) -> list[AgentTrajectory]:
    """Filter trajectories using first-thought prefix re-generation.
    
    Trajectories where the re-generated trajectory disagrees with the
    original are flagged as 'lucky' and excluded from the training set.
    """
    curated = []
    for traj in raw_trajectories:
        if not traj.outcome_verified:
            continue

        # Re-prompt the teacher on the same task
        first_step = traj.steps[0]
        response = teacher_client.messages.create(
            model=teacher_model,
            max_tokens=2048,
            system="Think step-by-step. Then produce your reasoning chain.",
            messages=[{"role": "user", "content": first_step.observation}],
        )
        regenerated_reasoning = response.content[0].text

        # If regenerated reasoning diverges significantly from the original,
        # the original trajectory was likely a lucky guess
        if semantic_similarity(regenerated_reasoning, first_step.model_reasoning) > 0.75:
            traj.steps[0].model_reasoning = regenerated_reasoning
            curated.append(traj)
        # else: skip — lucky trajectory

    return curated

def semantic_similarity(a: str, b: str) -> float:
    # Use embedding cosine similarity or an LLM-as-judge comparison
    # Simple proxy: check keyword overlap; production use a proper embedder
    words_a = set(a.lower().split())
    words_b = set(b.lower().split())
    overlap = words_a & words_b
    return len(overlap) / max(len(words_a), len(words_b), 1)
```

### Step 3 — Train the Student with Tool Access Baked In

Fine-tune a ≤3B model (e.g., Qwen2.5-3B-Instruct or Llama-3.2-3B) on the curated trajectories. Critical: give the *student* the same retrieval and code-execution tools at *inference time* that the teacher used during trajectory collection. The student learns a policy of "when unsure, call the search tool" rather than "when unsure, hallucinate."

```[python]
from unsloth import FastLanguageModel
import torch

def distill_student(
    curated_trajectories: list[AgentTrajectory],
    base_model: str = "unsloth/Qwen2.5-3B-Instruct",
    output_dir: str = "./student-agent",
    steps_per_epoch: int = 1000,
):
    """Fine-tune a small model on verified agent trajectories."""
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=base_model,
        max_seq_length=4096,
        load_in_4bit=True,          # QLoRA for commodity GPU fine-tuning
    )

    # Attach LoRA adapters for efficient fine-tuning
    model = FastLanguageModel.get_peft_model(
        model,
        r=16,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        lora_alpha=32,
    )

    # Format trajectories as instruction-tuning pairs
    training_data = []
    for traj in curated_trajectories:
        ex = traj.to_training_example(
            student_prompt=(
                "You are a customer service agent. Use tools to look up "
                "information. Think step-by-step. When you are uncertain, "
                "call the search tool rather than guessing."
            )
        )
        training_data.append(ex)

    # Standard supervised fine-tuning
    from trl import SFTTrainer
    from transformers import TrainingArguments

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=training_data,
        dataset_text_field="messages",
        max_seq_length=4096,
        args=TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=3,
            per_device_train_batch_size=4,
            gradient_accumulation_steps=4,
            warmup_ratio=0.1,
            learning_rate=2e-4,
            fp16=not torch.cuda.is_bf16_supported(),
            logging_steps=50,
            save_strategy="epoch",
        ),
    )
    trainer.train()
    trainer.save_model(f"{output_dir}/final")

    return model, tokenizer
```

### Step 4 — Deploy with Tool Registry Fallback

Even a well-distilled student will encounter edge cases outside its training distribution. Wrap the student in a fallback layer: when the student's confidence (logprob of top token) drops below a threshold, or when it attempts a tool not in the approved registry, route to the teacher. Track the fallback rate — if it exceeds 15%, trigger re-distillation.

```[python]
import anthropic

def route_to_student_or_teacher(
    query: str,
    student_model,
    student_tokenizer,
    teacher_client: anthropic.Anthropic,
    tool_registry: list[dict],
    fallback_threshold: float = 0.3,
) -> str:
    """Hybrid inference: cheap student + smart teacher fallback."""
    inputs = student_tokenizer(query, return_tensors="pt").to("cuda")
    
    with torch.no_grad():
        outputs = student_model.generate(**inputs, max_new_tokens=512)
        logits = outputs.logits
    
    # Confidence: probability mass on top token
    top_token_prob = torch.softmax(logits[0, -1], dim=-1).max().item()
    
    # Check if student is attempting an out-of-registry tool
    response_text = student_tokenizer.decode(outputs[0])
    attempted_tools = extract_tool_names(response_text)
    unknown_tools = [t for t in attempted_tools if t not in tool_registry]
    
    if top_token_prob < fallback_threshold or unknown_tools:
        # Fallback to teacher
        response = teacher_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": query}],
        )
        return response.content[0].text
    
    return response_text

# Production deployment: check fallback rate every 1000 requests
# If fallback_rate > 0.15: queue re-distillation pipeline
```

## Receipt

> Verified 2026-07-30 — Based on KAIST Agent Distillation (arXiv:2505.17612, Kang et al.), SWiRL (Step-Wise Reinforcement Learning), and Zylos Research "Distilling AI Agents" (April 2026). Framework is consistent with NVIDIA enterprise AI distillation guidance and NVIDIA-Atlan synthetic data pipeline patterns. Code adapted from Unsloth/QLora fine-tuning conventions and standard Anthropic tool-calling patterns. Receipt pending — run the distillation pipeline end-to-end with a real teacher agent to verify student quality.

## See also

- [S-1770 · Agentic Serializability](stacks/s1770-the-agentic-serializability-stack-when-your-concurrent-agents-produce-corrupted-state.md) — concurrent agent state management (related: distillation doesn't fix race conditions)
- [S-06 · Model Routing](stacks/s06-model-routing.md) — routing between model tiers (related: hybrid student/teacher inference)
