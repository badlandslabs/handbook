# S-1930 · The Diminishing Returns Stack — When You Reach for Multi-Agent Orchestration Before You Need It

You have a task that chains three LLM calls. Someone tells you to use LangGraph. Someone else says CrewAI. You spin up a supervisor agent, three worker agents, message-passing state, and a DAG — and the task takes four times as long to build, twice as long to debug, and fails in a new way you didn't know was possible. The majority of agent orchestration failures aren't technical. They're architectural. Teams reach for the most complex pattern on day one.

## Forces

- **The simplicity paradox.** Anthropic's research across dozens of production deployments found the most successful implementations use simple, composable patterns — not frameworks. "The most successful implementations weren't using complex frameworks or specialized libraries." Yet the instinct is always to reach for the agent framework first.
- **Autonomy doesn't scale with complexity.** The real question isn't "chain vs. agent" — it's how much autonomy the LLM needs for this specific task. A document summarization task needs zero autonomy (simple chain). A codebase Q&A task needs some (router pattern). Only open-ended problems with tool use, planning, and recovery need full agent loops.
- **The multi-agent overhead tax.** Multi-agent systems introduce state management, message routing, failure propagation, and observability gaps that don't exist in single-agent designs. The graph becomes unmaintainable before the product is shippable.
- **Framework lock-in is real.** AutoGen moved to maintenance mode. Microsoft consolidated to Agent Framework. Picking a framework for orchestration philosophy (conversations vs. roles vs. state machines) is a long-term commitment that teams routinely make too early.
- **Most teams over-engineer on first build.** LangChain's 2025 production survey found that simple chains handle 80% of production use cases. Community discourse shifted in 2026 from "which framework?" to "how do I orchestrate without the graph becoming unmaintainable?"

## The Move

Match orchestration complexity to actual task complexity. Work up the stack, not down.

**The six-pattern complexity ladder (start at the bottom, move up only when blocked):**

1. **Sequential Chain** — Model A output feeds Model B input. Simple, predictable, easy to debug. Use for: summarize → classify → route. Extract → validate → store. Only breaks down when one step's output format doesn't match the next's, or when latency compounds.
2. **Router Pattern** — A classifier decides which of several chains or prompts to invoke. The LLM acts as a dispatcher, not an executor. Use for: task routing, intent classification, context-aware prompt selection. The simplest pattern that enables branching without full multi-agent complexity.
3. **Parallelization** — Break a task into independent subtasks, run them simultaneously, synthesize results. Use for: multi-document extraction, parallel web searches, multi-source analysis. Zero additional failure risk from splitting — each branch is isolated.
4. **Supervisor-Worker** — A supervisor triggers multiple LLM calls that are then synthesized together. The supervisor owns the orchestration logic; workers are stateless and focused. Use for: complex research tasks, multi-source synthesis, tasks requiring distinct tools per branch.
5. **Evaluator-Optimizer Loop** — One model generates output, another critiques it, the first revises — iterate until the evaluator passes quality. Use for: writing, code refinement, answer improvement. Stops when a quality threshold is met or iteration budget is exhausted.
6. **Multi-Agent Systems** — Specialized agents with distinct roles, each owning their tools and state, coordinating via message-passing or shared state. Use only when: tasks genuinely decompose by role, agents need independent tool access, or you need fault isolation between agents. The graph becomes the source of truth.

**The autonomy-matching rule:** Before choosing a pattern, ask — does this task need the LLM to dynamically direct its own process, or can a human (or simple code) define the path upfront? If the path is definable, use a workflow. If the path must emerge from the model's reasoning, use an agent.

**Framework selection when you do need orchestration:**
- **Going to production with complex stateful workflows** → LangGraph (90K+ GitHub stars, durable state, checkpointing, time-travel debug, used by Uber, LinkedIn, Klarna)
- **Prototyping multi-agent teams fast** → CrewAI (role-based, conversational, fastest setup)
- **All-in on OpenAI models** → OpenAI Agents SDK (tightest integration, minimal boilerplate)
- **Default to code over frameworks** for anything under 500 lines. "Many patterns can be implemented in a few lines of code" — Anthropic

**DoorDash's real-world approach:** DoorDash's agentic-orchestrator (open-source) uses a TUI-based supervisor pattern where a human makes high-level decisions while AI handles research, planning, implementation, code review, and PR — all running concurrently. The key insight: orchestration doesn't mean autonomous. The human remains in the loop for design decisions; the agent handles execution.

## Evidence

- **Anthropic Engineering Guide:** "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks. The most successful implementations weren't using complex frameworks or specialized libraries." Foundational research across dozens of production deployments. — [Anthropic: Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents) (Dec 2024)
- **LangChain Production Survey (2025):** Simple chains handle 80% of production use cases, yet teams consistently over-engineer with agents on their first implementation. — [Agentika citing LangChain production survey](https://agentika.uk/blog/llm-orchestration-patterns.html) (Feb 2026)
- **LangGraph at Scale:** 90K+ GitHub stars, v1.0 stable (Oct 2025). Production deployments at Uber, LinkedIn, and Klarna. The framework treats orchestration as a first-class state machine — enabling checkpointing, time-travel debugging, and crash-safe resume. — [Gheware Framework Comparison](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html) (updated Jun 2026)
- **Community Discourse Shift:** "In early 2026, the loudest thread on r/LangChain is no longer 'which framework should I use?' It is 'how do I orchestrate agents without the graph becoming unmaintainable?'" — [IdeaToMVP: LangGraph Orchestration Patterns](https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026) (Jun 2026)
- **DoorDash Orchestrator:** Open-source TUI for long-running coding agents. Supervisors own design decisions; AI handles execution. 87 GitHub stars, Apache-2.0, 97 commits since May 2026. — [GitHub: doordash-oss/agentic-orchestrator](https://github.com/doordash-oss/agentic-orchestrator)
- **Architectural Convergence:** "By 2025 that approach [chaining LLM calls] had collapsed under its own complexity: deadlocks, state corruption, silent failures, and runaway costs had taught teams that agent coordination deserves the same engineering discipline as distributed systems in general." — [Zylos Research: Agent Workflow Orchestration Patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns) (Apr 2026)

## Gotchas

- **Chains are DAGs; agents need cycles.** If your task has branching and convergence but no looping self-correction, a chain or router pattern is sufficient. You only need a state graph when an agent might need to revisit a prior state.
- **Framework philosophy mismatch kills teams.** AutoGen uses conversations, CrewAI uses roles, LangGraph uses state machines. The choice shapes every architectural decision downstream. Pick the mental model that matches your team's thinking, not the one with the most GitHub stars.
- **AutoGen is in maintenance mode.** Microsoft consolidated to Agent Framework with GA in Q1 2026. If you're on AutoGen, plan migration. Don't start new projects on it.
- **The graph becomes the failure point.** The most common new failure mode introduced by multi-agent orchestration isn't agent behavior — it's graph topology bugs: deadlocks, state corruption on edge cases, and silent message loss between agents.
- **Start single-agent with well-scoped tools before going multi.** Reddit community consensus: a single `create_agent` with 3–5 well-scoped tools beats a three-node graph with extra latency. Multi-agent earns its keep only when context limits bite or tasks genuinely decompose by role.
