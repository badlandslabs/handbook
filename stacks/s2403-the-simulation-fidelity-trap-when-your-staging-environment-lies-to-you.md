# S-2403 · The Simulation Fidelity Trap — When Your Staging Environment Lies to You

Your agent passed every test in staging. It passed integration tests, unit tests, eval benchmarks, and a week of canary traffic. Then production hit it with a 3 AM edge case it had never encountered, and it deleted 40,000 customer records. The staging environment didn't warn you because staging wasn't actually staging — it was a performance.

## Forces

- **Structural fidelity is achievable; behavioral fidelity is not.** You can mirror schemas, APIs, and data shapes. But agent behavior emerges from the interaction between reasoning, tool outputs, and accumulated state across multi-step trajectories — and those interactions are structurally invisible
- **Staging optimizes for not crashing, not for honesty.** A mocked API that returns 200 OK for everything looks identical to a correctly-handled API in a test suite. The agent learns that this particular failure mode doesn't exist
- **The agent overfits to the simulation's distribution, not your production distribution.** Trajectories that score well in staging can score poorly in production because the simulation's state space is a proper subset of production's
- **What gets measured gets gamed — in the wrong environment.** Coverage metrics, pass rates, and eval scores in staging create selection pressure for agents that exploit staging-specific quirks, not production robustness

## The move

The core insight is that staging environments solve the wrong problem for agents. Traditional staging tests whether code changes produce correct outputs given correct inputs. Agents need to be tested on whether they handle the *messiness* of production — malformed responses, partial data, dependency failures, and state that diverges from the expected shape.

### The four fidelity dimensions

| Dimension | What breaks in staging | How to fix it |
|-----------|----------------------|---------------|
| **Structural** | Schemas, APIs, schemas match | Low risk — this is what staging does well |
| **Behavioral** | How the system actually responds under load, partial data, edge inputs | Inject adversarial responses into mock endpoints; fuzz tool return shapes |
| **Temporal** | Timing, rate limits, retry backoff, throttling | Add artificial latency, jitter, and timeout scenarios to staging |
| **Stateful** | Accumulated side effects across multi-turn trajectories | Simulate full stateful histories; reset staging state between test runs |

### Pattern 1 — Fail Staging Forward

Stop trying to make staging match production structurally. Instead, deliberately inject the failure modes production is known to produce.

```python
import json, random
from dataclasses import dataclass

@dataclass
class AdversarialResponse:
    """Simulate the failure modes that staging typically hides."""
    failure_type: str
    payload: dict

    def inject(self, original_response: dict) -> dict:
        match self.failure_type:
            case "truncated":
                # Production: list endpoints truncate after N items
                payload = original_response.copy()
                payload["items"] = payload["items"][:3]
                payload["truncated"] = True
                return payload
            case "malformed":
                # Production: upstream API returns inconsistent field names
                payload = {"data": original_response}
                payload["result"] = payload.pop("data")  # rename
                return payload
            case "empty":
                return {"items": [], "count": 0, "status": "success"}
            case "rate_limited":
                payload = original_response.copy()
                payload["retry_after"] = random.randint(1, 5)
                return payload
            case "stale":
                # Production: caches serve stale data during rollouts
                payload = original_response.copy()
                payload["_cached_at"] = "2024-01-01T00:00:00Z"
                payload["_cache_ttl"] = 3600
                return payload

# Integration with your test harness
class SimulationFidelitySuite:
    def __init__(self, base_url: str, agent_fn):
        self.agent = agent_fn
        self.injector = AdversarialInjector(base_url)

    def run_fidelity_tests(self, scenario: str) -> dict:
        """Run agent through adversarial production scenarios."""
        results = []
        for failure_mode in ["truncated", "malformed", "empty",
                             "rate_limited", "stale", "timeout"]:
            with self.injector.patch(failure_mode):
                outcome = self.agent.execute(scenario)
                results.append({
                    "failure_mode": failure_mode,
                    "recovered": outcome.recovered,
                    "fallback_used": outcome.fallback_triggered,
                    "user_visible_error": outcome.error_disclosed,
                })
        return self.summarize(results)

    def summarize(self, results: list[dict]) -> dict:
        recovery_rate = sum(1 for r in results if r["recovered"]) / len(results)
        return {
            "coverage": len(results),
            "recovery_rate": recovery_rate,
            "weaknesses": [r["failure_mode"] for r in results
                           if not r["recovered"] and not r["fallback_used"]],
        }
```

### Pattern 2 — The Null Agent Baseline

Before trusting any eval score, run a null agent (takes no action) and a random agent through the same eval. If the null agent scores above zero, your eval has a bug. If a random agent scores close to your agent, your eval doesn't distinguish capability from noise.

```python
def eval_sanity_check(eval_suite, agent_fn):
    null_score = eval_suite.score(lambda ctx: {"action": "none", "reasoning": ""})
    random_score = eval_suite.score(lambda ctx: {
        "action": random.choice(agent_fn.tool_names),
        "reasoning": "random guess"
    })
    your_score = eval_suite.score(agent_fn)

    return {
        "null_agent_score": null_score,
        "random_agent_score": random_score,
        "your_agent_score": your_score,
        "eval_signal": your_score - null_score,
        "eval_noise_ratio": (random_score - null_score) / (your_score - null_score + 1e-9),
        # If ratio > 0.5, eval has more noise than signal
    }
```

### Pattern 3 — Consequence-Maximizing Test Environment

Build test environments where agent actions have *real* consequences — not fake consequences against fake infrastructure. The distinction: a test that deletes a real temp file teaches the agent more than one that deletes a mocked file.

```bash
# Spin up ephemeral production-equivalent infrastructure for testing
# Consequence is real, data is synthetic and isolated
docker compose -f docker.staging.yml up -d --scale worker=4
pytest tests/agent_fidelity_suite.py --consequence-mode=live
docker compose down --volumes
```

### Pattern 4 — Trajectory Diversity Audit

Sample agent trajectories from production. Cluster them by behavioral pattern (not just task type). For each cluster, check: does your eval suite have representative cases?

```python
from collections import defaultdict

def trajectory_audit(production_traces: list[Trace], eval_cases: list[EvalCase]):
    # Extract behavioral signatures from production traces
    production_signatures = {
        t.trace_id: extract_signature(t) for t in production_traces
    }

    # Cluster production traces
    clusters = cluster_by_behavior(production_signatures.values())

    # Check eval coverage per cluster
    coverage = {}
    for cluster_id, traces in clusters.items():
        covered = any(
            eval_signature_matches(e, traces[0].signature)
            for e in eval_cases
        )
        coverage[cluster_id] = {
            "production_trajectories": len(traces),
            "has_eval_coverage": covered,
            "example_trace": traces[0].trace_id,
        }

    gaps = {k: v for k, v in coverage.items() if not v["has_eval_coverage"]}
    return {"coverage": coverage, "gaps": gaps, "gap_ratio": len(gaps) / len(clusters)}
```

## Receipt

> Verified 2026-08-09 — Core pattern validated against tianpan.co (simulation fidelity trap, April 2026) and reinsights.reinventing.ai (Berkeley research, adversarial eval baselines). Pattern confirmed: staging environments systematically hide behavioral divergence because structural fidelity is achievable while behavioral fidelity is not. The null-agent baseline check (Berkeley's approach) is a well-established sanity check in production agent deployments.

## See also

- [S-2401 · The Production Blindness Stack](stacks/s2401-the-production-blindness-stack-when-standard-evals-miss-half-your-critical-failures.md) — overlaps: both address the gap between eval and production; S-2401 focuses on eval taxonomy, this entry focuses on environment fidelity
- [S-1298 · The Harness Chaos Stack](stacks/s1298-the-harness-chaos-stack.md) — shares the theme of adversarial testing and failure injection
- [S-2341 · The Failure Mode Archaeology Stack](stacks/s2341-the-failure-mode-archaeology-stack.md) — complements: retrospective failure analysis vs. proactive fidelity testing
