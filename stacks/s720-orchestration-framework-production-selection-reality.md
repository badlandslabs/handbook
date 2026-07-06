# S-720 · Orchestration Framework Selection: What Teams Actually Pick and Why

[Most teams approach framework selection as a research problem. It isn't. The decision is driven by team stage, reliability requirements, and a predictable migration path: CrewAI for the first month, LangGraph by month three, and custom state machines for anything that touches production money.]

## Forces

- **LangGraph and CrewAI optimize for opposite things.** CrewAI optimizes for time-to-first-agent. LangGraph optimizes for production maintainability. Teams confuse these as equivalent choices.
- **The migration tax is predictable and avoidable.** Most teams start on CrewAI (or raw API), hit reliability walls around month two, and spend month three migrating to LangGraph. The cost is real; the outcome is avoidable by choosing correctly upfront.
- **AutoGen occupies a different niche than it appears.** Despite similar surface-area, AutoGen's conversational multi-agent model fits Azure-first experimentation better than general-purpose production orchestration.
- **Framework choice is downstream of team composition.** A team of two shipping a startup feature has fundamentally different needs than a five-person AI engineering team building a multi-agent pipeline. The "right" answer changes with your stage.

## The Move

**Choose based on where you'll be in three months, not where you are today.**

### LangGraph — your destination for anything that matters
- Use it when: production deployment is 4+ weeks away, you need multi-step workflows with conditional branching, you need LangSmith observability or checkpointing, you are integrating MCP tools
- Architecture: graph-based state machines — agents are nodes, transitions are edges, state is explicit and serializable
- Strength: retry primitives, time-travel debugging, explicit control flow, first-class MCP integration
- Weakness: steeper learning curve, more boilerplate than CrewAI
- Telltale sign you need it: "our agent sometimes loops" or "we can't reproduce the failure"

### CrewAI — right for throwaway experiments and learning
- Use it when: internal prototype with a hard deadline, exploring multi-agent team concepts for the first time, the agent will be discarded after the experiment
- Architecture: role-based agents with shared goals — fastest onboarding of the three
- Strength: ships a demo agent in hours, intuitive concept of agents-as-roles
- Weakness: requires custom patterns for retry/long-running jobs, observability must be assembled manually, debugging harder in production
- Telltale sign you chose wrong: you are planning to "clean it up later" before shipping

### AutoGen — when collaboration is the product
- Use it when: you are building multi-agent conversational reasoning as a core UX feature, you are Azure-native, you are doing experimental research on agent-to-agent negotiation
- Architecture: conversational agents that exchange messages, optimized for dialogue patterns
- Strength: natural fit for agent collaboration use cases, strong Azure ecosystem integration
- Weakness: production-grade deployment requires significant custom scaffolding, harder to debug than LangGraph
- Telltale sign you need it: your primary use case is agents talking to each other as the user-facing product

### Model-tier routing — non-negotiable in production
- Route simple tasks (classification, extraction, routing) to Haiku or GPT-5.4 Nano
- Route most reasoning to Sonnet 4.6 or GPT-5.4
- Reserve Opus or GPT-5.5 for complex multi-step reasoning only
- Cost impact is 5-10x between tiers — routing mistakes compound monthly

## Evidence

- **GitHub decision guide (2026):** Framework matrix showing LangGraph for production reliability, CrewAI for demos, AutoGen for experimental collaboration, and raw Claude API as a viable no-framework path — [github.com/benconally/ai-agent-framework-decision-guide](https://github.com/benconally/ai-agent-framework-decision-guide)
- **Production lessons post:** Teams that succeed follow the same pattern: start simple (Level 1 single agent), instrument everything from day one, set cost guardrails before they need them, and resist the urge to go multi-agent until a single agent is reliable. Demos don't show the 30% of cases where agents loop or the silent data corruption that hits at 3 AM — [theaivibe.org/blog/building-production-ai-agents-lessons-2025](https://theaivibe.org/blog/building-production-ai-agents-lessons-2025)
- **Real cost data (Vincent van Deth, AI Architect):** 11-agent production system at $2,847/month unoptimized, dropped to $370/month after implementing cascading model routing, context trimming, and action-space enforcement — an 87% reduction from operational discipline, not model swaps — [vincentvandeth.nl/blog/real-cost-ai-agents-production](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Framework comparison (iSwift, 2026):** Teams searching LangGraph vs CrewAI vs AutoGen are not choosing a framework for demos — they are choosing for reliability under operational pressure. LangGraph leads on production reliability, CrewAI on prototyping speed, AutoGen on Azure-native conversational collaboration — [iswift.dev/comparisons/langgraph-vs-crewai-vs-autogen-2026](https://www.iswift.dev/comparisons/langgraph-vs-crewai-vs-autogen-2026)
- **Multi-agent coordination patterns (TURION.AI):** Three dominant coordination patterns — hierarchical (supervisor delegates to specialists), peer-to-peer (agents negotiate), and hybrid — with Generator-Verifier as a fourth production pattern that consistently outperforms single-agent loops on complex outputs — [turion.ai/blog/multi-agent-collaboration-patterns](https://turion.ai/blog/multi-agent-collaboration-patterns)

## Gotchas

- **CrewAI is not production-ready out of the box.** It ships fast but requires significant custom scaffolding for retry logic, observability, and cost controls before it matches LangGraph's production defaults.
- **Migrating from CrewAI to LangGraph mid-production is painful.** State that was implicit in CrewAI's role-based model needs to be made explicit in LangGraph's graph structure. Plan for this.
- **AutoGen's conversational model is not the same as orchestration.** If you need reliable workflow orchestration (branching, state, retries), AutoGen's dialogue-oriented architecture creates impedance mismatches. Use it for what it is: agent collaboration as the product feature, not the infrastructure.
- **Cost compounds before teams notice.** Retries, chained calls, and context stuffing can drive a single agent's token consumption to 180K tokens for a task that should use 20K. Track per-agent, per-task-type from day one — aggregate numbers hide the real waste.
- **Multi-agent before single-agent is reliable is a regression.** The Generator-Verifier pattern (one agent produces, another validates) is the one exception — it can improve reliability of a single agent rather than replacing it.
