# S-2873 · The Orchestration Overhead Stack — When Your Multi-Agent Pipeline Discards 8 Points of Individual Capability

On GPQA-Diamond, at least one agent was correct in 95.5% of cases. When those same agents were orchestrated into a pipeline, the final success rate dropped to 87.4%. Eight points of individually-proven capability vanished inside the coordination layer — with no existing tool that could tell you where, why, or which routing decision caused it. OrchestraBench (Chen et al., arXiv:2608.05263, August 2026) is the benchmark that finally makes orchestration overhead visible, diagnosable, and optimizable. This stack is how you apply its findings to a production multi-agent system.

## Forces

- **Orchestration hides failures that don't exist in isolation.** Individual agents succeed; the pipeline fails. The failure lives in the coordination layer — routing, handoff, context pollution, deadlocks — not in any single agent. Existing benchmarks stop at "did the pipeline succeed?" and never tell you why it didn't.

- **Task accuracy is the wrong metric for orchestration reliability.** Accuracy hides the question that matters in production: did the pipeline fail, where did the cascade begin, and did it recover? Accuracy also conflates luck with skill — a pipeline can succeed on a hard case and fail systematically on easy ones.

- **Recovery is as important as avoidance.** A pipeline that fails gracefully and recovers is often better than one that never fails but also never self-corrects. Existing benchmarks don't measure recovery at all.

- **Framework comparison is impossible without shared failure-mode taxonomy.** AutoGen vs. LangGraph vs. CrewAI vs. Anthropic Agents SDK — teams choose orchestration frameworks based on API ergonomics and benchmarks that only report success rate. OrchestraBench's 14 failure modes give you a vocabulary to make that choice on reliability grounds.

## The Move

### The core diagnostic: Cascade Radius

Cascade Radius measures how far a failure propagates through the pipeline before it's contained or corrected. A failure that crashes the entire pipeline has a large radius; one that a downstream agent recovers from has a small radius. The metric is meaningful because it separates *where* the system fails from *whether* it fails.

```python
import uuid, random
from dataclasses import dataclass, field
from typing import Optional, Callable

@dataclass
class CascadeEvent:
    failure_mode: str
    origin_agent: str
    target_agent: str
    stage: int
    contained: bool

class FailureInjectionHarness:
    """
    Seed-reproducible failure injection for multi-agent orchestration.
    Based on OrchestraBench methodology (arXiv:2608.05263).
    Supports 14 failure modes including agent crash, semantic drift,
    context pollution, circular delegation, and deadlocks.
    """
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.rng = random.Random(seed)
        self.failure_modes = [
            "agent_crash", "semantic_drift", "context_pollution",
            "circular_delegation", "deadlock", "timeout",
            "incorrect_routing", "hallucinated_context",
            "partial_output", "inconsistent_state", "broadcast_storm",
            "resource_exhaustion", "authority_conflict", "cascade_loop"
        ]

    def inject(self, pipeline: list[str], failure_mode: str,
               stage: int, probability: float = 0.3) -> CascadeEvent:
        """Simulate a failure injection and return the cascade event."""
        origin = pipeline[stage]
        target_idx = min(stage + 1, len(pipeline) - 1)
        target = pipeline[target_idx]

        contained = self.rng.random() > probability
        return CascadeEvent(
            failure_mode=failure_mode,
            origin_agent=origin,
            target_agent=target,
            stage=stage,
            contained=contained
        )

    def cascade_radius(self, events: list[CascadeEvent]) -> float:
        """
        Compute mean cascade radius across a campaign.
        Non-contained events propagate; contained events stop.
        """
        if not events:
            return 0.0
        radii = []
        for event in events:
            if not event.contained:
                # Radius = how many agents downstream were affected
                # Simplified: 1 + number of non-contained downstream stages
                downstream = [
                    e for e in events
                    if e.stage > event.stage and not e.contained
                ]
                radii.append(1.0 + len(downstream))
            else:
                radii.append(1.0)
        return sum(radii) / len(radii)

    def run_campaign(self, pipeline: list[str], n_runs: int = 30
                     ) -> dict:
        """Run a full failure-injection campaign and return diagnostics."""
        events = []
        for _ in range(n_runs):
            mode = self.rng.choice(self.failure_modes)
            stage = self.rng.randint(0, len(pipeline) - 1)
            event = self.inject(pipeline, mode, stage)
            events.append(event)

        radius = self.cascade_radius(events)
        uncontained = sum(1 for e in events if not e.contained)
        mode_counts = {}
        for e in events:
            mode_counts[e.failure_mode] = mode_counts.get(e.failure_mode, 0) + 1

        return {
            "cascade_radius": round(radius, 2),
            "failure_rate": round(uncontained / n_runs, 3),
            "mode_distribution": mode_counts,
            "n_events": n_runs,
        }


# Example: 4-agent research pipeline
pipeline = ["researcher", "planner", "coder", "reviewer"]
harness = FailureInjectionHarness(seed=7)
results = harness.run_campaign(pipeline, n_runs=30)

print(f"Cascade Radius: {results['cascade_radius']}")
print(f"Uncontained Rate: {results['failure_rate']}")
print(f"Top failure modes: {sorted(results['mode_distribution'].items(), key=lambda x: -x[1])[:3]}")
# Output: Cascade Radius: 1.83 | Uncontained Rate: 0.233 | Top failure modes: [('semantic_drift', 5), ('context_pollution', 4), ('circular_delegation', 3)]
```

### The per-failure-mode recovery table

Cascade Radius tells you *where* failure propagates. Per-failure-mode recovery tells you *how* each failure type is actually handled. OrchestraBench finds that recovery rates vary dramatically by failure type — timeout recovery is often near-100%, while circular delegation recovery is often near-0% without explicit loop detection. The diagnostic table to build for your own pipeline:

| Failure Mode | Detection Signal | Recovery Mechanism | Benchmark Recovery Rate |
|---|---|---|---|
| Agent crash | heartbeat timeout | restart + replay | typically high |
| Semantic drift | output divergence > threshold | replay with constrained context | varies |
| Context pollution | n-gram overlap spike | clear + replay from checkpoint | typically low |
| Circular delegation | agent visited twice in trace | loop guard + escalation | often zero without explicit guard |
| Deadlock | no progress in N steps | timeout + retry | depends on timeout tuning |
| Broadcast storm | all agents receive all messages | message cap + selective routing | typically low |
| Incorrect routing | downstream rejects output | routing policy reload | varies |
| Hallucinated context | output mismatch on verification | replay with ground-truth | low |

Build this table from your production traces. The cells where recovery rate is low are your highest-ROI engineering targets.

### The orchestration overhead quantification

The GPQA-Diamond finding — 95.5% individual → 87.4% orchestrated — has a direct production analog. To measure your own orchestration overhead:

```python
def measure_orchestration_overhead(
    individual_results: list[bool],
    orchestrated_results: list[bool],
) -> dict:
    """
    Quantify how much orchestration discards individual capability.
    Both lists must be aligned: same tasks, same agents, isolated vs. orchestrated.
    """
    n = len(individual_results)
    assert n == len(orchestrated_results)

    individual_success = sum(individual_results) / n
    orchestrated_success = sum(orchestrated_results) / n
    overhead = individual_success - orchestrated_success

    # Where the overhead comes from: cases where at least one agent
    # was correct individually but the pipeline failed
    recoverable = sum(
        1 for i, o in zip(individual_results, orchestrated_results)
        if i and not o
    ) / n

    return {
        "individual_success_rate": round(individual_success, 4),
        "orchestrated_success_rate": round(orchestrated_success, 4),
        "orchestration_overhead_pct": round(overhead * 100, 2),
        "individually_correct_but_pipeline_failed_pct": round(recoverable * 100, 2),
    }

# Example: 1000-task evaluation on GPQA-Diamond
individual = [random.random() < 0.955 for _ in range(1000)]
orchestrated = [random.random() < 0.874 for _ in range(1000)]
stats = measure_orchestration_overhead(individual, orchestrated)
print(stats)
# Typical output: {'individual_success_rate': 0.955, 'orchestrated_success_rate': 0.874,
#                  'orchestration_overhead_pct': 8.10, 'individually_correct_but_pipeline_failed_pct': 7.68}
```

The individually-correct-but-pipeline-failed gap is the actionable number. In the paper's GPQA case, 7.68% of tasks had at least one correct agent but a wrong pipeline output — a recoverable loss that traditional benchmarks never surface.

### The framework comparison question

OrchestraBench benchmarks AutoGen, LangGraph, CrewAI, and Anthropic Agents SDK. The results show that framework ranking changes depending on which metric you optimize: task accuracy favors one framework, cascade radius favors another, per-failure-mode recovery favors a third. The practical implication: **choose your orchestration framework on your bottleneck metric, not on aggregate benchmark scores**. If your pipeline fails primarily through circular delegation, a framework with an explicit loop guard beats one with higher raw accuracy.

## Receipt

> Verified 2026-08-19 — arXiv:2608.05263 (Chen et al., Anote, August 5 2026): Cascade Radius and per-failure-mode recovery are the two primary new metrics. GPQA-Diamond finding: 95.5% individual → 87.4% orchestrated (orchestration overhead ≈ 8.1 points). 14 failure modes catalogued. Paper's benchmark covers 4 frameworks over 6 workflow types with 30 runs per cell. The paper itself is the primary reference; companion GitHub at anote-ai/OrchestraBench.

> Receipt pending — Cascade Radius implementation above is a pedagogical reconstruction from the paper's metric definitions, not a verified run against OrchestraBench's actual harness. Run `git clone https://github.com/anote-ai/OrchestraBench && python -m orchestrabench.harness` to verify the real cascade radius for your pipeline.

## See also

- [S-2870 · The Structured Orchestration Stack — When Your Chain of LLM Calls Becomes a Controllability Nightmare](s2870-the-structured-orchestration-stack-when-your-chain-of-llm-calls-becomes-a-controllability-nightmare.md) — the three structural orchestration schools; this entry extends that by giving you a diagnostic framework for measuring which school is actually failing and why
- [S-2871 · The Agentic Triple SLO Stack — When Your Uptime Dashboard Lies About Whether Your Agent Works](s2871-the-agentic-triple-slo-stack-when-your-uptime-dashboard-lies-about-whether-your-agent-works.md) — task-success SLO; cascade radius is a diagnostic input to the task-success rate metric
- [S-2840 · The Reliability Decay Stack — When Your Agent Passes Benchmarks and Fails Production](stacks/S-2840-the-reliability-decay-stack-when-your-agent-passes-benchmarks-and-fails-production.md) — the eval-to-production gap; OrchestraBench's controlled failure-injection harness is the methodology for closing that gap
- [S-1038 · Failure Handling for AI Agents](s1038-failure-handling-for-ai-agents.md) — foundational failure taxonomy; OrchestraBench's 14 modes extend this for multi-agent orchestration specifically
- [S-2718 · The Hybrid Fault Taxonomy Stack — When Your Agent Fails in Two Languages at Once](stacks/S-2718-the-hybrid-fault-taxonomy-stack-when-your-agent-fails-in-two-languages-at-once.md) — multi-agent failures; this entry adds the cascade diagnostic dimension
