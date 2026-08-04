# S-2149 · The Agentic Synthetic Data Generation Stack: When Your Training Pipeline Has a Data Scientist Inside

Your model needs domain-specific training data. Manual annotation is slow and expensive. Public datasets exist but don't match your distribution. You could hire labelers, but they lack the expertise to generate the edge cases that actually break your model. Meanwhile, the frontier has moved: the same LLM infrastructure that powers agents can now generate, evaluate, and refine its own training data — with a data scientist agent in the loop.

## Forces

- **Annotation bottleneck kills iteration speed.** Human annotation pipelines have fixed throughput. Every model change that requires new data waits weeks for labels, decoupling model development from data development.

- **Distribution mismatch kills generalization.** Public synthetic datasets look correct but fail to capture the distributional quirks of your domain — legal contracts in your jurisdiction, support tickets in your product's voice, code in your company's style.

- **Single-pass generation has predictable failure modes.** Naive synthetic data (generate → use → train) reproduces the teacher's biases and misses the hardest cases. Without an evaluation loop, synthetic data amplifies model weaknesses rather than fixing them.

- **Quality measurement is harder than generation.** Generating data is cheap. Knowing whether it actually improves your model is expensive — requires trained-vs-untreated eval, distribution comparison, downstream task measurement.

## The move

The pattern: an **autonomous data scientist agent** in a tight generate → evaluate → refine loop, iteratively improving a data-generation recipe until the resulting synthetic dataset passes quality gates.

**Step 1 — Ground in source documents.**
Give the agent your ground truth: domain documents, legal texts, codebases, customer conversations, API schemas. This is the factual foundation. The agent must not invent distribution — it must extract and extend it.

**Step 2 — Define the data schema and difficulty distribution.**
The agent specifies the target data shape: fields, types, constraints, and crucially — a **difficulty distribution** (what fraction should be easy vs. hard vs. adversarial). Without explicit difficulty targeting, synthetic data concentrates on the median case.

**Step 3 — Generate with controlled variance.**
Generate N examples using the recipe. Apply controlled perturbations: paraphrase diversity, adversarial transformations, edge-case injection. Track generation parameters — temperature, sampling strategy, constraint strictness — as explicit variables, not defaults.

**Step 4 — Evaluate quality with an independent judge.**
Run the generated data through a quality assessment pipeline:
- **Format compliance**: Does it match the schema?
- **Distribution fidelity**: Does it match the source distribution (embedding-space proximity, statistical tests)?
- **Difficulty calibration**: Are hard examples actually harder (measured by a separate model's error rate)?
- **Novelty**: Does it contain cases absent from the training set?

**Step 5 — Refine the recipe.**
Based on eval output, the agent adjusts: generation prompts, constraint parameters, perturbation strategies. This is the meta-learning loop — the agent learns *how to generate* data that trains better models.

**Step 6 — Iterate until quality gates pass.**
Loop steps 3-5 until the dataset passes all quality gates or a max-iteration cap is hit. Cap prevents infinite loops on genuinely hard distributions.

```python
# Minimal agentic SDG loop
from anthropic import Anthropic
import json

client = Anthropic()

def generate_batch(recipe: dict, n: int) -> list[dict]:
    """Agent generates N examples from recipe."""
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{
            "role": "user",
            "content": f"""Generate {n} examples following this recipe:
{json.dumps(recipe, indent=2)}

Return a JSON array of examples."""
        }]
    )
    return json.loads(response.content[0].text)

def evaluate_batch(examples: list[dict], ground_truth: list[dict]) -> dict:
    """LLM-as-judge evaluates quality across four dimensions."""
    prompt = f"""Evaluate this synthetic dataset against ground truth.
Rate 0-10 on: format compliance, distribution fidelity,
difficulty calibration, novelty vs training set.

Dataset: {json.dumps(examples[:5])}
Ground truth sample: {json.dumps(ground_truth[:5])}"""
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    # Parse scores and return aggregated eval result
    return {"scores": response.content[0].text}

def refine_recipe(recipe: dict, eval_result: dict) -> dict:
    """Agent adjusts recipe based on eval failures."""
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""The current recipe produced this eval result:
{json.dumps(eval_result)}

Current recipe: {json.dumps(recipe)}

Suggest a refined recipe that addresses the failure modes.
Return the updated recipe as JSON."""
        }]
    )
    return json.loads(response.content[0].text)

def agentic_sdg(
    seed_documents: list[str],
    target_count: int = 5000,
    quality_threshold: float = 8.0,
    max_iterations: int = 20
) -> list[dict]:
    # Step 1: Ground recipe in source documents
    recipe = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": f"""Analyze these documents and create a data generation recipe.
Schema, constraints, difficulty distribution, edge cases to cover.
Documents (truncated): {seed_documents[:3]}"""
        }]
    )
    recipe = json.loads(response.content[0].text)

    dataset = []
    for iteration in range(max_iterations):
        examples = generate_batch(recipe, n=500)
        eval_result = evaluate_batch(examples, seed_documents)
        score = eval_result["overall_score"]

        if score >= quality_threshold:
            dataset.extend(examples)
            if len(dataset) >= target_count:
                break

        recipe = refine_recipe(recipe, eval_result)

    return dataset
```

## Key design decisions

- **Recipe versioning**: Every recipe version + resulting dataset gets a version tag. Dataset provenance matters for debugging trained model behavior.
- **Difficulty targeting**: Explicitly allocate 60% standard / 30% challenging / 10% adversarial cases. Without this, generated data clusters at median difficulty.
- **Ground truth anchoring**: The agent must reference source documents in every generation call. Pure-freeform generation drifts from your distribution.
- **Iteration cap**: Set a hard stop (default: 20). If quality gates don't pass, surface the failure — some distributions genuinely need human annotation.
- **Eval independence**: The judge model should differ from the generator model. Same-model self-evaluation is systematically optimistic.

## Receipt

> Receipt pending — 2026-08-04

## See also

- [S-02 · Context Budget](stacks/s02-context-budget.md) — Recipe grounding and context management are siblings: both fight information loss
- [S-2005 · The Production Eval Harness Stack](stacks/s2005-the-production-eval-harness-stack-when-benchmarks-lie-and-users-complain.md) — Eval harness and SDG eval are the same infrastructure
- [S-1890 · The Difficulty-Aware Escalation Stack](stacks/s1890-the-difficulty-aware-escalation-stack-when-static-tiers-hit-their-ceiling.md) — Difficulty targeting applies to data generation as much as to model routing
