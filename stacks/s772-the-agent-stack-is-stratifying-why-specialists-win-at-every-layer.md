# S-772 · The Agent Stack Is Stratifying: Why Specialists Win at Every Layer

Every new wave of infrastructure eventually stratifies. Cloud computing became IaaS/PaaS/SaaS. The modern data stack fractured into ingestion, transformation, warehousing, and BI layers. The AI agent stack is doing the same right now — and teams that treat it as a monolith are paying the price.

## Forces

- **The layers have different rates of change.** Model capabilities move weekly. Orchestration patterns move monthly. Security posture needs to be stable. A single tool that covers all three is optimized for none.
- **Lock-in lives at different heights.** 37% of enterprises now run five or more AI models in production — single-provider lock-in is the new single-cloud risk. But context (your data, your organizational memory, your retrieval pipeline) is harder to rebuild than the model call above it. The most defensible layer is not the one most teams optimize for.
- **Shallow context kills agents.** Agents can retrieve the right documents. They cannot yet reconstruct the reasoning processes humans follow to make decisions. The gap between "retrieval" and "judgment" is where most enterprise agentic AI projects stall.
- **Gartner predicts 40% of agentic AI projects will be canceled by end of 2027** due to escalating costs, unclear ROI, and inadequate evaluation infrastructure. The failure mode is not capability — it is architecture.
- **Sandboxing is its own discipline now.** Agent code execution — running untrusted Python, executing agent-generated shell commands — has spawned dedicated products (E2B, Modal, Fly Sprites). Treating it as an afterthought creates RCE risk.

## The Move

The six-layer enterprise agent stack, from bottom to top:

1. **Security / Sandboxing** — Isolated execution environments. Not a feature. A separate product category. E2B (ephemeral, 80ms cold start), Fly Sprites (persistent Firecracker microVMs with checkpoint/restore under 1s), Modal (gVisor, dynamic runtime). Pick based on whether your agents need stateful sessions or pure ephemeral isolation.
2. **Context / Memory** — Vector storage, knowledge graphs, semantic memory. The highest lock-in, hardest-to-rebuild layer. Choices: Pinecone (managed, teams <5 engineers), Qdrant (self-hosted, best price/performance at >5M vectors), pgvector (if you already run Postgres at scale), Weaviate (hybrid BM25 + vector search). Chunking strategy matters more than which engine you pick.
3. **Models** — The layer everyone optimizes for and nobody can sustain as a moat. OpenAI for general-purpose API reliability. Anthropic (Claude) for long-context reasoning and safety properties. Open-source (Llama, Qwen, Mistral via Ollama) for cost-sensitive or data-sovereign workloads. Multi-model routing is table-stakes: 37% of enterprises already use 5+ models in production.
4. **Orchestration / Framework** — LangGraph (stateful graph workflows, fine-grained control, Python-native), CrewAI (role-based agent teams, rapid prototyping), AutoGen/AG2 (conversational multi-agent, research-heavy), OpenAI Agents SDK (minimal, opinionated), Google ADK (Agent Development Kit for Gemini-native workflows). Pick based on your control requirements, not hype.
5. **Tool Calling / Integration** — MCP (Model Context Protocol) has won the standard. 97M+ monthly SDK downloads, 5,800+ servers, 300+ client applications, donated to Linux Foundation's Agentic AI Foundation. **Critical warning: 43% of MCP servers have command injection flaws; exploit probability exceeds 92% with 10 plugins.** Schema validation, allow-lists, and audit logging are not optional.
6. **Agents / Applications** — The visible layer. What your users interact with. Four domains consistently shipped to production in 2025: developer tooling (tight feedback loop via compile+test+human review), internal operations automation (ticket triage, workflow routing), customer-facing support (high-volume, low-stakes), and vertical SaaS embedded agents (legal, finance, healthcare).

## Evidence

- **Analyst Report:** 37% of enterprises run 5+ AI models in production; Gartner predicts 40% of agentic AI projects canceled by end of 2027 — [philippdubach.com](https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/)
- **HN Discussion:** The agent stack splitting into specialized layers; sandboxing becoming its own discipline with Shuru, E2B, Modal, Firecracker wrappers — [HN](https://news.ycombinator.com/item?id=47114201)
- **Show HN:** Mercury — visual canvas orchestration platform; delegation as a primitive, persistent tasks across activations, 800+ Composio tool integrations, adapters for Claude Code, Devin, Manus, and any MCP-compatible agent — [HN](https://news.ycombinator.com/item?id=47758643)
- **Show HN:** Opensoul — 6-agent marketing agency stack (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) running on Paperclip orchestration with scheduled heartbeats and autonomous task delegation — [HN](https://news.ycombinator.com/item?id=47336615)
- **Comparison Article:** LangGraph for graph-based workflows, AutoGen for conversational multi-agent, CrewAI for rapid role-based prototyping — [Tacavar](https://tacavar.com/blog/ai-agent-frameworks-compared-2026)
- **Comparison Article:** Start with pgvector if you already run Postgres; Pinecone if team <5 engineers; Qdrant for >5M vectors at best price/performance — [Synthara](https://www.syntharatechnologies.com/blog/vector-database-comparison-2026)
- **Research Report:** MCP at 97M+ monthly SDK downloads, 5,800+ servers, 300+ clients; 43% of servers have command injection flaws — [Deepak Gupta](https://guptadeepak.com/research/mcp-enterprise-guide-2025)
- **E2B vs Fly Sprites:** E2B 80ms cold start (ephemeral), Fly Sprites persistent microVMs with checkpoint/restore <1s (stateful sessions) — [Medium/Robert Mill](https://bertomill.medium.com/e2b-vs-fly-machines-which-sandbox-runtime-is-right-for-your-ai-agents-56684a8931bb)
- **Multi-agent benchmarks:** ChatDev 33.3% correctness on real programming tasks; AppWorld 86.7% failure on cross-app workflows; logistics systems +27% throughput, -22% cost — [Thread Transfer](https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns)

## Gotchas

- **Don't monolith your stack.** Picking one vendor for all six layers means you're optimized for none of them. Each layer has different winners, different economics, and different defensibility profiles.
- **MCP security is not solved.** The protocol is winning on adoption but 43% of servers have command injection flaws. Add schema validation, allow-lists, and output auditing before exposing any MCP tool to production agents.
- **Chunking matters more than the vector engine.** Teams spend weeks benchmarking Pinecone vs Qdrant, then use the same 500-token fixed-size chunks that lose paragraph boundaries. Fix chunking strategy first.
- **Multi-agent overhead compounds.** The coordination tax (latency, token cost, failure surface) can wipe out parallelism gains. Pattern choice matters more than model size — logistics throughput gains came from coordination design, not bigger models.
- **Evaluation is the forgotten layer.** Gartner's 40% cancellation prediction is partly an evaluation infrastructure problem. Agents are non-deterministic; semantic drift is harder to detect than value drift. LangSmith, Phoenix, or custom logging — instrument evaluation from day one, not after you ship.
