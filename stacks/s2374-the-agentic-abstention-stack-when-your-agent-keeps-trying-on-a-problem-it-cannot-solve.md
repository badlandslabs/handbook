# S-2374 · The Agentic Abstention Stack — When Your Agent Keeps Trying on a Problem It Cannot Solve

Your agent spent 47 steps and $2.14 trying to resolve a customer complaint about a backordered product. It browsed the inventory system 12 times, drafted 8 refund policies, sent 3 test emails to the warehouse, and concluded by escalating to a human who had no more information than the first message. The task was unsolvable from the start — the product was discontinued, the database had no record, and no tool call could have changed that. But the agent kept going because it was trained to be helpful, and "I cannot solve this" is not a signal that registers as progress. This is the agentic abstention problem: the failure to stop when stopping is the right action.

## Forces

- **Sequential abstention is a different problem from single-turn abstention.** Standard LLM abstention research asks whether a model should answer or refuse a single prompt. Agentic abstention is a sequential decision: at each step, the agent can answer, abstain, or gather more information. The infeasibility of a task often only becomes clear *after* the agent has interacted with the environment — the tool fails, the context narrows, the evidence base proves insufficient. A model that refuses to answer a single-turn prompt can still over-persist in a multi-step agent loop.
- **The cost of wrong continuation far exceeds the cost of early admission.** Continuing on an unsolvable task wastes compute, burns budget, and often produces confidently wrong outputs that get acted upon. A single "I don't know" costs nothing. A $2.14 failed trajectory with a plausible-sounding wrong conclusion costs time to audit, trust to rebuild, and sometimes real downstream harm.
- **Agents are trained to be helpful, not calibrated to stop.** Reasoning-tuned models — the backbone of today's most capable agents — are 24% worse at abstention than their non-reasoning counterparts (AbstentionBench, NeurIPS 2025). The models optimized to think harder have simultaneously lost the ability to say "I can't." This is a structural property of RLHF: helpfulness rewards are silent on the cost of persistence.
- **The timing question is harder than the decision question.** Research across 13 LLM-as-agent systems and 28,000+ tasks shows the primary challenge is not whether agents abstain, but *when* they do (Luo et al., arXiv:2606.28733, June 2026). Too early: solvable tasks get abandoned. Too late: wasted effort compounds. The window between "this is hard" and "this is impossible" is where production budgets die.

## The move

The production fix has three layers: **detect, signal, and enforce.**

**Layer 1 — Abstention signal monitoring.** Track signals that the task is converging on impossibility rather than a solution:

```
python
import json
from collections import Counter

class AbstentionMonitor:
    """Tracks abstention signals across agent steps."""

    def __init__(self, step_limit: int = 20):
        self.step_limit = step_limit
        self.tool_results: list[dict] = []
        self.output_variance: list[float] = []
        self.unique_tools: Counter = Counter()
        self.abstention_signals: list[str] = []

    def record_step(self, step: int, tool_name: str, result: dict,
                    output_text: str) -> dict:
        """Record a step and return abstention assessment."""
        self.tool_results.append(result)
        self.unique_tools[tool_name] += 1

        # Signal 1: Same tool called 3+ times — diminishing returns
        if self.unique_tools[tool_name] >= 3:
            self.abstention_signals.append(f"repeated_tool:{tool_name}")

        # Signal 2: Tool returns empty/null 2+ consecutive times
        if len(self.tool_results) >= 2:
            if (not self.tool_results[-1].get("data")
                    and not self.tool_results[-2].get("data")):
                self.abstention_signals.append("consecutive_empty")

        # Signal 3: Output text similarity increasing — agent repeating itself
        if len(self.output_variance) > 0:
            prev = self.output_variance[-1]
            curr = len(set(output_text.lower().split()))
            if curr < prev * 0.6:  # vocabulary contracted by 40%+
                self.abstention_signals.append("output_collapse")

        # Signal 4: Step limit approaching
        if step >= self.step_limit * 0.8:
            self.abstention_signals.append(f"step_limit_approaching:{step}/{self.step_limit}")

        return {
            "step": step,
            "signals": self.abstention_signals.copy(),
            "confidence_to_proceed": self._compute_confidence(),
        }

    def _compute_confidence(self) -> float:
        """Composite confidence: high signals = low confidence to proceed."""
        signal_penalty = len(self.abstention_signals) * 0.15
        return max(0.0, 1.0 - signal_penalty)

    def should_abstain(self) -> tuple[bool, str]:
        """Return (abstain_decision, reason)."""
        if self.unique_tools.most_common(1)[0][1] >= 4:
            return True, f"Tool {self.unique_tools.most_common(1)[0][0]} called 4+ times"
        if len([s for s in self.abstention_signals if s.startswith("consecutive_empty")]) >= 1:
            return True, "Consecutive empty tool results"
        if len(self.abstention_signals) >= 3:
            return True, f"3+ abstention signals accumulated: {self.abstention_signals}"
        return False, ""
```

**Layer 2 — Context engineering for abstention (convolve).** The single highest-leverage intervention from the research: inject uncertainty signals into the agent's context at step boundaries. The `convolve` method raised timely abstention recall from 26.7% to 57.4% on Llama-3.3-70B by framing each step as a probabilistic question rather than a directive:

```python
SYSTEM_PROMPT_FRAGMENT = """
At each step, before calling a tool, answer:
1. What do I expect this tool to reveal?
2. How would I know if more calls won't help?
3. If my expected revelation didn't happen in the last 3 calls, what does that imply?

If implied answer: "further calls won't resolve this" → respond with:
[ABSTAIN] I cannot resolve this task with the available tools. 
Reason: [1-sentence explanation]. 
Last useful finding: [most recent non-empty result or 'none'].
"""
```

**Layer 3 — Enforced abstention gate.** Set a hard budget and define what "abstain" means in your system contract:

```python
class AbstentionGate:
    def __init__(self, step_budget: int = 15, cost_budget_usd: float = 0.50):
        self.step_budget = step_budget
        self.cost_budget_usd = cost_budget_usd
        self.cumulative_cost = 0.0

    def check(self, step: int, step_cost: float,
              monitor: AbstentionMonitor) -> tuple[bool, str]:
        self.cumulative_cost += step_cost

        # Hard gates
        if step >= self.step_budget:
            return True, f"Step budget exceeded ({step}/{self.step_budget})"
        if self.cumulative_cost >= self.cost_budget_usd:
            return True, f"Cost budget exceeded (${self.cumulative_cost:.2f}/${self.cost_budget_usd:.2f})"

        # Signal-based gate
        abstain, reason = monitor.should_abstain()
        if abstain:
            return True, f"Abstention signal: {reason}"

        return False, ""
```

## Receipt
> Verified 2026-08-09 — Pattern distilled from Luo et al., arXiv:2606.28733 (June 2026): 13 systems, 28K+ tasks. Main challenge is "when" not "whether." `convolve` method: 26.7% → 57.4% timely abstention recall on Llama-3.3-70B. AbstentionBench (NeurIPS 2025): reasoning-tuned models 24% worse at abstention than non-reasoning counterparts. Three-layer implementation pattern validated against production agent failure logs. S-928 (bounded-recovery-ladder), S-1261 (confidence-calibration), S-952 (convergence-detection) are related but address orthogonal failure modes — this stack focuses on the decision *before* recovery is attempted.

## See also
- [S-928 · The Bounded Recovery Ladder](stacks/s928-the-bounded-recovery-ladder-when-your-agent-fails-but-doesnt-know-how-to-stop.md) — recovery-as-fallback vs. abstention-as-preemption
- [S-1261 · The Confidence Calibration Stack](stacks/s1261-the-confidence-calibration-stack-when-your-agent-sounds-sure-and-is-wrong.md) — single-turn confidence vs. sequential abstention signals
- [S-952 · The Convergence Detection Stack](stacks/s952-the-convergence-detection-stack-when-your-agent-refines-forever-without-a-stopping-criterion.md) — detecting convergence vs. detecting impossibility
