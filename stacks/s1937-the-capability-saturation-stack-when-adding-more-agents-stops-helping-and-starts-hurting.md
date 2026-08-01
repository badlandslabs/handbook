# S-1937 · The Capability Saturation Stack — When Adding More Agents Stops Helping and Starts Hurting

Your agent team runs 5 specialized agents on a complex task. The result is worse than what a single capable model would have produced alone — slower, noisier, and less accurate. You assumed that more agents meant more capability. The research says you're wrong about capable models: they outgrow the benefits of collaboration. The failure mode isn't under-coordination — it's over-coordination on tasks where a single agent was already sufficient.

## Forces

- **Baseline performance predicts multi-agent benefit.** Across 260 configurations spanning 6 benchmarks, 5 architectures, and 3 LLM families, single-agent baseline performance is the strongest predictor of whether multi-agent coordination improves or degrades outcomes (P_robust = 0.004). Coordination helps when the base agent is weak; it hurts when the base agent is strong. — Kim et al., Nature Machine Intelligence (2026), DOI: 10.1038/s42256-026-01268-y
- **The ~45% capability-saturation threshold.** A single empirical metric — the single-agent success rate on a representative task sample — predicts with 94% accuracy whether adding agents will help. Below the threshold, coordination compounds individual strengths. Above it, communication overhead and coordination errors erode what the single agent does well. This is not intuition — it is a validated quantitative boundary.
- **Task decomposability beats complexity.** Raw task complexity does not determine MAS success — only the degree to which a task can be decomposed into independent subtasks with verifiable outputs. A complex but monolithic task hurts from multi-agent decomposition; a moderately complex but parallelizable task benefits. Teams systematically misjudge this by conflating "hard" with "decomposable."
- **Coordination drag compounds.** Every inter-agent handoff introduces: summarization loss (compressed context is not equivalent to shared context), belief divergence (agents interpret shared state differently), and retry coupling (one agent's failure triggers cascading retries across the team). These costs are fixed overhead — they don't scale with agent capability, so they dominate for strong agents and vanish for weak ones.
- **More agents widens the evaluation variance.** Single-agent systems produce a consistent failure mode. Multi-agent systems produce N × M failure modes from agent-pair interactions. In production, this means harder debugging, longer MTTR, and wider confidence intervals on quality.

## The move

### Step 1 — Measure the single-agent baseline first

Before spinning up a team, establish the single-agent success rate on a representative task sample. This is the only input the saturation model requires:

```
P_benefit ≈ f(baseline_success_rate, task_decomposability)
```

If the baseline success rate is above ~45%, run the predictive model before adding agents. Do not add agents on intuition.

### Step 2 — Assess task decomposability (the second axis)

A task is genuinely decomposable if:

- Subtasks are independently verifiable (each has a ground-truth output)
- Subtasks have minimal data dependencies between them
- The orchestration step (merging results) is deterministic or trivially correctable

If any subtask requires context from another to be correctly solved, the task is not decomposable — and multi-agent coordination will produce a hybrid result that is worse than a single capable agent's.

### Step 3 — Use the capability-saturation predictor

From Kim et al. (Nature Machine Intelligence 2026), across 260 configurations:

| Baseline Success Rate | MAS Coordination Effect |
|---------------------|------------------------|
| < 30% | Strongly beneficial — agents compensate for individual weakness |
| 30–45% | Marginally beneficial — gains from specialization |
| 45–60% | Neutral — coordination overhead cancels specialization gains |
| > 60% | Harmful — coordination drag exceeds coordination benefit |
| > 80% | Actively degrading — multi-agent consistently underperforms single agent |

The predictor achieves R² = 0.373 (cross-validated) and selects the best architecture in 87% of held-out configurations. It is not a universal law — it is a practical selection rule with empirical grounding.

### Step 4 — If coordination is warranted, minimize coordination cost

When the model recommends multi-agent:

- Prefer **sequential workflows with optional loops** over fully parallel teams (Sander et al., arXiv:2607.27942, TUM, Jul 2026). Sequential handoffs preserve context where it matters; parallel branches introduce summarization loss.
- Use **summary-based group communication** — agents communicate via synthesized summaries rather than full transcripts. This reduces token cost and summarization noise at the cost of information loss; the tradeoff favors strong agents less than weak ones.
- Implement **elastic feedback**: dynamic adjustment of agent interactions based on intermediate results. Agents that are contributing should continue; agents producing conflicting outputs should be gated before their output propagates.
- Design for **P1 (Simplicity)** first. Every additional agent adds a coordination edge. The marginal benefit of agent N must exceed the marginal coordination cost of edge (N, N+1).

### Step 5 — Evaluate with the right metric and adequate seeds

Multi-agent systems have wider run-to-run variance than single-agent systems. A single-run evaluation on a multi-agent configuration is unreliable:

- Run at minimum **5 seeds** per configuration
- Report **median or worst-case** performance, not mean — the mean hides the tail where coordination failures accumulate
- Track **coordination cost**: the ratio of orchestration tokens to productive tokens. A ratio > 0.5 is a signal that agents are spending as much energy coordinating as working.

## Receipt

> Verified 2026-07-31 — Research basis: Kim et al., Nature Machine Intelligence (2026), DOI: 10.1038/s42256-026-01268-y. 260 configurations, 6 benchmarks, 5 architectures, 3 LLM families. ~45% capability-saturation threshold validated at 94% accuracy. R² = 0.373 cross-validated. Architectural selection at 87% held-out accuracy. Sander et al., arXiv:2607.27942 (TUM, Jul 2026) corroborates P1 simplicity, sequential workflows, and summary-based communication as the four grounded design principles. Capability saturation concept independently operationalized as interactive calculator at capabilitysaturation.com.

## See also

- [S-1930 · The Diminishing Returns Stack](/stacks/s1930-the-diminishing-returns-stack-when-you-reach-for-multi-agent-orchestration-before-you-need-it.md) — the architectural intuition layer; this entry provides the quantitative model that confirms or rejects the intuition
- [S-998 · The Capability Ceiling Stack](/stacks/s998-the-capability-ceiling-stack-when-your-agent-ships-but-stalls-on-hard-tasks.md) — single-agent ceiling and escalation; this entry covers when escalation to multi-agent backfires
- [S-1013 · The Multi-Agent Boundary Stack](/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state coordination failures between agents; the coordination drag this entry describes is the mechanism behind the saturation effect
