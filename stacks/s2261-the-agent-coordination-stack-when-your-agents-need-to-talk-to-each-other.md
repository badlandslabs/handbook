# S-2261 · The Agent Coordination Stack — When Your Agents Need to Talk to Each Other

When you split one agent into two, they immediately face a problem that single agents never have: how do they exchange context, negotiate capability, and hand off work without losing state or diverging on shared facts? The answer in 2026 has converged on a two-protocol stack — A2A for agent-to-agent coordination and MCP for agent-to-tool access — and the teams that understand when each applies are the ones shipping reliable multi-agent systems.

## Forces

- **The handoff tax** — without a structured protocol, every agent-to-agent call requires custom code: serialization, retry logic, state negotiation, capability matching. This is N×M complexity that grows with every new agent
- **The discovery problem** — a supervisor agent trying to delegate to a specialist can't do so if it doesn't know what the specialist can do, what interface it speaks, or what version it is
- **The state boundary problem** — each agent has its own context window. When Agent A finishes and hands to Agent B, B may have a slightly different read of the shared record, causing downstream failures that look like logic errors but are actually consistency errors
- **The MCP/A2A confusion** — teams reach for the wrong protocol. A2A solves "agents talking to agents." MCP solves "agents talking to tools." Using A2A for tools or MCP for agents leads to verbose, brittle workarounds

## The Move

**The 2026 standard stack: A2A for inter-agent collaboration, MCP for tool access, with Agent Cards enabling capability discovery.**

- **Use A2A (Agent-to-Agent Protocol) for agent-to-agent communication** — task delegation, streaming intermediate results, negotiating capabilities, and managing shared task state across agent boundaries. A2A is agent-native: it models agents as peers with skills, not tools with functions
- **Use MCP (Model Context Protocol) for agent-to-tool access** — connecting agents to databases, APIs, file systems, and external services. MCP is tool-native: it standardizes function calling and context injection. As of April 2026, MCP has ~97M monthly SDK downloads vs A2A's ~10.9M — MCP won the tool layer first
- **Expose every agent with an Agent Card** — a JSON manifest advertising the agent's capabilities, skills, supported A2A version, authentication requirements, and push notification endpoint. Other agents discover and match capabilities at runtime without hardcoded routing logic
- **Implement deterministic handoffs with explicit state contracts** — each handoff message should carry a payload schema, idempotency key, trace ID, and a declaration of what work the upstream agent completed vs. what remains for the downstream agent. Non-deterministic handoffs produce state drift within the first week of production traffic
- **Choose the coordination topology to match the workflow** — supervisor/worker (hub-and-spoke, one coordinator routing to specialists), pipeline (sequential A→B→C, linear transformations), or fan-out (one-to-many parallel with fan-in aggregation). Topology choice is a latency/cost trade-off, not a quality decision

## Evidence

- **Adoption milestone (Linux Foundation, April 2026):** A2A Protocol reached 150+ supporting organizations, deep integration across Google, Microsoft, and AWS, 22,000+ GitHub stars, and active production deployments in supply chain, financial services, insurance, and IT operations within its first year. Five production-ready SDKs (Python, JavaScript, Java, Go, .NET) — [Linux Foundation press release](https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year)
- **Empirical protocol comparison (University of York, arXiv:2607.23884, July 2026):** Implemented the same multi-agent coordination scenario (domain model generation) with both A2A and MCP. Found: MCP has lower coordination complexity for tool-facing tasks but requires explicit application-layer logic for state management; A2A provides native multi-turn, streaming coordination with substantially greater support for stateful collaboration. Key finding — "Model picks are not the bottleneck; the handoff protocol is" — [arXiv:2607.23884](https://arxiv.org/abs/2607.23884)
- **Real-world adoption sentiment (Hacker News, Ask HN #48582679, 96 points):** Practitioners report MCP SDK downloads at ~257M vs A2A's ~10.9M monthly — MCP is ~24x more downloaded, indicating MCP won the tool layer first while A2A adoption is concentrated among enterprise platforms (Google Gemini Enterprise Agent Platform, Salesforce AgentForce, SAP Business AI, ServiceNow AI Agents, and n8n). HN comment: "once an agent has tools and services and data and contacts, the point of interaction becomes the agent itself — and if you build other agents you want them to interact because they have the most relevant context" — [HN Discussion](https://news.ycombinator.com/item?id=48582679)
- **Enterprise reference architecture (SAP, 2026):** SAP adopted both A2A and MCP as the interoperability layer for its AI agent ecosystem, with A2A managing "agent integration, task delegation, capability negotiation, and structured information exchange across agent boundaries" and MCP handling "tool exposure and consumption via standardized interface." Architecture separates agent collaboration concerns from tool access concerns, enabling independent development and versioning — [SAP Architecture Center](https://architecture.learning.sap.com/docs/ref-arch/76ec36)

## Gotchas

- **A2A and MCP are complementary, not competing** — deploying A2A for tool access or MCP for agent-to-agent communication produces verbose, fragile code. A2A models agents as peers; MCP models tools as functions. Use each for its intended layer
- **Agent Cards are the discovery mechanism — don't skip them** — without a structured Agent Card, agents must hardcode routing to their known peers. This defeats the purpose of a protocol designed for dynamic, scalable coordination
- **Handoff state must be explicitly declared** — the arXiv study found that without deterministic handoff contracts, state drift (each agent having a different read of the shared record) appears within the first week of production traffic and is the top cause of multi-agent failures that look like logic bugs but are actually consistency failures
- **A2A is enterprise-heavy, not startup-simple** — the protocol is production-proven in enterprise stacks (SAP, ServiceNow, Salesforce) but adds complexity that single-agent or simple pipeline systems don't need. For teams with 2–3 agents and well-defined workflows, a lightweight message queue or direct API call is often sufficient until coordination complexity demands the standard
