# S-1457 · The Synthetic Trajectory Pipeline Stack — When You Train an Agent Without a Single Human-Labeled Example

You need a domain-specific agent — for your internal API, your support workflow, your codebase. The public base model can't do it. Fine-tuning requires training data. You have 200 examples. You need 80,000. Human labeling costs more than your infrastructure budget. The solution that's now standard across NVIDIA, Scale AI, and every serious agent lab: build a pipeline that generates, validates, and scores its own training data — then close the loop on production failures to keep the pipeline alive.

## Forces

- **Human annotation hits a wall fast.** 200 seed examples might cost $2K and take 2 weeks. 80,000 training examples cost $800K and take 6 months. By the time you're done, the use case has changed.
- **Synthetic data quality is pipeline-dependent, not model-dependent.** A frontier model generating training data is only as good as the quality gates that filter the output. The model is the generator; the pipeline is the product.
- **Distribution collapse is the silent killer.** Agents fine-tuned on synthetic data without production feedback loops tend to memorize the synthetic distribution rather than generalize. Without a closed loop, you train into a distribution that exists nowhere in the real world.
- **The 70/30 ratio is the operational sweet spot.** 70–80% synthetic / 20–30% human gives the best generalization in tractable domains (AgentMarketCap, April 2026). The human portion is reserved for edge cases and validation, not generation.

## The Move

The pipeline has five stages. Each stage has a failure mode. Each failure mode has a mitigation.

### Stage 1: Seed Set Curation

Start with 100–300 high-quality, diverse examples of the target task. These are the only human-labeled data in the pipeline.

```python
# Seed curation criteria: diversity × quality, not quantity
seed_examples = [
    {"instruction": "Find pending orders for customer acme-2024",
     "environment": "internal-erp-v2", "difficulty": "easy"},
    {"instruction": "Reconcile the Q3 invoice batch and flag discrepancies >$500",
     "environment": "internal-erp-v2", "difficulty": "medium"},
    # Domain-specific, realistic, ground-truth verifiable
]
# Rule: every seed must have a verifiable outcome
# anti-pattern: "Find the answer to this question" (unverifiable)
```

**Failure mode:** Seeds over-represent easy cases → model learns the distribution of your examples, not the task.
**Mitigation:** Score seed diversity across instruction type, environment state, and difficulty. Aim for entropy across all three dimensions.

### Stage 2: Synthetic Expansion

Expand seeds using frontier models via Self-Instruct or Evol-Instruct patterns. Generate 20–100 synthetic variants per seed.

```python
def expand_seed(seed, target_count=50, teacher_model="claude-opus-4-7"):
    """Evol-Instruct style: generate variants across difficulty + style + domain"""
    variants = []
    for i in range(target_count):
        # Rewrite instruction: vary formality, length, framing, edge cases
        expanded = teacher_model.complete(
            f"Generate a distinct variant of: {seed['instruction']}\n"
            f"Constraints: vary difficulty level, rephrase naturally."
        )
        variants.append({"instruction": expanded, "reference": seed})
    return variants
```

**Failure mode:** Model collapse (，反复训练导致母分布漂移). After 2–3 generations, outputs start resembling the model's own distribution rather than the real domain.
**Mitigation:** Limit expansion depth to 1–2 generations from seeds. Use a different teacher model than the one used for rollout.

### Stage 3: Trajectory Generation and Quality Gates

Generate full agent trajectories by running expanded instructions through a teacher agent in the target environment. Each trajectory is a (instruction, tool_call_sequence, outcome) triplet.

```python
def generate_trajectory(instruction, environment, agent):
    """Roll out instruction through agent in sandboxed environment"""
    trace = []
    state = environment.reset()
    step = 0
    max_steps = 20

    while step < max_steps:
        action = agent.decide(state, instruction)
        result = environment.step(action)
        trace.append({"state": state, "action": action, "result": result})
        state = result["new_state"]
        if result["done"]:
            break
        step += 1

    outcome = environment.evaluate(state)  # ground-truth check
    return {"instruction": instruction, "trace": trace, "outcome": outcome}
```

**Gate 1 — Format gate:** Trajectory produces valid tool calls, no JSON truncation, no malformed output.
**Gate 2 — Outcome gate:** The agent's final state passes the ground-truth evaluator for the environment. Reject failures from the training set (you want correct trajectories).
**Gate 3 — Diversity gate:** Tool-call sequence differs from existing trajectories by >30% (Jaccard distance). Prevents mode collapse into a single "optimal" path.
**Gate 4 — Faithfulness gate:** Claude-as-judge checks whether the reasoning chain actually explains the tool calls. Filter trajectories where the LLM's explanation contradicts the action taken.

### Stage 4: Preference Pair Generation

For DPO/PPO training, generate (chosen, rejected) pairs from trajectories that share an instruction but diverge in outcome or efficiency.

```python
def make_preference_pairs(trajectories):
    """Group by instruction, rank by outcome score + token efficiency"""
    from collections import defaultdict
    groups = defaultdict(list)
    for traj in trajectories:
        groups[traj["instruction"]].append(traj)

    pairs = []
    for instr, trajs in groups.items():
        if len(trajs) < 2:
            continue
        # Rank: higher outcome score = chosen; lower = rejected
        ranked = sorted(trajs, key=lambda t: (t["outcome"], -len(t["trace"])))
        pairs.append({
            "instruction": instr,
            "chosen": ranked[-1],    # best outcome + shortest path
            "rejected": ranked[-2]     # second-best (don't use failures as rejects)
        })
    return pairs
```

**Failure mode:** Using failed trajectories as "rejected" examples teaches the agent to avoid mistakes without teaching it the correct alternative.
**Mitigation:** Only use trajectories that reach a correct outcome as "chosen." Use slower/costlier correct trajectories as "rejected." This teaches efficiency, not just correctness.

### Stage 5: Training + Production Feedback Loop

Fine-tune with LoRA/QLoRA on a single 80GB GPU in days. Then deploy and monitor for failures.

```python
# NVIDIA blueprint (per arXiv 2026): three-component closed loop
# 1. NeMo Aligner for DPO training
# 2. TensorRT-LLM for inference
# 3. NIM microservices for serving

from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="llama-4-8b",
    max_seq_length=4096,
    load_in_4bit=True,  # QLoRA on a single GPU
)
model = FastLanguageModel.get_peft_model(
    model, r=16, lora_alpha=32,
    target_modules=["q_proj", "v_proj", "k_proj", "o_proj"]
)
# Train on filtered synthetic pairs
```

**The critical loop:** Monitor production failures and inject them back as new seeds. Production edge cases become the seeds for the next pipeline run. Without this, the agent's training distribution drifts from reality.

## Receipt

> Verified 2026-07-21 — Key metrics sourced from AgentMarketCap (April 2026): 70–80% synthetic / 20–30% human ratio is the operational sweet spot; 4× cost reduction via AI-assisted annotation; 0.03% hallucination rate with 30K examples + LoRA. NVIDIA pattern confirmed via NVIDIA January 2026 release showing single 80GB GPU fine-tuning in days. Quality gate architecture is the product-engineering consensus across Scale AI, NVIDIA NeMo, and open-source agent labs (AgentMarketCap, Future AGI blog, arXiv trajectory synthesis literature).

## See also

- [R-12 · Agent-RLVR](r12-agent-rlvr-training-loop.md) — RL training with verifiable rewards (the training loop inside the pipeline)
- [R-13 · Agent Trajectory Synthesis](r13-agent-trajectory-synthesis.md) — trajectory generation methods (the generator stage of this pipeline)
- [S-1004 · Agent Eval Stack](s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — production evaluation gates (the monitoring half of the feedback loop)
- [S-1036 · Trajectory Quality Index](s1036-the-trajectory-quality-index-when-your-agent-passes-but-the-path-is-broken.md) — measuring trajectory quality (the scoring logic for preference pairs)
