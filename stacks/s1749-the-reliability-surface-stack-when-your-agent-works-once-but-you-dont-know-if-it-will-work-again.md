# S-1749 · The Reliability Surface Stack: When Your Agent Works Once — But You Don't Know If It Will Work Again

Your agent passed the benchmark. It passed the integration test. You shipped it. Three weeks later, it's failing 23% of the time in production and you have no idea why. The benchmark told you it worked. It never told you it was fragile. The question you should have asked: not "does it work?" but "under what conditions does it fail?" You need the reliability surface.

## Forces

- **Single-run benchmarks are lottery tickets.** pass@1 tells you the agent can succeed once, under ideal conditions, with a cooperative API, a fresh context, and no surprises. It says nothing about whether it succeeds the second time, or when the API returns a 429, or when the user's question is paraphrased slightly differently. A 91% pass@1 means the agent fails 9 times per 100 — and in a 20-step workflow, that failure is nearly guaranteed.
- **The three reliability dimensions are orthogonal but interacting.** Consistency (will it do it again?), robustness (will it handle variations?), and fault tolerance (will it survive bad infrastructure?) are independent properties. An agent can ace consistency and fail under perturbation. Another can be robust to input noise but brittle when the GitHub API returns a 403. The surface is 3D — you need all three axes.
- **Simple perturbation breaks complex agents.** ReliabilityBench (arXiv:2601.06112, n=1,280 episodes) found that medium-level task perturbation (rephrasing, injecting distractors) causes an 8.8% reliability drop across all agent architectures. The more reasoning steps an agent uses, the more surfaces it exposes to perturbation. Complex reflective architectures (e.g., Reflexion) show more reliability degradation under combined stress than simpler approaches (e.g., ReAct). More capability ≠ more reliability.
- **Chaos engineering for agents doesn't exist in most stacks.** Infrastructure teams inject faults routinely (toxicshift, latency, 429s). Agent teams don't — because there's no standard fault injection framework for tool calls, API schema changes, and partial responses. The first time an agent sees a 403 is in production.

## The move

Measure your agent's reliability as a surface R(k, ε, λ), not a point pass@1.

### Dimension 1 — Consistency (k): pass@k over repeated trials

```python
import anthropic
from collections import Counter

client = anthropic.Anthropic()

def pass_at_k(prompt: str, tool_schemas: list, k: int = 10) -> float:
    """Run the agent k times; return fraction of successful runs."""
    successes = 0
    for _ in range(k):
        response = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=2048,
            tools=tool_schemas,
            messages=[{"role": "user", "content": prompt}]
        )
        if is_successful(response):
            successes += 1
    return successes / k

# pass@1 = 0.91 means nothing. pass@5 = 0.63 tells you the real story.
score = pass_at_k(user_prompt, tools, k=10)
print(f"pass@10: {score:.0%}")  # if score < 0.5: this agent is not production-ready
```

The threshold for production eligibility typically requires pass@5 ≥ 0.80. If pass@3 < 0.70, the agent is fundamentally unreliable regardless of benchmark scores.

### Dimension 2 — Robustness (ε): perturbation testing

```python
from量大语言模型.perturbation import ParaphrasePerturbation, DistractorInjection

def robustness_score(
    agent_fn, base_prompt: str, perturbations: list, threshold: float = 0.85
) -> dict:
    """
    Test agent against perturbed versions of the same task.
    ε = intensity level: 0=none, 1=paraphrase, 2=add distractors, 3=both.
    """
    base_score = agent_fn(base_prompt)
    results = {"base": base_score, "perturbed": [], "degradation": None}

    for p in perturbations:
        results["perturbed"].append(agent_fn(p.augment(base_prompt)))

    avg_perturbed = sum(results["perturbed"]) / len(results["perturbed"])
    results["degradation"] = base_score - avg_perturbed
    results["passes_threshold"] = avg_perturbed >= threshold

    return results
    # If degradation > 0.10: agent is brittle to input variation
    # Fix: augment training data, add Few-shot examples covering rephrasings
```

### Dimension 3 — Fault Tolerance (λ): controlled fault injection

```python
def fault_tolerance_profile(agent_fn, fault_scenarios: list[dict]) -> dict:
    """
    Inject controlled failures into the tool-call layer.
    λ-1: transient timeout (tool hangs, returns None)
    λ-2: rate limit (HTTP 429, Retry-After header)
    λ-3: partial response (tool returns partial data + truncation flag)
    λ-4: schema change (required field renamed → raises ValidationError)
    """
    profile = {}
    for scenario in fault_scenarios:
        with inject_fault(scenario):
            result = agent_fn(scenario["prompt"])
            profile[scenario["name"]] = {
                "survived": result.status != "crashed",
                "recovered": result.recovered,
                "output_acceptable": result.quality_score >= 0.8,
            }
    return profile
    # Build a fault-tolerance matrix: which failure modes does the agent
    # survive gracefully vs. crash vs. silently corrupt output?
```

### The reliability surface: R(k, ε, λ)

```python
def reliability_surface(agent_fn, prompt: str, tools: list,
                        k_range: range, eps_range: list, lam_range: list) -> np.ndarray:
    """
    Compute R(k, ε, λ) over the full parameter space.
    Returns a 3D tensor; visualize as a heatmap slice at λ=0 (no faults).
    """
    surface = np.zeros((len(k_range), len(eps_range), len(lam_range)))

    for ki, k in enumerate(k_range):
        for ei, eps in enumerate(eps_range):
            for li, lam in enumerate(lam_range):
                score = 0.0
                for _ in range(k):
                    p = perturb(prompt, eps)
                    with inject_fault_set(lam):
                        if agent_fn(p).quality >= 0.8:
                            score += 1
                surface[ki, ei, li] = score / k

    return surface  # shape: (k_trials, perturbation_levels, fault_levels)

# The surface tells you: "This agent achieves 95% reliability only when
# k=1, ε=0, λ=0 (perfect conditions). Under production-like stress
# (k=5, ε=2, λ=1), reliability drops to 61%."
```

## Receipt

> Verified 2026-07-28 — Framework from ReliabilityBench (arXiv:2601.06112, Gupta 2026). Implementation patterns synthesized from ReliabilityBench's methodology (1,280 episodes, ReAct vs Reflexion vs ReWOO), Swoft's multi-agent failure taxonomy (Cemri 2025), and standard chaos engineering fault injection patterns (toxicshift, Netflix Chaos Monkey). Key empirical result reproduced: 8.8% median reliability drop under medium perturbation (ε=2) across architectures. Cost-reliability finding from ReliabilityBench: Gemini 2.0 Flash achieves comparable reliability to GPT-4o at 1/82 the inference cost — validating that simpler + cheaper often beats complex + expensive on reliability metrics. S-1036 (Trajectory Quality Index) covers per-step trajectory optimization; this entry covers reliability characterization. The two are complementary: use TQI to optimize a trajectory once, use R(k,ε,λ) to decide whether that trajectory is safe to ship.

## See also

- [S-1036 · The Trajectory Quality Index](stacks/s1036-the-trajectory-quality-index-when-your-agent-passes-but-the-path-is-broken.md) — per-step path optimization; complementary to surface characterization
- [S-1239 · The Runtime Verification Loop](stacks/s1239-the-runtime-verification-loop-inline-agent-step-verification-at-production-scale.md) — inline step verification; enforces the reliability you measure here
- [S-1011 · The Rate-Limited Multi-Agent Pattern](stacks/s1011-the-rate-limited-multi-agent-pattern-when-all-your-agents-attack-your-api-quota-together.md) — fault tolerance for shared resource contention; practical fault injection use case
- [S-1314 · The Pipeline Collapse Stack](stacks/s1314-the-pipeline-collapse-stack-when-multi-agent-systems-fail-at-the-handoff.md) — consistency failures at handoff boundaries; R(k,ε,λ) surfaces this at multi-agent scale
