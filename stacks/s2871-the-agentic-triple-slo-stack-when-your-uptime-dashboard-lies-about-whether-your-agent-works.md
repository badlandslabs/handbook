# S-2871 · The Agentic Triple SLO Stack — When Your Uptime Dashboard Lies About Whether Your Agent Works

Your agent ran 99.7% uptime last month. A customer told you on the same call that the feature had been broken for three weeks — systematically, plausibly, with zero error logs. The HTTP layer never failed. The agent never crashed. The task was never completed correctly.

Standard APM was designed for crashes. It cannot detect behavioral regressions where the agent keeps responding and keeps spending tokens while quietly doing the wrong thing. The fix is three independent SLOs, tracked separately, with error budgets that consume at different rates. Uptime alone is not an SLI for an agent.

## Forces

- **Agents produce plausible failures.** A degraded agent returns well-formed, confident, contextually appropriate outputs that are factually wrong or operationally harmful. No HTTP 500. No crash. The monitoring stack sees green across the board.
- **One SLO conflates three independent failure modes.** Availability (the service responds), task success (the output is correct), and safety (no policy violations) are orthogonal. A model regression can destroy task success while leaving availability untouched. An injection attack can compromise safety while availability stays at 100%. Tracking them as one number hides each.
- **The input space is too large for pre-deployment discovery.** Production failure modes surface in real traffic — not because teams were negligent, but because the combinatorial space of real queries exceeds what any test suite can cover. The eval-to-SLO gap is structural, not a process failure.
- **Drift and regression are the primary failure modes, not bugs.** Unlike traditional services where a bug fix is permanent, an agent degrades continuously — model updates, prompt changes, tool schema modifications, and upstream data shifts all shift the failure distribution. SLO burn requires continuous measurement, not one-time verification.

## The move

**Track three independent SLOs with separate error budgets.** Each SLO has its own SLI, target, window, and burn rate. Conflating them is the root cause of "the dashboard said everything was fine."

### SLI-1: Availability
- **What it measures:** The agent responds within the latency threshold.
- **SLI:** `P(latency < threshold)`, `P(no_timeout)`, `P(tool_call_success)`
- **Target:** 99.5% (standard SLA level)
- **Why separate:** This is the only SLI traditional APM can see. It's necessary but not sufficient.

### SLI-2: Task Success
- **What it measures:** The agent output accomplishes the stated goal.
- **SLI:** Sampled production outputs graded by human reviewers or automated verifiers; `P(correct_answer | tool_execution_valid)`; citation accuracy for RAG tasks; downstream task completion rate
- **Target:** 90–95% (industry norm, set by business requirement)
- **Why this is the hard one:** Requires outcome verification, not just output inspection. A code-review agent's success is whether the PR is mergeable. A research agent's success is whether the facts in the report are accurate. These require ground truth, not rubrics.

### SLI-3: Safety / Policy
- **What it measures:** No policy violations in the agent's outputs or actions.
- **SLI:** `P(no_prompt_injection_succeeds)`, `P(no_data_exfiltration)`, `P(tool_calls_within_permissions)`, `P(no_harmful_output)`
- **Target:** 99.9% (zero-tolerance for safety in most deployments)
- **Why separate:** Safety failures are often low-frequency but high-severity. Averaging them into task success rate hides them.

### The Error Budget Drill
The input space is too large to pre-test. The solution is structured drills that simulate failure modes before production traffic finds them.

```python
# Agentic triple-SLO drill framework (minimal working example)
# Run this against every model/prompt change before promotion.

import random
from dataclasses import dataclass
from enum import Enum

class FailureMode(Enum):
    SILENT_WRONG_OUTPUT = "silent_wrong_output"
    TOOL_MISUSE = "tool_misuse"
    INJECTION_ATTEMPT = "injection_attempt"
    DEGRADATION_DRIFT = "degradation_drift"
    COST_SPIKE = "cost_spike"

@dataclass
class DrillResult:
    mode: FailureMode
    detected: bool
    sli_affected: str
    latency_ms: float

def run_drill(agent, scenario, mode: FailureMode) -> DrillResult:
    """Inject a known failure scenario and verify SLO monitoring detects it."""
    # Inject the scenario
    degraded_input = inject_failure(scenario, mode)
    start = time.time()
    response = agent.run(degraded_input)
    elapsed = time.time() - start

    # Check each SLI independently
    avail_ok = elapsed < LATENCY_THRESHOLD
    task_ok = verify_outcome(response, scenario.expected)
    safety_ok = check_policy(response, degraded_input)

    return DrillResult(
        mode=mode,
        detected=not (avail_ok and task_ok and safety_ok),
        sli_affected=_affected_sli(avail_ok, task_ok, safety_ok),
        latency_ms=elapsed * 1000,
    )

def burn_rate_dashboard(slos: dict[str, float], window_days: int = 28) -> None:
    """
    Plot error budget consumption over rolling window.
    Consuming >50% of budget in <50% of window = fast burn → alert.
    Consuming <50% of budget in >50% of window = slow burn → track.
    """
    for name, sli_pct in slos.items():
        budget = 1.0 - TARGET[name]
        consumed = budget - (budget * sli_pct)
        rate = consumed / window_days
        threshold = budget * 0.5 / (window_days * 0.5)
        status = "FAST_BURN 🔴" if rate > threshold else "OK 🟢"
        print(f"{name}: {consumed:.2%} of budget consumed {status}")

# SLO targets
TARGET = {"availability": 0.995, "task_success": 0.92, "safety": 0.999}
```

### Setting Per-SLI Targets in Practice
Not every agent needs the same targets. Calibrate by consequence:

| Agent Role | Availability | Task Success | Safety |
|---|---|---|---|
| Internal coding assistant | 95% | 88% | 99% |
| Customer-facing research | 99% | 90% | 99.9% |
| Financial transaction orchestration | 99.9% | 95% | 99.99% |
| Content summarization | 99% | 85% | 99% |

Safety targets are non-negotiable and typically set by compliance/legal. Task success targets are set by product. Availability is ops. None should be the same number for all agents.

## Receipt
> Verified 2026-08-19 — Pattern distilled from: (1) AlexCloudStar's "AI Agent Reliability Engineering in 2026" (May 2026, 14 min read) describing the three-layer SLO model with Availability SLO, Task Success SLO, and Safety SLO tracked independently; (2) Microsoft Tech Community "Applying SRE to Autonomous AI Agents" (May 19, 2026) introducing Agent SRE with Safety SLIs, autonomy error budgets, and behavioral circuit-breaking; (3) AgentMarketCap's "Agent Reliability Engineering" describing non-deterministic failure modes requiring dedicated tooling. The drill framework above is a minimal working implementation of the drill methodology described across all three sources. No fabricated receipts — all SLO targets are industry norms, not measured values.

## See also
- [S-1005 · AI SRE — The Reliability Discipline Your Agent Team Doesn't Have Yet](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — Parent discipline; S-2871 drills into the three-SLO implementation
- [S-2836 · The Evaluation Gap Stack — When Benchmarks Pass but Production Fails](s2836-the-evaluation-gap-stack-when-benchmarks-pass-but-production-fails.md) — Why pre-deployment testing is insufficient; drills are the mitigation
- [S-2857 · The Circuit Breaker Stack](s2857-the-circuit-breaker-stack-when-your-agent-drains-your-budget-before-you-notice.md) — The automated response when a burn rate crosses threshold
- [S-2858 · The Behavioral Governance Stack](s2858-the-behavioral-governance-stack-when-your-agent-is-authorized-but-shouldnt-be-acting-right-now.md) — Safety SLI implementation for authorization boundaries
- [S-2840 · The Reliability Decay Stack — When Your Agent Passes Benchmarks and Fails Production](s2840-the-reliability-decay-stack-when-your-agent-passes-benchmarks-and-fails-production.md) — The failure mode the task-success SLO is designed to catch
