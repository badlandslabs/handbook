# S-1191 · The Correctness SLO Stack — When Your Agent Is Accurate 94% of the Time and You Don't Know It

Your agent ran 40,000 tasks last night. Your dashboards are green. P50 latency: 1.2s. Error rate: 0.2%. Token spend: on budget. A customer emails: "Your agent has been giving wrong policy information for five days." You check the logs. Every call returned HTTP 200. The trace shows a valid reasoning chain, a tool that executed successfully, and an answer that is completely wrong. Nobody set a SLO for that.

This is the correctness SLO gap: agents are the only production system where teams routinely ship without a Service Level Objective for the primary thing the system is supposed to do — produce correct outputs.

## Forces

- **Infrastructure telemetry is blind to correctness.** Datadog's State of AI Engineering 2026 found 1 in 20 production AI requests fail. But 60% of those are capacity failures (rate limiting, context exhaustion) — the remaining 40% are semantic: wrong answers, reasoning collapse, and context degradation that return 200 and look fine in every dashboard. Standard APM dashboards measure the wrong dimension.
- **Accuracy is not a unit test, it's a rate.** You don't measure latency once and call it done — you track it over time, set an SLO, and alert on burn rate. Accuracy must be treated the same way. A single eval run tells you nothing about whether correctness is degrading week over week as your context grows, your model updates, or your data pipelines drift.
- **The 94% that passes hides the 6% that matters.** In high-stakes domains (legal, medical, financial), the failure distribution is not random. The agent is systematically wrong on edge cases, on users with uncommon circumstances, on tasks that look like the common case but aren't. A 94% accuracy score hides a systematic bias that your users absorb and your team never sees.
- **Model updates silently change correctness rates.** A provider update to gpt-4o-mini shipped on a Tuesday. By Thursday, the agent's tool-call frequency shifted — more retries, longer reasoning chains. Cost was up 40%. Accuracy was down — but nothing alerted because accuracy wasn't being measured.
- **Per-request correctness checks are not the same as correctness rates.** Semantic exit gates (S-1016) verify individual outputs. Correctness SLOs verify aggregate rates over time. You need both: exit gates catch bad individual outputs, SLOs catch degradation that no individual gate would flag.

## The move

**Define correctness as a rate, not a binary.** Track the percentage of agent tasks that produce correct outcomes over rolling windows (1h, 24h, 7d). Set a SLO target (e.g., 97% correct) and an error budget. Treat it the same as latency or availability.

**Layer three measurement approaches:**

1. **Direct outcome sampling** — spot-check a random sample of completed tasks against ground truth. Fast, cheap, gives you a correctness rate. For structured tasks (classification, extraction, routing), ground truth is often derivable programmatically. For open-ended tasks, use LLM-as-judge with calibrated thresholds (see I-042 for failure modes of LLM-as-judge).

2. **Behavioral proxies** — track signals that correlate with correctness degradation without measuring it directly: task retry rate, tool-call count per task, context window utilization rate, response length trend. A spike in any of these precedes a correctness drop. Alert on the proxy; investigate the cause.

3. **Downstream feedback loops** — route user corrections, escalation events, and downstream API errors back as correctness signals. A user clicking "this answer is wrong" is a concrete correctness data point. These signals are noisy but directionally accurate and free.

**Set burn rate alerts, not static thresholds.** Alert when the correctness rate falls below SLO *and* the rate of decline exceeds your error budget burn rate. A slow 2% drift over two weeks might breach your 30-day error budget without triggering a traditional threshold alert.

```python
import datetime, json, statistics
from collections import deque

class CorrectnessSLO:
    """
    Track correctness SLO for an agent.
    Records outcome + correctness signal per task.
    Computes rolling rate and budget burn.
    """

    def __init__(self, slo_target: float = 0.97, window_hours: int = 24,
                 error_budget_days: int = 30):
        self.slo_target = slo_target
        self.window_hours = window_hours
        self.error_budget = 1.0 - slo_target
        self.window_dt = datetime.timedelta(hours=window_hours)
        self.budget_dt = datetime.timedelta(days=error_budget_days)
        self.outcomes: deque[tuple[datetime.datetime, bool]] = deque()

    def record(self, task_id: str, outcome_correct: bool):
        """Record a task outcome. True = correct, False = incorrect."""
        self.outcomes.append((datetime.datetime.utcnow(), outcome_correct))

    def _prune(self):
        cutoff = datetime.datetime.utcnow() - self.window_dt
        while self.outcomes and self.outcomes[0][0] < cutoff:
            self.outcomes.popleft()

    def correctness_rate(self) -> float:
        self._prune()
        if not self.outcomes:
            return 1.0
        return statistics.mean(r for _, r in self.outcomes) if isinstance(
            next(iter(self.outcomes))[1], bool) else 1.0

    def rate(self) -> float:
        """Alias for correctness_rate()."""
        self._prune()
        if not self.outcomes:
            return 1.0
        return sum(1 for _, c in self.outcomes if c) / len(self.outcomes)

    def budget_remaining(self) -> float:
        """% of error budget remaining. 1.0 = full budget, 0.0 = exhausted."""
        self._prune()
        if not self.outcomes:
            return 1.0
        elapsed = datetime.datetime.utcnow() - (self.outcomes[0][0])
        budget_fraction_consumed = min(
            elapsed / self.budget_dt,
            len(self.outcomes) / max(len(self.outcomes), 1)
        )
        # Burn rate = actual errors / allowed errors
        correct_count = self.rate() * len(self.outcomes)
        allowed_errors = self.error_budget * len(self.outcomes)
        if allowed_errors <= 0:
            return 1.0
        burn_rate = (len(self.outcomes) - correct_count) / allowed_errors
        return max(0.0, 1.0 - burn_rate * budget_fraction_consumed)

    def is_breaching(self) -> bool:
        return self.rate() < self.slo_target

    def alert_payload(self) -> dict:
        rate = self.rate()
        budget = self.budget_remaining()
        return {
            "correctness_rate": round(rate, 4),
            "slo_target": self.slo_target,
            "sample_size_24h": len(self.outcomes),
            "error_budget_remaining": round(budget, 4),
            "breaching": rate < self.slo_target,
            "severity": "critical" if budget < 0.25 else "warning" if rate < self.slo_target else "ok"
        }


# Usage in agent loop:
# slo = CorrectnessSLO(slo_target=0.97, window_hours=24)
# for task in task_queue:
#     result = agent.run(task)
#     correct = human_review(result) or llm_judge(result, ground_truth)
#     slo.record(task.id, correct)
# alert_payload = slo.alert_payload()
# if alert_payload["severity"] != "ok":
#     send_alert(alert_payload)
```

## Receipt
> Receipt pending — 2026-07-16

## See also
- [S-1151 · The Behavioral Telemetry Stack](s1151-the-behavioral-telemetry-stack-when-your-agent-returns-200-ok-and-a-wrong-answer.md) — telemetry infrastructure for detecting wrong answers
- [S-1016 · The Agent Failure Intervention Stack](s1016-the-agent-failure-intervention-stack-when-your-agent-works-but-wrong.md) — per-request correctness gates
- [S-101 · Deterministic Agent Sessions](s101-deterministic-agent-sessions.md) — replay infrastructure for post-incident correctness analysis
- [I-042 · LLM-as-Judge Failure Modes](knowledge-pulse.md) — echo chamber and calibration risks when using LLM judges to measure correctness
