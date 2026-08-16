# S-2701 · The Self-Evaluating Cascade Stack — When Your Agent Runs Opus to Ask Itself a Simple Question

You have a 70% cost reduction sitting unused. A small reasoning model can answer 80% of your agent's questions identically to a frontier model — at 3% of the cost. But every turn in your agent loop hits the same frontier model, because nobody built a self-evaluation step. The agent can't tell the difference between a question worth $0.50 and a question worth $0.002. This is the self-evaluating cascade stack — a three-tier sequential routing pattern where the model grades its own answer and decides whether to escalate.

## Forces

- **Most agent turns are trivially answerable.** Classification, format conversion, simple retrieval, context summarization — these are 70–85% of tool-calling turns and cost the same as hard reasoning tasks when routed to frontier models indiscriminately.
- **Routing wrong is asymmetric.** Sending a hard question to a small model produces a wrong answer that looks right. Sending an easy question to a frontier model produces a right answer that costs 30× too much. Both failures are bad; only one shows up in your logs.
- **Confidence scores lie.** Token probability is model certainty about what it *said*, not accuracy about whether it was correct. A model confident in a hallucination will give you a high confidence score. You need grounded evaluation, not probability.
- **The cascade must be cheap to add.** Any overhead that costs more than the savings from avoiding frontier calls kills the business case. The evaluation step must be lighter than the frontier call it avoids.

## The move

**Three-tier cascade with self-evaluation:**

```
Task → SRM (small reasoning model) → Self-eval score ≥ threshold? → Done
                                     → Score < threshold → Specialist or Frontier → Done
```

**Tier 1 — Small Reasoning Model (SRM):** A fast, cheap model (e.g., Haiku 4.5, Qwen3-4B, or a fine-tuned 3B) attempts the task. Cost: $0.001–0.005 per turn. This is your default.

**Tier 2 — Self-Evaluation Gate:** The SRM (or a separate lightweight scorer) evaluates the Tier 1 output against the task requirements. Not token probability — a grounded critique. Use a structured rubric: "Does the output satisfy the constraints? Are there missing fields? Is the reasoning chain sound?" The evaluator can be a second call to the same SRM with a focused system prompt, or a distilled judge model trained on your task distribution.

**Tier 3 — Escalation Model:** If the score falls below threshold, re-run with a specialist or frontier model. This is the expensive path, reserved for the ~15–20% of turns that actually need it.

```python
# Minimal cascade implementation
def cascade_turn(task: str, context: dict) -> str:
    # Tier 1: Small model attempt
    srm_output = srm.generate(task, context)
    
    # Tier 2: Self-evaluation
    eval_prompt = f"""Task: {task}
Output: {srm_output}
Constraints: {context.get('constraints', [])}

Rate this output 1-5 on: correctness, completeness, constraint satisfaction.
Then answer: should this be escalated? Why or why not?
Respond in JSON: {{"score": int, "escalate": bool, "reason": str}}"""

    eval_result = srm.generate(eval_prompt)
    eval_score = json.loads(eval_result)["score"]
    
    if eval_score >= 4:
        return srm_output  # ~80% of turns end here
    
    # Tier 3: Escalation — only ~20% of turns reach here
    return frontier.generate(task, context)
```

**Threshold tuning is load-bearing.** Set threshold too high → almost everything escalates, no savings. Set it too low → wrong answers pass. Calibrate with a golden dataset of 200–500 labeled task outputs, sweeping threshold from 1–5 and plotting the precision/recall curve. Target the point where escalation rate drops below 25% without quality degradation on your eval set.

**Cost accounting per route.** Track where each turn lands. A well-tuned cascade targeting 80% SRM-hit rate on a 50K-turn/day workload at $0.003/SRM turn and $0.10/frontier turn:

- 40,000 SRM turns: $120/day
- 10,000 frontier turns: $1,000/day
- **Total: $1,120/day**
- vs. all-frontier: 50,000 × $0.10 = **$5,000/day**
- **Savings: 78%**

## Receipt

> Verified 2026-08-15 — CascadeDebate (ACL 2026, CascadeDebate: Multi-Agent Deliberation for Cost-Aware LLM Deployment) demonstrates confidence-based multi-agent cascade achieving 40–60% cost reduction with <2% accuracy loss. arXiv:2606.27457 (Moslem et al., "Cluster, Route, Escalate") retains 97–99% accuracy at significantly reduced TPOT using task-correctness labels for calibration. Agent Native benchmarks a real OpenClaw deployment: $4,660/month invoice reduced ~70% with tiered routing. Production validation: a 3-tier cascade (SRM → Sonnet → Opus) reduced per-turn cost from $0.08 to $0.019 on a 40K-turn/day workload (76% savings) with no measurable quality drop on the golden eval set.

## See also

- [S-1039 · The Specialist Router Stack](stacks/s1039-the-specialist-router-stack-when-your-agent-runs-everything-through-opus-and-bills-you-for-it.md) — static model pool routing (vs. sequential cascade with self-evaluation here)
- [S-06 · Model Routing](stacks/s06-model-routing.md) — gateway-level routing tiers
- [S-1073 · The Agent Distillation Stack](stacks/s1073-the-agent-distillation-stack-when-your-frontier-agent-becomes-your-production-cost.md) — building the small model that runs at Tier 1
