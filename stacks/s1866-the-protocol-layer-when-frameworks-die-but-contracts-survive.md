# S-1866 · The Protocol Layer — When Frameworks Die but Contracts Survive

You build your agent stack on LangGraph in January. By October, Microsoft has put AutoGen into maintenance mode, merged it into Agent Framework, and deprecated three upstream patterns. Your orchestration layer still works — because you built on MCP and A2A, not on framework abstractions. Teams that hardwired against AutoGen's conversation API spent Q4 rewriting. Teams that built on protocols spent Q4 shipping.

## Forces

- **Frameworks rot faster than protocols.** AutoGen had 60,000+ GitHub stars and went into maintenance in October 2025, eight months after the YC S25 batch was full of AutoGen-based startups. LangChain, CrewAI, and LlamaIndex have each had major breaking-version transitions that broke production stacks. Meanwhile, MCP and A2A — the protocol layer — persist across framework churn.
- **37% of multi-agent failures trace to inter-agent coordination, not individual agent capability.** The pattern you choose for connecting agents — not the model you pick — determines reliability, latency, cost, and debuggability at scale. (Swarmsignal, Feb 2026)
- **Two protocols, two layers, no overlap.** MCP governs how agents reach tools. A2A governs how agents reach each other. Conflating them is the most common architectural mistake teams make in 2025–2026.
- **Protocol adoption outlasts framework lock-in.** A2A was donated to the Linux Foundation in June 2025 with 50+ partners including AWS, Microsoft, Salesforce, and SAP. MCP has native support across Anthropic, OpenAI, Google Gemini, and AWS Bedrock. Both are vendor-neutral and persist independent of any single framework.

## The Move

Use MCP for the tool-integration layer and A2A for the inter-agent communication layer. Build your orchestration logic against these protocol contracts, not against LangGraph or CrewAI abstractions.

- **MCP (Model Context Protocol):** The 3-step tool call cycle — schema presentation, model outputs structured call, system executes and feeds result back. Replace hardcoded tool definitions in system prompts with Dynamic Manifests that fetch only the tools relevant to the current intent. This cuts token overhead and reduces hallucinated tool invocations. Anthropic released it November 2024; adoption is now universal.
- **A2A (Agent-to-Agent):** Google's open protocol for agent-to-agent collaboration, using Agent Cards for discovery and task exchange. Standardizes the "hand-off" problem — who does what, who gets notified, who owns the final output. Donated to Linux Foundation June 2025 with 50+ partners.
- **Supervisor-Worker as the stable pattern:** A central supervisor agent classifies each task and routes to specialized sub-agents. Communication scales O(N) rather than O(N²) (where every agent talks to every other). This is the pattern Optio uses in Kubernetes, routing Claude Code/Codex agents in isolated pods per repository. It's also the dominant pattern in enterprise multi-agent stacks documented across LangGraph, CrewAI, and the AI system design guide.
- **Protocol adapters over framework coupling:** Write thin adapter layers between your orchestration code and the framework SDK. When the framework dies (AutoGen → maintenance), you swap the adapter, not the orchestration logic. This is the insight teams who survived the AutoGen migration share: protocol-level contracts are the stable surface.
- **Five supervisor design principles (Markaicode, 2026):** Centralized state store (PostgreSQL/Redis for checkpointing), timeout + retry per sub-agent with exponential backoff, stateless supervisor (reload context from store on every request), OpenTelemetry instrumentation on sub-agent execution, hard recursion depth limits.

## Evidence

- **AutoGen maintenance mode (October 2025):** Microsoft merged AutoGen and Semantic Kernel into Microsoft Agent Framework. AutoGen is now bug/security fixes only. The community fork (AG2) and the new Agent Framework SDK diverge from AutoGen's conversation API. Source: [Microsoft Learn — AutoGen to Agent Framework Migration Guide](https://learn.microsoft.com/en-us/agent-framework/migration-guide/from-autogen/), [Atlan — AutoGen Explained](https://atlan.com/know/ai-agent/what-is-autogen/), [Automations Cookbook](https://automationscookbook.com/blog/autogen-to-microsoft-agent-framework-migration-guide)
- **MCP + A2A as the converging stack:** MCP released November 2024, adopted by Anthropic, OpenAI, Google, Microsoft, AWS, and Cursor/Zed for IDE integration. A2A donated to Linux Foundation June 2025. Zylos Research (Feb 2026) documents the convergence: "the industry consensus points toward multi-protocol coexistence, analogous to how HTTP, WebSockets, and gRPC coexist for different communication needs." Source: [Zylos Research — Agent Communication Protocols](https://zylos.ai/research/2026-02-15-agent-to-agent-communication-protocols), [Xcapit — MCP vs A2A](https://www.xcapit.com/en/blog/agent-to-agent-protocols-mcp-a2a-2026)
- **Dynamic manifests replacing hardcoded tools:** The AI System Design Guide (GitHub, ombharatiya/ai-system-design-guide) documents the production shift from hardcoded tool schemas in system prompts to Dynamic Manifests that fetch only the relevant tool subset per intent — reducing token overhead and tool-call hallucination rates. Source: [AI System Design Guide — Tool Use and MCP](https://github.com/ombharatiya/ai-system-design-guide/blob/main/07-agentic-systems/03-tool-use-and-mcp.md)

## Gotchas

- **MCP and A2A are complementary, not competing.** MCP governs agent-to-tool. A2A governs agent-to-agent. If you try to use only one, you end up forcing agents to share state through tool calls — which collapses the separation of concerns and creates the O(N²) coordination mess the supervisor pattern solves.
- **Framework abstractions leak into your logic if you let them.** If your orchestration code directly calls `langgraph.graph.invoke()` or `crewai.Kickoff()`, swapping frameworks requires rewriting orchestration. Use thin protocol-level wrappers instead — your supervisor graph should be readable as intent-to-agent mappings, not as framework SDK calls.
- **Dynamic manifests add latency on cold paths.** Fetching the tool manifest per intent introduces an upfront call. Cache aggressively (5-minute TTL minimum) and fall back to a pinned manifest for latency-sensitive paths.
