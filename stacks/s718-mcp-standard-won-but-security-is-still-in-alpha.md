# S-718 · MCP Won — Now Fix the Security Model

[The Model Context Protocol solved the tool-calling fragmentation problem. 97M+ monthly SDK downloads, 5,800+ servers, adoption across OpenAI, Google, Microsoft, Anthropic. But 43% of deployed servers have command injection flaws, and exploit probability exceeds 92% with 10 plugins. The standard matured faster than the threat model.]

## Forces

- **MCP's value proposition is real and undeniable.** It ended the era of custom one-off connectors between every model and every tool. "USB-C for AI" was the right metaphor and the market validated it.
- **Security was not designed in — it was bolted on after adoption.** The 43% command injection flaw rate across MCP servers is not a vendor problem; it's a protocol design gap. The authentication model is insufficient for untrusted tool schemas.
- **Enterprise procurement requires governance scaffolding MCP doesn't provide yet.** The donation to Linux Foundation's Agentic AI Foundation (December 2025) was the right move — vendor-neutral governance — but vendor-neutral security standards don't exist yet.
- **The protocol and the orchestration layer serve different concerns.** MCP connects agents to tools. It has no opinion on agent logic, state, or coordination. Teams conflate "we use MCP" with "we have an agent architecture" — they're orthogonal.

## The Move

Treat MCP adoption and MCP security as two separate projects with separate timelines.

**On adoption:** Plug in. Use MCP servers for standard integrations (filesystem, GitHub, Slack, database). Use MCP clients in LangGraph, CrewAI, or your custom orchestrator. The ecosystem is real — 300+ client applications, major cloud providers (Azure, AWS) have native MCP services.

**On security:** Treat every MCP server as an untrusted subprocess until proven otherwise. Apply these before production:

- **Schema validation at the client boundary.** MCP servers advertise their tools via JSON schemas. Validate incoming tool definitions before passing them to the LLM. Malformed or adversarial schemas are an injection vector.
- **Sandbox MCP servers.** Run each server in an isolated process or container. A compromised server should not have access to the host filesystem, network, or secrets store.
- **Limit tool permissions by trust tier.** Not all MCP servers are equal — a server you built is different from a community server. Apply least-privilege scoping per tier.
- **Audit tool call logs end-to-end.** Log every tool invocation with request/response, timestamps, and source server. This is non-negotiable for regulated environments.

**On governance:** Follow the Linux Foundation Agentic AI Foundation for evolving MCP security specs. The donated spec doesn't yet include mandatory authentication between client and server — that's in progress.

## Evidence

- **MCP market traction:** 97M+ monthly SDK downloads, 5,800+ MCP servers, 300+ client applications. OpenAI adopted MCP in March 2025; Google and Microsoft followed in April–May 2025. — [Xenoss Blog / MCP in Enterprise](https://xenoss.io/blog/mcp-model-context-protocol-enterprise-use-cases-implementation-challenges)
- **MCP security metrics:** 43% of MCP servers have command injection flaws; exploit probability exceeds 92% when 10 plugins are active. These are structural gaps, not vendor bugs. — [Deepak Gupta Research / MCP Enterprise Guide 2025](https://guptadeepak.com/research/mcp-enterprise-guide-2025)
- **MCP governance move:** Anthropic donated MCP to the Linux Foundation's Agentic AI Foundation in December 2025, eliminating single-vendor risk for enterprise procurement. Azure and AWS rolled out MCP workflow services. — [Synvestable / MCP for Enterprise 2026](https://www.synvestable.com/model-context-protocol.html)

## Gotchas

- **Don't confuse MCP adoption with agent architecture.** MCP solves the tool-integration layer. You still need orchestration (LangGraph, CrewAI, custom), state management, memory, and guardrails. MCP is a component, not a stack.
- **Community MCP servers are not audited.** Downloading an MCP server from GitHub and running it in production is equivalent to running any untrusted binary. The same rigor you apply to Docker containers from untrusted registries should apply here.
- **MCP's protocol-level auth is nascent.** Current MCP authentication is not sufficient for adversarial environments. Until the Linux Foundation spec matures, apply transport-layer controls (network segmentation, mTLS) as a compensating control.
- **LangGraph and CrewAI have different MCP integration models.** LangGraph has first-class MCP tool support in its tool-calling pipeline. CrewAI exposes MCP through its tool abstraction. Neither exposes MCP's security gaps — they're your responsibility.
