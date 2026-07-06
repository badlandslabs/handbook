# S-685 · The Production Agent Core: Roll-Your-Own Consensus

[The heavy framework era is ending in production. After 18 months of LangChain and CrewAI prototypes, teams that survived into production converged on the same conclusion: build your own agent loop, integrate only what you need, and treat the framework as scaffolding — not structure.]

## Forces

- **Framework debt compounds.** LangChain and CrewAI are excellent for prototyping — fast to scaffold, fast to iterate. But they carry 50+ transitive dependencies, version-locked model compatibility, and abstractions that fight you when the next model drops. Multiple teams report 4-8 weeks of rewrite when migrating to a new model or adding novel tool patterns that don't fit the framework's assumptions.
- **The observability tax.** LangChain's abstractions obscure where an agent is spending tokens, time, and cost. Teams hit a wall when trying to instrument the agent loop — the framework's internal calls are opaque to their tracing stack.
- **The 2026 framework reckoning.** With Microsoft Agent Framework 1.0 GA (April 2026) unifying AutoGen and Semantic Kernel, LangGraph solidifying as the state-machine standard, and CrewAI still dominating demos — the ecosystem fragmented further, not converged. Teams that bet on a single framework got burned by breaking changes. The response: own the loop, outsource the dependencies.

## The Move

The pattern that emerged across independent production teams: strip the framework down to its primitives and implement the core loop yourself.

- **Implement your own agent loop.** A `while not done: think() → act() → observe()` loop in 50-100 lines of Python. Add streaming, retries, and checkpointing explicitly rather than inheriting them opaquely. This is what teams at Digits and AWS recommend as the production default.
- **Use reflection-based tool registration.** Rather than hand-writing JSON schemas for every tool, use Go's reflection (or Python's `inspect` module) to dynamically generate schemas from existing API signatures. Lets existing access controls handle security without re-implementing it inside the agent.
- **Treat memory as a tool, not a feature.** Provider-managed memory (LangChain memory, CrewAI memory) creates vendor lock-in and obscures what's actually stored. Production teams use memory as a tool they call explicitly — same interface regardless of whether it's backed by Pinecone, pgvector, or a JSON file.
- **Pick one orchestration layer if you need multi-agent.** LangGraph for state machines and complex branching. Nothing else unless you have a specific reason. The decision guide at benconally/ai-agent-framework-decision-guide makes this explicit: "Run in production next month → LangGraph. Avoid a framework entirely → Raw Claude API + tool use."
- **Keep the framework as scaffolding, not structure.** If you need LangChain's retrieval utilities or CrewAI's role templates, import them as libraries — don't structure your agent around them. The framework should be a dependency, not an architecture.
- **Instrument before you need it.** Build cost and token tracking into the loop from day one. A 4-agent CrewAI pipeline that looks reasonable can run $47,000 in 11 days from a single infinite loop. Visibility is not optional in production.

## Evidence

- **Conference talk — Digits AI in Production 2025:** "Open source frameworks like LangChain and CrewAI are great for prototyping but bring too many dependencies for production. The recommendation? Implement your own core agent loop." — [digits.com/blog/ai-in-production-2025](https://digits.com/blog/ai-in-production-2025)
- **Decision guide — @agentsthink / benconally/ai-agent-framework-decision-guide (GitHub, updated 2026-04):** Quick reference table: "Ship a demo this week → CrewAI. Run in production next month → LangGraph. Avoid a framework entirely → Raw Claude API + tool use." LangGraph gets ★★★★★ for MCP support and LangSmith observability. — [github.com/benconally/ai-agent-framework-decision-guide](https://github.com/benconally/ai-agent-framework-decision-guide)
- **Enterprise survey — Cleanlab State of AI Agents 2025:** Of 1,837 respondents, only 95 had agents live in production. Regulated industries rebuild their AI stack every 3 months or faster (70%); unregulated: 41%. The churn is driven partly by framework lock-in forcing rewrites when requirements shift. — [cleanlab.ai/ai-agents-in-production-2025](https://cleanlab.ai/ai-agents-in-production-2025)
- **Framework comparison — Turion.ai 2026 comparison:** "LangGraph is the production default... Most enterprise 2026 systems use LangGraph + MCP for tools. Pick LangGraph unless you have an explicit reason for the other two." AutoGen leads on multi-agent collaborative patterns. CrewAI excels at demos. — [turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026](https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **Enterprise evaluation — Amazon / AWS:** HITL (human-in-the-loop) becomes critical for multi-agent systems because automated metrics fail to capture emergent behaviors. Emphasizes framework-agnostic evaluation — teams should own their evaluation harness, not depend on framework-provided testing. — [aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon](https://aws.amazon.com/blogs/machine-learning/evaluating-ai-agents-real-world-lessons-from-building-agentic-systems-at-amazon)

## Gotchas

- **"Roll your own" still means borrowing the hard parts.** Don't re-implement token counting, streaming, or JSON parsing. Use libraries for the plumbing; own the decision logic.
- **CrewAI is not production-inadequate — it's demo-inadequate for complex systems.** If your use case fits CrewAI's role-based team model cleanly, it remains a valid production choice. The warning is against CrewAI as the foundation when requirements expand beyond its mental model.
- **The governance layer is still worth standardizing on.** TrustGate (Cohorte AI) — a 6-library open-source governance stack covering policy enforcement, context routing, behavior monitoring, and agent identity — exists because teams need standardized governance even when the core is custom. Don't mistake "own the loop" for "reinvent everything."
- **Instrument cost from the first prototype, not the first production deploy.** Token costs compound invisibly in multi-agent pipelines. Retrofitting cost tracking into a framework you're trying to escape is painful.
