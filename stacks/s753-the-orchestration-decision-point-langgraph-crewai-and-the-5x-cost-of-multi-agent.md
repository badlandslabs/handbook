# S-753 · The Orchestration Decision Point — LangGraph, CrewAI, and the 5× Cost of Multi-Agent

When you have one agent working, the next question is how to coordinate multiple. The answer is not obvious and the trade-offs are steep. Teams that pick a framework without understanding the cost profile and control surface end up either over-engineered and slow, or under-controlled and burning budget.

## Forces

- **Fast prototyping and production stability pull in opposite directions.** CrewAI gets you a working multi-agent system in hours with its role-based team model. LangGraph gives you graph-based state machines that survive production but require significantly more code.
- **Token cost multiplies with every additional agent.** Multi-agent conversations in CrewAI cost 5× more than a single-agent equivalent. Enterprises average $85,521/month in AI operational costs — and teams report runaway agent loops costing anywhere from $15 in 10 minutes to $47,000 over 11 days.
- **The most common "multi-agent" production pattern is supervisor + specialists.** True peer-to-peer agent coordination is rare in production; most systems use one agent to decompose tasks and route to specialists that execute and report back.
- **MCP is becoming the de facto tool integration standard**, adopted by Anthropic, OpenAI, Google, Microsoft, IBM, and Amazon — which changes the long-term portability calculus for any orchestration choice.
- **Many experienced teams are rolling their own.** On HN's multi-agent production thread, multiple practitioners (segnomdy, pablovarela, olegbk) independently said "0 framework out there that's good enough for serious work."

## The move

**Match orchestration complexity to demonstrated need — not anticipated scale.**

### Pick CrewAI when:
- Building a role-based multi-agent team (Director → Strategist → Creative → Analyst)
- Speed-to-prototype matters more than fine-grained control
- Workflows map cleanly to agent roles with clear delegation
- Accept 5× token cost multiplier as baseline

### Pick LangGraph when:
- You need durable workflows with human-in-the-loop and time travel (replay, fork, rollback)
- State management across long conversations is critical
- You need graph-based visualization and precise step control
- You have the engineering capacity to manage a more explicit state machine model

### Pick AutoGen when:
- You're building in the Azure ecosystem
- Conversational multi-agent reasoning (agents debating, critiquing each other) is the core pattern
- Note: Microsoft's Agent Framework merger (AutoGen + Semantic Kernel) is targeting GA Q1 2026 — reassess landscape then

### Roll your own when:
- Production observability, failure recovery, and cost controls are non-negotiable
- Standard frameworks introduce unnecessary complexity for your actual workflow shape
- You need isolation and a control plane that frameworks don't expose
- Tools: AGNO is gaining traction as a minimalist option with clean isolation primitives

### Regardless of framework — enforce cost controls:
- Implement hard budget circuit breakers per agent per run
- Log input tokens, output tokens, latency, and cost for every LLM call
- Set max turn limits on agent loops (5–8 is typical)
- Route cheap tasks (classification, routing) to Haiku-class or Gemini Flash Lite models ($0.08–1.00/M input tokens)

## Evidence

- **HN Ask — Multi-Agent Orchestration:** Practitioners report rolling custom because frameworks lack production-grade observability and failure recovery. Data passing patterns: MongoDB, Redis scratchpads, shared state layers. Triggers: mix of webhooks, cron, and manual. — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)

- **TURION.AI — Multi-Agent Orchestration Lessons:** Supervisor + specialists is the dominant production pattern — one agent decomposes and routes, specialists execute. Pipeline (sequential) works for linear workflows. Most production "multi-agent" systems are actually this. Peer networks (agents negotiate directly) are rare and complex to debug. — [https://turion.ai/blog/multi-agent-orchestration-infrastructure-production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)

- **AIStackHub — Framework Comparison 2026:** Token cost multiplier for CrewAI multi-agent: 5× vs single-agent equivalent. All three major frameworks (LangGraph, CrewAI, AutoGen) are open source with no framework cost — only model API and infra. LangGraph chosen for durable enterprise workflows; CrewAI for fastest prototyping; AutoGen for Azure conversational patterns. — [https://aistackhub.ai/ai-agent-orchestration-platforms](https://aistackhub.ai/ai-agent-orchestration-platforms)

- **MCP Institute — Adoption Report 2026:** MCP (Model Context Protocol) reached enterprise adoption phase by Q2 2025. Linux Foundation took stewardship in December 2025. Adopted by Anthropic, OpenAI, Google, Microsoft, IBM, and Amazon. Phase 3 (2025–2026): enterprise production deployments. Changes the long-term lock-in calculus — MCP-compliant tool integrations are now portable across frameworks. — [https://mcp.institute/research/mcp-adoption-report](https://mcp.institute/research/mcp-adoption-report)

- **Zylos Research — Agent Cost Engineering:** Enterprise AI operational costs averaged $85,521/month in 2025. 60–85% of spend is recoverable through caching, routing, and budget enforcement. Model routing from Opus ($5/M in) to Haiku ($1/M in) for simple classification tasks saves ~80%. Prompt caching recovers 30–50% on repeated contexts. — [https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics](https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics)

- **Dev.to — Multi-Agent Patterns:** Claude Opus 4.6 at $5.00/$25.00 per M tokens vs Gemini Flash Lite at $0.08/$0.30. A routing agent that classifies and routes saves ~98% on routing calls. Every agent iteration costs tokens, time, and compounding error probability. — [https://dev.to/matt_frank_usa/building-multi-agent-ai-systems-architecture-patterns-and-best-practices-5cf](https://dev.to/matt_frank_usa/building-multi-agent-ai-systems-architecture-patterns-and-best-practices-5cf)

- **Data-Gate — Multi-Agent Production Lessons:** A fintech company reduced agent count from 7 to 3 after discovering 4 agents were handling tasks a single well-prompted agent could do. Start with one agent, identify specific bottlenecks, split only at natural boundaries (different expertise domains, parallelizable subtasks, quality checkpoints). — [https://data-gate.ch/multi-agent-systems-production-lessons](https://data-gate.ch/multi-agent-systems-production-lessons)

- **HN Comment — Stack Stratification:** The agent stack is stratifying into layers (orchestration, sandboxing, execution, memory, tools) with different defensibility profiles. Going monolithic across layers is the wrong call. Sandboxing is becoming its own specialized layer (E2B, Modal, Firecracker wrappers). — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)

## Gotchas

- **Don't add agents before you have a single agent working end-to-end.** Multi-agent complexity compounds reliability problems (see S-752: compound probability). Split only at demonstrated bottlenecks.
- **MCP adoption is no longer optional for long-term portability.** If your framework doesn't support MCP, your tool integrations will require custom adapters for every new service. All major providers now support it.
- **Framework choice is sticky.** Switching from CrewAI's role-based model to LangGraph's graph model mid-production is expensive. Audit whether your actual workflow is role-centric or control-flow-centric before committing.
- **Observability is the most underinvested part of multi-agent systems.** Multiple HN practitioners cite it as the gap in every framework. Build dedicated logging (input/output/token/latency per agent step) before you need it, not after.
- **Cost circuit breakers must be explicit, not aspirational.** Define max budget per agent per run, not per system. A runaway sub-agent can exhaust a session budget while the main agent looks fine.
