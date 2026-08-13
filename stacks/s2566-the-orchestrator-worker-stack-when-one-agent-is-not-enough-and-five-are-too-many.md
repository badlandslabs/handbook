# S-2566 · The Orchestrator-Worker Stack — When One Agent Is Not Enough and Five Are Too Many

A single agent handles your first use case cleanly. Then branching logic appears, parallel research is needed, and someone asks for a human approval gate before the final step. You reach for another agent. Then another. Now you have five agents with no clear ownership, shared state that lives in Slack threads, and a system that is harder to debug than what you started with. This stack gives you the minimum necessary structure: a single orchestrator that plans and aggregates, paired with specialized workers that do the actual work.

## Forces

- **Adding agents before you need them multiplies failure surface.** Every agent-to-agent handoff is a potential point of failure: wrong context passed, stale data returned, or a worker that silently takes a wrong approach.
- **Starting too simple locks you out of the capability you actually need.** A single-threaded agent with 10 tools works until you need parallel research with a human approval gate — then the refactor is expensive.
- **Orchestration is not a framework problem; it is a boundary problem.** The question is not "which framework?" but "what does each agent own, and who decides what happens next?"

## The move

**Use the orchestrator-worker pattern as your default starting point. Add agents only when a clear boundary of ownership emerges.**

The orchestrator-worker pattern (hub-and-spoke) is the most common production pattern and the right one for most complex tasks. A central orchestrator agent owns the top-level goal, decomposes it into subtasks, dispatches work to specialized workers, and aggregates results. Workers do one thing well and return their output to the orchestrator.

Key implementation decisions:

- **One orchestrator, minimum workers.** Anthropic's engineering team explicitly recommends using as few agents as possible — "every handoff between agents is a potential break in context and coherence." Start with 1 orchestrator + 2 workers. Only add a third when a distinct ownership boundary genuinely exists.
- **Workers are specialized by role, not by topic.** A "researcher" agent searches the web; a "writer" agent drafts the report. Not "fintech-researcher" and "healthcare-researcher." Role-based specialization keeps workers reusable across tasks.
- **Context separation is a feature, not a workaround.** Anthropic's research system deliberately uses context separation between subagents to "reduce path dependency" — each worker starts fresh from the orchestrator's instructions, avoiding the drift that comes from carrying full conversation history through a long task.
- **Structured output from workers, always.** Workers return structured artifacts (JSON, markdown sections) rather than free text. The orchestrator parses these programmatically rather than extracting information from natural language — this is the single biggest improvement for production reliability.
- **Fan-out parallelism for independent subtasks.** When workers have no data dependencies (e.g., searching three different sources simultaneously), fan them out in parallel and merge results. This is where multi-agent systems earn their complexity cost — a 3x speedup on parallel research tasks.
- **Use LangGraph when state machine semantics are needed.** LangGraph (the most-cited production framework in 2025-2026 community discussions) is the right tool when you need branching logic, crash-safe resumption, or auditability. For simple sequential tasks, a plain Python loop calling an agent is easier and more debuggable.

## Evidence

- **Engineering Blog — Anthropic "How We Built Our Multi-Agent Research System":** Anthropic's Research feature uses an orchestrator-worker pattern where a lead agent plans research processes and spawns parallel subagents to search the web and Google Workspace simultaneously. Key lessons: "context separation" reduces path dependency, "distributed compression" before returning to the lead prevents context overflow, and the system explicitly uses hierarchical decomposition to handle tasks that no single agent context window can hold. — [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Engineering Blog — Google Developers "Architecting Efficient Context-Aware Multi-Agent Framework for Production":** Google's Agent Development Kit (ADK) formalizes context as "a compiled view over a richer stateful system — not a mutable string buffer." Documents the three-way pressure of cost, latency, and context explosion that forces teams into multi-agent architectures, and provides ADK's tiered context architecture as the solution. Specifically recommends compiled views to avoid passing verbose tool payloads through every agent handoff. — [developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production](https://developers.googleblog.com/architecting-efficient-context-aware-multi-agent-framework-for-production)
- **Community Synthesis — Idea to MVP "Agent Orchestration with LangGraph" (Jun 2026):** Synthesizes recurring Reddit and X community consensus that LangGraph has become the default for multi-agent production when teams need branching, parallelism, durable resumption, or auditability. Confirms the "use LangGraph when you need cycles, not chains" principle — DAG-based chains handle sequential workflows, but state machines are required for loops, approvals, and branching based on tool output. — [ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026](https://ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026)
- **Production Guide — ExplainX "Multi-Agent Orchestration Patterns" (Jun 2026):** Documents the five core patterns (orchestrator/worker, pipeline, fan-out, fan-out/fan-in, debate) with tradeoffs. Key finding: the orchestrator/worker pattern is the most flexible and the most commonly adopted, but carries the highest coordination overhead. Fan-out is best for parallel independent tasks where speed matters more than sequential refinement. — [explainx.ai/blog/multi-agent-orchestration-patterns-guide-2026](https://explainx.ai/blog/multi-agent-orchestration-patterns-guide-2026)

## Gotchas

- **Do not pre-optimize for multi-agent.** The most common mistake is building a three-node LangGraph before confirming that a single agent with 3-5 scoped tools cannot handle the task. A sequential agent loop is 10x easier to debug.
- **Workers that accumulate their own context cause silent failures.** If a worker maintains its own conversation history across calls, it will develop path dependency and diverge from the orchestrator's intent. Each worker should receive a fresh context per invocation, with the orchestrator controlling what history is passed.
- **Fan-out without a merge step produces fragmented results.** Sending 5 workers in parallel and concatenating their outputs is not the same as merging them. A merge step (orchestrator review, cross-reference, or a dedicated synthesis agent) is required to produce coherent output from parallel work.
- **Cost and latency scale non-linearly with agent count.** Every agent handoff is an additional LLM call. A 3-worker fan-out with a merge step is 5 calls minimum. For simple tasks, this adds 3-5x latency and cost over a single agent call.
