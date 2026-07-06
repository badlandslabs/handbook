# S-678 · The Agent Stack Is Stratifying Into Specialized Layers

[The monolithic agent framework — one library does orchestration, tool execution, memory, safety, and observability — is a demo artifact. Production systems are splitting into six distinct layers, each with different economics, defensibility profiles, and failure modes. Teams that recognize this early avoid expensive rewrites.]

## Forces

- **The 37% forcing function.** a16z's 2025 enterprise AI survey found 37% of enterprises are already running 5+ AI models in production — not as an academic exercise, but because different layers have different optimal models. The stack stratifies because the requirements stratify.
- **Defensibility mismatch.** Building everything in one framework locks you into one team's rate of innovation. Sandboxing moves faster than orchestration. Memory databases evolve independently. A team that goes monolithic owns none of these layers deeply.
- **The cognitive load trap.** CrewAI gets you running in hours; by month three, implicit state and opaque routing create a wall you can only break through by extracting the orchestration into something explicit. The fast start becomes technical debt.
- **Sandboxing is a different problem class.** Code execution, file system access, API calls — these are systems problems. LLMs are not good at constraining them. The separation of concerns is not just architectural preference; it's where the real failure modes live.

## The Move

Recognize the six-layer stack and design for layer boundaries from day one:

**1. Orchestration Layer** — LangGraph, Temporal, or custom state machine. Explicit graph, not implicit conversation. Controls workflow topology, routing, and retry policy.

**2. Execution Layer** — The agent loop itself: model + tools + state. MCP (Model Context Protocol) is emerging as the standard interface here. Separates "what to do" from "how to execute."

**3. Tool/Sandbox Layer** — E2B, Modal, Shuru, or Firecracker wrappers. Sandboxed code execution, file system isolation, network policy. This is its own product category with 4+ dedicated players.

**4. Memory/Persistence Layer** — Pinecone, Qdrant, Weaviate, pgvector. Semantic memory, conversation history, learned preferences. Different query patterns than orchestration — treat it as a separate database concern.

**5. Safety/Guardrails Layer** — Input/output validation, hallucination detection, cost controls, rate limiting. This is not optional and should not live inside the orchestration layer. It has its own failure modes.

**6. Observability/Evals Layer** — LangSmith, Phoenix, or custom logging. 89% of teams have observability but only 52% have evals (RaftLabs 2025). The gap explains why multi-agent debugging is mostly guesswork.

## Evidence

- **Blog post:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — Philipp D. Dubach, citing his own a16z-informed analysis of layer defensibility (https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN discussion:** camkego on the same thread: "If you are not saving your context for decision making and your conc [context]..." — pointing to the memory layer as a separate concern. (https://news.ycombinator.com/item?id=47114201)
- **GitHub README:** langchain-ai/langgraph explicitly positions LangGraph as a "low-level orchestration framework" used by Replit, Uber, LinkedIn, GitLab — distinct from the tool/execution layer. (https://github.com/langchain-ai/langgraph)
- **Engineering post:** Turion.ai's 2026 orchestration comparison explicitly maps LangGraph to "I build the flowchart, the framework executes it" vs CrewAI's "I hire a team, they figure it out" — these are incompatible mental models for the same layer. (https://turion.ai/blog/langgraph-vs-crewai-vs-autogen-comparison-2026)
- **GitHub:** jaredtribe/agent-architecture-patterns documents MCP (Model Context Protocol) as the emerging standard interface between execution and tool layers, separating tool schema from orchestration logic. (https://github.com/jaredtribe/agent-architecture-patterns)
- **Survey data:** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025; 57% of organizations already have agents in production (RaftLabs, November 2025). (https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **Production post:** Teams wrapping up 2025 confirmed: agents shipped in developer tooling, internal operations, research synthesis, and customer-facing support — but only where software engineering discipline (bounded scope, tested behavior, scoped identity, observable runtime) was applied. (https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

## Gotchas

- **Don't conflate orchestration with execution.** LangGraph is not a sandbox. CrewAI is not a vector store. Putting everything in one framework feels productive until you need to upgrade one layer independently.
- **MCP adoption is real but incomplete.** The Model Context Protocol is the right abstraction for the tool/execution boundary, but production deployments require primitives not in the base spec: identity propagation, tool budgeting, and structured error semantics. Expect broker pipelines and custom error taxonomies to fill the gap.
- **Evals are the gap, not observability.** Most teams instrument their agents; few evaluate them. A system that logs everything but tests nothing is flying blind. The eval suite is the feedback loop that makes iteration tractable.
- **Sandboxing is not optional for code execution.** The "70% token reduction" gains from code-mode execution (per agent-architecture-patterns) are real, but the attack surface expands. Firecracker microVMs, E2B, or Modal are not overengineering — they are where the blast radius lives.
- **Cost compounds across layers.** A 4-agent orchestrator-worker workflow costs $5-8 per complex task in inference alone (RaftLabs 2025). Anthropic's multi-agent research showed 15x token cost for the capability gain. Model the economics before committing to a topology.
