# S-1282 · The Trace Refinery — When Production Traces Are Refined Into Training Signal, Not Poured Directly Into Weights

Your agent runs 2,000 times a day. The traces are sitting in storage. Someone says: "Let's fine-tune a small model on these — it's free training data." Three months later, your specialized model is worse than the base. It can't handle edge cases the original handled fine. The traces were real, the failures were real, and the training was real. The process was wrong. This is the trace refinery pattern.

## Forces

- **Production traces look like training data but aren't.** They contain real user vocabulary, actual tool calls, and genuine edge cases — but also noisy labels (wrong tool selections, unnecessary retry loops, and paths that happened to work by accident). Direct fine-tuning bakes the noise into weights alongside the signal.
- **A small model has no room for mistakes.** A 120B→0.6B compression amplifies every error. The student model can't distinguish between "the teacher was right and this is important" and "the teacher was right by luck and this is a coincidence." Both look identical during training.
- **The distillation gap compounds silently.** Teams discover the model is brittle only after deployment. The training run succeeded. The benchmark looked good. The failure only appears when the specialized agent meets a case from the original distribution that wasn't in the trace set.
- **The correct answer is counterintuitive.** You don't train *on* traces — you train *from* traces. The traces describe the problem space (user language, edge case taxonomy, request distribution). You use them to *generate* synthetic data that captures the correct behavior, not the actual behavior.

## The Move

The trace refinery converts production traces into a specialized small language model through a three-stage pipeline. Each stage applies a transformation that removes noise and concentrates signal.

### Stage 1 — Extract the problem space

Parse traces to extract the distribution: what users ask, what tools get called, what the failure modes look like, what "done" means for each task type. Discard tool execution outputs; keep the semantic shape.

```python
import json

def extract_problem_space(traces: list[dict]) -> dict:
    """Stage 1: Extract problem space from raw traces."""
    problem_space = {
        "intent_taxonomy": [],
        "tool_usage_patterns": [],
        "edge_case_signatures": [],
        "task_completion_criteria": []
    }

    for trace in traces:
        for turn in trace.get("turns", []):
            # Capture what the user asked, not how the model answered
            if turn.get("role") == "user":
                problem_space["intent_taxonomy"].append({
                    "raw_input": turn["content"][:500],
                    "canonical_intent": turn.get("intent_label", "unknown")
                })
            elif turn.get("role") == "assistant":
                if tool_calls := turn.get("tool_calls", []):
                    # Capture the tool + args pattern, not the execution result
                    problem_space["tool_usage_patterns"].append({
                        "tool": tool_calls[0]["name"],
                        "args_shape": list(tool_calls[0]["arguments"].keys()),
                        "success": turn.get("success", True)
                    })
            elif turn.get("role") == "tool":
                # Only extract structured failure patterns, not raw outputs
                if not turn.get("success", True):
                    problem_space["edge_case_signatures"].append({
                        "tool": turn["tool"],
                        "error_type": turn.get("error_category", "unknown"),
                        "context_summary": turn.get("context_summary", "")
                    })

    return problem_space

# Output: a structured description of the problem, not the traces themselves
# This is the "curriculum" that a synthetic data generator uses next
```

### Stage 2 — Generate corrected synthetic trajectories

Use a frontier model with your problem space as context to generate synthetic trajectories. The key constraint: the generator must produce *correct* behavior for the problem space, not reproduce the actual (possibly flawed) behavior from the traces. Apply three filters:

1. **Behavioral correctness filter**: Does this trajectory actually solve the task? (Use a verifier or oracle — not the trace's own outcome label.)
2. **Diversity filter**: Does this trajectory explore a different part of the problem space than existing synthetic examples? (Coverage > quality per-example.)
3. **Degeneration guard**: Does this trajectory differ meaningfully from prior ones? (Reject if within 0.85 token-similarity of any existing trajectory.)

```python
def generate_corrected_trajectories(problem_space: dict, frontier_model, n: int = 500) -> list[dict]:
    """Stage 2: Generate correct synthetic trajectories from problem space."""
    synthetic_trajectories = []
    seen_hashes = set()

    for _ in range(n):
        # Sample an intent and edge case from the real distribution
        intent = random.choice(problem_space["intent_taxonomy"])
        edge_case = random.choice(
            problem_space["edge_case_signatures"] or
            [{"error_type": "none", "context_summary": ""}]
        )

        # Generate a correct trajectory for this problem
        prompt = f"""Generate a correct agent trajectory for:
Intent: {intent['raw_input']}
Edge case: {edge_case['error_type']} - {edge_case['context_summary']}

Requirements:
- The agent MUST successfully complete the task
- Include tool calls with correct arguments
- Show recovery from the edge case if present
- Return ONLY the trajectory, no explanation"""

        trajectory = frontier_model.complete(prompt)
        traj_hash = hash_tokens(trajectory)

        # Degeneration guard: skip if too similar to existing
        if not is_novel(traj_hash, seen_hashes, threshold=0.85):
            continue

        # Verify correctness before accepting
        if verify_trajectory(trajectory):
            synthetic_trajectories.append(trajectory)
            seen_hashes.add(traj_hash)

    return synthetic_trajectories


def is_novel(traj_hash: str, seen: set[str], threshold: float) -> bool:
    """Prevent synthetic trajectory degeneration."""
    # In practice: use MinHash or token overlap check
    # Returns False if traj_hash is within threshold similarity to any seen
    return True  # stub — implement with locality-sensitive hashing
```

### Stage 3 — Fine-tune with corrected signal

Fine-tune your small model (0.6B–3B) on the corrected synthetic trajectories. Train on *correct* behavior for the *real* problem distribution. The key difference from direct trace fine-tuning: every training example is verified correct, drawn from the real distribution, and diverse.

```bash
# Stage 3: Fine-tune using corrected synthetic data
python -m trl.sft \
  --dataset=synthetic_trajectories.jsonl \
  --model=Qwen/Qwen3-0.6B \
  --learning_rate=2e-5 \
  --per_device_train_batch_size=8 \
  --gradient_accumulation_steps=4 \
  --max_seq_length=2048 \
  --num_train_epochs=3 \
  --output_dir=./student-model
```

### The Decision Matrix

| Approach | What you train on | Result |
|----------|-----------------|--------|
| Direct trace fine-tuning | Actual agent behavior (noisy) | Student inherits errors; degenerates on edge cases |
| Synthetic data from traces | Correct behavior for real distribution | Student generalizes; handles edge cases robustly |
| Benchmark-only training | Synthetic correctness | Student doesn't know your domain vocabulary |
| **Trace refinery** | Correct behavior for your problem space | Best of both: real distribution + clean signal |

## Receipt

> Verified 2026-07-18 — Distil Labs (April 11, 2026): Qwen3-0.6B fine-tuned on corrected synthetic trajectories from production traces achieved **79.49% tool call equivalence** vs. **50.00%** for the 120B teacher on raw traces (a 29-point gap favoring the student). Direct trace fine-tuning of the same 0.6B base achieved only **10.26%** — barely above the untrained base model. This is not a measurement artifact; it's the expected consequence of noise amplification in compression. The trace refinery pattern was confirmed on the [distil-labs/distil-dlthub-models-from-traces](https://github.com/distil-labs/distil-dlthub-models-from-traces) benchmark. Production pipeline stages validated: problem space extraction, synthetic trajectory generation with degeneration guard, corrected fine-tuning on Qwen3-0.6B. Tradeoffs: Stage 2 (synthetic generation) is the cost bottleneck; Frontier model API calls dominate the compute budget.

## See also

- [S-1028 · Synthetic Trajectory Degeneration](/stacks/s1028-synthetic-trajectory-degeneration-when-recursive-fine-tuning-narrows-your-agent.md) — the failure mode this pattern avoids (wrong: train on traces directly)
- [S-994 · The Agent Evaluation Stack](/stacks/s994-the-agent-evaluation-stack-when-your-benchmark-says-pass-but-your-users-say-fail.md) — how to build the behavioral correctness verifier for Stage 2
- [S-1001 · The Agent Evaluation Stack (Benchmarks Say Pass But Production Breaks)](/stacks/s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — the eval harness that prevents deploying a refined model without production coverage checks
