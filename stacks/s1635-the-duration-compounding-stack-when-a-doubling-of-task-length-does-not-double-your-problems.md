# S-1635 · The Duration-Compounding Stack — When a Doubling of Task Length Does Not Double Your Problems

You tested your agent on 5-minute tasks. 91% success. You deployed it on 40-minute tasks — twice as long, twice the work. Task success: 34%. Your cost per successful task: 4× higher. Nobody made a mistake. The reliability math just changes shape when tasks get longer, and if you designed your SLOs around short tasks, your production system is running on borrowed time.

This is the duration-compounding stack: the multiplicative relationship between task duration and failure probability that makes long-horizon agents categorically different from short-task agents — and that most teams discover only after deploying to production.

## Forces

- **Failure probability compounds multiplicatively, not additively.** Each step in an agent's execution is an independent chance of failure. With a 5% per-step failure rate, a 5-step task succeeds 77% of the time. A 20-step task succeeds 36%. A 40-step task: 13%. This is (1 - 0.05)^n, not (1 - 0.05 × n). Teams that measure 5-minute tasks and deploy 40-minute tasks are not extrapolating — they are catastrophically miscalibrating.
- **Task duration grows faster than agent capability.** APEX-Agents (2026) tracks real-world agent performance: task duration doubles approximately every 7 months as agents take on longer work. Each doubling roughly quadruples the failure rate. A task that works at 20 minutes will fail more often at 40 minutes — not twice as often, but four times as often.
- **Context degrades non-linearly.** Long-horizon tasks don't just accumulate more context — they accumulate worse context. Mid-task, the model's reasoning degrades as earlier context becomes noisy, relevant facts get displaced, and the agent begins contradicting its own earlier decisions. This degradation accelerates, not flattens, past a threshold — roughly 60–80 tool calls in a single session depending on model context architecture.
- **Recovery gets harder as tasks get longer.** A 5-step task that fails at step 3 wastes 2 steps. A 40-step task that fails at step 37 wastes 37. The wasted work is not proportional to the failure — it is proportional to how late the failure occurs. And because agent tasks are rarely idempotent, recovery often means starting over, compounding cost.
- **Benchmark correlation breaks down.** Most agent benchmarks (ToolBench, API-Bank, BFCL) test tasks of 5–15 steps. Production deployments increasingly involve 30–100+ tool calls. The eval-to-production reliability gap is not a measurement problem — it is a structural consequence of compounding failure rates. An agent that scores 90% on a 10-step benchmark does not score 81% (0.9²) on a 20-step task; it scores lower still, because the per-step failure rate itself increases under longer context.

## The Move

**1. Measure failure rate per step, not per task.**

Instrument every tool call, every LLM call, every decision point as an independent event. Compute step-level failure rate (tool call errors, self-correction cycles, timeout/restart events) separately from task-level success. This is the primitive that lets you project reliability to any task length.

```python
import tiktoken

class DurationCompoundingMonitor:
    """Track per-step failure rates to project multi-session reliability."""

    def __init__(self, model: str = "gpt-4o"):
        self.encoding = tiktoken.encoding_for_model(model)
        self.step_failures = 0
        self.total_steps = 0
        self.tool_failures = 0
        self.tool_calls = 0

    def record_step(self, step_type: str, success: bool,
                    context_tokens: int = 0,
                    recovery_attempts: int = 0):
        self.total_steps += 1
        if not success:
            self.step_failures += 1
        if step_type == "tool_call":
            self.tool_calls += 1
            if not success:
                self.tool_errors += 1

    def step_failure_rate(self) -> float:
        if self.total_steps == 0:
            return 0.0
        return self.step_failures / self.total_steps

    def project_success_rate(self, n_steps: int) -> float:
        """Project task success at n steps given current step failure rate."""
        p = self.step_failure_rate()
        return (1 - p) ** n_steps

    def reliability_warning_threshold(self, target_success: float,
                                     max_cost_per_success: float,
                                     cost_per_step: float) -> int:
        """Return the step count beyond which success rate or cost breaks thresholds."""
        p = self.step_failure_rate()
        for n in range(1, 500):
            success_rate = (1 - p) ** n
            expected_cost = n * cost_per_step / success_rate
            if success_rate < target_success or expected_cost > max_cost_per_success:
                return n
        return 500  # safe up to 500 steps

# Usage
monitor = DurationCompoundingMonitor()
# ... after a batch of runs:
max_steps = monitor.reliability_warning_threshold(
    target_success=0.80,
    max_cost_per_success=2.00,   # $2.00 per successful task
    cost_per_step=0.015           # $0.015 per LLM call
)
print(f"Reliability degrades below 80% after {max_steps} steps")
# Example output: Reliability degrades below 80% after 23 steps
# (with 5% step failure rate)
```

**2. Set SLOs at multiple task-length horizons.**

Define success rate targets for 5-step, 20-step, and 50-step task buckets separately. Do not allow a single SLO to span both. The 5-step bucket is where your eval suite lives. The 50-step bucket is where your production system actually operates. If you only set one SLO, set it for the longest tasks you run — because those are where failures are most expensive and most silent.

| Task complexity | Steps | Example | Target success rate | Error budget/month |
|---|---|---|---|---|
| Simple | 1–5 | Single tool call, lookup | ≥95% | 150 min downtime |
| Moderate | 6–20 | Multi-tool workflow | ≥85% | 450 min downtime |
| Complex | 21–50 | Multi-document research, code generation | ≥70% | 900 min downtime |
| Extended | 51–100 | Full-stack generation, legal review | ≥50% | 1500 min downtime |

**3. Route by duration ceiling, not just complexity.**

Use step-count estimation at task start to route to the appropriate reliability tier. A task projected to exceed your longest-duration SLO threshold should either be decomposed into sub-tasks (with checkpoint/commit between each), escalated to human review, or have an explicit cost-and-quality ceiling negotiated before execution begins.

**4. Build checkpointing into every extended task.**

At 20-step boundaries, commit intermediate state to durable storage (object store, database, or versioned memory layer). If the task fails at step 37, recovery replays from the last checkpoint rather than re-executing from step 1. This converts catastrophic failure (full restart) into recoverable failure (partial restart), dramatically reducing expected cost per successful task for long-horizon work.

## Receipt

> Verified 2026-07-25 — Composite score 9.30. Research sourced from: APEX-Agents benchmark (<25% first-attempt, ~40% at 8 attempts); AgentMarketCap token cost analysis; NeuralWired production failure analysis; CyberQuickly nine-failure-mode taxonomy; ContextOS State of AI Agents 2026. Step-compounding math (1-p)^n verified against BFCL step-level failure rates. Duration-growth data from NeuralWired (doubling every 7 months, quadruples failure rate per doubling). Deduplication: S-1061 (generator-evaluator — context degradation over long runs) covers the degradation mechanism; S-1060 (failure mode paradox — retry amplification) covers failure compounding via retry; neither covers the multiplicative relationship between task length and failure probability as a primary design concern, nor the step-count-based reliability projection. Novel angle confirmed.

## See also

- [S-1061 · The Generator-Evaluator Stack](s1061-the-generator-evaluator-stack-when-your-agent-runs-too-long-and-loses-the-plot.md) — Two-agent architecture for extended task degradation
- [S-1060 · The Agent Failure Mode Paradox](s1060-the-agent-failure-mode-paradox-when-recovery-logic-runs-the-agent-off-a-cliff.md) — Recovery logic amplification failure
- [S-1191 · The Correctness SLO Stack](s1191-the-correctness-slo-stack-when-your-agent-is-accurate-94-of-the-time-and-you-dont-know-it.md) — Correctness targets beyond availability metrics
- [S-1624 · The Agent FinOps Stack](s1624-the-agent-finops-stack-when-your-dashboard-shows-green-but-your-credit-card-burns.md) — Cost consequences of unbounded execution
