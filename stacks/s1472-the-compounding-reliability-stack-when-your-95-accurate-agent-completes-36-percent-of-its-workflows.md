# S-1472 · The Compounding Reliability Stack — When Your 95%-Accurate Agent Completes 36% of Its Workflows

Your agent hits 95% accuracy on every tool call. Your evals show green. You ship a 20-step enterprise workflow. Three out of five runs fail — not at any particular step, but at the workflow level. The agent isn't broken. Arithmetic is. Each step that succeeds 95% of the time produces a 20-step chain that succeeds 0.95^20 ≈ 36% of the time. This is Lusser's Law applied to agents: the reliability of a series of steps equals the product of their individual reliabilities. No benchmark, no demo, and no prompt engineering will change this equation. Only architecture can.

## Forces

- **Lusser's Law is indifferent to model quality.** Even a perfect 99%-per-step agent delivers only 82% end-to-end reliability across 20 steps. The arithmetic doesn't care how good the model is. The only levers are chain length, redundancy, and interstep verification.
- **Step-level metrics are the trap.** Industry optimized per-step reliability from 2024–2026. Step-level gains translate to workflow-level gains at exponential discount. A 5% improvement in per-step accuracy (90% → 95%) doubles end-to-end success at 20 steps (12.2% → 35.8%) — but only because the baseline is catastrophically low. The real leverage is in architecture.
- **Demos don't show compounding.** A 3-step demo produces a 0.95³ = 86% success rate — acceptable in a screenshot. Production tasks that take humans an hour+ routinely run 10–50 steps. The failure surface only appears when stakes and length both increase.
- **Chain length is a design choice teams don't realize they're making.** Every "just one more step to be thorough" decision multiplies failure probability. Shortening a chain from 20 to 10 steps doubles end-to-end reliability at 95% per-step (35.8% → 59.9%). Before adding steps, ask: what is this step's marginal contribution to reliability?

## The move

Four architectural patterns address compound reliability. They form a stack — each addresses a different failure mode in the chain.

### 1. Chain Shortening First

Before any other pattern: reduce step count. Every removed step is a reliability multiplier, not just a cost saver.

```
[Step A] → [Step B] → [Step C] → [Step D] → [Step E]
              ↓
         Can B+C merge?
         Can D be conditional (skip if X)?
```

Merge adjacent steps where the LLM can handle multi-tool intent in one call. Make steps conditional — skip low-value steps unless a guard condition fires. At 95% per-step: 5 steps = 77.4%, 4 steps = 81.5%, 3 steps = 85.7%.

### 2. Interstep Verification Gates

Place a lightweight judge between critical step pairs. The judge is not another LLM call doing the same work — it is a structured check: "Did the output from Step N satisfy its preconditions for Step N+1?"

```python
import anthropic

client = anthropic.Anthropic()

def verify_step_output(step_name: str, output: dict, next_step: dict) -> bool:
    """Lightweight verification gate before high-stakes or expensive steps."""

    # Only invoke the judge LLM for step pairs where failure cost > verification cost
    verification_cost_threshold = 0.01  # dollars
    failure_cost = next_step.get("failure_severity", 0)
    step_cost = next_step.get("estimated_cost", 0)

    if failure_cost * 0.1 < step_cost:
        # Failure is cheap enough to risk without verification
        return True

    # Structured prompt: the judge inspects a specific precondition contract,
    # not the full semantic output. Narrow scope = consistent, cheap judgment.
    response = client.messages.create(
        model="claude-haiku-4",
        max_tokens=64,
        system="You are a structured precondition checker. "
               "Given a step output and a precondition contract, "
               "answer ONLY 'PASS' or 'FAIL'. Be strict.",
        messages=[{
            "role": "user",
            "content": f"Step output: {output}\nPrecondition for '{next_step['name']}': {next_step['precondition']}"
        }]
    )
    verdict = response.content[0].text.strip().upper()
    return verdict == "PASS"
```

The gate is cheap when using a small model (haiku-class) with a narrow contract. It is expensive when using a large model with open-ended "is this good?" prompts. Scope the judge to the specific precondition, not the full output quality.

### 3. Fork-Join Redundancy

For high-stakes steps where p^n is unacceptable, run N variants in parallel, then vote. This trades cost for reliability. At 95% per-step with N=3 parallel agents and majority vote:

```
P(success) = C(3,2)·0.95²·0.05 + C(3,3)·0.95³
           = 3·0.9025·0.05 + 0.8574
           = 0.1354 + 0.8574
           ≈ 99.3%
```

At 3x cost, 20 steps at 95% yields 98% end-to-end instead of 36%.

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

async def fork_join_step(
    agents: list[callable],
    inputs: list[Any],
    voting_fn: callable,
    max_parallel: int = 3,
) -> Any:
    """
    Run N agent variants in parallel, return majority-voted result.
    Each agent receives the same task description but may use different
    models, prompts, or tool configurations — N-version programming for agents.
    """

    # Semaphore limits concurrent cost exposure
    semaphore = asyncio.Semaphore(max_parallel)

    async def run_agent_with_limit(agent_fn, inp):
        async with semaphore:
            return await agent_fn(inp)

    # Fire all variants simultaneously
    results = await asyncio.gather(
        *[run_agent_with_limit(agent, inp) for agent, inp in zip(agents, inputs)]
    )

    # Majority vote — requires odd N
    if len(results) % 2 == 0:
        raise ValueError("Fork-join requires odd number of variants for majority vote")
    return voting_fn(results)
```

Use fork-join selectively: only for steps where failure is expensive and computation is cheap relative to failure cost. A 3x cost increase on a 20-step chain that was delivering 36% success is worth it if the workflow's value exceeds 3x the step cost.

### 4. Reliability Circuit Breaker

Monitor rolling success rate. If p drops below a threshold, halt the chain and escalate — don't let a degraded agent continue through 20 steps of guaranteed failure.

```python
from collections import deque
import time

class ReliabilityCircuitBreaker:
    """
    Tracks per-step success rate across recent runs.
    Halts the chain if reliability drops below threshold.

    Reliablity is measured at the step-pair level: did Step N's output
    enable Step N+1 to produce a valid result?
    """

    def __init__(self, window_size: int = 20, threshold: float = 0.80):
        self.window = deque(maxlen=window_size)
        self.threshold = threshold
        self.consecutive_failures = 0
        self.max_consecutive = 5  # hard halt even within window

    def record(self, success: bool):
        self.window.append(success)
        if success:
            self.consecutive_failures = 0
        else:
            self.consecutive_failures += 1

    def can_proceed(self, step_name: str) -> bool:
        recent_rate = sum(self.window) / len(self.window) if self.window else 1.0

        if self.consecutive_failures >= self.max_consecutive:
            print(f"[CIRCUIT] Hard halt: {self.consecutive_failures} consecutive failures")
            return False

        if recent_rate < self.threshold:
            print(f"[CIRCUIT] Halted at '{step_name}': rolling reliability {recent_rate:.1%} < {self.threshold:.1%}")
            return False

        return True

    def project_end_to_end(self, remaining_steps: int) -> float:
        """Project current reliability forward: what end-to-end rate can we expect?"""
        if not self.window:
            return 1.0
        p = sum(self.window) / len(self.window)
        projected = p ** remaining_steps
        print(f"[CIRCUIT] Projected E2E success for {remaining_steps} remaining steps: {projected:.1%}")
        return projected
```

### Applying the Stack in Order

```
┌─────────────────────────────────────────────────────────────┐
│  Step 0: Can the chain be shorter?                         │
│           → Merge, make conditional, remove low-value steps │
│  Step 1: Is the step high-stakes?                          │
│           → Insert verification gate before it               │
│  Step 2: Does the step's failure cascade?                   │
│           → Fork-join with N-version agents                 │
│  Step 3: Is the chain running hot on reliability?           │
│           → Circuit breaker monitors and halts              │
└─────────────────────────────────────────────────────────────┘
```

Budget math: A 20-step chain at 95% per-step costs $X and delivers 36% success. Add interstep gates on 5 high-stakes transitions (~$0.05 each, $0.25 total): cost +25%, reliability +roughly 5–15% depending on gate accuracy. Add fork-join on 2 critical steps (3x cost on 2 steps, effectively 6x overhead on those steps): cost +60%, reliability on those steps jumps to ~99%. The circuit breaker adds negligible cost but prevents worst-case scenarios from completing and billing.

## Receipt

> Verified 2026-07-22 — Compound reliability math confirmed against three independent sources: AgentMarketCap (Apr 2026) accuracy decay table (95%→36% at 20 steps), Revonex Labs (May 2026) 0.85^10 = 19.7% finding, LensHQ (May 2026) formalization via Lusser's Law. Fork-join reliability calculation verified: C(3,2)·0.95²·0.05 + C(3,3)·0.95³ = 99.28%. Interstep gate pattern verified against TRACE Probe framework (arXiv:2607.06184) normalize→detect→score pipeline structure. Circuit breaker pattern verified against AgentOps session replay methodology. Deduplication: S-964 covers compounding calibration error (RLHF degrades confidence accuracy); this entry covers architectural mitigation (redundancy, gates, abort). S-1027 covers loop detection and scaffold infrastructure; this entry covers reliability projection and proactive circuit breaking. S-1013 covers multi-agent state disagreement; this entry covers interstep verification between any sequential operations. None of the above cover the fork-join N-version agent pattern or the p^n reliability projection math for production workflow design.

## See also

- [S-964 · The Compounding Calibration Stack](s964-the-compounding-calibration-stack-when-your-95-accurate-agent-is-wrong-60-percent-of-the-time.md) — RLHF degrades calibration; confidence is trusted too far downstream
- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — liveness ≠ progress; agents fail silently without structural detection
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — two agents disagree on state; interstep gates prevent downstream cascade
- [S-1036 · The Trajectory Quality Index](s1036-the-trajectory-quality-index-when-your-agent-passes-but-the-path-is-broken.md) — TRACE Probe evaluates the path, not just the output
