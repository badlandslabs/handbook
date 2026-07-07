# S-736 · Stack Stratification: The Agent Stack Is Splitting into Specialized Layers

The monolith era of agent frameworks is ending. The same consolidation pressure that hit "full-stack JavaScript" in 2014 is hitting LangChain-in-a-box in 2026 — teams are replacing broad toolkits with targeted components at each layer, because no single framework wins at orchestration, sandboxing, observability, and evaluation simultaneously.

## Forces

- **Each layer has different defensibility profiles.** Sandboxing (Firecracker, E2B) is a systems problem. Observability (Phoenix, LangSmith) is a data engineering problem. Orchestration (LangGraph, Temporal) is a graph problem. A single framework can't be best-in-class at all three — and teams that try ship technical debt.
- **Lock-in risk concentrates at the context layer, not the model layer.** Per Dubach (2026): "The defensible asset in enterprise AI is not the model. Context — the curated memory, retrieved documents, and reasoning traces that ground an agent's decisions — is where lock-in actually lives." Most teams obsess over model selection while their context pipeline is the real moat.
- **Multi-vendor model usage is now mainstream.** 37% of enterprises use five or more AI models in production (Dubach 2026). Monolithic frameworks designed around a single LLM provider create immediate friction. Composable stacks let you route tasks to the right model without rewriting orchestration.
- **Sandboxing for AI-generated code is non-negotiable in production.** Standard Docker containers share a kernel with the host — insufficient for executing untrusted agent code. Firecracker microVMs deliver ~125ms boot and ~5MB memory overhead (Manveer C, 2026). Teams that skip this layer risk arbitrary code execution on shared infrastructure.

## The move

**Replace framework-centric thinking with layer-aware stack design.** Treat each concern as a replaceable component:

- **Orchestration:** LangGraph for complex graph-based workflows; Temporal for durable, fault-tolerant task execution; CrewAI for team-style multi-agent coordination; custom state machines for simple bounded flows. Choose based on workflow complexity, not brand loyalty.
- **Sandboxing:** E2B or Modal SDK for managed code-interpreter features (days to integrate, no infra); microsandbox for self-hosted, air-gapped environments; Firecracker primitives only if you need maximum control and have compliance requirements.
- **Observability:** Phoenix (Arize) for LLM traces and latency analysis; LangSmith for LangChain-specific debugging; custom structured logging for production cost attribution and failure triage.
- **Memory/retrieval:** Separate the vector store (Qdrant, Weaviate, pgvector) from the orchestration layer. The retrieval pipeline should be testable and replaceable independently of the agent logic.
- **Context curation:** This is where you invest the most. Parent-document chunking, hybrid dense/sparse retrieval, reranking with cross-encoders — these determine whether your agent retrieves the right information or the plausible-sounding wrong one.

## Evidence

- **HN post / Blog:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers." — philipdubach on HN, February 2026, referencing their own analysis on stratifying the agent stack for defensibility — https://news.ycombinator.com/item?id=47114201
- **Engineering blog:** 37% of enterprises now use five or more AI models in production; "Context, not models, sits in the highest lock-in and hardest-to-rebuild zone"; Gartner predicts 40% of enterprise apps will feature AI agents by 2026, but 40% of agentic projects will be canceled by 2027 due to unclear business value — https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/
- **Engineering guide:** The AI agent sandboxing landscape in 2026 uses a three-layer architecture: Layer 1 primitives (Firecracker ~125ms boot, gVisor syscall interception), Layer 2 managed platforms (E2B SDK, Modal), Layer 3 self-hosted alternatives (microsandbox using libkrun for air-gapped environments). Standard Docker containers are insufficient due to shared kernel surface — https://open.substack.com/pub/manveerc/p/ai-agent-sandboxing-guide
- **Case study:** Opensoul — an open-source agentic marketing stack with 6 specialized agents (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) organized as a real marketing agency, running autonomously on scheduled heartbeats with inter-agent delegation — https://news.ycombinator.com/item?id=47336615

## Gotchas

- **Fitting a square peg in a round hole.** Reaching for a complex orchestration framework (LangGraph, AutoGen) when a simple state machine or sequential pipeline would suffice adds debugging overhead proportional to framework complexity. Match workflow shape to orchestration complexity.
- **Swapping frameworks doesn't fix bad context.** Teams that migrate from LangChain to LangGraph to Temporal while leaving a mediocre retrieval pipeline intact gain nothing. The context layer is where most agent quality gains live — invest there first.
- **Ignoring cost at the multi-agent layer.** Per-agent inference costs compound: Gartner-tracked multi-agent inquiries surged 1,445% (Q1 2024 → Q2 2025), and inference costs reach $5–8 per complex multi-agent task (RaftLabs 2025). Without per-agent cost attribution, you won't know which agent is burning budget until the bill arrives.
