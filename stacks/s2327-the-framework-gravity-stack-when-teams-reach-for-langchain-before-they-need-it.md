# S-2327 · The Framework Gravity Stack — When Teams Reach for LangChain Before They Need It

A team ships a prototype in three days using direct API calls. It works. A colleague says: "We should really use a framework — for production." Six months later, they are still migrating, the framework's abstraction layers don't map cleanly to their internal observability stack, and the "production-ready" agent runs on a single path that a direct-API prototype had already solved. This is not a technology failure. This is a decision pattern — the gravitational pull toward heavyweight orchestration frameworks before the problem actually requires them.

## Forces

- **Framework adoption is the default, not the earned choice.** Frameworks like CrewAI (52k stars, ~2B agent executions in 12 months), LangGraph, AutoGen, and Semantic Kernel present themselves as the "serious" choice. Starting with direct API calls feels like a prototype decision, not a production decision.
- **Abstraction layers have hidden coupling costs.** A framework's tool interface, memory model, and observability hooks don't map cleanly to your internal stack. Every gap requires adaptation code that defeats the purpose of the abstraction. HN users reported months-long migrations from ad-hoc API code to frameworks, then struggled to integrate framework outputs with existing observability.
- **Single agents win most of the time.** Princeton NLP found single agents match or outperform multi-agent systems on **64% of benchmarked tasks** at roughly half the cost. Multi-agent adds 2.1 percentage points of accuracy at double the cost. Reaching for an orchestration framework is usually premature optimization.
- **The "production-ready" framing is a trap.** Anthropic's own guidance (building effective agents) says: "start by using LLM APIs directly." Anthropic's own Claude Code SDK — the tool built to demonstrate agentic best practices — is intentionally minimal, single-agent, and direct-API-based. The framework that ships is not the framework the model maker ships.
- **Framework churn is high.** Microsoft Agent Framework reached 1.0 GA in April 2026, unifying AutoGen and Semantic Kernel. CrewAI crossed 52k stars in mid-2026. LangChain has been reorganized multiple times. Picking a framework means picking a point in a moving landscape.

## The move

**Start at the API. Add complexity only when the cost of that complexity is lower than the cost of its absence.**

- **Ship V0 on direct API calls.** Use the provider's native SDK (Anthropic, OpenAI, Google). Build your own orchestration loop in <200 lines. Ship. This gives you a working baseline with full control over every abstraction layer.
- **Add a framework only when you have a specific, named problem the API approach can't solve cleanly.** E.g., "we need to run 50 agents in parallel and fan-in their results" or "we need A2A protocol support for cross-service agent communication." The problem statement must come before the framework, not the other way around.
- **Treat multi-agent orchestration as a scaling decision, not a launch decision.** 64% of tasks don't need it. If your agent's workflow is linear or branching-within-context, a single agent with good tool definitions and a max-turns guard is sufficient.
- **Isolate the framework at the boundary.** If you adopt CrewAI or LangGraph, wrap it behind an internal interface. The day you need to swap — and you likely will — the migration cost stays bounded.
- **Validate the orchestration pattern before the framework.** Read the failure modes of each pattern: Orchestrator-Worker (cascade failures), Supervisor pattern (single bottleneck), Pipeline (no recovery from mid-stream failure), Hierarchical (coordination overhead). Know which one your problem actually needs.

## Evidence

- **Anthropic engineering guidance:** "We suggest that developers start by using LLM APIs directly" — contrasted against the industry's rush to framework adoption. Anthropic's own Claude Code SDK (minimal, single-agent, direct-API) is the reference implementation of this principle.
  — [Building Effective AI Agents](https://www.anthropic.com/engineering/building-effective-agents) (June 2025), HN discussion 543 points, 88 comments
- **HN practitioner report:** A developer described shipping a V0 with direct Java API calls, delivering quickly with clean architecture and observability. A team then spent months migrating to a named framework, still incomplete. "People underestimate that cost. So by default to get your V0 product off the ground (if you are not a complete startup), just use the API."
  — [Building Effective AI Agents | Hacker News](https://news.ycombinator.com/item?id=44301809), comment by davedx (June 2025)
- **Princeton NLP benchmark:** Single agents matched or outperformed multi-agent systems on 64% of benchmarked tasks. Multi-agent added 2.1 percentage points of accuracy at approximately double the cost. Multi-agent is justified only for complex cross-domain tasks — not the majority of production agent deployments.
  — [beam.ai synthesis of Princeton NLP findings](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production) (August 2026)
- **MMC Ventures research:** Surveyed 30+ European agentic AI startup founders + 40+ enterprise practitioners. Found 62% of startups tap Line of Business budgets — meaning they had to ship something, not architect something. The top deployment challenges were workflow integration (60%), employee resistance (50%), and data privacy (50%) — organizational problems, not framework-selection problems.
  — [State of Agentic AI: Founder's Edition](https://mmc.vc/research/state-of-agentic-ai-founders-edition/), MMC Ventures (November 2025)
- **RAND Corporation + Gartner:** ~80% of enterprise AI projects fail to move beyond proof of concept. For agentic AI specifically, Gartner projects >85% failure rates through 2026 without proper evaluation frameworks — not without proper orchestration frameworks. The failure is in scope definition and measurement, not in tool selection.
  — [Why 80% of AI Agent Projects Fail](https://udit.co/blog/raw/why-ai-agent-projects-fail), 50+ production deployments (2025)
- **Framework landscape data:** CrewAI 1.14.6 (52.4k stars, ~2B agent executions in 12 months); Microsoft Agent Framework 1.0 GA April 2026 (unified AutoGen + Semantic Kernel, MCP + A2A support); Google ADK four-language SDK (Python, TypeScript, Java, Go); Anthropic Claude Code SDK intentionally minimal single-agent.
  — [AI Agent Frameworks 2026 Comparison](https://www.morphllm.com/ai-agent-framework) (2026)

## Gotchas

- **The "we'll add evals later" trap.** Most agent project failures are attributed to wrong orchestration patterns or scope creep — not to missing frameworks. Frameworks don't fix either. Ship something measurable, then add complexity.
- **Framework comparisons are cargo-culted.** Reading "CrewAI vs LangGraph vs AutoGen" blog posts is not the same as understanding your actual workflow. The comparison is only meaningful after you've shipped and found a specific gap.
- **MCP and A2A are protocols, not frameworks.** Anthropic, Google, and Microsoft have aligned on MCP (tool use) and A2A (agent-to-agent communication) as open protocols. Adopting these protocols doesn't require adopting any particular framework — use them directly if your use case needs cross-agent tool sharing.
- **The framework you pick today may not exist tomorrow.** LangChain has restructured multiple times. AutoGen merged into Microsoft's unified Agent Framework. Framework loyalty is not a viable strategy — interface isolation is.
