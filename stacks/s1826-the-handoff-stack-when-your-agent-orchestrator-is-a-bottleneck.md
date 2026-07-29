# S-1826 · The Handoff Stack — When Your Agent Orchestrator Is a Bottleneck

Your supervisor agent routes every task. It works at first — 3 agents, clean delegation. Then you add 7 more. The supervisor becomes the bottleneck: it handles all routing decisions, holds the full conversation context, and becomes the single point of failure. When it times out, everything stops. The handoff stack fixes this by letting agents transfer control directly, so routing decisions stay distributed and the topology matches the actual workflow.

## Forces

- **Centralized routing collapses under specialization.** A single supervisor that knows all agent capabilities becomes a prompt-bloated bottleneck and a single point of failure. As the team grows, so does the supervisor's context window and routing complexity.
- **Agent-as-tools creates ownership ambiguity.** When the primary agent calls a specialist as a tool, the primary retains responsibility. The specialist can't take follow-up actions, can't escalate cleanly, and can't hand off to a third agent without the primary managing the chain. Real workflows don't follow a tree.
- **Directed graphs need back-edges.** A user asks about a billing issue, the billing agent investigates, then needs a product expert — but the topology was only defined forward. Hardcoding every possible back-edge is brittle; letting agents decide makes the graph dynamic.
- **Context must travel with control.** When an agent hands off, the next agent needs the full conversation state, not just the last message. Most implementations get this wrong and hand off empty.

## The move

The core insight from Microsoft's Agent Framework research and real deployments at scale: **declare the agents and the valid edges between them; let the agents decide when to traverse those edges.** The framework injects the tool calls; developers own the topology and guardrails.

**Key mechanics:**
- **Shared transcript** — a running conversation object that all agents in the handoff chain read and write. When Agent A hands off to Agent B, B receives the full transcript, not just a summary.
- **Explicit transfer of control** — the receiving agent takes full ownership. The handing-off agent is done. No nested call stack, no delegation tree to track.
- **Bounded mesh topology** — agents connect directly without a central router. Developers define which edges are valid; agents choose when to traverse them. This makes back-edges natural (Agent B can hand back to Agent A after a follow-up).
- **Structured output at termination** — handoff terminates cleanly when an agent emits a typed response (e.g., `EndTurn` with a `summary` field), signaling the user should receive the output.
- **Guardrails at the topology level** — routing logic stays with agents; security and permission boundaries stay with the developer-defined graph structure.

**Contrast with alternatives:**

| Pattern | Control | Ownership | Context |
|---------|---------|-----------|---------|
| Supervisor | Central orchestrator decides all routing | Orchestrator retains full responsibility | Orchestrator holds full context |
| Agent-as-Tools | Primary agent delegates | Primary retains responsibility | Primary manages all shared state |
| Handoff | Agents decide within valid edges | Receiving agent takes full ownership | Full transcript travels with control |

## Evidence

- **Microsoft Agent Framework documentation:** The handoff orchestration pattern was designed specifically to solve the case where "agents need follow-ups, ownership changes mid-conversation, or back-edges become necessary." Developers declare participating agents and directed edges; the framework injects the tool calls agents use to transfer control. — [devblogs.microsoft.com/agent-framework/a-tour-of-handoff-orchestration-pattern](https://devblogs.microsoft.com/agent-framework/a-tour-of-handoff-orchestration-pattern)
- **BASF Coatings deployment (Databricks + Microsoft Teams):** A supervisor agent coordinating 11,000+ employees across 70+ sites initially faced the bottleneck problem — a single routing agent managing all specialized agents became a context-overflow risk. The supervisor approach worked at their scale only because it was paired with a structured output model (AI/BI Genie for structured data, vector search for documents), not raw LLM delegation. The key architectural decision was using a single interface with specialized backend agents rather than a monolithic orchestrator. — [databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)
- **Azure Architecture Center:** Maps five distinct orchestration patterns (sequential, concurrent, group chat, handoff, magentic) and explicitly notes that handoff is the right choice when "a single agent doesn't have all the tools or knowledge needed to complete a task." The pattern enables agents to "collaboratively work toward a shared goal, passing control when additional expertise is required." — [learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

## Gotchas

- **Handoff only works when all agents support local tool execution.** Microsoft Agent Framework requires this explicitly — agents without tool support can't participate in the handoff mesh.
- **You still need a termination condition.** Without an explicit `EndTurn` or equivalent, handoff chains can loop indefinitely. Define what "done" looks for each agent role.
- **Context bloating is the new bottleneck.** If your shared transcript grows unbounded across a long handoff chain, you recreate the supervisor's context problem. Prune or summarize older turns at defined boundaries.
- **Not every agent mesh is appropriate.** Handoff makes sense when task ownership genuinely changes between agents (billing → product → legal). For parallel independent work, fan-out/fan-in is faster and cheaper.
