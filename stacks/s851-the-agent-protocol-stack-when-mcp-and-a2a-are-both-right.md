# S-851 · The Agent Protocol Stack — When MCP and A2A Are Both Right

You built a multi-agent system. It works in the demo. In production, Agent A from Vendor X can't talk to Agent B you built internally. Every team has its own tool-calling format. Every vendor ships a proprietary function-calling schema. You have N×M integration points instead of a reusable stack. The solution isn't picking one protocol — it's stacking two.

This is **The Agent Protocol Stack** — layering MCP (agent → tools) and A2A (agent → agent) as complementary standards, each addressing a different communication problem.

## Forces

- **Bespoke integration hell.** For three years every framework (LangChain, AutoGen, CrewAI, LlamaIndex) invented its own tool-calling convention. Every vendor ships proprietary function-calling JSON. Each new agent pair requires a custom integration. The combinatorial explosion makes N-agent systems unmaintainable.
- **Two communication problems, one agent.** Agents need to talk to tools (databases, APIs, files, memory) and also to each other (delegate, negotiate, collaborate). These are architecturally different operations — the first is a capability invocation, the second is a collaborative negotiation — but teams used the same hammer for both.
- **Protocol wars distract from the real question.** MCP and A2A are frequently framed as competitors. In practice they address non-overlapping layers and production systems need both. Treating them as mutually exclusive causes teams to either over-engineer with one protocol doing double duty, or build parallel bespoke systems that fragment the ecosystem.
- **Vendor adoption is real but the landscape is fragmented.** Both protocols have reached significant adoption milestones, but teams still encounter legacy agents, proprietary wrappers, and partial implementations that break end-to-end flows.

## The move

**Layer MCP inside, A2A outside.** MCP handles how a single agent connects to its capabilities. A2A handles how multiple agents coordinate. Think of it as USB-C (MCP) for connecting peripherals, and HTTP (A2A) for network communication — different layers, both necessary, neither competing.

### Practical stacking

- **Use MCP to register and invoke tools.** MCP servers expose tools, resources, and prompts as discoverable endpoints. An agent connects to MCP servers to query databases, call APIs, search files, or access memory. One agent, many MCP server connections. Anthropic open-sourced MCP in November 2024; as of 2026, there are 10,000+ active public MCP servers with 110M+ monthly SDK downloads.
- **Use A2A to connect agents to each other.** A2A handles agent discovery, task delegation, status streaming, and multi-turn collaboration. Built on HTTP, SSE, and JSON-RPC. Google launched A2A in April 2025 with 50+ partners (AWS, Microsoft, Salesforce, SAP, IBM, ServiceNow). Donated to the Linux Foundation June 2025, reached v1.0 in early 2026. 150+ organizations in production as of mid-2026.
- **Implement both in the same agent.** A single agent can expose an A2A endpoint (so other agents can delegate to it) while also connecting to MCP servers (so it can call tools). The Google Cloud ADK supports this natively. This is the standard enterprise pattern emerging in 2026.
- **Enforce structured handoff contracts at A2A boundaries.** When Agent A delegates to Agent B over A2A, don't pass raw string prompts. Use JSON Schema or Pydantic models to define the task contract. Raw string handoffs allow downstream agents to hallucinate or misparse task context — structured contracts make the interface verifiable.
- **Start with one protocol, add the other when needed.** A single-agent system with tool access only needs MCP. Add A2A when you need a second agent. This avoids premature complexity — the HN consensus is "don't start with multi-agent."
- **Prefer open standards over proprietary SDKs for the protocol layer.** Both MCP and A2A have multi-vendor, multi-language support (Python, JavaScript, Java, Go, .NET for A2A alone). Lock-in at the protocol layer creates the same integration fragmentation these standards solve.

### Decision criteria

| Situation | Protocol needed |
|-----------|----------------|
| Single agent + tools/APIs | MCP only |
| Two+ agents coordinating | MCP + A2A |
| Agent swarms (10+ agents) | MCP + A2A + orchestration layer |
| Legacy systems to integrate | Consider MCP as adapter layer first |

## Evidence

- **Multi-agent coordination failures are the dominant degradation mode.** Guo et al. identify that as agent count grows, "coordination failures — agents that contradict one another, duplicate effort, or produce inconsistent shared state — become the dominant cause of system-level degradation, distinct from the individual capability limitations covered by standard benchmarks." Token duplication is severe: MetaGPT at 72%, CAMEL at 86%, AgentVerse at 53% — these represent wasted context and cost that structured protocol handoffs can reduce. — MDPI Preprints, "LLM-Based Multi-Agent Orchestration: A Survey of Frameworks, Communication Protocols, and Emerging Patterns," 2026 — https://www.mdpi.com/1999-5903/18/6/326

- **A2A reached production scale with cross-vendor backing.** Google announced A2A in April 2025 with 50+ enterprise partners. By mid-2026: 150+ organizations in production, 22,000+ GitHub stars, 5 production SDKs (Python, JavaScript, Java, Go, .NET), v1.0 released, governed by Linux Foundation. Cross-vendor adoption reduces the bespoke integration problem. — Zylos Research, "Agent-to-Agent Communication Protocols: A2A, MCP, and Multi-Agent Orchestration," 2026-05-16 — https://zylos.ai/zh/research/2026-05-16-agent-to-agent-communication-protocols-a2a-mcp/

- **The "MCP inside, A2A outside" model is the emerging enterprise standard.** Google Cloud's official documentation states the architecture explicitly: "MCP is a protocol that enables agents to reliably connect to data sources and tools... A2A (Agent2Agent) is a standard for agent-to-agent collaboration." Their reference architecture shows agents as A2A endpoints that internally connect to MCP servers. BBVA deployed 2,900 custom agents within five months using multi-protocol patterns. — Google Cloud Blog, "Building Connected Agents with MCP and A2A," Mollie Pettit, December 15, 2025 — https://cloud.google.com/blog/topics/developers-practitioners/building-connected-agents-with-mcp-and-a2a

## Gotchas

- **A2A doesn't replace MCP — it complements it.** Teams that heard "A2A is the agent protocol" dropped MCP and then had to build custom tool-calling for every agent. The protocols address different layers; dropping one to use the other creates gaps.
- **MCP security boundaries don't automatically extend across A2A.** MCP's authentication and authorization apply within a tool invocation. When an agent delegates a task to another agent over A2A, that remote agent inherits the delegating agent's permissions unless you implement explicit A2A auth. The protocol supports Zero Trust patterns but doesn't enforce them by default.
- **Legacy agents still need adapters.** Not every agent in a production environment supports MCP or A2A in 2026. Expect to build protocol adapters for proprietary agents. MCP is often the better adapter target since tool-calling is simpler to wrap than full collaborative negotiation.
- **Streaming status across A2A is non-trivial.** A2A supports SSE for long-running task streaming, but implementing reliable progress updates with proper error propagation across agent boundaries requires careful engineering. Don't assume the protocol handles it automatically.
- **Structured handoff contracts require upfront schema design.** JSON Schema or Pydantic contracts at agent-agent boundaries are the right approach but add design overhead. Teams that skip this find debugging handoff failures across 3+ agents painful — the error surface is in the interface, not the agent logic.
