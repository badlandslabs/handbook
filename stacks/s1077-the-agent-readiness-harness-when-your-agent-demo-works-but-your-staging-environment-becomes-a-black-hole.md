# S-1077 · The Agent Readiness Harness — When Your Agent Demo Works But Your Staging Environment Becomes a Black Hole

Your agent runs beautifully in the demo. It answers questions, calls the right tools, writes correct code. You push it to staging. Three weeks later it's still in staging. Nobody can explain why — the model hasn't changed, the prompt is the same, the tool definitions are identical. The problem isn't the agent. It's that nobody built a harness that answers: *is this agent ready to receive real traffic?*

## Forces

- **Demo environment is a lie.** A demo has clean inputs, cooperative tools, and an operator who steers away from failure modes. Production has dirty inputs, rate-limited APIs, tools that timeout, and users who ask questions nobody anticipated.
- **68% of agent projects stall at the evaluation stage** (QCode, 2026). The bottleneck is not model capability — it is the absence of a repeatable engineering structure that answers readiness questions before traffic routing.
- **Agent quality is multidimensional.** Correctness, safety, cost, latency, robustness, tool-call validity, and failure-mode coverage are orthogonal dimensions. A single aggregate score hides which dimension is failing.
- **The harness is the agent's production prerequisite**, not an afterthought. Just as you wouldn't deploy a service without a load test, you shouldn't route real users to an agent without a readiness gate.

## The Move

### The Seven Readiness Dimensions

Before routing traffic, evaluate across seven independent dimensions:

| Dimension | Question | How to measure |
|-----------|----------|---------------|
| **Correctness** | Is the output right? | Gold-set comparison, integration test fixtures, assertion-based task completion |
| **Safety** | Does it generate harmful, non-compliant, or out-of-scope content? | Adversarial probe set, content policy check, scope boundary test |
| **Cost** | Is token/dollar cost per task within budget? | Token metering, cost-per-outcome tracking |
| **Latency** | Is per-turn latency within SLA? | P50/P95/P99 end-to-end timing |
| **Robustness** | Does it degrade gracefully under stress? | Latency spikes, partial tool failures, noisy inputs |
| **Tool-call validity** | Does it call the right tools with correct arguments? | Schema validation, call-sequence assertion, argument correctness probe |
| **Failure-mode coverage** | Does it fail predictably when it should fail? | Negative test suite, boundary condition probes, permission denial handling |

### The Four Harness Patterns

**Pattern 1 — Fixture Harness (simplest)**
Feed the agent a fixed test dataset with known ground-truth outputs. Score each dimension. Gate on minimum thresholds per dimension.

```python
# Minimal readiness harness skeleton
from dataclasses import dataclass
from typing import Callable

@dataclass
class ReadinessResult:
    correctness: float   # 0.0 – 1.0
    safety: float        # 0.0 – 1.0
    cost_per_task: float # USD
    latency_p95_ms: float
    tool_call_accuracy: float
    failure_predictability: float

def readiness_check(
    agent: Callable,
    fixtures: list[dict],
    thresholds: dict[str, float],
) -> ReadinessResult | str:
    results = []
    for fixture in fixtures:
        # Run agent on fixture
        output, trace = agent(fixture["input"], return_trace=True)
        results.append({
            "correct": fixture["validator"](output),
            "cost": trace.total_cost_usd,
            "latency_ms": trace.wall_time_ms,
            "tool_calls": trace.tool_calls,
        })

    aggregate = ReadinessResult(
        correctness=mean(r["correct"] for r in results),
        safety=adversarial_probe_score(agent),
        cost_per_task=mean(r["cost"] for r in results),
        latency_p95_ms=nth_percentile([r["latency_ms"] for r in results], 95),
        tool_call_accuracy=tool_call_validator(results),
        failure_predictability=failure_mode_coverage(agent),
    )

    # Dimension-by-dimension gate
    failures = []
    for dim, val in as_dict(aggregate).items():
        if dim in thresholds and val < thresholds[dim]:
            failures.append(f"{dim}: {val:.2f} < {thresholds[dim]:.2f}")

    if failures:
        return f"BLOCKED — readiness gaps: {failures}"
    return aggregate
```

**Pattern 2 — Sandbox Harness (real execution)**
Run the agent in an isolated environment (container, VM, or Firecracker microVM) against staged external services. Tools that would call production APIs get stubbed with realistic responses including injected failures. Detects environment-specific failures (permission errors, network conditions, dependency availability) that fixture harnesses miss.

**Pattern 3 — Canary Harness (production shadow)**
Mirror live traffic to the agent in shadow mode — no output is returned to users, but the harness scores every dimension against real inputs. The canary harness catches distribution shift: the agent was evaluated on your test distribution but your users ask differently. Catch this before the percentage flips.

**Pattern 4 — Replay Harness (regression gate)**
Capture every production failure trace as a structured replay fixture. On every model or prompt change, replay all captured traces and diff trajectories. Replay catches silent regressions where the agent reaches correct answers via different (and now broken) reasoning paths.

### CI Gate Integration

The harness runs as a CI gate on every commit or prompt change:

```yaml
# .github/workflows/agent-readiness.yml
- name: Agent Readiness Check
  run: |
    python -m agent_harness readiness \
      --fixtures ./fixtures/staging_set.jsonl \
      --thresholds correctness=0.85,safety=0.95,cost_per_task=0.02,latency_p95=2000
  # Exit code 1 if any threshold fails → PR blocked
```

The thresholds are team-specific. Start with conservative values, tighten as the agent matures. The goal is not perfection — it is *repeatable evidence* that the agent is ready for the next stage.

## Receipt

> Receipt pending — 2026-07-14 — Harness skeleton code above requires a `return_trace=True` interface on the agent callable and a `fixtures/staging_set.jsonl` file. Integrate with DeepEval or Inspect AI for the actual scoring layer.

## See also

- [S-1037 · The Evaluation Gap](s1037-the-evaluation-gap-when-your-agent-scores-high-and-fails-in-production.md) — benchmark vs. production divergence
- [S-1044 · The Trajectory Eval Stack](s1044-the-trajectory-eval-stack-when-your-agent-looks-accurate-but-fails-in-production.md) — per-step measurement
- [S-1013 · The Trace Replay Harness](s1013-the-trace-replay-harness-when-your-agent-breaks-in-production-and-you-cannot-reproduce-it.md) — replay as regression gate
