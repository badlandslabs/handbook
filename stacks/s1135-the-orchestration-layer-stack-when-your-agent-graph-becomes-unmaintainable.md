# S-1135 · The Orchestration Layer Stack — When Your Agent Graph Becomes Unmaintainable

You built a working prototype. One agent, a few tools, a prompt that fit on one screen. Then the product owner said it needs branching logic, parallel research, human approval at step three, crash-safe resumption after a Thursday deploy, and cost attribution per request. Your single-agent loop cannot do this. You need an orchestration layer — and choosing the wrong one, or building one yourself, is how a two-week prototype becomes a six-month refactor.

## Forces

- **Single-agent loops are fine until they aren't.** A straight ReAct loop (reason → act → observe → repeat) handles linear tasks well. The moment you need two branches, two agents, or a pause-for-human step, the loop abstraction breaks. You end up patching the loop with if-statements until nobody can reason about it.
- **Every framework lies about being simple.** CrewAI's "three lines to an agent" is true for the first hour. LangGraph's "graph-based state machine" is true on day three. The Lie of Simplicity migrates teams from CrewAI to LangGraph once they hit branching, human-in-the-loop, or crash-resume requirements — usually after shipping something to users.
- **The graph you can't visualize is the graph you can't debug.** A LangGraph workflow with a dozen nodes, conditional routing, and parallel fan-out is opaque without a diagram. Production debugging requires trace-level observability — not just logs, but per-call token counts, tool call inputs/outputs, and full chain reconstruction.
- **Tool overload is the silent performance killer.** Binding 70+ MCP tools to a single agent creates context pollution. The LLM struggles to identify the right tool for each task. This is not a model problem — it is an orchestration problem.

## The Move

**Start with the workflow shape, not the framework.** The dominant production pattern is a **supervisor-agent hierarchy** — a planner/manager agent that decomposes a task and delegates to specialists, then synthesizes results. This pattern shows up in Anthropic's Research feature, OpenAI's Agents SDK, LangGraph's supervisor example, and CrewAI's agent delegation model. It is the closest thing to a canonical answer that the field has converged on.

Five orchestration patterns that have real-world production backing:

1. **Supervisor / Hierarchical** — A supervisor LLM routes tasks to specialist subagents. Think team lead, not air traffic controller. The supervisor does not need deep expertise in each domain; it needs to know which specialist handles which type of job. Anthropic uses this in its Research feature: an orchestrator plans based on the user query, then spawns parallel subagents that search simultaneously with separate context windows. Subagents facilitate compression — distilling insights from different angles before the supervisor synthesizes.

2. **LLM-as-Router** — A separate LLM call with structured output (a `ToolSelection` schema) analyzes the query and selects the 5–7 most relevant tools before execution. This solves tool overload: binding 70+ MCP tools to one agent degrades performance; dynamic tool selection narrows context to only what the task needs. The routing call costs one extra LLM turn but dramatically improves tool selection accuracy.

3. **Pipeline / Sequential** — Agents chained in order, each consuming the previous agent's output. Used for multi-stage reasoning where each step builds on the prior one: draft → review → edit → publish. Tool for linear workflows, not for anything requiring branching.

4. **Parallel fan-out / fan-in** — One agent spawns N parallel subagents, each working on a slice of the problem. All results converge into a synthesis step. Best for research, data extraction, and any task where independent exploration beats sequential processing. Anthropic's Research system is the canonical example.

5. **Human-in-the-loop with checkpointing** — `interrupt()` in LangGraph pauses execution at a defined node (e.g., before executing a payment or sending an email). State is checkpointed to Postgres. The graph waits. A human approves via `Command(resume={"approved": True})` hours or days later using the same `thread_id`. This is the feature that separates toy demos from finance and operations deployments.

**The practical migration path** (confirmed across r/LangChain, r/LocalLLaMA, and framework comparison threads): prototype in CrewAI for speed, migrate to LangGraph when branching, human approval, or crash-resume enters the requirements. The migration is painful but inevitable for teams that ship to real users.

## Evidence

- **Engineering blog (primary source):** Anthropic's multi-agent research system uses an orchestrator that plans and spawns parallel subagents, each with a separate context window. Published June 13, 2025. Key quote: "Subagents facilitate compression by operating in parallel with their own context windows, exploring different aspects simultaneously before condensing." — [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Engineering synthesis (primary source):** LangGraph's five core orchestration patterns — Supervisor, LLM Router, Pipeline, Parallel fan-out/fan-in, and Human-in-the-loop — validated across r/LangChain and r/LocalLLaMA community discussions. The interrupt/resume checkpointing pattern is described as "the feature r/LangChain threads say separates toy demos from finance/ops deployments." — [ideatomvp.ai](https://ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026), June 2026

- **Framework comparison (synthesis of primary sources):** LangGraph gives full state-machine control and token tracking; CrewAI gives the fastest path to a working role-based prototype. The common production pattern: prototype in CrewAI, ship in LangGraph. AutoGen models agent interaction as a conversation (critique → execute → critique loop); better suited for code review and debate-style problems than for production pipelines. Token overhead in CrewAI is ~56% more per request compared to hand-rolled state machines. — [groovyweb.co](https://www.groovyweb.co/blog/crewai-vs-langgraph-vs-autogen-framework-comparison-2026), 2026

## Gotchas

- **Do not build the orchestration layer by hand.** Teams that start with a custom while-loop + if-statement agent inevitably rebuild it in LangGraph six weeks later. The build-vs-buy calculus here is strongly toward "buy" (LangGraph or equivalent) because the edge cases — cycles, branching, checkpointing, interrupt-and-resume — are all solved problems in the frameworks.
- **Do not give agents 70 tools.** Dynamic tool selection (LLM router → top 5–7 tools) outperforms giving the agent the full tool list. The LLM's tool selection degrades significantly past ~15 tools, and context pollution from irrelevant tool descriptions compounds the problem.
- **Token duplication in multi-agent systems is a real cost.** Measured token overhead ranges from 53% (AgentVerse) to 86% (CAMEL) versus a single-agent baseline. Budget for this in cost estimates — it is not a rounding error.
- **The graph you cannot diagram is your blind spot.** Before going to production, draw the LangGraph (or equivalent) as nodes and edges. If you cannot explain the routing logic to a colleague in under two minutes, the production debugging session will be a nightmare.
