# S-800 · The Orchestration Framework Stack: Picking Between LangGraph, CrewAI, and the Rest

You're starting a multi-agent system. Your team has used LangChain for single-call stuff. Someone wants to try CrewAI because they saw a demo. Another engineer wants the OpenAI Agents SDK since they already use GPT. AutoGen keeps coming up in discussions but the docs look stale. You don't want to rewrite this twice. This is the orchestration framework stack — how teams actually choose, and what the tradeoffs cost in production.

## Forces

- **Multi-agent coordination overhead vs. single-agent simplicity.** Agents that chat with each other sound elegant but introduce latency, context bleeding, and failure propagation that a well-designed single-agent-with-tools system avoids. The microservices analogy holds: coordination is only worth it when domain complexity genuinely decomposes into specialized tasks with clean interfaces.
- **Small agents outperform large agents on instruction-following.** Smaller, focused agents tend to have better accuracy on their narrow tasks than a single agent that tries to do everything. But more agents means more coordination surface.
- **Framework maturity varies wildly on what matters in production.** AutoGen is effectively in maintenance mode (2026). LangGraph has durable checkpointing, time-travel debugging, and LangSmith tracing. CrewAI has the fastest initial setup but less production hardening. The OpenAI Agents SDK has the tightest model integration and minimal boilerplate — but only works with OpenAI models.
- **Cost and reasoning loops compound.** Complex agents need powerful models. If your agent gets stuck in a reasoning loop, your API budget can evaporate in an afternoon. Framework choice affects how easily you can add step limits, budget guards, and tracing.

## The Move

The decision tree:

1. **If you're using OpenAI models and want minimal boilerplate** → OpenAI Agents SDK. Handoffs between agents are built in. It has guardrails, streaming, and tracing that you'd otherwise build yourself. Don't pick it if you need multi-provider flexibility — the SDK is tied to OpenAI.

2. **If your workflow is complex, stateful, or multi-provider** → LangGraph. It models workflows as state machines with nodes (functions) and edges (transitions). Checkpointing lets you pause and resume long-running workflows. Time-travel debugging lets you inspect any past state. Used in production at Klarna, LinkedIn, and Uber. The cost: steeper learning curve than CrewAI, and you're effectively buying into LangChain's ecosystem.

3. **If you want to ship a multi-agent prototype fast with role-based agents** → CrewAI. Agents have defined roles ("researcher", "writer"), goals, and tools. The conversational handoff model is intuitive. The tradeoff: less production hardening, harder to add fine-grained error recovery, and operational tooling lags behind LangGraph.

4. **If you want AutoGen** → reconsider. It's in maintenance mode as of 2026. The community has largely moved to LangGraph or CrewAI. If you're already on AutoGen, plan a migration.

5. **If your agents need to evolve topology at runtime** → Hive (GitHub: aden-hive/hive, ~10k stars). It dynamically generates multi-agent topologies from a graph-based execution DAG. Treats exceptions as observations rather than hard failures — agents build error responses into their execution graph. Zero-setup, model-agnostic.

6. **If you want agents that manage their own memory** → Letta (formerly MemGPT). Three-tier memory: core (always in prompt), archival (external store, retrieved on demand), recall (full conversation history). The agent itself decides what to keep in context vs. externalize. This is the approach that survived in personal AI assistants and long-running chatbots.

## Evidence

- **Framework comparison (production engineer, 2026):** "LangGraph is production-ready from a framework perspective — durable state, checkpointing, time-travel debug, LangSmith tracing. Run by Klarna, LinkedIn, Uber. AutoGen is in maintenance mode — not recommended for new production builds." — [OpenHelm Blog: OpenAI Agents SDK vs LangGraph vs AutoGen](https://www.openhelm.ai/blog/openai-agents-sdk-vs-langgraph-vs-autogen)
- **HN comment on multi-agent coordination cost:** "The microservices analogy is spot-on — multi-agent systems introduce coordination overhead that's only justified when domain complexity naturally decomposes into specialized tasks with clear interfaces. Smaller agents tend to have better instruction-following accuracy [than a single large agent]." — [Hacker News: Rowboat IDE thread](https://news.ycombinator.com/item?id=43763967)
- **Memory architecture surviving production:** MemGPT/Letta's three-tier memory (core, archival, recall) showed up across multiple independent reference architectures in Boston-area deployments. Key pattern: "Pin a stable runtime version — treat the underlying framework version as you would a database. Make state durable from day one. Wire up evals before features." — [CallSphere: MemGPT in Production 2026](https://callsphere.ai/blog/td30-fw-memgpt-in-production-2026-lessons-learned-honest)
- **Framework adoption in production:** LangGraph for complex/durable workflows, CrewAI for rapid prototyping, OpenAI Agents SDK for OpenAI-centric apps. AutoGen avoided in new builds. — [PE Collective: AI Agent Frameworks 2026](https://pecollective.com/blog/ai-agent-frameworks-compared)

## Gotchas

- **Don't over-architect on the first build.** Start with a single-agent-with-tools approach. Add multi-agent coordination only when the domain complexity genuinely justifies the coordination overhead. Most teams start too complex.
- **Framework version stability matters like a database.** Treat your agent framework version as pinned and tested infrastructure. The MemGPT/Letta production lessons are explicit on this: bolt-on durability at month 6 costs roughly 5x what doing it right at week 2 costs.
- **Tracing and observability aren't optional.** OpenTelemetry-compatible traces let you see where your agent spent compute, where it looped, and what tool calls consumed budget. LangGraph's LangSmith, or equivalent, should be wired up before your first production deploy — not after your first incident.
