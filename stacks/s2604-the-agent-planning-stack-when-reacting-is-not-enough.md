# S-2604 · The Agent Planning Stack — When Reacting Is Not Enough

Your agent takes five steps to answer a simple question. Fine. But when the task is "migrate our customer database to the new schema while preserving all relationships and notifying the ops team," your ReAct loop burns 47 tool calls and outputs garbage — because it never stopped to think through the steps first. Reactive agents are reliable at trivial tasks and dangerous at complex ones.

## Forces

- **ReAct loops are cheap to build and expensive to run** — each iteration costs a model call, and without planning, the agent re-discovers the same sub-problems across every loop cycle.
- **Planning feels premature** — you don't know all the steps until you start. But shipping into production without a plan means every failure mode is discovered on your infrastructure, not in design.
- **Plan-then-act trades flexibility for predictability** — a rigid plan can miss context that only emerges mid-execution, but a fully reactive agent can never escape its immediate context window.
- **The 2025 enterprise shift** — second-wave production agents (2025+) moved from reactive loops to plan-then-act architectures because step explosion and cost variability were killing ROI.

## The move

Break the work into explicit phases before tool execution begins. The pattern that emerged across production deployments in 2025–2026:

- **Decompose upfront** — on task receipt, run a dedicated planning step: break the goal into ordered sub-tasks, identify dependencies, and assign each a responsible "node" in a graph. Don't let the model discover sub-problems during execution.
- **Validate the plan** — sanity-check the decomposition against known constraints (permissions, API rate limits, data schema). Block (Square/Cash App) found that plans failing this check early saved 10x the cost vs. discovering the failure mid-execution.
- **Execute with checkpointing** — each sub-task completes with a state checkpoint. If execution fails, the agent resumes from the last checkpoint rather than re-running the full plan. This is the key differentiator between a plan and a script.
- **Replan only at decision nodes** — allow mid-course corrections, but gate them: the agent can deviate from the plan only at explicitly marked decision points, not whenever it feels uncertain.
- **Persist plan state** — the plan graph itself is stored, not just the conversation history. This enables the agent to answer "where am I in the execution" without re-parsing prior context.
- **Human checkpoint for high-stakes steps** — any sub-task tagged as destructive (delete, write, send) requires explicit human confirmation before execution, even if the plan says to proceed.

## Evidence

- **CMU research (Routine Framework, 2025):** A structural planning framework for LLM agents in enterprise settings found that first-wave reactive architectures suffered from "step explosion, context fragmentation, and cost variability caused by frequent execution loops." The second wave adopted plan-then-act with explicit task decomposition, tool orchestration, and checkpoint-based recovery. — [arXiv:2507.14447](https://arxiv.org/pdf/2507.14447v1)
- **AWS ML Blog (text-to-SQL agent, May 2025):** An HN-linked AWS post documented a text-to-SQL agent using an LLM loop with tool use — the model generates a query, runs explain plans, inspects errors, then loops to refine. The key insight: the agent plans its own query construction rather than relying on a single-shot prompt. — [AWS ML Blog](https://aws.amazon.com/blogs/machine-learning/build-a-robust-text-to-sql-pipeline/), [HN discussion](https://news.ycombinator.com/item?id=43998472)
- **Block / Goose MCP agent (2025):** Block's internal agent Goose uses MCP architecture with in-house MCP servers. Their approach involves explicit planning-phase integration — the agent decomposes requests before tool execution rather than discovering tools dynamically mid-loop. — [NSA MCP Security Report](https://www.nsa.gov/Portals/75/documents/Cybersecurity/CSI_MCP_SECURITY.pdf), [Angie Jones on LinkedIn/YT](https://www.youtube.com/watch?v=rT02gylPWiI)
- **Simon Willison (cited in agent implementations, 2025):** A widely-referenced ReAct implementation pattern based on Willison's approach uses explicit thought/action/observation loops as the base, with the critical addition that the loop terminates with a final answer — not a tool call. Production variants add planning nodes before the loop starts. — [GitHub: mattambrogi/agent-implementation](https://github.com/mattambrogi/agent-implementation)

## Gotchas

- **Planning overhead is real** — a planning step adds one model call per task. For trivial tasks, this adds 30–50% latency with zero benefit. Gate planning on task complexity: simple lookups don't need it; multi-step operations with dependencies do.
- **Plans become stale** — external state can change between planning and execution. A plan to "archive all orders from 2023" is wrong the moment a new 2023 order arrives. Build plan-revalidation checkpoints for long-running executions.
- **Over-planning is a failure mode** — some teams build agents that spend more tokens planning than executing. The sweet spot is 1–3 planning steps before execution begins; more is usually architecture theater.
- **Replan gating is hard to implement correctly** — it's tempting to let the agent replan whenever it wants "for flexibility," but this recreates the reactive loop problem. Decision nodes must be explicit and bounded.
