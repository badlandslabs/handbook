# S-737 · The Protocol Layer: MCP and A2A Are Becoming the Wires of Agentic Systems

The biggest unsolved problem in agentic AI isn't the model — it's getting agents to talk to tools reliably and to each other without custom glue code. MCP and A2A are converging as the de facto answer: MCP connects a single agent to its tool ecosystem, A2A connects agents to each other. Together they form the protocol stack that lets you swap components without rewriting the wiring.

## Forces

- **Protocol fragmentation is the new lock-in.** Without shared wires, every agent framework ships its own tool-calling implementation. Integrations become one-off and brittle. The market has been waiting for a winner-takes-most standard.
- **MCP and A2A solve different layers, not competing problems.** MCP is vertical (agent → tools/data). A2A is horizontal (agent → agent). Production systems need both, and VentureBeat's 2025 analysis concluded "the tool-calling and task-coordination layers are largely solved" — the unsolved piece is transport.
- **Enterprise adoption accelerates standards.** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. When that many teams are building, they push for common interfaces — and three major protocols (MCP, A2A, IBM ACP) are racing to fill the vacuum.
- **Security surface grows with adoption.** Thoughtworks flagged MCP-scan as a needed tool category — as MCP servers proliferate, the attack surface for prompt injection and tool hallucination expands. Rush-converting existing APIs to MCP servers creates both security and efficiency risks.

## The Move

**Use MCP for tool integration, A2A for agent handoffs, and plan for the transport layer gap:**

- **MCP is the tool-wiring standard.** Anthropic released it in November 2024; by late 2025 it had adoption from OpenAI, Google, Microsoft, and thousands of developers. Define your tools as MCP servers and any MCP-compatible agent can use them without per-framework glue code.
- **A2A is the handoff protocol.** Google's Agent-to-Agent protocol handles task delegation, status sharing, and output passing between agents — the "horizontal" layer that MCP doesn't cover. It pairs naturally with MCP: use MCP for tool calls within an agent, A2A for coordination between agents.
- **Schema your handoffs, not just your prompts.** The #1 killer of multi-agent workflows is untyped data passing between agents (per RaftLabs, "untyped handoffs kill workflows faster than any other issue"). Define structured output schemas for every agent boundary.
- **Watch the transport layer.** VentureBeat reports the transport layer — how agents discover and connect to each other across network boundaries — is 18-24 months from solved. Plan for it but don't block on it.
- **Don't rush-convert existing APIs to MCP.** Thoughtworks advised caution: turning every internal API into an MCP server creates a sprawl problem and expands the security surface. Prioritize new integrations and high-value tool boundaries.
- **Start with hierarchical coordination for reliability.** The manager-agent-decomposes-delegates-specialists-review pattern reduces coordination complexity from O(n²) to O(n) per Zylos Research, and adds 3-5x defect detection over single-pass agents. Add peer coordination only when task dependencies are genuinely lateral.

## Evidence

- **{Technspire Blog (Dec 2025):}** End-2025 production review — agents shipped in developer tooling, internal ops, research/analysis, and customer support drafts. Key success factor: bounded scope, tested behavior, scoped identity, observable runtime. Agents stalled everywhere else. — [technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)
- **{VentureBeat (Jul 2025):}** "MCP solved tool calling. A2A solved coordination. What solves transport?" — Analyzes MCP (vertical/tool layer) vs A2A (horizontal/agent layer) and identifies transport as the remaining unsolved piece, 18-24 months out. — [venturebeat.com/orchestration/mcp-solved-tool-calling-a2a-solved-coordination-what-solves-transport](https://venturebeat.com/orchestration/mcp-solved-tool-calling-a2a-solved-coordination-what-solves-transport)
- **{Zylos Research (Mar 2026):}** Hierarchical coordination reduces complexity from O(n²) to O(n) with management layers; iterative review loops detect 3-5x more defects but show diminishing returns after 3-4 rounds; security degrades 37.6% after 5+ AI-assisted iterations. — [zylos.ai/research/2026-03-01-hierarchical-ai-agent-coordination](https://zylos.ai/research/2026-03-01-hierarchical-ai-agent-coordination)
- **{RaftLabs (Nov 2025):}** 57% of organizations have agents in production; 1,445% surge in multi-agent inquiries (Gartner, Q1 2024 → Q2 2025); 89% have observability but only 52% have evals; untyped handoffs identified as the #1 failure mode in multi-agent systems. — [raftlabs.com/blog/multi-agent-systems-guide](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **{Cuttlesoft Blog (Nov 2025):}** MCP adoption analysis — one year post-release, MCP became the de facto tool-integration standard with cross-vendor adoption. — [cuttlesoft.com/blog/2025/11/25/anthropics-model-context-protocol-the-standard-for-ai-tool-integration](https://cuttlesoft.com/blog/2025/11/25/anthropics-model-context-protocol-the-standard-for-ai-tool-integration)
- **{Beam (Mar 2026):}** Orchestration framework comparison — 65% of teams hit a wall within 12 months and rewrite; default recommendation shifts to LangGraph for production due to flexibility and observability. — [getbeam.dev/blog/agent-orchestration-frameworks-compared-2026.html](https://getbeam.dev/blog/agent-orchestration-frameworks-compared-2026.html)
- **{GitHub - agentic-ai-system-design-primer (2025):}** Real production cost data: simple support ticket resolution ~$0.016/ticket with Haiku routing; complex multi-agent tasks $5-8/task; enterprise build costs $40K–$400K+ depending on complexity and compliance. — [github.com/HimClix/agentic-ai-system-design-primer](https://github.com/HimClix/agentic-ai-system-design-primer/blob/main/resources/cost-engineering/real-world-numbers.md)
- **{AIThinkerLab (Jun 2026):}** Agentic RAG with knowledge graphs cut hallucination ~62% across 47 production deployments; GraphRAG earns its cost only on cross-document questions. — [aithinkerlab.com/build-rag-systems-2026-architecture-patterns](https://aithinkerlab.com/build-rag-systems-2026-architecture-patterns/)

## Gotchas

- **MCP servers proliferate without governance.** Every team adds a new MCP server; you end up with 40+ tool definitions, none documented, some duplicating each other. Treat MCP server registration like API versioning.
- **A2A doesn't auto-solve trust.** Agents can hand off tasks correctly but produce wrong outputs. Review loops catch this — Zylos found diminishing returns after round 3-4, but zero review rounds means zero defect detection.
- **The transport gap breaks cross-organizational handoffs.** If your agents need to coordinate with agents outside your system, neither MCP nor A2A fully solves discovery and authentication yet.
- **Cost compounds silently in multi-agent loops.** Infinite loops between agents have costed teams $47K+ in a single incident (per cost engineering reference). Budget per-task caps and step-count limits are non-negotiable production guards.
