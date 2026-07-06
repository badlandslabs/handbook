# S-702 · Orchestration Stratification — A Spectrum, Not a Framework

[You've built a proof-of-concept agent. It works. Now you're deciding what runs it in production — and every framework you evaluate has a different mental model. The real question isn't "LangGraph vs CrewAI" — it's "how much orchestration complexity does your workflow actually require, and can you pay that cost?"]

## Forces

- **Framework overhead vs. capability:** High-control tools (LangGraph) give you time-travel debugging, human-in-the-loop interrupts, and explicit state machines — but they require significant framework investment. High-abstraction tools (CrewAI, AutoGen) get you running in hours but lock you into their mental model.
- **Workflow complexity vs. team size:** The more agents, conditional branching, and rollback requirements your workflow has, the more you need explicit orchestration. But if your team is three people and your agent is a single loop, all that infrastructure is tax, not leverage.
- **Multi-agent is mostly marketing:** McKinsey analyzing 50+ agentic builds found that "most multi-agent architectures in production are actually single agents augmented with tools." True multi-agent coordination — where agents negotiate, delegate, and resolve conflicts — is rare and expensive to get right.
- **The 2% ceiling:** Only 2% of organizations have full production agent deployments. Gartner projects 40%+ of agentic AI projects will be cancelled by 2027. The bottleneck is rarely the LLM — it's the workflow design and orchestration infrastructure.

## The Move

Orchestration isn't a framework choice — it's a stratified capability ladder. Match your position to your workflow complexity:

**Layer 1 — Loop + Tools (lowest overhead):**
- Single ReAct loop with function-calling tools
- No framework needed: raw API calls + structured output parsing
- Stateless or simple Redis session storage
- Best for: narrowly scoped, high-volume tasks (classification, extraction, single-step API interactions)

**Layer 2 — High-level orchestration (moderate overhead):**
- CrewAI, AutoGen, or n8n agents
- Role-based agents, sequential or parallel task execution
- Built-in memory, tool registry, basic observability
- Best for: multi-step workflows with 2-5 agent roles, team-like task decomposition

**Layer 3 — Graph-based state machines (high overhead, high control):**
- LangGraph (or Temporal + LLM adapters)
- Explicit graph topology: nodes = agents, edges = state transitions
- Checkpointing, time-travel debugging, human-in-the-loop interrupts
- Conditional branching without hardcoded if/else chains
- Best for: complex workflows requiring rollback, multi-turn negotiation, complex branching logic

**Layer 4 — Platform orchestration (outsourced complexity):**
- Azure AI Agent Service, AWS Bedrock Agents, OpenAI Assistants API
- Built-in tool calling, memory, file management, rate limiting
- Less control, faster time-to-production, vendor lock-in risk
- Best for: teams without dedicated AI engineering, standard enterprise workflows

## Evidence

- **McKinsey QuantumBlack (Sep 2025):** Analyzed 50+ agentic builds. Primary finding: "It's not about the agent — it's about the workflow." Organizations focusing on workflow redesign achieved value; those focusing on agent technology frequently ended up re-hiring people where agents had failed. 2% of organizations have full production deployments. — [mckinsey.com/capabilities/quantumblack/our-insights/one-year-of-agentic-ai-six-lessons](https://www.mckinsey.com/capabilities/quantumblack/our-insights/one-year-of-agentic-ai-six-lessons-from-the-people-doing-the-work)
- **Technspire State of Agentic AI (Dec 2025):** Of four categories that shipped to production — developer tooling, internal ops automation, research/analysis, customer support augmentation — "more accurately described as tool-augmented LLMs than true multi-step agents." The multi-agent hype vastly outpaced actual architectural adoption. — [technspire.com/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/blog/state-of-agentic-ai-end-2025-production-lessons)
- **HN discussion on multi-agent platform stacks (Jul 2025):** Practitioners building multi-agent platforms reported LangGraph as the "low level but useful" choice citing time travel, human-in-the-loop interrupts, and flexible state management as key differentiators. One team noted: "Once you need to scale beyond 5 agents with shared state and conditional routing, custom state machines hit a wall — that's when LangGraph pays for itself." — [news.ycombinator.com/item?id=48074184](https://news.ycombinator.com/item?id=48074184)

## Gotchas

- **The CrewAI production cliff:** Multiple teams report that agents behaving correctly in notebooks break when moved to production due to non-deterministic tool execution, lack of persistent memory, and missing retry logic. CrewAI works well for demos; LangGraph or custom state machines are the common escape route for production.
- **Multi-agent ≠ more agents:** Splitting a single agent into "planner" + "executor" agents doesn't make it multi-agent — it's still a single reasoning loop with a delegation step. True multi-agent coordination (peer negotiation, shared goals, conflict resolution) requires graph topology, not just role assignment.
- **Framework lock-in is real:** LangGraph's checkpointing, CrewAI's agent roles, and platform agents each create different migration costs. Teams that chose high-abstraction tools for speed often hit a ceiling where they can't express the workflow they actually need. Starting at Layer 2 is usually fine; starting at Layer 1 and migrating to Layer 3 mid-project is expensive.
- **LLM choice follows orchestration choice:** Complex graph-based workflows benefit from models with strong tool-calling and structured output (Claude 3.5 Sonnet, GPT-4o). Simple loop workflows can often use cheaper models (GPT-4o-mini, Claude 3.5 Haiku). Don't choose the LLM before sketching the orchestration layer.
