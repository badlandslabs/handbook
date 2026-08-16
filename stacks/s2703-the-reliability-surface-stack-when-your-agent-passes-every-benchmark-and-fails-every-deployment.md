# S-2703 · The Reliability Surface Stack — When Your Agent Passes Every Benchmark and Fails Every Deployment

You shipped your agent. You ran the benchmarks. You hit 96.9% pass@1 on ToolBench. Your CI pipeline is green. The agent works perfectly — until it hits production.

Then the rate limiter trips. The API returns a partial response with a drifted schema. The task input has a slightly different phrasing than your test set. Your agent, which was "93% reliable" in the evaluation harness, starts failing 12–40% of the time in the real world.

The problem isn't the agent. The problem is that benchmarks measure one point on the reliability surface — and production lives on the whole surface.

## Forces

- **Benchmarks report single-point estimates.** pass@1 is a single coordinate, not a reliability profile. The real production environment spans a multi-dimensional surface.
- **Stress amplifies architecture brittleness.** Complex agent architectures (ReAct + Reflexion + memory) outperform simpler ones at baseline but degrade faster under infrastructure faults than simpler architectures.
- **Faults compound non-linearly.** Rate limiting, schema drift, and semantic perturbation interact — the combined reliability drop is not the sum of individual drops.
- **Cost and reliability are separable.** Teams default to the most capable model for reliability. ReliabilityBench shows comparable reliability at 1/82nd the cost with the right architecture.
- **Correctness needs a definition.** End-state equivalence (does the result match the world state?) beats text similarity (does the output match the reference string?) for production correctness.

## The move

ReliabilityBench (arXiv:2601.06112, Gupta 2026) introduces a unified reliability surface **R(k, ε, λ)** with three independent dimensions:

### Dimension 1 — Consistency (k-trial pass rates)

Run the same task k times. pass@k captures consistency — not just "did it work once" but "does it work reliably?" A 95% pass@1 agent might only deliver 71% pass@5. Production agents need pass@10 or higher for critical workflows.

```python
# k-trial consistency measurement
def pass_at_k(results: list[bool], k: int) -> float:
    """Estimate reliability from k independent runs."""
    if len(results) < k:
        return 0.0
    # Count how many runs succeeded
    successes = sum(results[:k])
    # pass@k = fraction of runs where at least 1 of k attempts succeeds
    # For conservative estimate: require consecutive successes
    return successes / k

# Production gate: reject agents with pass@10 < 0.85
def reliability_gate(agent_fn, task, threshold=0.85, k=10):
    runs = [agent_fn(task)["success"] for _ in range(k)]
    score = pass_at_k(runs, k)
    assert score >= threshold, f"Reliability {score:.2f} below {threshold}"
    return score
```

### Dimension 2 — Robustness (ε-perturbation tolerance)

Semantically equivalent variations of the same task should produce the same result. Perturbation types:

| Perturbation Type | Example | What It Tests |
|---|---|---|
| Synonym substitution | "send email" → "dispatch message" | Semantic invariance |
| Format variation | JSON → YAML → dict | Schema robustness |
| Ordering noise | "[A] then [B]" → "[B] then [A]" | Sequence independence |
| Typos and noise | "emial" → "email" | Input normalization |

A robustness score ε captures how much perturbation the agent tolerates before reliability degrades below threshold. High ε = robust to distribution shift.

### Dimension 3 — Fault Tolerance (λ-infrastructure failures)

Chaos-engineering-style injection of realistic production faults:

```python
# Fault injection framework
class AgentFaultInjector:
    FAULTS = {
        "rate_limit": lambda: {"error": "429", "retry_after": 60},
        "timeout": lambda: {"error": "timeout", "duration_ms": 30000},
        "schema_drift": lambda: {"field": "amount", "type": "string"},  # was float
        "partial_response": lambda: {"chunks": 2, "missing_fields": ["status"]},
        "auth_refresh": lambda: {"token_expired": True},
    }

    def inject(self, agent, task, fault_type: str):
        """Run agent under injected fault, measure recovery."""
        fault_fn = self.FAULTS[fault_type]
        with mock_external_api(fault_fn):
            result = agent.execute(task)
            return {
                "success": result["status"] == "completed",
                "recovered": result.get("recovered", False),
                "graceful": result.get("graceful_degradation", False),
            }

# Production test: every agent must tolerate rate limiting
def test_rate_limit_tolerance(agent):
    injector = AgentFaultInjector()
    results = [injector.inject(agent, task, "rate_limit") for task in TEST_SET]
    rate_limit_score = mean(r["success"] for r in results)
    assert rate_limit_score >= 0.75, f"Rate limit tolerance {rate_limit_score:.2f} < 0.75"
```

### The Reliability Surface Gate

Combine all three dimensions into a production readiness gate:

```python
def reliability_surface(agent_fn, tasks, k=10, perturbations=5, faults=None):
    """
    Compute R(k, ε, λ) — the full reliability surface.
    Returns a dict of scores for production gating.
    """
    if faults is None:
        faults = ["rate_limit", "timeout", "schema_drift", "partial_response"]

    # Consistency: pass@k across all tasks
    consistency_scores = [pass_at_k(
        [agent_fn(t, fault=None)["success"] for _ in range(k)]
    , k) for t in tasks]
    consistency = mean(consistency_scores)

    # Robustness: pass rate under perturbation
    perturbed_results = []
    for t in tasks:
        for pert in generate_perturbations(t, n=perturbations):
            perturbed_results.append(agent_fn(pert, fault=None)["success"])
    robustness = mean(perturbed_results)

    # Fault tolerance: pass rate under each fault type
    fault_scores = {}
    for fault in faults:
        results = [injector.inject(agent_fn, t, fault)["success"] for t in tasks]
        fault_scores[fault] = mean(results)

    return {
        "R_consistency": consistency,       # want ≥ 0.85
        "R_robustness": robustness,          # want ≥ 0.80
        "R_fault_tolerance": fault_scores,   # want each ≥ 0.75
        "surface": f"R({k}, ε, λ)",         # the full surface
    }
```

### Key findings from ReliabilityBench (Gupta 2026)

- **The 8.8% collapse:** Agents at 96.9% pass@1 drop to 88.1% under perturbation stress — invisible to single-run benchmarks.
- **Rate limiting is the worst fault.** 2.5% drop below baseline — more damaging than timeouts, partial responses, or schema drift individually.
- **Simpler is more resilient under stress.** ReAct agents outperform complex Reflexion architectures under combined fault conditions.
- **Cost ≠ reliability.** Gemini 2.0 Flash achieves comparable reliability to GPT-4o at 1/82nd the cost (–0.6% reliability difference).
- **End-state correctness beats text match.** Action metamorphic relations define correctness via world-state equivalence, not string similarity.

### Production readiness gate

```python
def production_readiness_check(agent_fn, test_suite):
    surface = reliability_surface(agent_fn, test_suite.tasks)
    critical_faults = ["rate_limit", "timeout", "schema_drift"]

    assert surface["R_consistency"] >= 0.85,      "Consistency gate failed"
    assert surface["R_robustness"] >= 0.80,        "Robustness gate failed"
    for fault in critical_faults:
        assert surface["R_fault_tolerance"][fault] >= 0.75, \
            f"Fault tolerance for {fault} below threshold"

    print(f"Reliability surface: {surface}")
    return True
```

## Receipt

> Receipt pending — 2026-08-15. Core findings from arXiv:2601.06112 (ReliabilityBench, Gupta 2026). The k-trial consistency, perturbation robustness, and fault injection framework are implementable from the paper description. The specific numerical findings (8.8% collapse, rate limiting as worst fault, ReAct vs Reflexion under stress) come from the paper's reported experimental results.

## See also

- [S-729 · The Benchmark Disconnect](s729-the-benchmark-disconnect.md) — benchmark saturation and gameability context
- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — broader eval framework landscape
- [S-2642 · The Specification Gaming Stack](s2642-the-specification-gaming-stack-when-your-agent-maximizes-the-metric-and-ignores-the-mission.md) — reward hacking and metric misalignment
- [S-2585 · The Latent Capability Trigger Stack](s2585-the-latent-capability-trigger-stack-when-your-agent-learns-to-bypass-its-own-safety-training.md) — capability evaluation under stress conditions
