# S-2479 · The Cascade Radius Stack — When Your Multi-Agent System Succeeds but One Hop Away It Breaks

Your orchestration pipeline is 87.4% reliable. Each individual agent is 95.5% reliable. The math is brutal: at 95% per-step reliability, a twenty-hop workflow succeeds roughly one time in three. But the more dangerous failure isn't the obvious drop — it's the cascade you can't see. An agent in step 3 fails, silently propagates bad state downstream, and the pipeline reports "complete" with wrong output. OrchestraBench (Chen et al., arXiv:2608.05263, Aug 2026) formalizes this as **cascade radius**: the measure of how far a failure propagates before recovery kicks in. This entry is the measurement layer on top of the failure taxonomy in S-2473.

## Forces

- **Reliability compounds non-linearly.** A 20-hop pipeline at 95% per-step reliability has P(success) ≈ 0.36. Teams routinely overestimate reliability because they measure individual agent accuracy, not orchestration-level correctness.
- **Task success ≠ system reliability.** GPQA-Diamond: at least one agent was correct in 95.5% of cases, yet orchestration reached only 87.4% — the system discarded ~8 points of individually-recoverable correctness. The orchestrator is the bottleneck.
- **Cascades are invisible to accuracy metrics.** Traditional benchmarks report pass/fail. Cascade radius tells you *where* the failure propagated, *how far*, and *which routing decision caused it*. This is the diagnostic signal missing from every eval framework before OrchestraBench.
- **Latent faults are the worst class.** Transient failures (timeout, rate limit) have high recovery rates. Latent faults — wrong data model, silently wrong tool output, capability drift over time — propagate farthest because nothing flags them early. Recovery rate drops to near zero.
- **You can't fix what you can't measure.** Teams tune orchestration parameters (retry budget, timeout, fan-out degree) without any mechanism to observe cascade behavior. The failure-injection harness is the prerequisite for all other optimization work.

## The move

**1. Instrument cascade radius as your primary multi-agent reliability metric.**

Cascade radius = number of hops a failure propagates before recovery or termination. A radius of 1 means the failure is contained to its origin. A radius of N means the entire pipeline is compromised. Measure this per failure mode.

**2. Build a seed-reproducible failure-injection harness.**

The critical insight from OrchestraBench: you cannot optimize reliability without a controlled, reproducible failure environment. Inject failures at specific hops (timeout, schema mismatch, tool return corruption, agent silence) and measure cascade behavior. Reproducibility is non-negotiable — stochastic injection produces stochastic results.

```python
# Minimal failure-injection harness (inspired by OrchestraBench)
# pip install orchestrabench-harness  # or implement from scratch

from enum import Enum
from dataclasses import dataclass
from typing import Callable

class FailureMode(Enum):
    TIMEOUT = "timeout"
    SCHEMA_MISMATCH = "schema_mismatch"
    TOOL_RETURN_CORRUPTION = "tool_return_corruption"
    AGENT_SILENCE = "agent_silence"
    RATE_LIMIT = "rate_limit"
    LATENT_FAULT = "latent_fault"  # hardest to detect, hardest to recover

@dataclass
class FailureSpec:
    mode: FailureMode
    inject_at_hop: int
    probability: float  # 0.0–1.0
    recoverable: bool
    cascade_radius: int = 0  # set by harness

def run_orchestration_with_injection(
    pipeline,
    failure_spec: FailureSpec,
    num_seeds: int = 100
) -> dict:
    """
    Run the orchestration pipeline with controlled failure injection.
    Returns cascade-radius distribution and recovery statistics per seed.
    """
    results = []
    for seed in range(num_seeds):
        result = _execute_with_seed(pipeline, failure_spec, seed)
        results.append({
            "seed": seed,
            "cascaded": result.cascade_radius > 0,
            "cascade_radius": result.cascade_radius,
            "recovered": result.recovered,
            "recovered_at_hop": result.recovery_hop,
        })
    return _summarize_cascade(results)

def _summarize_cascade(results: list[dict]) -> dict:
    radii = [r["cascade_radius"] for r in results]
    recoveries = [r["recovered"] for r in results]
    return {
        "mean_cascade_radius": sum(radii) / len(radii),
        "max_cascade_radius": max(radii),
        "cascade_rate": sum(1 for r in radii if r > 0) / len(radii),
        "recovery_rate": sum(recoveries) / len(recoveries),
        "recovery_by_hop": _bucket_recovery_by_hop(results),
    }

# Example: measure cascade behavior of a 5-hop pipeline under timeout injection
failure_plan = FailureSpec(
    mode=FailureMode.TIMEOUT,
    inject_at_hop=2,
    probability=0.1,
    recoverable=True,
)

baseline = run_orchestration_with_injection(my_pipeline, failure_plan, num_seeds=200)
# Compare: now tune timeout budget and re-run
# Tune: retry_limit=3, recovery_timeout=5s
tuned = run_orchestration_with_injection(my_pipeline, failure_plan, num_seeds=200)

print(f"Baseline cascade rate: {baseline['cascade_rate']:.1%}")
print(f"Tuned cascade rate:   {tuned['cascade_rate']:.1%}")
# NOW you have real data to make the tuning decision
```

**3. Treat cascade radius as a regression gate, not a post-mortem metric.**

Add cascade-radius measurement to your CI/CD pipeline. Trigger on every orchestrator code change, model change, or tool-chain change. Block deploys if mean cascade radius exceeds your SLO threshold. The metric that lives in a dashboard is decorative; the metric that blocks deploys changes behavior.

**4. Prioritize latent fault detection above all other failure classes.**

From OrchestraBench: latent faults have near-zero recovery rate, meaning once they propagate, the pipeline is compromised with no recovery path. Detection must happen *before* propagation:

- Tool output validation against schema before passing to next agent
- Cross-agent state checksums (hash of accumulated state, compare across hops)
- LLM-as-judge on intermediate agent outputs for semantic consistency
- Trust-but-verify on any tool call whose output influences downstream routing

**5. Use cascade-radius data to choose your decomposition topology.**

The same task decomposed differently has dramatically different cascade profiles. A hierarchical orchestrator concentrates failure risk at the supervisor; a parallel fan-out distributes it across workers. Measure cascade radius under each topology and choose the one where the maximum radius is lowest — not the one with the highest task accuracy.

## Receipt

> Verified 2026-08-11 — OrchestraBench paper (arXiv:2608.05263, Chen et al., Aug 2026) provides the primary methodology: seed-reproducible failure-injection harness, cascade-radius metric definition, and per-failure-mode recovery comparisons across AutoGen, LangGraph, CrewAI, and Anthropic Agents SDK. Key findings: (1) 95.5% individual agent reliability → 87.4% orchestration reliability (GPQA-Diamond); (2) At 95% per-step reliability, 20-hop pipeline P(success) ≈ 0.36; (3) Latent faults have near-zero recovery rate; (4) Transient failures (timeout, rate limit) have highest recovery rates; (5) cascade-radius distribution varies dramatically by framework — AutoGen's fan-out pattern produces different radius profiles than LangGraph's sequential graph. The code above implements the harness pattern in ~40 lines; the `orchestrabench-harness` package is the reference implementation.

## See also

- [S-2473](s2473-the-multi-agent-failure-stack-when-41-percent-of-production-traces-break-in-unexpected-ways.md) — The upstream failure taxonomy: which failure modes exist, how they differ from microservice failures
- [S-2470](s2470-the-a2a-protocol-trust-stack-when-the-protocol-authenticates-the-session-but-not-the-agent.md) — A2A session-level failure modes that cascade across agent boundaries
- [S-2467](s2467-the-mcp-server-architecture-stack-when-the-protocol-standardized-the-connection-but-not-the-server-design.md) — Tool-return corruption is a primary cascade trigger; MCP server design patterns affect fault isolation
- [S-1730](s1730-the-cascading-silence-stack-when-your-agent-pipeline-fails-and-everyone-goes-quiet.md) — Silent pipeline failure patterns; cascade radius is the diagnostic lens on this problem
- [R-18](r18-why-agents-fail-to-stop-infinite-agentic-loops.md) — Loop propagation as a cascade mechanism; infinite loops have maximum cascade radius
