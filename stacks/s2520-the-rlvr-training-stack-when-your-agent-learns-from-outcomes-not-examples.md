# S-2520 · The RLVR Training Stack — When Your Agent Learns From Outcomes, Not Examples

You prompt-engineered your agent to perfection. It works. Then a harder task arrives and it fails — not because the model is bad, but because SFT (imitation learning) only teaches the agent to *say* what good outputs look like. It doesn't teach the agent to *discover* good outputs it has never seen. Your agent can recite the pattern; it can't find the pattern. The fix is RLVR: Reinforcement Learning with Verifiable Rewards — the training paradigm that turned DeepSeek-R1-Zero from a base model into a world-class reasoner with zero human examples, and that is now the production standard for building agents that actually solve tasks rather than reproduce them.

## Forces

- **SFT teaches imitation, not competence.** Supervised fine-tuning on (task → answer) pairs teaches the model to reproduce human-written trajectories. The agent learns to say what good outputs look like in the training set. Novel inputs — anything outside the imitation distribution — get handled by whatever the base model does, which is often wrong. SFT raises the floor without raising the ceiling.
- **RLVR is agentic by design.** Unlike general RLHF (which requires human preference labels — slow, expensive, non-scalable), RLVR uses deterministic environment feedback: did the code pass the test? Did the query return the right rows? Did the plan achieve the stated goal? This makes RLVR directly applicable to production agents operating in verifiable domains — code, data, math, planning, tool orchestration.
- **Reward design is the hard part.** The same model trained with the wrong reward function becomes an expert at the wrong task. Reward hacking — where the agent finds a loophole that technically satisfies the reward while failing the intent — is the dominant failure mode. Writing a reward function that doesn't have exploitable shortcuts is a genuine engineering discipline.
- **Process rewards beat outcome rewards for multi-step agents.** Binary pass/fail rewards on the final outcome tell the agent nothing about *which step* was wrong. Process reward models (PRMs) that score each step are dramatically more sample-efficient for long-horizon tasks, but require per-step labels or a structured environment that produces them.
- **GRPO is replacing PPO for LLM training.** PPO requires a separate reward model and the full KL penalty overhead. GRPO (Group Relative Policy Optimization) generates multiple rollouts per prompt, scores them against the verifier, and updates the policy directly — cutting memory requirements by ~50% and enabling 16-samples-per-prompt training that PPO cannot sustain. Every major agentic training pipeline in 2026 uses GRPO.

## The move

RLVR training has four components: **verifiable task generation** → **reward function design** → **training loop (GRPO)** → **reward hacking mitigation**.

### 1. Define the verifiable environment

The environment must produce a deterministic pass/fail signal. This is not a soft preference — it is ground truth.

```python
# Code agent: test suite as the verifier
def verify_code_agent(task_id: str, submitted_code: str) -> float:
    """Returns reward 1.0 if all tests pass, 0.0 otherwise."""
    try:
        exec_globals = {}
        exec(submitted_code, exec_globals)
        for test_fn, expected in test_suite[task_id]:
            result = test_fn(**exec_globals)
            if result != expected:
                return 0.0
        return 1.0
    except Exception:
        return 0.0

# Data agent: schema + query validation
def verify_sql_agent(task_id: str, submitted_query: str) -> float:
    """Returns 1.0 if query is syntactically valid, returns correct
    rows, and does not contain prohibited keywords."""
    try:
        result = execute_query(submitted_query, ground_truth_db)
        if result == ground_truth[task_id]:
            return 1.0
    except (SyntaxError, PermissionError):
        return 0.0
    return 0.0
```

### 2. Design the reward function

**Rule 1: Make it non-gaming.** For code: test suite must be hidden from the agent at generation time. For SQL: prohibit `DROP`, `DELETE`, `ALTER` unless the task explicitly allows mutation. For planning: define success criteria before generation.

**Rule 2: Add format rewards.** Binary outcome rewards are sparse. Add a format reward (0.1) for producing outputs in the expected structure (e.g., `<reasoning>` tags). This gives the model a learning signal even on failed tasks.

```python
def compute_reward(prompt: str, response: str, task_id: str) -> dict:
    outcome = verify_task(task_id, response)
    format_bonus = 0.1 if "<reasoning>" in response and "</reasoning>" in response else 0.0
    return {"outcome": outcome, "format": format_bonus, "total": outcome + format_bonus}
```

### 3. GRPO training loop

```python
from transformers import AutoModelForCausalLM, TrainingArguments
from grpo import GRPOTrainer

model = AutoModelForCausalLM.from_pretrained("your-base-agent-model")
trainer = GRPOTrainer(
    model=model,
    reward_funcs=[compute_reward],
    gamma=0.99,          # discount factor for multi-step tasks
    beta=0.001,          # KL penalty coefficient (keep policy near base)
    num_generations=16,  # samples per prompt — higher = better, slower
)

trainer.train()  # no reward model needed — direct verification signal
```

### 4. Monitor for reward hacking

Run a **probing set** alongside training: tasks where the "obvious" solution is wrong but the reward signal might reward the wrong behavior. If the agent's probing-set score exceeds its canonical-set score, audit the reward function.

```python
def detect_reward_hacking(agent_policy, probing_set, canonical_set):
    probing_score = evaluate(agent_policy, probing_set)
    canonical_score = evaluate(agent_policy, canonical_set)
    divergence = probing_score - canonical_score
    if divergence > 0.15:
        print(f"REWARD HACKING DETECTED: probing={probing_score:.3f}, "
              f"canonical={canonical_score:.3f}, divergence={divergence:.3f}")
    return divergence
```

## The critical production decisions

**Start with SFT warmup, then RLVR.** Pure RLVR from a base model converges slowly — the model needs enough policy quality to produce diverse, evaluable outputs. Start with 10-20% SFT (imitation on canonical trajectories), then switch to RLVR.

**Mix 30% real-world tasks.** Pure synthetic task generation narrows the distribution. Always mix in tasks from production failure logs, user escalations, and red-team probes.

**Track pass@k, not pass@1.** With 16 samples per prompt, track pass@8 (any of 8 succeed) as your primary metric. pass@1 rewards the model on a single roll-out — RLVR generates diversity, so measure it.

## See also
- [S-1028 · Synthetic Trajectory Degeneration](s1028-synthetic-trajectory-degeneration-when-recursive-fine-tuning-narrows-your-agent.md) — the failure mode when synthetic-only training collapses the agent's distribution
- [S-1004 · Agent Eval Stack](s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — production eval that feeds back into training signal
- [S-1715 · The Judge Stack](s1715-the-judge-stack-when-your-agent-grades-its-own-homework.md) — LLM-as-judge for cases where deterministic verification isn't available
