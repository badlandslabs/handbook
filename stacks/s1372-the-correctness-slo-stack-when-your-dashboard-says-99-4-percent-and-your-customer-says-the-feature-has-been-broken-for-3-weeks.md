# S-1372 · The Correctness SLO Stack — When Your Dashboard Says 99.4% and Your Customer Says the Feature Has Been Broken for 3 Weeks

Your monitoring dashboard shows 99.4% uptime. Your on-call rotation is quiet. Your agent returns HTTP 200 on every request. Then a customer calls and says the feature has been broken for three weeks — it was silently approving refunds for orders that don't exist, and they stopped renewing. The agent was never down. It was always wrong. This is the correctness SLO gap, and it is the defining reliability failure mode of production AI agents in 2026.

## Forces

- **Traditional SLOs measure uptime, not correctness.** HTTP 200 is not a quality signal. A semantic failure — a confident hallucination, a misread tool response, a silently degraded model swap — returns the same 200 as a successful task completion. Your SLO dashboard has no visibility into this.
- **Quality is the production killer for 32% of agent teams.** Per agentmarketcap.ai (April 2026), quality failures now outrank infrastructure, latency, and cost as the #1 agent production problem. The teams losing customers aren't the ones with slow agents or budget overruns — they're the ones with agents that silently do the wrong thing.
- **Agent accuracy is non-stationary.** A model that scores 93% in eval can degrade to 71% three weeks later after a provider-side model swap. Without a correctness SLO and error budget, this drop is invisible until a customer reports it.
- **The benchmark-to-SLO gap is a measurement problem.** SWE-bench Verified at 79% means the agent solves 79% of isolated coding tasks with verifiable answers. It says nothing about the 40 daily customer-service tasks your agent runs where "correct" is a judgment call and there is no ground truth. You need production-grounded SLOs, not benchmark proxies.

## The move

Define correctness SLOs the same way SRE teams define availability SLOs: a target, a measurement method, and an error budget that drives action.

### 1. Define the correctness dimension that matters

Pick the output that actually creates or destroys value. Three common choices:

- **Task completion rate**: Did the agent finish the intended task? (e.g., "refund processed end-to-end" vs. "API called")
- **Claim accuracy**: Did the agent's factual assertions hold up? (e.g., "pricing data is correct within ±2%")
- **Policy adherence**: Did the agent follow every constraint? (e.g., "no refunds over $500 without human approval")

Do not pick a dimension because it is easy to measure. Pick the dimension whose failure causes customer harm.

### 2. Establish a baseline with production sampling

Run 5–10% of production tasks through a correctness evaluation. Log input, output, and a correctness verdict. Do not use the agent's own self-assessment — use either:
- A code-based verifier (for deterministic outputs)
- A separate LLM judge with calibrated confidence thresholds
- Human review for high-stakes cases

Build a rolling correctness histogram. This is your baseline.

### 3. Set the SLO target and error budget

| SLO dimension | Example target | Error budget (monthly) |
|---|---|---|
| Task completion | ≥ 90% | 10% of tasks may fail correctness check |
| Claim accuracy | ≥ 95% | 5% of claims may be wrong |
| Policy adherence | ≥ 99% | 1% of actions may violate policy |

Error budgets follow the same logic as SRE: the budget is the allowance. When the budget is spent, the team shifts from new features to correctness work. When it is not spent, the team can move fast.

### 4. Measure continuously, not just at release

The hardest part: correctness SLOs decay. A correct agent at launch is not a correct agent three months later. Set up:
- **Daily rolling correctness sampling**: 5% of production traffic, evaluated every 24 hours
- **Pre-deploy correctness regression gate**: any change to model, prompt, or toolchain requires passing the current SLO threshold on a held-out eval set
- **Provider-side model change alert**: log model versions per request; trigger a full correctness re-evaluation when the model version changes

### 5. Close the feedback loop

Correctness SLOs only work if violations trigger action. Define a response protocol:

```
Correctness < 90% for 24h → PagerDuty alert, freeze model/prompt changes
Correctness < 80% for 1h  → Immediate incident, revert to last-known-good config
Error budget 80% consumed  → Feature freeze, correctness remediation required
Error budget 100% consumed → Post-mortem, no new agent features until resolved
```

## Example: Correctness SLO implementation

```python
import structlog, time, random
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Callable, Any

log = structlog.get_logger()

@dataclass
class CorrectnessSLO:
    target: float          # e.g. 0.90 for 90%
    window: timedelta      # e.g. 30 days rolling
    sample_rate: float     # e.g. 0.05 for 5% of traffic
    budget_pct: float      # e.g. 0.10 for 10% error budget

    total_requests: int = 0
    sampled_requests: int = 0
    correct_count: int = 0
    budget_spent: float = 0.0
    window_start: datetime = field(default_factory=datetime.utcnow)

    def record_request(self, request: Any, task_fn: Callable[[], Any],
                       judge_fn: Callable[[Any, Any], bool]):
        """Call per production request. Samples and evaluates."""
        self.total_requests += 1
        if random.random() > self.sample_rate:
            return  # Not sampled

        self.sampled_requests += 1
        result = task_fn()  # Run the actual agent task

        is_correct = judge_fn(request, result)
        self.correct_count += 1 if is_correct else 0

        # Budget accounting
        self.budget_spent += 0.0 if is_correct else (1.0 / (self.total_requests * self.sample_rate))

        # Rolling window reset
        if datetime.utcnow() - self.window_start > self.window:
            self._reset_window()

        # Alerting
        current_rate = self.correct_count / max(self.sampled_requests, 1)
        budget_remaining = 1.0 - self.budget_spent

        if current_rate < self.target:
            log.error("correctness_slo_breach",
                current_rate=current_rate,
                target=self.target,
                budget_remaining=budget_remaining,
                sampled=self.sampled_requests)

        if budget_remaining <= 0:
            log.critical("error_budget_exhausted",
                feature=request.get("task_type", "unknown"))

    def _reset_window(self):
        self.sampled_requests = 0
        self.correct_count = 0
        self.budget_spent = 0.0
        self.window_start = datetime.utcnow()

    @property
    def current_correctness(self) -> float:
        return self.correct_count / max(self.sampled_requests, 1)

    @property
    def budget_exhausted(self) -> bool:
        return self.budget_spent >= 1.0
```

```python
# Usage: wrap your agent task
slo = CorrectnessSLO(target=0.90, window=timedelta(days=30),
                     sample_rate=0.05, budget_pct=0.10)

def judge(request, result):
    # For refund approval: verify amount matches order, policy constraints met
    return (
        result["order_exists"]
        and result["refund_amount"] <= request["order_total"]
        and result["approval_timestamp"] < datetime.utcnow() - timedelta(hours=24)
    )

# Per request:
slo.record_request(
    request={"task_type": "refund", "order_id": "ORD-9982"},
    task_fn=lambda: agent_process_refund("ORD-9982", user_id="U-441"),
    judge_fn=judge
)

if slo.budget_exhausted:
    freeze_agent_features()  # Your incident response hook
```

> Receipt pending — 2026-07-19

## See also

- [S-1024 · The Kappa Deflation Problem](/handbook/stacks/s1024-the-kappa-deflation-problem-when-your-llm-judge-reports-85-but-has-kappa-0.48.md) — LLM judges inflate accuracy; Cohen's κ exposes the gap
- [S-1004 · The Agent Eval Stack](/handbook/stacks/s1004-the-agent-eval-stack-when-your-benchmark-says-pass-but-production-keeps-breaking.md) — Production eval framework for agentic systems
- [S-1023 · The Recovery Ladder](/handbook/stacks/s1023-the-recovery-ladder-when-your-agent-thinks-it-succeeded-but-didnt.md) — When the agent's own success signal lies
