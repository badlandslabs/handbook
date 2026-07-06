# S-708 · The Agent Stack Is Stratifying Into Specialized Infrastructure Layers

[Teams used to build one agent system with one stack. Today the production stack fragments into distinct layers — sandboxing, orchestration, memory, protocol, reasoning — each converging on specialized infrastructure. Ignore the stratification and you pay for it in brittleness, cost, or both.]

## Forces

- **Sandboxing is no longer a configuration option.** Agents that execute code, browse the web, or call third-party APIs need isolation. Teams that bolted this on late discovered it touches every other layer.
- **The framework is not the product.** Picking LangGraph vs CrewAI vs AutoGen matters less than building the operational substrate around it — monitoring, fallback, recovery, cost control.
- **Production costs 5–15x prototype costs.** The gap is wider than traditional software because every layer adds operational overhead you don't see in a demo.
- **MCP is consolidating tool integration.** Custom tool schemas are being replaced by the Model Context Protocol, but the ecosystem is still immature — adapters and server availability vary.

## The Move

Treat the agent stack as five distinct infrastructure layers, each with its own tooling and evaluation criteria:

**1. Reasoning layer (LLM)**
- Claude 3.7 Sonnet for complex reasoning tasks, GPT-4.1 for broader tool use, o3-mini for cost-sensitive high-volume tasks
- Cascade models: fast/cheap for classification, capable/expensive for final output
- Never route directly to frontier models without a routing gate

**2. Protocol layer (tool communication)**
- MCP (Model Context Protocol) is the emerging standard for tool integration — reduces custom schema maintenance
- Still immature: not all tool servers exist, adapters required for legacy APIs
- Each tool should declare its network access requirements at schema definition time

**3. Sandboxing layer (execution isolation)**
- Emerging as its own category: E2B, Modal, Firecracker microVMs, Shuru
- Enables skill/plugin installation with declared network whitelists and AST scanning before execution
- Sandboxing is where defensibility lives — not in the orchestration framework
- Personal-scale agents: subprocess isolation with network whitelists is sufficient
- Production multi-tenant: hardware-level isolation (microVMs) becomes necessary

**4. Orchestration layer (multi-agent coordination)**
- LangGraph: state-machine graphs for production systems needing durable execution and observability (used at Klarna, Replit, Elastic)
- CrewAI: role-based crews for fast delivery, content pipelines, stakeholder-readable agent role maps
- AutoGen: maintenance mode as of October 2025 — successor is Microsoft Agent Framework
- DSPy: declarative approaches gaining traction for teams wanting to separate pipeline definition from LM optimization
- Sequential pipeline: tasks with strict linear dependencies
- Hierarchical/supervisor: complex workflows where a director agent delegates to specialists
- Peer-to-peer: research and brainstorming where agents collaborate without a clear hierarchy

**5. Memory/persistence layer**
- Personal agents: SQLite + FTS5 — zero infrastructure, handles retrieval well at this scale
- Production: Qdrant, Pinecone, or pgvector for vector similarity; semantic caching for repeated queries
- Cross-channel memory: context should persist regardless of which channel initiated the request
- Semantic caching can reduce token costs by 30–50% on repeated query patterns

## Evidence

- **HN post:** The agent stack is splitting into specialized layers; sandboxing is becoming its own distinct thing — Shuru, E2B, Modal, Firecracker wrappers. Different defensibility profiles per layer make going monolithic the wrong call. — https://news.ycombinator.com/item?id=47114201
- **Opensoul / Paperclip:** Built a 6-agent marketing agency (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) using Paperclip orchestration. Each agent runs on scheduled heartbeats, checks work queues, delegates, and reports — showing heartbeat-based autonomy at scale. — https://news.ycombinator.com/item?id=47336615
- **Xcapit production cost analysis:** AI agent production costs run 5–15x prototype costs. Token/API spend = 30–50% of total; compute = 20–35%; observability = 10–20%; hidden costs (reliability engineering, fallbacks) = 15–25%. Monthly production range: $7,050–$21,100. — https://www.xcapit.com/en/blog/real-cost-ai-agents-production
- **Technspire end-of-2025 assessment:** Agents shipped in four categories — developer tooling (tight feedback loops), internal ops automation, vertical SaaS integration, and research. Core lesson: "Agents work where software engineering discipline works. Bounded scope, tested behavior, scoped identity, observable runtime." — https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons
- **JetThoughts framework comparison:** LangGraph used in production at Klarna/Replit/Elastic for observability and durable execution. CrewAI active v0.98+ for content and support pipelines. AutoGen in maintenance mode since Oct 2025 — successor is Microsoft Agent Framework. — https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025
- **AI Workflow Lab 2026 guide:** Multi-agent patterns: sequential (linear dependencies), hierarchical with supervisor (complex coordination), peer-to-peer (collaboration). 57% of companies deploying agents in production in 2026, up from smaller percentages in 2025. — https://aiworkflowlab.dev/article/building-multi-agent-ai-systems-2026-architecture-patterns-mcp-production-orchestration

## Gotchas

- **Choosing a framework by feature list ignores team maturity.** A team in week 2 picks CrewAI for its simplicity. Six months later, the "simple" abstraction fights them when they need state-machine debugging.
- **MCP adoption is real but incomplete.** Don't assume all your tools have MCP servers. The adapter layer adds complexity you won't see in the demo.
- **Tool hallucination increases with agent complexity.** Each additional tool call multiplies the chance the model calls a non-existent method or mis-typed parameter. Validate tool schemas at load time, not runtime.
- **Hidden costs dominate at scale.** Observability and reliability engineering often exceed the LLM API bill — budget for both.
- **Human-in-the-loop isn't optional in production.** Even "autonomous" agents need review gates on high-stakes actions. Amazon's evaluation framework emphasizes HITL as critical for multi-agent coordination failure detection.
