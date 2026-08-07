# [S-2217] · The Multi-Agent Coordination Tax Stack

You add one more agent to your pipeline. The task gets split, workloads get parallelized, quality supposedly goes up. Then your token bill arrives and your three-agent workflow cost 2.9× what a single-agent version would have.

That multiplier is not a bug. It is the coordination tax — and it compounds with every agent you add.

## Forces

- **Context re-explanation overhead**: each agent handoff re-serializes state into natural language, bloating prompts by 40–60% per hop
- **Review and reflection loops**: in frameworks like ChatDev, iterative review stages consume 59.4% of total tokens — not the actual work
- **Tool proliferation tax**: distributed systems with >10 active tools suffer 2–6× efficiency loss from retrieval and routing overhead
- **The deception of parallelism**: parallel agents look efficient on a diagram; in practice, barrier synchronization and output merging often erase the gains
- **Prompt cache misses**: because each agent invocation is semantically unique, prompt caching hits 1-hour TTL windows at low rates — the cache is designed for repeated prompts, not dynamic orchestration

## The move

### Measure before splitting

Run a single-agent baseline on your task. Record tokens per successful task (TPS). Every architectural decision downstream should be justified against that baseline.

```python
import asyncio
from anthropic import AsyncAnthropic
from dataclasses import dataclass, field
from typing import Optional

client = AsyncAnthropic()

@dataclass
class TokenBudget:
    baseline_tps: float = 0.0          # tokens per successful task (single agent)
    measured_tps: float = 0.0           # tokens per successful task (current config)
    coordination_overhead: float = 0.0  # (measured - baseline) / baseline

    def record(self, tokens: int, success: bool):
        if success:
            self.measured_tps = (self.measured_tps + tokens) / 2
            self.coordination_overhead = (
                (self.measured_tps - self.baseline_tps) / self.baseline_tps
                if self.baseline_tps > 0 else 0.0
            )

    def should_split(self, num_agents: int = 2) -> bool:
        """Rough model: coordination overhead ~35% per agent.
        Only split if task time savings exceed this.
        """
        estimated_overhead = 0.35 * (num_agents - 1)
        return estimated_overhead < 0.4  # require >40% time savings to justify split


@dataclass
class AgentConfig:
    name: str
    prompt: str
    tools: list = field(default_factory=list)
    max_tokens: int = 4096
    temperature: float = 0.0


async def measure_coordination_tax(
    task: str,
    baseline_agent: AgentConfig,
    split_agents: list[AgentConfig],
    n_runs: int = 10,
) -> dict:
    """Compare single-agent vs multi-agent token consumption."""
    results = {"baseline": [], "multi_agent": [], "ratio": 0.0}

    for _ in range(n_runs):
        # Baseline: single agent
        msg = await client.messages.create(
            model="claude-opus-4-5",
            max_tokens=baseline_agent.max_tokens,
            messages=[{"role": "user", "content": baseline_agent.prompt.format(task=task)}],
        )
        results["baseline"].append(msg.usage.input_tokens + msg.usage.output_tokens)

        # Multi-agent: orchestrate and merge
        sub_tasks = task.split("|")  # naive split — adjust to your decomposition
        sub_results = await asyncio.gather(
            *[
                client.messages.create(
                    model="claude-opus-4-5",
                    max_tokens=agent.max_tokens,
                    messages=[
                        {"role": "user", "content": agent.prompt.format(task=sub_task)}
                    ],
                )
                for agent, sub_task in zip(split_agents, sub_tasks)
            ]
        )

        orchestration_prompt = (
            f"Original task: {task}\n"
            f"Sub-results:\n" +
            "\n".join(r.content[0].text for r in sub_results)
        )
        merge_msg = await client.messages.create(
            model="claude-opus-4-5",
            max_tokens=baseline_agent.max_tokens,
            messages=[{"role": "user", "content": orchestration_prompt}],
        )

        multi_agent_tokens = sum(
            r.usage.input_tokens + r.usage.output_tokens
            for r in sub_results
        ) + merge_msg.usage.input_tokens + merge_msg.usage.output_tokens
        results["multi_agent"].append(multi_agent_tokens)

    import statistics
    results["ratio"] = (
        statistics.mean(results["multi_agent"]) /
        statistics.mean(results["baseline"])
    )
    return results
```

### Apply targeted reductions

| Technique | Typical Savings | When to Use |
|-----------|-----------------|-------------|
| Structured output contracts | 10–30% | All inter-agent handoffs |
| Context compression (summarize then pass) | 20–57% | Long context handoffs |
| Prompt caching (1-hr TTL) | 15–40% | Repeated agent invocations |
| Typed handoff schemas | 15–25% | Every agent-to-agent call |
| KV-snapshot sharing | 20–50% | Disaggregated inference setups |
| Decision threshold routing | 30–60% | When a single agent can handle subtasks below complexity threshold |

```python
# Typed handoff contract — eliminates re-explanation overhead
from typing import TypedDict, Optional
from pydantic import BaseModel

class HandoffContract(BaseModel):
    task_id: str
    delegator: str
    delegate: str
    intent: str                       # one-sentence goal
    constraints: list[str]            # what the delegate MUST NOT do
    input_schema: type[BaseModel]    # enforced input contract
    output_schema: type[BaseModel]   # enforced output contract
    max_tokens: int                   # per-step budget
    escalation_trigger: str            # condition that hands back to orchestrator

    class Config:
        # No free-form text fields — every field is typed
        extra = "forbid"
```

### Budget the coordination layer explicitly

Treat agent coordination as a first-class cost center. Set per-handoff token budgets, enforce circuit breakers on handoff chains, and track coordination cost as a separate metric from task cost.

## Receipt

> Verified 2026-08-06 — Pattern analysis from Zylos Research (2026-06-05): ChatDev coordination study reports 59.4% of tokens consumed by iterative review stages; three-agent pipelines cost 2.9× single-agent equivalent (~10K vs ~29K tokens); tool-heavy distributed systems show 2–6× efficiency loss. Token-efficient router (GitHub sickagents) reports 60–75% savings via task routing. No live benchmark run — code provided as architectural reference.

## See also

- [S-643 · The Coordination Layer Is the Product](s643-the-coordination-layer-is-the-product.md) — structural overview of multi-agent coordination
- [S-464 · KV-Snapshot Sharing for Multi-Agent Inference](s464-kv-snapshot-sharing-for-multi-agent-inference.md) — prefix reuse technique
- [S-1388 · The A2A Context Fidelity Stack](s1388-the-a2a-context-fidelity-stack-when-your-agent-hands-off-a-task-and-the-receiver-loses-the-thread.md) — context preservation across handoffs
- [S-2186 · The Agent Budget Guard Stack](s2186-the-agent-budget-guard-stack-when-your-agent-is-your-biggest-monthly-expense.md) — token budget enforcement
