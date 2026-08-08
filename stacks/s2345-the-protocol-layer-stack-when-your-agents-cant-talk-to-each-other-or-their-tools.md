# S-2345 · The Protocol Layer Stack — When Your Agents Can't Talk to Each Other or Their Tools

Every team building multi-agent systems hits the same wall twice. First: how does my agent actually connect to a database, a Slack channel, a browser? Second: how does my research agent tell my coding agent what it found? For two years, each team answered both questions differently. Now the ecosystem is standardizing — but the standard has two layers, not one, and most teams are still picking the wrong one for each job.

## Forces

- **MCP and A2A solved different problems, not competing ones.** MCP (Model Context Protocol, Anthropic, Nov 2024) handles agent-to-tool connectivity. A2A (Agent-to-Agent Protocol, Google, April 2025) handles agent-to-agent coordination. Treating them as alternatives is the most common and costly mistake in 2025-2026 agent architecture.
- **The two-layer stack is now the enterprise default.** By Q1 2026, 150+ organizations had A2A v1.0 in production, MCP had 17,468 indexed public servers and 110M monthly SDK downloads, and all three major protocols (MCP, A2A, ACP) sat under Linux Foundation governance — creating institutional alignment that individual vendors never could.
- **Cross-vendor collaboration requires a protocol layer, not a framework.** An agent built on LangGraph talking to an agent built on CrewAI, running Claude internally versus GPT-5, can't share a workflow graph — but they can share a well-defined message envelope via A2A. The framework layer stays fragmented; the protocol layer converges.
- **The MCP-to-A2A handoff is where systems break.** Most production failures in hybrid architectures aren't at either protocol boundary — they're at the transition where one agent has to decide what to hand off versus what to tool-call.

## The Move

The winning architecture in 2026 is a two-layer protocol stack: **MCP for vertical tool integration, A2A for horizontal agent coordination**. Design the split deliberately, not reactively.

- **Use MCP when an agent needs a capability, not a collaborator.** Query Postgres, read Stripe tickets, run browser automation, call a search API — these are tool calls. MCP is the agent's hands. One agent, one session, no state shared beyond the call context.
- **Use A2A when one agent needs to delegate a task to another agent.** The key signal: "this agent should own the outcome of this subtask." That means A2A — with streaming responses, task state, and artifact delivery across agent boundaries.
- **Agent Cards are the discovery layer for A2A.** Every A2A endpoint publishes an Agent Card (name, capabilities, skills, endpoint URL). Before any agent delegates, it queries the card. This is the mechanism that turns a static role assignment into a dynamic, discoverable collaboration.
- **Layer auth and observability above the protocols, not into them.** Neither MCP nor A2A specifies authorization — that's intentional. Handle auth at your orchestration layer (your framework, your gateway). The protocol's job is message format and delivery, not policy.
- **Design the MCP-to-A2A handoff explicitly.** The most common production failure: an agent that has both MCP tool access and A2A client capabilities, and routes everything through tools because it's simpler. Resist this. Reserve MCP for atomic operations; use A2A for any task that requires ownership, review, or iteration by another agent.
- **Monitor at the protocol level, not just the framework level.** MCP calls are traceable. A2A task exchanges are traceable. LangGraph/CrewAI/AutoGen internal execution is not — it's the opaque part. Instrument the protocol boundaries first.

## Evidence

- **Primary source — Google Developers Blog:** A2A was announced in April 2025 with 50+ founding partners (AWS, Microsoft, Salesforce, SAP, ServiceNow) and explicitly positioned as complementary to MCP. Google's rationale: internal scaling of multi-agent systems for enterprise customers required a protocol layer that tool-calling alone couldn't provide. — [Announcing the Agent2Agent Protocol (A2A)](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/)
- **Primary source — AgentMarketCap production data:** MCP crossed 10,000 active public servers with 110M monthly SDK downloads; A2A reached v1.0 GA with 150+ organizations in production. Key finding: enterprises are using both simultaneously — not choosing one. The "protocol war" never materialized. — [A2A vs. MCP: First Production Deployment Data (April 2026)](https://agentmarketcap.ai/blog/2026/04/25/a2a-vs-mcp-production-deployment-data-2026)
- **Primary source — HN discussion (Ask HN, 96 points, 45 comments):** Real practitioners reporting production usage. MCP downloads ~257M vs A2A ~10.9M monthly — MCP is ~24x more downloaded, but A2A adoption is concentrated in enterprise platforms (Gemini Enterprise, AgentForce, watsonx Orchestrate, SAP Joule) where the cross-vendor coordination problem is acute. — [Ask HN: Is anyone using the A2A protocol?](https://news.ycombinator.com/item?id=48582679)
- **Primary source — Engineering blog (Kim Jangwook):** 63% of enterprises are piloting AI agents; fewer than 25% have successfully scaled to production. The MCP+A2A hybrid is framed not as a feature choice but as a structural necessity — MCP as the agent's hands, A2A as the agents' language. — [A2A + MCP Hybrid Architecture: 2026 Multi-Agent Production Strategy](https://jangwook.net/en/blog/en/a2a-mcp-hybrid-architecture-production-guide)

## Gotchas

- **Don't build your own message envelope.** Before inventing a custom JSON schema for inter-agent messages, check whether A2A covers your case. The cost of a custom protocol is paid at every integration point, forever.
- **MCP doesn't do discovery.** MCP servers are static endpoints you configure. If your agent needs to find a capable peer at runtime, that's A2A with Agent Cards — MCP has no equivalent.
- **A2A doesn't replace your orchestration framework.** A2A is a transport and coordination protocol, not a workflow definition language. LangGraph, CrewAI, and AutoGen still define the execution graph. A2A defines how agents send messages across that graph's boundaries.
- **Version skew is a real production risk.** MCP servers and A2A endpoints you built against six months ago may have changed schemas. Pin protocol versions and treat breaking changes as first-class deployment incidents.
- **The A2A adoption gap is real but shrinking.** Hobbyist and startup adoption lags enterprise by roughly 2:1. If you're building a cross-vendor marketplace, A2A is essential now. If you're building a single-vendor internal system, MCP alone may be sufficient until you hit cross-agent delegation.
