# S-2475 · The Orchestration Complexity Stack — When the Graph Has More Nodes Than Your Entire Codebase

You start with a single LLM call. Six months later, your agent system has a directed graph with 23 nodes, 4 subgraphs, conditional branching on LLM outputs, a coordinator agent, two supervisor agents, and 14 tool definitions. Nobody on the team can trace a request through the full execution path. This is the orchestration complexity trap: the graph grows to match the team's ambition, not the problem's difficulty.

## Forces

- **Simplicity wins on simple problems.** Anthropic's engineering team — which built Claude Code and the Agent SDK — consistently finds that the most successful implementations use "simple, composable patterns rather than complex frameworks." Their recommendation: start at single LLM, move to workflows, only reach for agents when the prior level genuinely fails.
- **Multi-agent coordination creates hidden coupling.** When agents share state, message queues, or memory, they couple at the infrastructure level even when the architecture diagram shows independent nodes. The coupling is invisible in the code and surfaces only under production load.
- **The framework shapes your thinking.** LangGraph (explicit state machines) leads you toward graph design. CrewAI (role-based) leads you toward agent proliferation. AutoGen (conversational) leads you toward multi-turn dialogue patterns. Each framework makes certain patterns natural and others painful — which means framework choice is the most consequential early architecture decision.
- **Operational knowledge lives in markdown, not code.** Ultrathink's 10-agent production system stores agent definitions as markdown files in `.claude/agents/`, with the master coordination document reaching nearly 500 lines. The operational rules that make multi-agent systems work are documentation problems, not code problems.

## The Move

Orchestrate at the minimum complexity level the problem demands, and enforce a "complexity ceiling" that requires explicit justification to raise.

**Pattern selection ladder (in order of increasing complexity):**

- **Single LLM call** — retrieval + in-context examples. Handles 60–80% of use cases.
- **Sequential chain** — Model A output → Model B input. For strict linear dependencies: extract → validate → store; summarize → classify → route.
- **Router pattern** — One LLM classifies the task, dispatches to a specialized agent. Works for independent domains that never need to collaborate mid-task.
- **Plan-and-execute** — One planner LLM decomposes the task, a separate executor LLM runs the steps. Useful when planning quality matters more than execution speed.
- **LLMCompiler** — Planner generates a task DAG, then parallel-fetches tool arguments before executing. Cuts latency on independent tool calls.
- **Supervisor/hierarchy** — One coordinator agent manages a tree of specialized agents. Children communicate only through the supervisor. Best for complex tasks requiring cross-domain collaboration.
- **Multi-agent debate** — Two or more agents argue positions, a judge resolves. Best for high-stakes decisions with a clear correctness criterion.

**Enforce a complexity ceiling:**
- If a new requirement maps to a pattern already in the ladder, implement it at that level — don't add a new pattern.
- New tool definitions require the tool to appear in exactly one agent's scope, never two.
- If two agents need to coordinate mid-task, that's a signal to introduce a supervisor, not a point-to-point channel.
- Track the graph: if the directed graph has more than 15 nodes, pause and ask whether the problem needs splitting or the agents need consolidating.

## Evidence

- **Anthropic Engineering:** Documents the pattern ladder with explicit guidance to "start simple, increase complexity only when needed." Their production agents (Claude Code, Agent SDK) use the while-loop-with-tools architecture — a graph of 3–4 nodes, not 20. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Microsoft ISE Developer Blog (Lily Jia, June 2026):** Documents the transition from a modular monolith with router pattern (one agent per query) to a coordinator microservices architecture for a retail customer. Key insight: the router pattern was insufficient when a single complex query required multiple specialized agents collaborating, so they introduced a coordinator agent that manages a tree. — [devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **Ultrathink (AI-operated e-commerce, March 2026):** Ran 10 specialized agents (CEO, coder, QA, designer, product, security, marketing, social, operations, customer success) across 2,500+ tasks. Architecture: work queue → spawn Claude Code processes → heartbeat monitor → dependency graph chains → QA gates. Stack: Mac Mini, SQLite, `Process.spawn`. No Kubernetes, no message broker. Published the full agent definition kit as open source. — [ultrathink.art/blog/multi-agent-orchestration-lessons](https://ultrathink.art/blog/multi-agent-orchestration-lessons) and [github.com/ultrathink-art/agent-architect-kit](https://github.com/ultrathink-art/agent-architect-kit)
- **AI Workflow Lab (June 2026):** Benchmarks six orchestration patterns with concrete tradeoffs: sequential (low latency, no branching), router (O(n) routing cost), map-reduce (parallelization), ReAct (flexibility at latency cost), plan-and-execute (planning quality vs. execution speed), multi-agent (coordination overhead). — [aiworkflowlab.dev](https://aiworkflowlab.dev/article/building-multi-agent-ai-systems-2026-architecture-patterns-mcp-production-orchestration)

## Gotchas

- **Most teams over-engineer on first build.** LangChain's 2025 production survey found that simple chains handle 80% of production use cases, yet teams consistently start with multi-agent graphs. The graph grows to absorb organizational complexity that belongs in a process document.
- **LangGraph's graph becomes the bottleneck.** When the orchestration graph has more nodes than your application logic, debugging means reading the graph definition. Reddit threads in 2026 show teams migrating from CrewAI to LangGraph for branching/approval support — then discovering that LangGraph's graph is equally hard to maintain at scale. Treat graph complexity as a debt, not a feature.
- **Tool proliferation is a coupling signal, not a feature.** If your agents collectively need 14+ tools to function, the agent boundaries are wrong. Each tool should map to a capability that belongs in exactly one agent's scope. Tools shared across agents create implicit coupling that the architecture diagram won't show.
- **Prompt optimization plateaus at 85–90%.** Dr. Sarah Chen (Harness Engineering, March 2026) documents that getting from 90% to 97% task completion requires infrastructure engineering — not better prompts. The complexity ceiling isn't just about elegance; it's about where the actual failure modes live.
