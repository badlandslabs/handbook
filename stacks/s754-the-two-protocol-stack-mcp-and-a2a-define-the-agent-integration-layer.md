# S-754 · The Two-Protocol Stack — MCP and A2A Define the Agent Integration Layer

When you need an agent to call tools and coordinate with other agents, the answer is no longer "build your own glue." Two protocols have won complementary layers of the stack — but using them together requires understanding what each actually solves.

## Forces

- **The N×M integration problem is unbearable at scale.** With M agents and N tools/data sources, custom integrations create O(M×N) surface area. Something has to standardize.
- **MCP and A2A solved different problems but get conflated.** MCP handles agent-to-resource. A2A handles agent-to-agent. They stack, they don't replace each other.
- **Enterprise adoption demands protocol-level guarantees.** Auth, governance, and observability can't be bolted on after — they have to be architected into the protocol choice.
- **The ecosystem is still young enough that lock-in risks cut both ways.** Betting on neither means rebuilding integration code. Betting on both means managing two protocol stacks.

## The move

**Layer 1 — MCP (Model Context Protocol, Anthropic, Nov 2024): The tool-and-data interface.**
- Standardizes how any agent connects to any tool, API, or data source via JSON-RPC 2.0.
- Adopted by OpenAI, Microsoft, Google, LangChain/LangGraph, and 1,000+ community servers.
- Described as the "USB-C for AI" — stateless, pluggable, no per-integration custom code.
- Primary risk: prompt injection attacks on tool descriptions; no built-in auth model (teams add their own gateway layer).
- Primary risk: latency and token costs accumulate with each tool call round-trip.

**Layer 2 — A2A (Agent2Agent, Google, Apr 2025): The agent-to-agent coordination layer.**
- Standardizes discovery, delegation, task handoff, and status sharing between agents.
- Backed by 150+ organizations (AWS, Microsoft, Salesforce, SAP, IBM, ServiceNow); donated to Linux Foundation June 2025.
- v1.0 spec released early 2026; SDKs in Python, JavaScript, Java, Go, .NET; 22,000+ GitHub stars.
- Three interaction modes: synchronous (request/response), streaming (progressive updates), asynchronous (long-running tasks with callbacks).
- Agent Cards advertise each agent's capabilities — enabling dynamic discovery without hardcoded routing.
- Still maturing: enterprise governance, security, and compliance tooling are on the roadmap.

**The stack pattern:** MCP servers sit behind an agent and provide tools/resources. A2A sits between agents and handles handoffs. An agent uses MCP to call a tool, then uses A2A to hand off the result to a peer agent. This is not optional complexity — it's the minimum viable architecture for anything beyond a single-agent prototype.

**When to use both:**
- Multi-agent production systems with specialized roles (researcher, coder, reviewer, synthesizer).
- Enterprise deployments requiring audit trails on inter-agent communication.
- Systems that need dynamic agent discovery (adding a new agent doesn't require reconfiguring peers).

**When MCP alone suffices:**
- Single-agent systems with tool access but no peer coordination.
- Prototypes that won't scale to multi-agent in the near term.

**When neither suffices yet:**
- Fully decentralized agent marketplaces (ANP — Agent Network Protocol — addresses this but is pre-v1.0).
- Environments requiring deep compliance controls (SOC 2, HIPAA) — current SDKs don't cover this natively.

## Evidence

- **Blog post (Zylos Research, 2026):** A2A adoption as of mid-2026: 150+ organizational backers, 22,000+ GitHub stars, v1.0 spec, Python/JavaScript/Java/Go/.NET SDKs — https://zylos.ai/zh/research/2026-05-16-agent-to-agent-communication-protocols-a2a-mcp/
- **Blog post (AgentMarketCap, Apr 2026):** MCP adopted by OpenAI, Microsoft, Google; 1,000+ community MCP servers; A2A backed by AWS, Microsoft, Salesforce, SAP, IBM, ServiceNow — the "protocol war" framing was wrong; both won as complementary layers — https://agentmarketcap.ai/blog/2026/04/11/a2a-vs-mcp-agent-protocol-war-2026
- **Blog post (VentureBeat, Jun 2026):** Four protocols now in the landscape (MCP, A2A, ACP from IBM, ANP from independent working group); MCP solved tool calling, A2A solved coordination; the next open question is transport — https://venturebeat.com/orchestration/mcp-solved-tool-calling-a2a-solved-coordination-what-solves-transport
- **Blog post (Ajith Vallath Prabhakar, Aug 2025):** MCP as "USB-C for AI" solves N×M integration; enterprise requires API gateways, service registries, and containerization around MCP servers; biggest risks are prompt injection and auth gaps — https://ajithp.com/2025/08/17/model-context-protocol-mcp-the-integration-fabric-for-enterprise-ai-agents
- **HN thread (Mar 2026):** Developer notes the agent stack is stratifying into specialized layers; sandboxing (E2B, Modal, Firecracker) becoming its own thing; monolithic agent frameworks are the wrong call at scale — https://news.ycombinator.com/item?id=47114201

## Gotchas

- **Don't treat A2A as "MCP but for agents."** They solve orthogonal problems. A2A doesn't replace MCP; it sits above it.
- **MCP's security model is your problem.** The protocol specifies the interface, not the auth layer. Every production deployment needs an API gateway or service mesh around MCP servers.
- **A2A Agent Cards are a security surface.** Capability advertisements can leak sensitive system topology. Validate and scope them like any other API endpoint.
- **LangGraph has native MCP support.** If you're already on LangGraph, integrating MCP servers is documented and supported. Building A2A coordination into LangGraph requires custom nodes (as of mid-2026).
- **Protocol proliferation risk is real.** ACP (IBM, Mar 2025) and ANP (independent) add to the stack. Evaluate them against MCP+A2A on a timeline — the right answer today may shift in 12 months.
