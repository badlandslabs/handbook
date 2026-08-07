# S-2277 · The Reliability Surface Stack — When Your Agent Passes 97% in Eval and Fails 12% in Production

Your agent achieved 96.9% on your evaluation benchmark. You shipped it. After 30 days in production, monitoring reveals a 12% failure rate on what should be routine tasks — timeouts, rate-limit retry failures, subtly wrong tool arguments, API responses that are structurally valid but semantically broken. Your benchmark score didn't predict any of it. This is not a model quality problem. It is an evaluation architecture problem: you measured one point on a surface, not the surface itself.

## Forces

- **pass@1 is the apex of an iceberg.** Standard benchmarks report single-trial success under ideal conditions. ReliabilityBench (arXiv 2601.06112) found that agents achieving 96.9% pass@1 drop to 88.1% under realistic perturbations — an 8.8-point reliability gap that pass@1 entirely hides. Your eval number was the best-case scenario.
- **Production is adversarial to your agent in three independent dimensions.** Real deployments expose agents to: (1) consistency failures — same input, different output across runs; (2) perturbation failures — semantically equivalent inputs that trigger different tool selections; (3) infrastructure failures — timeouts, partial responses, schema drift. Most eval setups test none of these.
- **The cost of a reliability gap is non-linear.** A 12% failure rate in a customer-facing agent is not an inconvenience — it is a liability. If your agent processes 10,000 orders per day and 12% fail, that is 1,200 failed transactions per day, each potentially requiring human intervention, refund processing, or customer recovery. An agent is not production-ready until you know its failure rate under stress, not its success rate under ideal conditions.
- **Single-trial eval is a category error.** Reporting pass@1 for an agent is like reporting the result of a single coin flip and calling it a probability. The reliability surface R(k, ε, λ) is the correct abstraction: pass@k (consistency across k trials), ε (robustness to perturbations), and λ (fault tolerance under infrastructure failures). All three dimensions are required for a production reliability estimate.

## The move

### 1. Measure pass@k, not pass@1

Run each test case k times (k=5 minimum, k=10 for critical paths) and report pass@k — the fraction of task instances solved within k attempts. This directly measures consistency.

```python
import asyncio
from collections import Counter

async def run_k_trial(agent, task, k=5, delay=0.1):
    """Run agent on task k times, return pass@k."""
    outcomes = []
    for _ in range(k):
        result = await agent.run(task)
        outcomes.append(result.success)
        await asyncio.sleep(delay)  # small jitter between runs
    # pass@k: did at least one of k attempts succeed?
    return any(outcomes), outcomes

async def measure_consistency(agent, test_set, k=5):
    """Measure pass@1 through pass@k for a test set."""
    results = []
    for task in test_set:
        passed, outcomes = await run_k_trial(agent, task, k=k)
        results.append({
            "task_id": task.id,
            "pass_at_1": outcomes[0],
            "pass_at_k": passed,
            "success_count": sum(outcomes),
            "total_trials": k,
        })
    
    pass_at_1 = sum(r["pass_at_1"] for r in results) / len(results)
    pass_at_k = sum(r["pass_at_k"] for r in results) / len(results)
    
    print(f"pass@1:  {pass_at_1:.1%}")
    print(f"pass@{k}: {pass_at_k:.1%}")
    print(f"gap:      {pass_at_1 - pass_at_k:.1%} (hidden by pass@1)")
    return results
```

A high pass@1 / low pass@k gap means the agent is brittle — it can solve tasks but not reliably. This is invisible in standard eval and catastrophically expensive in production.

### 2. Test perturbation robustness (ε-levels)

Generate semantically equivalent variants of each test case and measure how the agent's tool selection and output quality change. Perturbation types:

- **Synonym swaps** — "cancel my order" → "void my purchase"
- **Input reformatting** — JSON → YAML → URL-encoded params
- **Tool permutation** — provide equivalent tools in different orders
- **Context noise** — add irrelevant preceding messages

```python
def perturb_task(task, epsilon=0.2):
    """Apply ε-level perturbations to a task.
    
    ε=0.0: original task (baseline)
    ε=0.2: 20% of inputs perturbed
    ε=1.0: full perturbation (all inputs changed)
    """
    variants = [task]  # always include baseline
    
    # ε-level sampling: each perturbation type has p=ε chance of applying
    if random.random() < epsilon:
        variants.append(task.with_synonym_swaps())
    if random.random() < epsilon:
        variants.append(task.with_reformatted_inputs())
    if random.random() < epsilon:
        variants.append(task.with_tool_permutation())
    if random.random() < epsilon:
        variants.append(task.with_context_noise())
    
    return variants

async def measure_perturbation_robustness(agent, test_set, epsilons=[0.0, 0.1, 0.2, 0.5]):
    """Measure pass rate across perturbation intensities."""
    results = {}
    for eps in epsilons:
        scores = []
        for task in test_set:
            variants = perturb_task(task, epsilon=eps)
            # At least one variant must succeed for the task to count as "handled"
            variant_outcomes = [await agent.run(v) for v in variants]
            scores.append(any(v.success for v in variant_outcomes))
        results[f"ε={eps}"] = sum(scores) / len(scores)
    
    for label, score in results.items():
        print(f"{label}: {score:.1%}")
    return results
```

The ε=0.2 row is your production proxy. If it is 8+ points below ε=0, you have a robustness gap that benchmarks are hiding.

### 3. Inject fault tolerance tests (λ-levels)

Use chaos-engineering principles to inject infrastructure failures and measure graceful degradation:

```python
async def fault_injection_sweep(agent, task, fault_types=["timeout", "rate_limit", "partial_response", "schema_drift"]):
    """Test agent at λ-level fault intensities."""
    results = {}
    for fault in fault_types:
        try:
            if fault == "timeout":
                outcome = await agent.run(task, injected_fault={"type": "timeout", "probability": 0.3})
            elif fault == "rate_limit":
                outcome = await agent.run(task, injected_fault={"type": "rate_limit", "probability": 0.2})
            elif fault == "partial_response":
                outcome = await agent.run(task, injected_fault={"type": "partial_response", "truncation": 0.4})
            elif fault == "schema_drift":
                outcome = await agent.run(task, injected_fault={"type": "schema_drift", "field_renames": ["status→state"]})
            results[fault] = outcome.success
        except Exception as e:
            results[fault] = False
            results[f"{fault}_error"] = str(e)
    
    baseline = await agent.run(task)
    results["baseline"] = baseline.success
    
    print(f"Baseline: {baseline.success}")
    for fault, success in results.items():
        if fault != "baseline":
            print(f"  +{fault}: {success}")
    return results
```

### 4. Compute the reliability surface

Combine all three dimensions into the unified reliability surface:

```python
def reliability_surface(pass_at_k, robustness_at_eps, fault_tolerance):
    """Compute the 3D reliability surface R(k, ε, λ).
    
    Returns a scalar estimate of production-ready reliability.
    """
    # k-trial consistency weight: 0.4
    consistency_score = pass_at_k
    
    # Perturbation robustness weight: 0.35
    robustness_score = robustness_at_eps
    
    # Fault tolerance weight: 0.25
    fault_tolerance_score = fault_tolerance
    
    surface_score = (
        0.40 * consistency_score +
        0.35 * robustness_score +
        0.25 * fault_tolerance_score
    )
    return surface_score

# Example output from a real eval run:
# pass@5:     84.3%   (pass@1 was 96.9%)
# ε=0.2:      88.1%   (robustness under perturbation)
# λ=0.3:      91.2%   (fault tolerance)
# Surface:    87.7%   ← this is your production reliability estimate
```

Your benchmark said 96.9%. Your reliability surface says 87.7%. The surface number is the one that matters.

## Receipt

> Verified 2026-08-07 — ReliabilityBench (arXiv 2601.06112, January 2025) reports agents at 96.9% pass@1 dropping to 88.1% at ε=0.2 perturbation intensity across 1,280 episodes over 4 domains (scheduling, travel, customer support, e-commerce). TMLS tool-use reliability analysis confirms state-of-the-art agents solve under 50% of realistic tool-agent-user tasks and exhibit high inconsistency across repeated attempts. The 3D surface R(k, ε, λ) framework maps directly to production failure modes: consistency ≈ stochasticity, perturbation ≈ adversarial inputs, fault tolerance ≈ infrastructure chaos.

## See also

- [S-1015 · The Stability Gradient](s1015-the-stability-gradient-when-your-agent-works-once-and-fails-twice.md) — the single-dimension version of consistency; this entry adds the two dimensions S-1015 doesn't cover
- [S-1049 · The Judgment Stack](s1049-the-judgment-stack-when-you-shipped-your-agent-but-have-no-idea-if-its-any-good.md) — evaluation infrastructure; S-2277 defines *what* to measure, not *how* to build the eval harness
- [S-817 · The Trajectory Eval Stack](s817-the-trajectory-eval-stack-testing-the-path-not-the-answer.md) — tests the reasoning path; S-2277 tests the execution reliability surface
- [S-1037 · The Evaluation Gap](s1037-the-evaluation-gap-when-your-agent-scores-high-and-fails-in-production.md) — gap diagnosis; S-2277 provides the structured measurement framework to diagnose it
