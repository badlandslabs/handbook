# S-750 · The Agent Stack Stratifies Into Six Layers — And Cost Is Now a First-Class Design Decision

By mid-2025 the "agent stack" was still being described as a linear pipeline. By mid-2026 it had fractured into six distinct layers, each with its own tooling ecosystem, failure modes, and defensibility profile. Teams that treated the stack as a monolith — one model, one framework, one vector DB — were paying for it in rewrite costs, unexpected bills, and brittle deployments. The teams winning were treating cost architecture as a design decision from day one, not a post-launch optimization.

## Forces

- **37% of enterprises now use five or more AI models in production.** Single-provider lock-in is the new single-cloud risk — and unlike cloud, switching model providers in a tightly coupled agent is a full rewrite. (Source: Philipp Dubach, "Don't Go Monolithic; The Agent Stack Is Stratifying," philipdubach.com, Feb 2026)
- **Model pricing spans 100x.** From Claude Haiku 3.5 at $0.80/$4.00 per million tokens to GPT-4o at $2.50/$10.00, the cost difference between the right model and the wrong model for a given subtask is 2–5x on the monthly bill. (Source: TokenFence, "Claude vs GPT-4o Cost Comparison for Production AI Agents 2026," tokenfence.dev, Mar 2026)
- **Gartner predicts 40% of agentic AI projects will be cancelled by end of 2027** due to unclear business value — driven largely by runaway inference costs that weren't modeled in the design phase.
- **The observability gap is the cost gap.** Without per-span token tracking and cost attribution by agent step, teams discover their bill only after the month closes. The highest-leverage cost decision in a production agent is model routing — not model selection.

## The Move

**Design the stack in layers, route models by task type, and instrument cost before you launch.**

### Layer the stack explicitly

The enterprise agent stack has six recognizable strata, each converging on different best-in-class tools:

1. **Foundation models** — Claude Sonnet 4, GPT-4o, Gemini 1.5 Pro. Selection based on capability per dollar, not benchmark scores.
2. **Orchestration/runtime** — LangGraph (complex stateful workflows), CrewAI (fast prototyping with role-based teams), AutoGen (conversational multi-agent). LangGraph leads production at Uber, LinkedIn, Klarna. CrewAI leads in Fortune 500 exploration.
3. **Memory/persistence** — Semantic memory via Pinecone, Qdrant, Weaviate, or pgvector for vector search; Redis or PostgreSQL for structured state; checkpointing via LangGraph's built-in persistence or Temporal.
4. **Tool layer** — MCP (Model Context Protocol) as the emerging standard for agent-to-tool discovery and integration; 14,000+ MCP servers cataloged by late 2025 with 72% of adopters expecting increased usage.
5. **Sandbox/execution isolation** — Firecracker MicroVMs, E2B, Modal, Shuru. Sandboxing is now its own tooling category — 16 days before the stack stratification article, an HN comment noted "the agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing."
6. **Observability** — LangSmith (400+ companies, 1T+ spans/month), Arize Phoenix (OpenTelemetry-native, self-hostable), Langfuse (fully open-source alternative). At minimum: per-span latency, token counts, cost, retrieval similarity scores.

### Route by task type, not model hierarchy

The routing pattern that works in production: small/fast models for routing and classification, capable models for reasoning, frontier models for final output. GPT-4o-mini at $0.15/$0.60 handles simple routing decisions; Claude Sonnet 4 handles complex reasoning; only the final generation touches the most expensive model.

### Instrument cost before launch

Every span should emit token count and computed cost. Aggregate by agent, by task type, by user. Budget alerts at 50%, 75%, 90% of monthly threshold. The teams seeing surprise bills are the ones running without per-agent cost attribution.

## Evidence

- **Blog post:** Philipp Dubach, "Don't Go Monolithic; The Agent Stack Is Stratifying" — Documents the six-layer decomposition, 37% multi-model adoption stat, Gartner 40% cancellation prediction — [philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN discussion:** "Ask HN: How are you monitoring AI agents in production?" — Practitioners documenting failure modes: surprise bills from untracked token usage, risky outputs going undetected, no audit trail. AgentShield and custom OTEL-based solutions shared — [news.ycombinator.com/item?id=47301395](https://news.ycombinator.com/item?id=47301395)
- **HN discussion:** "How are people debugging multi-agent AI workflows in production?" — OTEL + LGTM stack (Loki, Grafana, Tempo, Prometheus) emerging as the non-LangSmith path. Distributed tracing patterns adapted from traditional systems for agent-specific failure modes — [news.ycombinator.com/item?id=47358618](https://news.ycombinator.com/item?id=47358618)
- **Cost analysis:** TokenFence, "Claude vs GPT-4o Cost Comparison for Production AI Agents 2026" — Full pricing table, cost-per-task analysis showing 2–5x monthly bill difference based on routing strategy — [tokenfence.dev/blog/claude-vs-gpt4o-cost-comparison-ai-agents-2026](https://tokenfence.dev/blog/claude-vs-gpt4o-cost-comparison-ai-agents-2026)
- **Framework comparison:** Gheware, "LangGraph vs CrewAI vs AutoGen: Best AI Agent Framework 2026" — LangGraph at 90,000+ GitHub stars with production deployments; CrewAI at 60% Fortune 500 exploration; expert recommendation: "Default to LangGraph unless you have strong reasons not to" — [devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **"We'll optimize cost later" is a trap.** Cost architecture is a routing design problem, not an ops problem. Redesigning model routing after launch means touching every agent boundary.
- **MCP doesn't automatically mean secure.** The stack stratification article and the S-749 MCP security entry cover the same terrain from different angles: MCP reduces integration friction for developers and attackers alike. Every MCP server is a potential blast radius.
- **LangGraph's steeper learning curve pays off.** Expert guidance across multiple sources: start with LangGraph for production, not CrewAI — the graph-based state machine prevents the "painful rewrites 6–12 months in" that happen when prototyping in CrewAI meets production requirements.
- **Multi-model without observability is blind.** The HN production monitoring thread surfaced a pattern: teams running 5+ models in production without per-model cost attribution were discovering budget overruns only on the monthly invoice. Every model call needs a cost tag attached to the trace.
- **Sandboxing is not optional for agents with write access.** The stratification of the stack into execution isolation as a dedicated layer reflects hard-won experience: agents with real-world permissions (database writes, API calls, file operations) need containment that framework-level abstractions don't provide.
