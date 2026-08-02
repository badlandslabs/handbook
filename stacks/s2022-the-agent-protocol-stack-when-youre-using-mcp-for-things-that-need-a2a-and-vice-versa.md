# S-2022 · The Agent Protocol Stack — When You're Using MCP for Things That Need A2A (and Vice Versa)

You have a multi-agent system. Someone added an MCP server so the researcher agent can call the synthesizer agent. It kind of works, but the delegation is clunky, state doesn't carry across properly, and your monitoring is a mess. You assume you need a better MCP server. You probably need A2A — or neither.

## Forces

- **The protocols arrived within months of each other.** Anthropic released MCP in November 2024. Google released A2A in April 2025. The ecosystem is still absorbing what each one does and where the boundary falls.
- **Marketing conflates them deliberately.** Vendors claim "MCP support" as a proxy for "we're agent-compatible." Teams spend months adding MCP servers to problems that needed a simple HTTP call.
- **The stack looks the same from the outside.** Both protocols use JSON over HTTP. Both involve an agent on one end. The difference — tool invocation vs. agent collaboration — only surfaces when you hit the failure mode.
- **Framework vendors blur the boundary.** LangChain, CrewAI, and others abstract both protocols away behind agent abstractions, making it easy to wire the wrong one without realizing it.

## The Move

**The protocol stack has two layers. Use each for its intended purpose — not as interchangeable plumbing.**

1. **MCP (Model Context Protocol) is for tool access.** It connects a single agent to external resources: databases, file systems, APIs, services. The agent is the client; the MCP server is a resource. Think: LLM ↔ search tool, LLM ↔ calendar, LLM ↔ code interpreter.

2. **A2A (Agent-to-Agent Protocol) is for agent collaboration.** It connects two or more agents that each have their own identity, tools, state, and trust boundaries. Think: Researcher agent ↔ Synthesizer agent ↔ Reviewer agent, each from a different vendor or framework.

3. **Neither is needed for internal orchestration.** If two "agents" are just function calls within the same process, same team, same framework — use a function call or an internal message queue. Adding A2A overhead here is like using HTTP between microservices that share a process.

4. **Wire A2A above MCP in the stack.** The A2A spec was explicitly designed to complement MCP, not replace it. An A2A agent can use MCP tools internally. The protocol layers: `A2A (agents ↔ agents)` → `MCP (agents ↔ resources)` → `HTTP/WebSocket (transport)`.

5. **Use Agent Cards for discovery.** A2A's `AgentCard` JSON endpoint advertises capabilities so agents can dynamically discover collaborators — analogous to service discovery in microservices. Don't hardcode agent URLs.

6. **Watch the security boundary.** A2A's biggest unresolved problem is cross-agent authentication and audit trails. Agents delegating to agents inherit each other's permissions in ways that traditional IAM wasn't designed for. Until this matures, prefer A2A within a trust boundary rather than across vendors.

## Evidence

- **Linux Foundation press release:** A2A Protocol surpassed 150 supporting organizations and achieved deep integration across Google Cloud, Microsoft Azure, and AWS within its first year. Donated to Linux Foundation June 2025 with 50+ founding partners including Accenture, Salesforce, SAP, Cohere, and Microsoft. — [https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year](https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year)

- **Aima Tools analysis:** "A2A is not mainly about connecting an agent to a database, file system, calendar, API, or service — that is what MCP is for." The protocol stack clearly separates A2A (agent ↔ agent, top layer) from MCP (agent ↔ resources, middle layer). — [https://www.aimadetools.com/blog/agent-to-agent-communication](https://www.aimadetools.com/blog/agent-to-agent-communication)

- **Rost Glukhov (technical blog):** "A2A is not dead. It is just not universal." Documents where A2A genuinely shines — cross-framework, cross-vendor agent collaboration with independent ownership and trust boundaries — versus where it's overengineered — internal orchestration where simple function calls suffice. 150+ organizations in A2A production by April 2026; security remains the biggest unresolved gap. — [https://www.glukhov.org/ai-systems/comparisons/a2a-protocol-2026-adoption/](https://www.glukhov.org/ai-systems/comparisons/a2a-protocol-2026-adoption/)

## Gotchas

- **Adding an MCP server doesn't make your agents collaborative.** If your "agent" just calls a tool to get data and returns it, that's MCP's job. A2A is for when two agents negotiate, delegate, and exchange artifacts with independent state.
- **A2A is not a replacement for internal orchestration.** Teams new to the protocol sometimes over-apply it — wrapping every function call between agents in A2A. The overhead (Agent Cards, streaming, task lifecycle tracking) only pays off when agents are truly independent.
- **The "AI Agent Internet" is still aspirational.** A2A at one year has strong enterprise signal (150+ orgs, cloud platform support) but the vision of agents from different vendors collaborating freely faces real security, trust, and discovery challenges that haven't been solved yet.
