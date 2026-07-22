# S-1470 · The Environment-Free Traj Stack — When You Train an Agent Without a Single Real Environment

The traditional path to a better agent is: collect real trajectories, label them, fine-tune. The problem is that collecting real trajectories for API-calling agents requires fully implemented environments with executable backends and realistic pre-populated databases. You can't train a Slack agent without a Slack workspace. You can't train a CRM agent without a live Salesforce instance. The environment is the bottleneck — and building it costs more than the training itself.

Environment-free synthetic trajectory generation (ESAT) solves this by treating the LLM as a "digital world model." Given only API specifications — the names, parameters, return types, and descriptions — it generates complete, realistic interaction trajectories without ever touching a real system.

## Forces

- **Environment bootstrapping is the dominant cost in agent training pipelines.** Building a realistic sandbox with populated databases, error states, and edge-case responses for 50+ tools takes months and six-figure budgets. Teams either skip it (producing brittle agents) or delay it indefinitely.
- **Real trajectories are scarce, expensive, and can't be scaled on demand.** Human labelers can produce trajectories, but at $3–8 per trajectory for complex multi-tool tasks, cost scales linearly with quality. And you can't easily inject edge cases — rare failure modes, adversarial inputs, or novel tool combinations — into human-collected data.
- **LLMs already know how APIs behave.** A model that can call the GitHub API in production can also simulate what a GitHub API call would return, given the spec. The gap between simulation and reality is smaller than it seems — especially for well-documented, REST-style APIs.
- **Filtering is where the quality lives.** Raw synthetic output has a base quality rate of ~30–50%. The trajectory is only as good as the filtering layer that removes hallucinations, broken sequences, and implausible tool calls.

## The move

The full pipeline has four stages. Treat each as a distinct engineering component.

### Stage 1 — API Spec Injection

Feed the LLM generator the complete API specification: endpoint names, parameter types and constraints, return schemas, error codes, rate limits, and authentication requirements. This is the only ground truth. Everything else is simulation.

```python
# ESAT-style API spec injection
API_SPEC = {
    "github": {
        "base_url": "https://api.github.com",
        "endpoints": [
            {
                "name": "list_repos",
                "method": "GET",
                "path": "/user/repos",
                "params": {"type": "string", "sort": "string", "per_page": "int"},
                "returns": {"type": "array", "item": {"id": "int", "full_name": "str", "private": "bool"}},
            },
            # ... 50 more endpoints
        ],
    }
}

GENERATOR_PROMPT = f"""
You are simulating a realistic user session with the following API.
Generate complete trajectories: user request → tool call → API response → next call → ...
Only use responses consistent with the spec. Inject realistic errors (401, 403, 429).
"""
```

### Stage 2 — Trajectory Synthesis

Generate diverse, multi-turn trajectories at scale. Key techniques:

- **Seed expansion**: Start with a small set of human-authored "seed trajectories" that define the task types and conversation styles, then use the LLM to generate variants.
- **Tool mixing**: Interleave calls across multiple APIs to produce cross-domain trajectories (e.g., "create a GitHub issue and notify the Slack channel").
- **Irrelevant-tool mixing**: Include deliberate diversions — the agent calls a tool that looks relevant but isn't — to train rejection of plausible-but-wrong paths.
- **F1-style trajectory reward**: Score not just task completion but interaction efficiency. Penalize redundant calls, infinite loops, and over-fetching.

```python
# Trajectory generation with quality filtering
def generate_batch(specs: dict[str, API_Spec], count: int = 1000) -> list[Trajectory]:
    trajectories = []
    for _ in range(count):
        seed = random.choice(SEED_TRAJECTORIES)
        traj = llm.generate(
            GENERATOR_PROMPT,
            context={"specs": specs, "seed": seed, "mix_tools": True}
        )
        if quality_filter(traj):       # reject hallucinated API fields
            trajectories.append(traj)
    return trajectories

def quality_filter(traj: Trajectory) -> bool:
    # Rule 1: No tool calls with fields not in the spec
    for call in traj.tool_calls:
        if not spec.validate_call(call):
            return False
    # Rule 2: Reject trajectories where the agent calls
    #   an irrelevant tool and never recovers
    if traj.uses_irrelevant_tool and not traj.recovers:
        return False
    # Rule 3: Diversity gate — reject if too similar to
    #   an existing trajectory (cosine similarity > 0.85 on embeddings)
    return semantic_dedup(traj, existing_trajectories)
```

### Stage 3 — Two-Stage Training

Apply supervised fine-tuning first, then reinforcement learning over synthesized environments:

1. **SFT (Supervised Fine-Tuning)**: Train on filtered trajectories to learn tool-use mechanics and multi-turn sequencing.
2. **Multi-turn RL**: Run the agent through dynamically synthesized environments with online reward signals. Use trajectory-level rewards (F1: did the task complete AND was it efficient?).

```python
# Two-stage training loop
from unsloth import FastLanguageModel

# Stage 1: SFT on synthetic trajectories
model, tokenizer = FastLanguageModel.from_pretrained("Qwen/Qwen2.5-7B")
model = FastLanguageModel.get_peft_model(model, r=16)

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=synthetic_trajectories,  # quality-filtered ESAT output
    dataset_text_field="trajectory",
    max_seq_length=4096,
)
trainer.train()

# Stage 2: Online RL over synthetic environments
from trl import PPOTrainer
for round in range(RL_ROUNDS):
    envs = synthesize_environments(specs, diversity=True)
    for env in envs:
        response = model.generate(env.prompt)
        reward = compute_trajectory_reward(response, env.ground_truth)
        ppo_trainer.step([env.prompt], [response], [reward])
```

### Stage 4 — Distribution Matching

Validate that synthetic trajectories match the target distribution (real-world API call patterns, error frequencies, tool usage distributions). Use KL divergence between synthetic and a small held-out real sample as a quality gate. If KL divergence is too high, regenerate with revised prompts or adjusted temperature.

## When to use this

Use ESAT when:
- You're building an agent for APIs that don't exist yet (pre-launch integrations, partner systems)
- You need thousands of edge-case trajectories you can't collect from real users
- Your sandbox environment would take >4 weeks to build
- You need to fine-tune a small model (7B–13B) on specialized agent behaviors
- You want to compress a frontier model's trajectory patterns into a cheaper student

Don't use it when:
- Your API has complex side effects that can't be simulated (e.g., real-time state changes, third-party webhooks)
- You have abundant real trajectories and the marginal cost of simulation exceeds the marginal gain
- Your task is purely conversational (no tool use) — standard SFT applies

## Receipt

> Verified 2026-07-22 — ESAT paper (alphaXiv:2607.16900, July 18, 2026) by Lee et al. reports up to 60.5% performance gains on API-calling benchmarks using environment-free synthetic trajectories vs. zero real environment data. NVIDIA (January 2026) demonstrated single 80GB GPU agent training in days via synthetic data pipelines. AgentMarketCap (April 2026) confirmed synthetic data as the "default substrate for agent RL training" across enterprise teams.

## See also

- [S-1296 · The Synthetic Training Data Stack](s1296-the-synthetic-training-data-stack-agent-fine-tuning-via-programmatic-trajectory-generation.md) — broader coverage of synthetic data for agent training; this entry is the environment-free variant
- [S-1312 · The Frontier Compression Stack](s1312-the-frontier-compression-stack-agent-distillation-from-teacher-traces-to-specialized-student-models.md) — agent distillation from teacher traces; ESAT pairs well as the trajectory source for student model training
- [S-943 · The Semantic Cache Stack](s1266-the-semantic-cache-blind-spot-when-identical-queries-return-different-answers.md) — semantic caching; the trajectory quality-filtering step in ESAT uses similar semantic dedup techniques
