# S-2909 · The Agent Orchestration Pattern Stack

When one agent is too many and ten is not enough — choosing how to coordinate multiple LLMs, tools, and state in a production agentic system.

## Forces

- **The God Agent problem** — a single agent handling routing, retrieval, reasoning, and execution burns through context windows, produces confusing reasoning traces, and fails non-deterministically. One 2000-line prompt is impossible to debug.
- **The multi-agent coordination problem** — splitting work across agents introduces new failure modes: infinite loops, race conditions on shared state, error cascading, and context blowup from passing full conversation history between agents.
- **The framework choice problem** — three dominant paradigms (graph state machines, role-based crews, conversational agents) look similar in tutorials but diverge sharply in production. Picking the wrong one means weeks of refactoring.
- **The protocol explosion problem** — MCP and A2A now define the integration layer, but teams still have to decide where in the stack they sit and which one to adopt first.

## The move

### Choose your orchestration paradigm by failure mode tolerance, not feature list

- **LangGraph (graph-based state machines)** — explicit nodes, edges, and typed state. Built-in checkpointing to SQLite/PostgreSQL/Redis lets you resume on failure. `interrupt()` enables first-class human-in-the-loop. Best for: complex cycles, fault tolerance requirements, production systems where you need to audit exactly what happened at each step. ~10,200 GitHub stars, 38M+ monthly PyPI downloads.
- **CrewAI (role-based crews)** — agents as "researcher," "writer," "critic" with explicit tasks and delegation. Faster to scaffold; harder to debug because execution flow is implicit. Best for: rapid prototyping, content pipelines, well-defined role-mapping problems. ~47,000 GitHub stars, $18M Series A.
- **AutoGen (conversational agents)** — fundamentally about agents talking to each other. Elegant for chat patterns, awkward for anything else. Entered maintenance mode October 2025; successor is Microsoft Agent Framework. Avoid for new projects.

### Constrain agents ruthlessly at the prompt level

- 2 tools + specific backstory beats 6 tools + broad goals. Narrow scope prevents tool-calling confusion and reduces hallucination surface.
- Set `max_iter` explicitly — CrewAI defaults to 25, which can burn 5–10× your token budget on a single bad run. Set to 5–8 per agent.
- Use `output_pydantic` (or equivalent structured output) to force valid formats and enable programmatic downstream processing. This is the top production reliability fix teams report.

### Layer protocols beneath the orchestration framework

- **MCP (Model Context Protocol)** — standardizes agent-to-tool connections. Anthropic-origin (Nov 2024), donated to Agentic AI Foundation under Linux Foundation (Dec 2025). Reached 97M monthly SDK downloads and 10,000+ public servers by early 2026. Every major provider (OpenAI, Google, Microsoft) ships first-class MCP support. Use it to connect agents to external tools and data sources.
- **A2A (Agent2Agent Protocol)** — Google-origin (Apr 2025), complements MCP by standardizing agent-to-agent discovery, negotiation, and delegation. Uses HTTP + JSON-RPC + SSE for streaming. ~150 production adopters by mid-2026. Use it when two agents need to negotiate work, not just share context.
- **AP2** — emerging protocol for agent-to-agent payments (referenced in production guides; adoption metrics less settled).

### Model routing within the orchestration layer

- Use cheap/fast models (Claude Haiku, GPT-5.4 Nano, Gemini 2.5 Flash) for routing, classification, and extraction tasks.
- Use balanced models (Claude Sonnet 4.6, GPT-5.4, Gemini 2.5 Pro) for most production reasoning.
- Use premium models (Claude Opus 4.7, GPT-5.5, Gemini 2.5 P) only for complex multi-step reasoning.
- Teams report 3-agent pipelines at 100 runs/day cost ~$900/month; switching editors to gpt-4o-mini saves ~30%.

### Design for the four failure modes explicitly

1. **Infinite loops** — add explicit termination conditions and iteration caps.
2. **Context blowup** — pass only relevant slices of state between agents, not full history.
3. **Error propagation** — isolate agents so one bad tool call doesn't corrupt the entire workflow.
4. **Race conditions** — if agents write to shared state in parallel, use a serialization checkpoint or mutex node in your graph.

## Evidence

- **Blog post:** "Multi-agent AI systems in production: LangGraph, CrewAI, AutoGen" — Imperialis Tech. Documents all three frameworks against production criteria. Notes that 70% of organizations building multi-LLM apps will use orchestration platforms by 2028 (Gartner). Source: https://imperialis.tech/en/blog/multi-agent-systems-langgraph-crewai-autogen-production
- **Blog post:** "CrewAI in Production 2026: Real Lessons from Deploying Multi-Agent Systems" — AgileSoftLabs (June 2026, 16-min read). Reports `max_iter=25` default causes 5–10× token budget overages; recommends 5–8. Reports `output_pydantic` as top reliability fix. Documents 3-agent pipeline at 100/day ≈ $900/month. Source: https://www.agilesoftlabs.com/blog/2026/06/crewai-in-production-2026-real-lessons
- **DEV Community:** "AutoGen vs LangGraph vs CrewAI: Which Agent Framework Actually Holds Up in 2026?" — Moon Robert (March 2026). Author rebuilt identical 4-agent pipeline (Researcher, Summarizer, Critic, Writer with cycle) in all three frameworks. Recommends LangGraph for production-facing, cycle-requiring pipelines: "the state machine model maps directly to how complex workflows actually behave, the debugging story with LangSmith is strong, and the code is explicit enough that I can reason about failures without rerunning everything." Source: https://dev.to/synsun/autogen-vs-langgraph-vs-crewai-which-agent-framework-actually-holds-up-in-2026-3fl8
- **Blog:** "LangGraph vs CrewAI: Multi-Agent Orchestration Compared (2025)" — Nexus. Reports LangGraph ~10,200 GitHub stars / 38M+ PyPI downloads; CrewAI ~47,000 GitHub stars / $18M Series A. Documents both frameworks' state management, checkpointing, and human-in-the-loop capabilities. Source: https://agent.nexus/blog/langgraph-vs-crewai
- **Blog:** "Agent Orchestration in Production: LangGraph, CrewAI, and Multi-Agent Workflows" — Sandesh Rana / Nepex Group (July 2026). Lists four canonical failure modes: infinite loops, context blowup, error propagation, race conditions. Source: https://blog.nepexgroup.com/ai/backend/2026/07/04/agent-orchestration-langgraph-crewai-production-workflows.html
- **Blog:** "MCP at 97M Downloads" — Agent MarketCap (April 2026). Documents Anthropic-origin (Nov 2024), Linux Foundation donation (Dec 2025), 97M monthly SDK downloads, 10,000+ public servers, 50+ enterprise partners. Notes adoption pace faster than React (3 years) or gRPC (7 years). Source: https://agentmarketcap.ai/blog/2026/04/14/mcp-97m-sdk-downloads-10000-servers-protocol-platform-inflection
- **GitHub:** Google's A2A protocol repo. Documents protocol design (HTTP + JSON-RPC + SSE), April 2025 launch with 50+ enterprise partners, Linux Foundation contribution June 2025, 150+ production adopters by mid-2026. Source: https://github.com/a2aproject/A2A
- **GitHub:** "Arvo – TypeScript toolkit for event-driven agentic workflows" — HN Show HN (2025). Implements virtual orchestration through physical choreography; handlers stateless, workflows persist as JSON. Source: https://news.ycombinator.com/item?id=46451417

## Gotchas

- **AutoGen is effectively deprecated** for new work — it entered maintenance mode October 2025. If you're starting a project that might need conversational patterns, evaluate Microsoft Agent Framework instead.
- **CrewAI's speed is its trap** — scaffolding a crew takes hours; debugging a production crew with 5+ agents takes days. The ease of setup misleads teams into underestimating production complexity.
- **Sequential > Hierarchical for reliability** — hierarchical agent delegation adds non-determinism. Start with sequential chains; promote to hierarchical only when you've characterized the failure modes of the simpler setup.
- **MCP adoption ≠ A2A adoption** — most teams use MCP for tool access today. A2A for agent-to-agent negotiation is earlier in adoption. Don't assume your whole team needs both; start with MCP if you're primarily connecting agents to external tools.
- **Framework choice is sticky** — switching from CrewAI's role-based model to LangGraph's state machine model after the crew is built requires near-complete rewrite. Invest time in the decision upfront.
