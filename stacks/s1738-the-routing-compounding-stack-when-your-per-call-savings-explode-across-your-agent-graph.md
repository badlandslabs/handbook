# S-1738 · The Routing Compounding Stack — When Your Per-Call Savings Explode Across Your Agent Graph

You route Agent A's classification step to a $0.001/model and save $40/day. Three weeks later, your overall LLM bill is 3× what it was before routing. The math should have worked. The per-call costs are lower. But in multi-agent systems, routing decisions don't sum — they *compound*. Downstream agents amplify upstream routing errors, and the total bill has a graph topology you never instrumented.

## Forces

- **Per-call routing optimizes locally; agent costs accumulate globally.** Every routing framework — RouteLLM, Martian, Not Diamond, OpenRouter — evaluates routing correctness against the *immediate* output quality. None evaluates downstream propagation cost. A cheap model that gets a classification slightly wrong doesn't just produce a slightly wrong label; it produces an Agent B whose entire reasoning path is now misdirected.
- **Routing errors in early pipeline stages have exponential blast radius.** In a supervisor → specialist pipeline, routing the supervisor to a low-capability model corrupts the task decomposition. All downstream specialists receive flawed context. The cost of fixing it equals re-running every specialist agent plus the supervisor. One $0.01 routing save → ten $0.50 re-runs.
- **Agents interpret ambiguity differently than single-call LLMs.** A single-call LLM returns "unsure" when it doesn't know. An agent with a routing budget reasons its way to a confident-but-wrong answer. The wrong answer enters the agent graph and propagates until a human notices or a downstream failure triggers a rollback.
- **Agent-graph cost models assume linear scaling.** Team topologies, supervisor patterns, and parallel fan-outs all create non-linear cost curves. Adding a second specialist doesn't double your routing cost — it creates a combinatorial explosion of routing-path interactions.

## The move

**Route at the graph level, not the call level.** For multi-agent systems, the routing decision isn't "which model for this step?" — it's "which model for this step, given the full dependency chain this step initiates?"

### The compounding model

Every agent in a dependency chain has a *routing multiplier* — the ratio of its expected downstream cost to its own execution cost:

```
Agent A routing decision
  └─→ Cost(A) + RoutingMultiplier(A) × Cost(all downstream from A)
```

If Agent A routes to a $0.001 model and saves $1 on A, but this causes Agent B (a specialist) to rerun twice, you've spent $3 on B to save $1 on A. The routing multiplier for A is 3× — and most routing frameworks never compute it.

### Three compounding patterns

**1. Supervisor misroute → specialist cascade.** Supervisor routes to Haiku for task decomposition. Haiku misses a nuance in the user's request and creates a flawed plan with 5 specialist tasks instead of 2. Now 5 specialists run in parallel, each calling expensive tools, each producing outputs that need synthesis. The routing "savings" on the supervisor generated 5× the downstream work.

**2. Reasoning-model routing on intermediate steps.** A routing rule sends "fast tasks" to fast models. In a ReAct agent, every tool-use loop is a "fast task" — it looks simple. But fast-model tool calls have higher error rates, which cause the agent to re-think, re-act, and re-observe. The fast-model tool call saves $0.001 and costs $0.50 in extra loop iterations.

**3. Fan-out without routing governance.** A supervisor routes to 8 specialist agents in parallel. Each specialist independently routes its sub-tasks. The routing of each specialist is individually optimal but collectively saturates your API rate limits, triggering 429s that cascade into timeouts across the fan-out. The individual routing decisions all looked correct; the collective behavior was a thundering-herd failure.

### The fix: upstream routing with downstream cost awareness

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class RoutingDecision:
    model: str
    routing_cost: float
    estimated_downstream_cost: float
    compounding_factor: float  # downstream_cost / routing_cost

def route_with_compounding(
    agent_id: str,
    task: str,
    context: dict,          # includes upstream output quality signals
    downstream_agents: list[str],
    downstream_costs: dict[str, float],
) -> RoutingDecision:
    """
    Route with awareness of downstream amplification.

    context["upstream_quality_score"]: float 0-1
      - 1.0 = perfect upstream output, downstream work is predictable
      - < 0.7 = upstream is noisy, downstream agents will need to handle ambiguity
      - < 0.5 = reroute upstream agent to a higher tier even if this step is cheap

    downstream_costs maps agent_id -> estimated_cost
      - If any downstream cost is > 10× this step's cost, the compounding
        factor demands a higher-tier model for this step.
    """
    # Rule: if downstream amplification risk exceeds threshold, promote tier
    max_downstream = max(downstream_costs.values(), default=0)
    compounding_risk = max_downstream / estimate_step_cost(agent_id, task)

    if context.get("upstream_quality_score", 1.0) < 0.7:
        # Low-quality upstream = noisy input = downstream rerun risk
        # Force mid-tier minimum regardless of routing score
        return force_tier("mid", agent_id, task, compounding_risk)

    if compounding_risk > 10:
        # Downstream cost is >10× this step's cost
        # A wrong call here saves pennies and costs dollars
        return force_tier("mid", agent_id, task, compounding_risk)

    # Otherwise, normal routing
    return normal_route(agent_id, task)


# Anti-thundering-herd routing for parallel fan-outs
def route_parallel_fanout(
    supervisor_decision: dict,
    specialists: list[dict],
    rate_limit: int,
) -> list[RoutingDecision]:
    """
    Avoid thundering-herd by staggering specialist routing tiers.

    If all specialists would route to the same model at the same time,
    promote a random 30% to a higher tier to absorb rate-limit headroom
    and provide execution diversity.
    """
    decisions = [route_with_compounding(**s) for s in specialists]
    models_used = {d.model for d in decisions}

    if len(models_used) == 1 and len(decisions) > 3:
        # All same model — diversify 30%
        diversify_count = int(len(decisions) * 0.3)
        for i in range(diversify_count):
            idx = i % len(decisions)
            decisions[idx] = promote_to_next_tier(decisions[idx])

    return decisions
```

### Routing budget decomposition

Decompose your total agent-graph budget *before* routing decisions:

```
Total Budget = Σ Cost(Agent_i × Tier_i) for all i in graph

Constraint: Cost(graph) ≤ Budget_limit
Objective:  Maximize Σ DownstreamConfidence(Agent_i) × Tier_i

The routing optimizer minimizes per-call cost while respecting
the global budget constraint — not individual call budgets.
```

This is a knapsack problem over the agent graph, not a per-call threshold problem. RouteLLM-style classifiers solve the wrong problem for multi-agent systems.

## Receipt

> Verified 2026-07-27 — Routing compounding confirmed via production cost analysis from AgentMarketCap (April 2026): teams implementing multi-agent routing reported 40-60% cost reductions vs. single-model baselines, but 3 teams reported "unexpected cost spikes" at 3-4 weeks post-deployment traced to routing in early pipeline stages cascading to specialist re-runs. The compounding mechanism is documented but not yet codified as a named pattern in the agentic AI literature. The fix pattern (upstream cost awareness, compounding-factor routing, thundering-herd diversification) synthesizes practices from Martian's routing architecture, Not Diamond's cost-model work, and multi-agent orchestration best practices from a16z's State of AI Agents (2026).

## See also

- [S-06 · Model Routing](s06-model-routing.md) — foundational routing (per-call, not graph-level)
- [S-322 · Multi-Agent Cost Observability Patterns](s322-multi-agent-cost-observability-patterns.md) — cost visibility without compounding analysis
- [S-1063 · The Multi-Agent Orchestration Stack](s1063-the-multi-agent-orchestration-stack-when-one-agent-isnt-enough-but-five-becomes-a-debugging-nightmare.md) — orchestration topology (adjacent to compounding effects)
