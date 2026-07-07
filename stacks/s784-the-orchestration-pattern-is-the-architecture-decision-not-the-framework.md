# S-784 · The Orchestration Pattern Is the Architecture Decision, Not the Framework

When you need multiple agents to work together, the first question most teams ask is "LangGraph or Temporal or AutoGen?" This is the wrong question. The framework is an implementation detail. The orchestration pattern is the architecture — it determines latency, failure behavior, cost ceiling, and whether your system handles 5 agents or 50.

## Forces

- **Framework-first leads to pattern mismatch.** Picking a framework before choosing an orchestration pattern means you get whatever model-of-work the framework defaults to, which may not fit your problem's shape.
- **Patterns aren't mutually exclusive.** Production systems combine 2–3 patterns within a single workflow, but teams that don't name their patterns explicitly can't reason about where each one applies.
- **The complexity ladder has a right answer at every rung.** Multi-agent orchestration is the right answer for a narrow band of problems. Above it, you're paying coordination overhead you don't need. Below it, a single agent with tools would suffice.
- **Context passing is the hard part, not tool calling.** Frameworks give you tool abstractions easily. The architecture decision is how context — findings, partial results, shared state — flows between agents who may run in parallel, sequentially, or on separate schedules.

## The move

**Name the orchestration pattern before touching the framework.**

1. **Start at the bottom of the complexity ladder.** Single LLM call → single agent with tools → multi-agent orchestration. Only escalate when the lower rung genuinely fails (a single agent hitting context limits or tool bloat, not a feeling that "this could be more modular").

2. **Match the pattern to the problem shape.** Supervisor (one orchestrator delegates to specialists) for exploratory research. Sequential Pipeline (output of agent N feeds agent N+1) for deterministic multi-step tasks. Fan-Out/Fan-In (one trigger spawns parallel agents, a reducer collects results) for parallel exploration of independent subtasks. Evaluator-Optimizer (a producer generates, a critic judges, they loop until quality threshold) for content that needs iterative refinement.

3. **Treat the framework as a substrate, not a solution.** DAG-based frameworks (LangGraph, Temporal, Dagster) work well for explicit dependency graphs. Event-driven (Kafka + A2A + MCP) for reactive, async consumption. Actor model (AutoGen/MAF) for isolated state and supervision hierarchies. Many teams in production end up writing custom orchestration logic on top of a message queue because no framework fits their exact pattern mix.

4. **Design context flow explicitly.** The HN practitioner consensus: treat the full conversation thread as the context window, not just the latest message. Every prior result from a specialist agent, every piece of research, flows through to downstream agents. Without explicit context-passing architecture, parallel agents produce results the coordinator can't use.

5. **Combine patterns in layers, not alternatives.** Anthropic's own Research system uses a lead agent that plans and spawns parallel agents — a Supervisor spawning Fan-Out workers — followed by a synthesis step. The architecture is hierarchical on top, parallel in the middle, sequential at the output. No single pattern owns the whole workflow.

6. **Calibrate confidence thresholds for autonomous vs. escalatable action.** In high-stakes domains (sales, medical, legal), the cost of an agent acting on low-confidence output exceeds the cost of delay. Build explicit confidence-gated escalation: if confidence < threshold, surface for human review. The orchestrator is responsible for this judgment, not the individual agent.

## Evidence

- **HN Ask thread (production practitioners):** A sales team runs a Supervisor pattern where a thin orchestration layer routes bounded tasks (research → draft → send → parse reply) end-to-end. Full conversation thread — including prior prospect research — passes through every agent. Critical design: agents own clearly scoped tasks; the orchestrator's only job is sequencing and routing, not doing. — [Ask HN: How are you orchestrating multi-agent AI workflows in production?](https://news.ycombinator.com/item?id=47660705)

- **Anthropic Engineering Blog (June 2025):** Claude's Research feature uses a lead planner agent that dynamically decomposes queries and spawns parallel agents for simultaneous exploration, each with an independent context window. A synthesis step collects and distills results. The architecture layers Supervisor (planner) over Fan-Out (parallel workers) over Sequential (synthesis). Key lesson: "The research team found that separating the planning agent from the execution agents — each with their own context — was essential for preventing context pollution." — [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Azure Architecture Center / Zylos Research (2026):** Three architectural schools crystallize across production deployments: DAG-based (deterministic, explicit dependencies), Event-Driven (async pub/sub, reactive), and Actor Model (isolated state, supervision hierarchies). Critically: "These patterns are not mutually exclusive. Most production systems blend them." Enterprise production systems layer 2–3 patterns. — [AI Agent Orchestration Patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns) and [Agent Workflow Orchestration Patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)

## Gotchas

- **Starting multi-agent when single-agent-with-tools suffices.** The complexity ladder exists for a reason. If one agent can reasonably call the necessary tools in sequence, adding coordination overhead buys you modularity at the cost of latency and failure surface. Only escalate when a single agent genuinely hits context limits or role confusion.
- **No explicit stop condition on the coordination loop.** Parallel agents can produce conflicting results. Sequential pipelines can diverge. Without a defined termination condition — a confidence threshold, an iteration cap, a human approval gate — agents loop indefinitely or return partial output as if it were complete.
- **Context grows unbounded between orchestration steps.** Each agent handoff passes accumulated context. Without explicit summarization or compression at handoff boundaries, context windows saturate mid-workflow. Anthropic's research system uses a "distill" step specifically to prevent this.
- **The "all-hands" pattern where every agent talks to every other agent.** Point-to-point communication topology doesn't scale. As agent count grows, the number of communication channels grows as O(n²). Supervisor or Router patterns with explicit routing maintain sanity.
