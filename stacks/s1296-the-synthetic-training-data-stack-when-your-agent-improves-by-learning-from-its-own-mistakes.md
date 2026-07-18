# S-1296 · The Synthetic Training Data Stack — When Your Agent Improves by Learning from Its Own Mistakes

Your agent succeeds 73% of the time on Tier-1 tasks. You need 90%. You have 800 real interactions in production logs. Privacy teams blocked you from using them. A labeled dataset for fine-tuning would cost $40K and take six weeks. Synthetic data generation closes the gap: generate agent training trajectories programmatically, from seed examples, from model outputs, or from traces — with full control over distribution, failure modes, and edge cases.

## Forces

- **Real data is scarce, expensive, and legally constrained.** Production logs are narrow (users cluster on common tasks), noisy (typos, mid-task abandonments), and legally risky (PII, proprietary workflows). A customer-support agent that handles 10,000 tickets will have 9,200 that look identical and 800 that are genuinely different. Training on the 9,200 produces a mediocre model. Training on the 800 produces an overfit one.
- **Synthetic data is cheap but dangerous.** Generate 50,000 trajectories in an afternoon — but if the generation process embeds the same biases as your base model, you get recursive narrowing (S-1028). Quality control on synthetic data is the actual work.
- **Agent training data is not just text.** A single agent trajectory includes tool calls, function arguments, execution outcomes, retry paths, failure modes, and state transitions. Naive text-to-text synthetic data misses all of this. You need structured trajectory synthesis.
- **Distribution shift between training and deployment kills agents.** The synthetic distribution must match the production distribution in the right ways: same task types, same tool surfaces, same failure modes — not the same exact prompts.

## The move

The production pattern for agent synthetic data generation has three layers:

### 1. Seed the distribution

Start with real-but-sanitized seeds. 50–200 hand-crafted examples that cover the task taxonomy: happy paths, edge cases, failure recovery, multi-step chains. For a code review agent, seed 10 file-change scenarios with 5 complexity levels each.

```python
# Seed generation: hand-crafted trajectories with known correct outcomes
SEED_TRAJECTORIES = [
    {
        "task": "Review pr/1234: add rate limiting middleware",
        "steps": [
            {"tool": "read_file", "args": {"path": "src/middleware/rate_limit.py"}},
            {"tool": "read_file", "args": {"path": "src/routes/api.py"}},
            {"tool": "search_code", "args": {"pattern": "rate_limit", "scope": "src/"}},
            {"verdict": "MISSING", "reason": "rate_limit middleware exists but not applied to /api/v2/orders"},
        ]
    },
    # ... 49 more
]

# Use seeds to bootstrap generation diversity
# Perturb: change file names, change frameworks, change bug types
```

### 2. Expand with LLM-augmented generation

Apply structured expansion to seeds using a frontier model (GPT-5, Claude 4.7 class):

```python
def expand_seed(seed: dict, n_variants: int = 10) -> list[dict]:
    """Generate N semantically diverse variants of one seed trajectory."""
    prompt = f"""
You are generating synthetic training data for an AI code review agent.
Generate {n_variants} variants of this seed trajectory.

Seed:
{safe_json_dump(seed)}

Rules:
- Keep the same task type (e.g., "missing error handling") but vary:
  - File names and project structure
  - Programming language (Python → Go → TypeScript)
  - Bug severity and location
  - Whether the agent should catch it (true positive) or miss it (false negative)
- Vary the tool call sequences: some shorter, some longer with detours
- Include 20% failure-mode trajectories where the agent takes a wrong action

Output: JSON list of {n_variants} trajectory dicts, each with:
  - task, steps[], verdict, ground_truth, metadata[variant_id]
"""
    response = llm.generate(prompt, schema=TrajectoryList)
    return response.trajectories
```

### 3. Filter with a quality gate

Run the generated trajectories through a quality filter before using them for fine-tuning:

```python
def quality_gate(trajectory: dict) -> bool:
    """
    Multi-stage filter: format → diversity → ground truth → plausibility.
    Returns True only if trajectory passes all stages.
    """
    # Stage 1: Format — does the trajectory have the right structure?
    if not trajectory.get("steps") or not trajectory.get("verdict"):
        return False

    # Stage 2: Diversity — is this different enough from existing trajectories?
    embedding = embed(trajectory["task"])
    if any(cosine_sim(embedding, e) > 0.92 for e in seen_embeddings):
        return False  # too similar to existing data

    # Stage 3: Ground truth — does the verdict match the evidence?
    if trajectory["verdict"] == "MISSING":
        # Verify the "missing" thing actually isn't in the steps
        tool_results = [s.get("result", "") for s in trajectory["steps"]]
        if any(trajectory.get("ground_truth", "") in str(r) for r in tool_results):
            return False  # ground truth contradicts the verdict

    # Stage 4: Plausibility — would this scenario actually happen?
    plausibility_score = judge_plausibility(trajectory)
    return plausibility_score >= 0.75

def judge_plausibility(trajectory: dict) -> float:
    """Use a separate judge model to score trajectory realism."""
    prompt = f"""
Score this synthetic agent trajectory for realism: 0.0 to 1.0.

Trajectory: {safe_json_dump(trajectory)}

Consider: Would a real developer actually encounter this scenario?
Would the described tool calls actually be the right ones?
Is the verdict (MISSING/FALSE_POSITIVE/CORRECT) well-supported?

Respond with a single float.
"""
    return float(llm.generate(prompt, schema=PlausibilityScore))
```

### 4. Build the DPO preference pair dataset

For RLHF-style fine-tuning, generate preference pairs from trajectories:

```python
def build_preference_pairs(seed: dict) -> list[PreferencePair]:
    """
    Generate chosen/rejected pairs where:
    - Chosen: agent takes the correct action
    - Rejected: agent takes the wrong action on the same scenario
    """
    # Generate a correct trajectory
    correct = expand_correct(seed)
    # Generate a wrong trajectory by injecting a mistake
    wrong = expand_with_mistake(seed, mistake_type="tool_misuse")

    return {
        "chosen": correct.to_messages(),
        "rejected": wrong.to_messages(),
        "preferred_outcome": correct.verdict == "CORRECT"
    }
```

## Receipt

> Verified 2026-07-18 — Approach validated against Coasty AI blog (Jul 2026, "Synthetic Data for Fine Tuning LLM Agents"), Future AGI documentation (2026), and NVIDIA 2026 synthetic RL loop guidance. Seed→expand→filter→preference-pair pipeline is the documented production pattern. Quality gate (4-stage filter) aligns with Future AGI's "evaluate before fine-tuning" guidance. Specific code is illustrative of the pattern; adapt to your framework (Distilabel, Outlines, or custom LLM pipeline).

## See also

- [S-1028 · Synthetic Trajectory Degeneration](s1028-synthetic-trajectory-degeneration-when-recursive-fine-tuning-narrows-your-agent.md) — the failure mode when synthetic data cycles narrow your agent
- [S-1001 · The Evaluation Gap](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — eval harnesses for verifying synthetic data quality
- [S-989 · The Tool Surface](s989-the-tool-surface-stack-when-your-agent-has-50-tools-and-picks-the-wrong-one.md) — tool calling taxonomy needed for trajectory structure
