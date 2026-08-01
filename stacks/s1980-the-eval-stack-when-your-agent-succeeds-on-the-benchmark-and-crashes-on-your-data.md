# S-1980 · The Eval Stack — When Your Agent Scores High and Ships Badly

*When your agent nails the benchmark, then quietly fails on real users — because you were measuring the wrong things. Eval engineering is the discipline of building production-grade measurement before it becomes obvious you needed it. Teams that invest in multi-dimensional eval infrastructure catch failures that aggregate scores miss entirely.*

## Forces

- **Aggregate scores hide where failure happens.** A single "85% success rate" tells you nothing about whether the agent is reaching the right answer via a clean two-step path or a wasteful twelve-step detour that happens to land correctly. Both scenarios register as one point on an aggregate. The cost and latency profiles are radically different.
- **Reliability and consistency are different metrics.** Agents that score 60% on a single run can drop to 25% consistency over 8 runs — empirically measured in enterprise deployments. This makes cost projections unreliable and makes "good enough for now" a trap: the model that looks adequate on one try will fail intermittently in production, and intermittent failures are harder to debug than consistent ones.
- **The belief-execution gap is 57 percentage points wide.** 72% of AI teams strongly believe comprehensive testing drives reliability. Only 15% achieve elite eval coverage (90–100% of behaviors tested). The gap is not knowledge — teams know eval matters. The gap is operational execution: building the infrastructure to measure continuously, not just at release time.
- **Spec failures dominate multi-agent failures (~42%).** Specification errors — wrong tool definitions, missing edge cases in instructions, incorrect preconditions — account for nearly half of production failures in multi-agent systems. These are invisible without structured eval.

## The Move

Build eval infrastructure across four independent dimensions. Measure each separately. Never reduce to a single aggregate until you can explain each component.

**1. Trajectory — did the agent take a sensible path?**
- Track step count, unnecessary tool calls, detected loops/retries, correct ordering of required steps
- Flag "Scrappy Wins": tasks completed correctly but with excessive retries, backtracking, or wasted tool calls
- Langfuse calls this "Trajectory Accuracy" — the agent can reach the goal and still be operationally wrong

**2. Tool Use — did it call the right tools correctly?**
- Correct tool selected, arguments valid, tool error rate, recovery after tool failure
- Tool-use errors are often invisible in the final answer — the agent eventually recovers, but burned tokens and time are not recovered
- Langfuse's Context Intelligence patterns show agents re-executing the same mistake until enterprise-specific guidance is surfaced — tool-level eval catches this, final-answer eval misses it

**3. Task Success — did it actually accomplish the goal?**
- Binary or graded outcome: task completed / partially completed / failed
- Ground against known-good reference trajectories for golden cases
- For open-ended tasks, use LLM-as-judge with pairwise trajectory comparison (Plan-RewardBench style) — pairwise is more reliable than scalar rating per recent empirical work

**4. Robustness — does it hold under variation?**
- Run the same eval across 8+ seeds and measure consistency
- Adversarial variant testing: malformed inputs, edge cases, permission boundaries
- Cost-controlled evaluation: track tokens-per-task to catch agents that achieve high accuracy at 50x the cost of a simpler approach

**Operational discipline:**
- Multi-layer measurement: session-level (outcome), trace-level (full execution path), span-level (individual tool call)
- The 70/40 Rule: aim for 70%+ behavior coverage AND 40%+ of development time invested in eval — one without the other is insufficient
- Continuous evaluation in production via sampling and automated LLM grading, not just pre-release test suites
- Cluster analysis of failure traces to find patterns before they become incidents

## Evidence

- **Engineering blog:** Langfuse's four-dimension eval framework (Trajectory, Tool Use, Task Success, Robustness) — measures each independently because a single score conflates "got the right answer via the wrong path" with "got the right answer cleanly." They demonstrate that LangChain agents with Context Intelligence hit 100% Trajectory Accuracy vs. baseline agents that retry the same mistake. — [langfuse.com/resources/engineering/ai-agent-evaluation](https://langfuse.com/resources/engineering/ai-agent-evaluation)
- **Research report:** Galileo's State of Eval Engineering (2025–2026) found only 15% of teams achieve elite eval coverage (90–100% of behaviors tested) despite 72% believing it drives reliability — a 57-point belief-execution gap. Introduces the 70/40 Rule: elite teams use multi-layer measurement (session/trace/span) and invest proportionally in eval time. — [galileo.ai/blog/ai-agent-metrics](https://galileo.ai/blog/ai-agent-metrics)
- **Engineering blog:** Anthropic's "Effective Harnesses for Long-Running Agents" — establishes three-agent harness (Initializer, Coding, Evaluator) to maintain state across context windows. Progress files, completion criteria, and structured context management are the foundation — not prompt engineering. — [anthropic.com/engineering/effective-harnesses-for-long-running-agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- **Community resource:** Vectara's awesome-agent-failures — curated taxonomy of production failure modes including tool hallucinations, context overflow, loop detection gaps, and response halucination. Suggests mitigation patterns per failure type. — [github.com/vectara/awesome-agent-failures](https://github.com/vectara/awesome-agent-failures)
- **Research paper:** CLEAR framework (Cost, Latency, Efficacy, Assurance, Reliability) — empirically shows 50x cost variation between agents achieving similar accuracy, and consistency dropping from 60% (single run) to 25% (8-run consistency). — [arxiv.org/html/2511.14136](https://arxiv.org/html/2511.14136v1)
- **Case study:** TechBuddies Studio 8-week LangChain vs AutoGen evaluation (April 2026) — custom implementations delivered 23% lower costs, 50% lower error rates vs framework defaults. Key finding: default framework configurations underperform tuned custom pipelines across all dimensions. — [techbuddies.io](https://www.techbuddies.io/2026/04/09/case-study-building-production-ai-agents-with-langchain-vs-autogen-real-results-in-2026/)

## Gotchas

- **Synthetic benchmarks are not production measurement.** SWE-bench, WebArena, and GAIA can be gamed — teams have achieved near-perfect scores with single-character changes. Real eval uses production traffic sampling and structured human review, not leaderboard chasing.
- **Adding eval late is nearly worthless.** Eval infrastructure built after the agent ships catches only the failures users report. The 57-point coverage gap exists because teams retrofit measurement instead of building it upfront. Start with the four dimensions on day one.
- **Human review does not scale but remains the ground truth.** LLM-as-judge reduces cost dramatically and works for trajectory comparison, but it introduces positional bias and presentation effects. Pairwise evaluation with controlled order-swapping mitigates this. Acknowledge that human-in-the-loop review is irreplaceable for nuanced, high-stakes decisions.
