# A2A + MCP Protocol Stacking — Evidence Bank
*Last updated: 2026-08-02*

## Primary Sources

### 1. Linux Foundation A2A Milestone (April 2026)
**URL:** https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year
- A2A donated to Linux Foundation June 2025 with 50+ founding partners
- April 2026: 150+ supporting organizations
- Deep integration across Google Cloud, Microsoft Azure, AWS
- 4 enterprise partners cited with production deployments in first year
- Founding partners: Accenture, AWS, Atlassian, Box, Cohere, Microsoft, Salesforce, SAP, and 40+ others

### 2. Zylos Research — Agent-to-Agent Communication Protocol Standards
**URL:** https://zylos.ai/research/2026-02-15-agent-to-agent-communication-protocols
- MCP: Anthropic, Nov 2024 — tool access (LLM ↔ tools/resources)
- ACP: IBM, 2024 — multi-framework interoperability
- A2A: Google, Apr 2025 — enterprise agent collaboration
- ANP: Community, 2024-2025 — decentralized marketplaces
- "MCP and A2A are the protocols building the AI Agent Internet"
- 50+ founding partners for A2A including AWS, Microsoft, Salesforce, SAP

### 3. Aima Tools — Agent-to-Agent Communication Guide
**URL:** https://www.aimadetools.com/blog/agent-to-agent-communication
- Protocol stack layers: A2A (top) → MCP (middle) → HTTP/WebSocket/gRPC (bottom)
- MCP: connects agents to tools/resources
- A2A: connects agents to agents
- Agent Cards for capability discovery
- Critical distinction: "A2A is not mainly about connecting an agent to a database, file system, calendar, API, or service — that is what MCP is for"

### 4. Rost Glukhov — A2A Protocol in 2026: Adoption, Hype, and Reality
**URL:** https://www.glukhov.org/ai-systems/comparisons/a2a-protocol-2026-adoption/
- "A2A is not dead. It is just not universal."
- "A2A is genuinely valuable in specific contexts: where agents are independent systems with their own ownership, tools, and trust boundaries"
- Best mental model: MCP below, A2A above
- Where A2A is useful: cross-framework agent collaboration, enterprise multi-vendor agent marketplaces
- Where A2A is overhyped: internal orchestration (simple function calls suffice)
- 150+ organizations in production by April 2026
- Security remains the biggest unresolved question for A2A

### 5. Presenc AI — Agent Framework GitHub Rankings May 2026
**URL:** https://presenc.ai/research/ai-agent-framework-github-rankings-2026
- MCP launched Nov 2024, saw explosive adoption
- browser-use: 94K stars (general-purpose web automation by AI agents)
- MCP servers proliferating across every category

### 6. macgpu.com — Multi-Agent AI Architecture Production Guide
**URL:** https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html
- "From 2024–2025, agents moved from demos to production"
- Single agents hit walls: context window limits, diluted specialization, serial inefficiency, single points of failure
- Google internal experiments: 6× speedup (1hr → 10min) with multi-agent topology
- AdaptOrch (2026): topology impacts performance more than model selection (12–23% gains)

### 7. AgentMemo — State of AI Agent Memory 2026
**URL:** https://mem0.ai/blog/state-of-ai-agent-memory-2026
- Mem0 manages 50M+ memory operations daily
- 20 vector store backends supported (Qdrant, Chroma, Weaviate, Milvus, PGVector, Redis, Elasticsearch, FAISS, etc.)
- AgentOps, Raycast, OpenClaw integrations

## Key Findings

1. **Protocol layering is real but non-obvious**: MCP (tool access) ≠ A2A (agent collaboration). Teams conflate them constantly.

2. **A2A is production-ready but scoped**: 150+ orgs, deep cloud platform integration. But the "AI Agent Internet" vision is still aspirational.

3. **The A2A sweet spot**: cross-framework, cross-vendor, cross-team agent collaboration. NOT internal orchestration (just use function calls).

4. **Security is the unresolved A2A problem**: agents authenticating to agents, audit trails, trust boundaries — still being worked out.

5. **MCP remains the dominant production protocol**: A2A is the layer above, not the replacement.
