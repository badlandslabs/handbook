# S-1598 · The Orchestration Pattern Stack — When One Agent Is Not Enough

Your single agent accumulates 40 tool calls, loses track of what the first five did, hits a context ceiling, and hands you a confident answer that contradicts itself across steps. You reach for another agent to handle a second concern and discover you've just created a distributed system problem. This is the stack for deciding *which orchestration pattern* to reach for — and when adding orchestration makes things worse before it makes them better.

## Forces

- **Single agents hit context ceilings fast.** Even capable models degrade when asked to context-switch between research, coding, review, and deployment within one session. The fix isn't a bigger context window — it's partitioning cognitive load across specialized agents. Yet partitioning introduces coordination overhead that can exceed the original problem.
- **Multi-agent systems fail like distributed systems, not like chat.** Agents make implicit assumptions about state, ordering, and validation that don't survive contact with production. GitHub's analysis: "Common failure symptoms: agents take contradictory actions, downstream checks fail because prior steps didn't know they existed, actions are reasonable in isolation but break the overall workflow." Root cause: missing structure, not model capability. ([GitHub Blog — AI & ML, Feb 2026](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/))
- **Architecture-task alignment is the real differentiator.** By mid-2025, 73% of enterprises moved beyond AI pilots. Only 12% successfully scale autonomous agents across departments. Versalence's finding: "The difference between these groups is not budget or talent. It is architecture." ([Versalence Blogs, March 2026](https://blogs.versalence.ai/production-ai-agents-langgraph-complete-guide-2025))
- **72% of enterprise AI projects now involve multi-agent systems** (up from 23% in 2024), yet observability is the #1 barrier to production adoption. ([Zylos Research — Multi-Agent Orchestration Patterns 2025, Jan 2026](https://zylos.ai/research/multi-agent-orchestration-2025))

## The Move

Pick the orchestration pattern that matches your coordination requirement. Start simple; reach for complex patterns only when the simpler one demonstrably fails.

### The Six Core Patterns (ranked by complexity)

1. **Sequential Pipeline** — Agents in a fixed chain, each feeding output to the next. Best for: linear workflows where each step strictly depends on the prior (draft → review → edit → publish). Avoid when steps are independent — forcing serialization kills parallelism.
2. **Parallel Fan-Out / Fan-In** — One dispatcher sends independent tasks to multiple agents simultaneously, then aggregates results. Best for: parallel research, data collection across sources, batch operations. Avoid when tasks have hidden dependencies — you won't discover them until a downstream agent fails.
3. **Supervisor (Router)** — A single orchestrator agent decides which sub-agent handles each piece of work, routes accordingly, and assembles the response. Best for: complex, branching workflows with a clear governance point. Avoid when the supervisor becomes the bottleneck — if it can't route reliably, the whole system degrades.
4. **Hierarchical** — A supervisor delegates to sub-supervisors, which delegate to workers. Best for: enterprise-scale systems with 20+ agents, where flat coordination overhead becomes unmanageable. Avoid in small systems — the coordination hierarchy is overhead you don't need yet.
5. **Evaluator-Optimizer Loop** — A generator produces output; an evaluator judges it against criteria; the generator revises. Best for: tasks where quality improves through iteration (code generation, writing, planning). Avoid when iteration cost exceeds the quality gain — evaluate whether the first pass is "good enough."
6. **Event-Driven (Actor Model)** — Agents subscribe to event streams and react asynchronously. Best for: reactive systems, monitoring, real-time processing. Avoid when you need deterministic ordering — async behavior makes debugging harder.

### Practical Implementation via LangGraph (production-proven)

LangGraph has emerged as the foundational orchestration layer for complex agentic workflows, offering cyclic computation graphs that mirror how real business processes work. Three-level state management required for production: **Working Memory** (current conversation), **Persistent Storage** (cross-session), **Shared State** (between agents). ([Versalence Blogs](https://blogs.versalence.ai/production-ai-agents-langgraph-complete-guide-2025))

### Tool Connectivity via MCP

Anthropic's Model Context Protocol (MCP) is becoming the de facto standard for agent-tool connectivity. Production metrics: 6.7M weekly TypeScript SDK downloads, 9M+ Python SDK downloads, 1,100+ GitHub repositories, 16,000+ active MCP servers. AWS and Azure have rolled out MCP workflow services. Block built an internal agent called Goose on MCP architecture — all servers built in-house for security control. ([Xenoss — MCP in Enterprise, 2025](https://xenoss.io/blog/mcp-model-context-protocol-enterprise-use-cases-implementation-challenges))

Anthropic's November 2025 advanced tool use features address context bloat from large tool libraries: **Tool Search Tool** (85% token reduction, 95% context preserved), **Programmatic Tool Calling** (37% token reduction, parallel execution), **Tool Use Examples** (18% accuracy improvement: 72%→90%). ([Anthropic Engineering, Nov 2025](https://www.anthropic.com/engineering/advanced-tool-use))

## Evidence

- **Enterprise Survey — MMC Ventures:** 30+ startup founders + 40+ enterprise practitioners. Finding: "The main blockers aren't technical. Most founders pointed to workflow integration, employee trust, and data privacy as the toughest challenges — not model performance." Multi-agent systems evolved from simple Q&A chatbots → sophisticated systems capable of multi-step reasoning and autonomous action. ([MMC Ventures — State of Agentic AI, March 2025](https://mmc.vc/research/state-of-agentic-ai-founders-edition/))
- **GitHub Real-World Data:** Multi-agent workflow failures analyzed across GitHub Copilot and enterprise deployments. Root cause finding: "Multi-agent systems behave like distributed systems, not chat interfaces. Without explicit instructions, data formats, and interfaces, things won't work as planned." Specific mitigations: shared schemas between agents, explicit success/failure contracts, structured state passing. ([GitHub Blog — AI & ML, Feb 2026](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/))
- **Production LangGraph Guide — Versalence:** Real-world implementation showing stateful agent architecture outperforms stateless chatbot pattern. Key metrics: 73% enterprise pilot adoption, but only 12% achieve multi-department scaling — gap attributable to architecture decisions, not model capability. ([Versalence Blogs, March 2026](https://blogs.versalence.ai/production-ai-agents-langgraph-complete-guide-2025))
- **Zylos Research Cross-Reference:** 72% of enterprise AI projects now use multi-agent systems (up from 23% in 2024). Token duplication is a major concern: MetaGPT 72%, CAMEL 86%, AgentVerse 53%. Real-world results cited: 80% reduction in insurance claims processing, $18.7M annual savings in banking fraud. ([Zylos Research — Multi-Agent Orchestration Patterns 2025](https://zylos.ai/research/multi-agent-orchestration-2025))
- **GitHub Community Pattern Catalog:** awesome-agentic-patterns (4,828 stars, 433 forks, created May 2025) — community-curated patterns backed by blog posts, talks, repos, or papers. Explicit criteria: repeatable, agent-centric, traceable. ([GitHub — nibzard/awesome-agentic-patterns](https://github.com/nibzard/awesome-agentic-patterns))

## Gotchas

- **Adding agents before you need them.** A second agent introduces coordination, state-sharing, and failure-handling requirements that a single agent doesn't have. If your task doesn't have demonstrable cognitive load or independence problems, a sequential prompt chain inside one agent is faster and cheaper.
- **No shared schema between agents.** When agents pass data implicitly (through natural language), downstream agents misinterpret upstream outputs. The GitHub blog's fix: define explicit schemas for inter-agent contracts, including required fields, formats, and error conditions.
- **Token duplication across the team.** Zylos Research found that open multi-agent frameworks duplicate context aggressively — MetaGPT at 72%, CAMEL at 86%. If your agents share context, you pay for it twice. Anthropic's Tool Search Tool (85% token reduction) addresses this at the tool layer; you need an equivalent at the agent layer.
- **No observability layer.** Zylos identifies observability as the #1 barrier to production adoption. Without traces showing which agent produced which output, when, and with what input, debugging multi-agent failures is archaeology. Build instrumentation before you add the second agent.
- **The supervisor becomes a single point of failure.** In supervisor patterns, if the routing agent fails or misroutes, the whole system stops. Mitigations: explicit fallback routes, timeout guards, human-escalation paths for high-stakes tasks.
