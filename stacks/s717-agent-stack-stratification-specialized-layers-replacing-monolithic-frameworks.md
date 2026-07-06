# S-717 · Agent Stack Stratification: Specialized Layers Replacing Monolithic Frameworks

[The agent stack is fragmenting into six distinct horizontal layers — sandboxing, orchestration, tool execution, memory, routing, and safety — each converging on best-of-breed solutions. Teams that bolt everything onto a single framework pay the price in debuggability, cost control, and upgrade inertia.]

## Forces

- **Framework lock-in has compounding costs.** LangGraph, CrewAI, and AutoGen each make strong bets on orchestration topology — state machines, role hierarchies, or conversations respectively. Picking one for its secondary features (memory, tools, observability) means inheriting its orchestration assumptions everywhere.
- **Different layers have different defensibility profiles.** Sandboxing and routing are infrastructure problems with clean abstraction boundaries. Tool registries and memory architectures encode your organizational knowledge — the highest-value, highest-lock-in components. These deserve different investment than orchestration glue code.
- **Multi-provider LLM is now table stakes.** 37% of enterprises run 5+ AI models in production (up from 29%). A monolithic framework that owns your orchestration and inference backend makes this painful.
- **The failure rate of agentic AI projects remains above 40% (Gartner, 2025-2026).** Root causes cluster around two things: insufficient evaluation infrastructure and architectural brittleness from over-coupled stacks.

## The Move

Decompose the agent stack into six independent layers, each selected on its own merits:

- **Orchestration:** LangGraph for complex stateful workflows (34.5M monthly PyPI downloads, strong typed-state model); CrewAI for rapid prototyping of role-based agents; Temporal for long-running workflow reliability.
- **Sandboxing/Execution:** E2B, Modal, Shuru, or Firecracker-based microVMs — explicitly NOT bundled into the orchestration layer. Sandboxing is a security and resource-isolation problem that deserves its own operational maturity.
- **Tool calling:** MCP (Model Context Protocol) as the emerging standard for tool discovery and invocation across providers. Avoid proprietary per-framework tool schemas.
- **Memory/Persistence:** Scoped context windows for short-term; pgvector or Qdrant for semantic memory; structured DB (PostgreSQL) for entity state. Don't use LLM memory as a database.
- **Routing/Cost:** RouteLLM or similar classifier-based routing — demonstrated 85% cost reduction at 95% GPT-4 performance by routing non-frontier tasks to cheaper models. Layer semantic caching on top (30% query deflection).
- **Safety/Evaluation:** LangSmith or Phoenix for observability; Promptfoo for regression testing; human-in-the-loop for critical decision gates.

The key architectural rule: **upgrade any layer independently**. If your tool-calling layer needs to change, you change it without touching orchestration.

## Evidence

- **HN Show HN (2026):** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — corroborated by a 2026 post arguing monolithic agent frameworks have different defensibility profiles at each layer and should not be bundled. — [https://news.ycombinator.com/item?id=47114201](https://news.ycombinator.com/item?id=47114201)
- **Blog post (Philipp Dubach, 2026):** "The defensible asset in enterprise AI is not the model. It's the organizational world model." — maps each of the six layers to its defensibility and replacement difficulty, with context/memory being the hardest to rebuild. — [https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **Reddit r/MachineLearning:** Production teams report using Cohere Embed v3 + Pinecone for vector search, Azure OpenAI GPT-4o for inference, and Langfuse for observability — deliberately mixing providers across layers rather than standardizing on a single framework's ecosystem. — [https://www.reddit.com/r/MachineLearning/comments/1b4sdru/](https://www.reddit.com/r/MachineLearning/comments/1b4sdru/)
- **Zylos Research (2026):** Semantic caching deflects 30% of queries; model routing handles 50% with cheaper models; together with prefix caching and batch scheduling, the full optimization stack achieves 60–80% token spend reduction without quality degradation. — [https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing](https://zylos.ai/research/2026-04-12-ai-agent-cost-optimization-token-budget-model-routing)

## Gotchas

- **Siloed layers increase integration overhead.** Stratification helps at scale but adds complexity at small scale — if you're running one or two agents, a monolithic framework (CrewAI for rapid prototyping) is faster to ship.
- **MCP is not yet universal.** Many production systems still use proprietary tool schemas. Adopting MCP too early means building adapters; waiting too long means migrating. Watch the adoption curve.
- **Routing classifiers need tuning.** RouteLLM's 85% cost reduction is measured on specific task distributions. Your mileage depends on how well the classifier maps your query types to the right tier.
- **State management doesn't stratify cleanly.** Workflow state often lives across multiple layers. Document the state ownership contract explicitly or you will spend weeks on cross-layer bugs.
