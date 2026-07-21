# S-1441 · The Multi-Agent Coordination Stack — When Your Single Agent Hits a Ceiling and You Add Another

Your single agent handles one-off questions well. Add a second step and it degrades. By step five, it's inventing intermediate results. By step ten, the context window is so packed that the model's reasoning quality on the actual task drops by up to 73% — a figure documented by Comet ML in production evaluations of monolithic agent pipelines. You need multiple agents working together, but coordination is its own hard problem.

## Forces

- **Single-agent ceilings are real and documented.** A single agent with broad tool access suffers "Lost in the Middle" context degradation, persona bleeding, and buried guardrails. The monolithic "God Prompt" approach stops scaling past 3-5 tool steps.
- **Multi-agent complexity is non-trivial.** Spawning multiple agents introduces coordination overhead, inter-agent communication, consensus/termination logic, and race conditions that don't exist in single-agent systems.
- **Architectural choice constrains everything downstream.** Picking the wrong coordination pattern — or no pattern at all — leads to agents that duplicate work, contradict each other, or spin indefinitely.
- **State persistence is load-bearing.** Enterprise workflows crash mid-execution (rate limits, approvals, restarts). Without durable state, you can't resume a half-completed multi-step task without re-running completed steps at full cost.
- **Tool overloading is a failure mode too.** Giving agents too many tools without clear scope boundaries causes decision paralysis — the agent spends more tokens evaluating *which* tool to use than using tools.

## The Move

The pattern that ships in 2026 is **orchestrator-worker multi-agent architecture** with **graph-based state management** and **explicit coordination boundaries**. Specific moves:

- **Start with the orchestrator-worker pattern** for open-ended, path-dependent tasks (research, analysis, planning). A lead agent decomposes the goal and spawns parallel specialized subagents that operate concurrently. Anthropic documented this pattern in their own production Claude Research feature (June 2025): "a lead agent planning and spawning parallel subagents for simultaneous exploration."
- **Choose coordination patterns based on task shape:** Microsoft Azure Architecture Center's taxonomy — **sequential** for linear dependency chains, **concurrent** for independent parallel work, **group chat** for synthesis of perspectives, **handoff** (Anthropic's model) for explicit transfer of control, and **magentic** for emergent specialization.
- **Checkpoint state at every node transition.** LangGraph (12M downloads/month, 400+ enterprise users including Uber, LinkedIn, Klarna, J.P. Morgan) automatically checkpoints full graph state after each node execution. This enables durable resume: crash mid-migration, resume from the last successful node, not from scratch.
- **Scope each agent's tools to its role.** Anthropic's advanced tool use (Nov 2025) introduced the Tool Search Tool so agents can discover tools dynamically on-demand rather than loading every tool definition into every context. For systems not using dynamic discovery: explicit tool namespaces per agent role prevent decision paralysis.
- **Terminate with explicit conditions, not silence.** Parallel workers need defined stopping criteria: a maximum number of iterations, a quality threshold, or a supervisor-agent gate that evaluates outputs before returning to the orchestrator.

## Evidence

- **Engineering blog (primary source):** Anthropic's Claude Research feature uses a multi-agent system with orchestrator-worker pattern — a lead agent decomposes goals and spawns parallel specialized subagents. Published June 13, 2025 by Jeremy Hadfield, Barry Zhang, et al. — https://www.anthropic.com/engineering/multi-agent-research-system
- **Architecture documentation:** Microsoft Azure Architecture Center enumerates five multi-agent orchestration patterns (sequential, concurrent, group chat, handoff, magentic) with guidance on when each applies. Updated February 2026. — https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns
- **Enterprise production (primary source):** LangGraph in Fortune 500 production — LinkedIn uses it for a SQL bot that finds tables, writes queries, detects and fixes its own errors, and enforces access permissions. Uber and Klarna run stateful multi-agent workflows with graph-based checkpointing. 12M monthly downloads, 400+ companies on LangGraph Platform. — https://agentmarketcap.ai/blog/2026/04/08/langgraph-fortune-500-production-stateful-multi-agent-workflows

## Gotchas

- **Static role assignment is fragile.** Defining exact agent roles and conversation flows upfront in rigid configs works for predictable pipelines but breaks for open-ended research tasks. The orchestrator should dynamically decompose goals, not follow a pre-scripted choreography.
- **Full context passing to every parallel agent multiplies token cost.** In concurrent execution, avoid flooding every subagent with the full conversation history — use structured briefing documents or scoped context windows per agent role instead.
- **Agents that spawn sub-agents that spawn more sub-agents can spin indefinitely.** Without explicit max-depth or supervisor-gate termination conditions, parallel workers keep generating new tasks. Set hard bounds on agent spawn depth and iterations from the start.
