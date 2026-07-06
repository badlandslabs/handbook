# S-727 · The Stratifying Agent Stack: Six Layers, One Protocol, and the Cost Problem You Will Ignore Until It Bankrupts You

[Every team that builds a second agent regrets the first one. Not because of the model — because they built a monolith. The agent stack in 2026 is stratifying into six distinct layers with different economics, different defensibility profiles, and different winners. MCP is the connective tissue binding them together — but 43% of MCP servers have command injection flaws. And underneath everything, cost engineering determines whether your agent survives its first month in production.]

## Forces

- **The monolith is a trap.** Teams that wrap orchestration, execution, sandboxing, and tool access into a single system end up with something that works in demos and fails in production — and can't be debugged, patched, or replaced layer-by-layer.
- **MCP is winning but unverified.** Anthropic's Model Context Protocol reached 97M monthly SDK downloads and 5,800+ servers by late 2025. OpenAI, Google, and Microsoft all adopted it. But adoption speed outran security hardening — 43% of MCP servers have exploitable command injection flaws.
- **Cost is the last thing teams think about and the first thing that kills them.** Average enterprise AI operational cost is $85,521/month. Runaway agent loops have cost teams from $15 in ten minutes to $47,000 over eleven days. 60–85% of that spend is recoverable — but only if you engineer for it from day one.
- **Context, not models, is the lock-in.** 37% of enterprises already run 5+ AI models in production. The defensible asset is the organizational world model — how your agents understand and act on your specific domain. That lives in the memory/persistence layer, not the model layer.

## The move

**Design your agent system as six composable layers, not one stack.**

1. **Model layer** — Stateless inference. Swap models without touching anything else. Use Anthropic for reasoning-heavy tasks, OpenAI for function-calling reliability, open-source (Qwen, DeepSeek) for cost-sensitive high-volume work.

2. **Orchestration layer** — LangGraph for production graph-based workflows with checkpointing and time-travel debugging; CrewAI for fast role-based scaffolding when requirements are stable; raw Claude API when you need zero abstraction overhead.

3. **Tool/Integration layer** — MCP as the standard protocol (not custom REST wrappers per tool). Every MCP server is a first-class citizen, not a one-off integration. But: audit every server for injection vectors before production. 43% of production MCP servers have command injection vulnerabilities.

4. **Memory/Persistence layer** — Vector store (Qdrant for self-hosted, Pinecone for managed) plus structured state. Semantic memory goes in the vector DB; conversation state and agent working memory go in a durable store (Postgres with pgvector, or Redis for low-latency access).

5. **Execution/Sandbox layer** — Isolated execution environment per agent turn. Firecracker microVMs, E2B, Modal, or Shuru. This layer is its own defensible product category — do not roll your own.

6. **Observability/Governance layer** — LangSmith for LangGraph-native tracing; Phoenix (Arize) for custom evaluation pipelines. This layer enforces cost budgets, logs every tool call, and triggers circuit breakers on token spend thresholds.

**Cost-engineer from the start, not after:**
- Set per-turn token budgets with hard caps
- Route cheap tasks to cheap models (e.g., gpt-4o-mini for extraction, claude-sonnet for synthesis)
- Enable prompt caching wherever sessions are stateful
- Build a budget circuit breaker: if spend exceeds $X in Y minutes, halt and alert

## Evidence

- **HN comment, Feb 2026:** "The agent stack is splitting into specialized layers and sandboxing is clearly becoming its own thing. Shuru, E2B, Modal, Firecracker wrappers. Earlier this month I wrote about how these layers have very different defensibility profiles and why going monolithic is the wrong call." — user 7777777phil on Hacker News discussing Philipp Dubach's post — https://news.ycombinator.com/item?id=47114201

- **Blog post, Philipp Dubach (updated May 2026):** The enterprise AI agent stack splits into six layers: Model, Orchestration, Tool/Integration, Memory, Execution, Observability. Each has different economics and rates of change. 37% of enterprises already use 5+ models in production; the defensible asset is the organizational world model, not the model itself. — https://philippdubach.com/posts/dont-go-monolithic-the-agent-stack-is-stratifying/

- **Research report, Deepak Gupta (Dec 2025):** MCP reached 97M monthly SDK downloads, 5,800+ servers, and 300+ client applications by late 2025. OpenAI adopted MCP in March 2025, followed by Microsoft. MCP was donated to the Linux Foundation's Agentic AI Foundation in December 2025 for vendor-neutral governance. 43% of MCP servers have command injection flaws; exploit probability exceeds 92% with 10 plugins. — https://guptadeepak.com/research/mcp-enterprise-guide-2025

- **Research brief, Zylos Research (May 2026):** Enterprise AI operational costs averaged $85,521/month in 2025. Model API spend grew from $3.5B to $8.4B (late 2024 to mid-2025). 60–85% of spend is recoverable through prompt caching, model routing, and budget enforcement. Runaway agent incidents range from $15 in 10 minutes to $47,000 over 11 days. — https://zylos.ai/research/2026-05-02-ai-agent-cost-engineering-token-economics

- **Show HN post, Evan Drake (Opensoul, ~May 2026):** Built a 6-agent marketing team (Director, Strategist, Creative, Producer, Growth Marketer, Analyst) on Paperclip's orchestration platform. Each agent runs autonomously on scheduled heartbeats, checks a work queue, delegates to teammates, and reports progress. Demonstrates the "agency team" pattern — specialized roles with explicit handoff protocols. — https://news.ycombinator.com/item?id=47336615

## Gotchas

- **MCP's security posture is not production-ready by default.** The 43% command injection flaw rate means every MCP server you add to production is a potential attack surface. Audit servers, run in sandboxed environments, and do not trust server-provided tool schemas as gospel.
- **Cost circuit breakers must exist before deployment, not after the first incident.** Teams that skip this always end up with a war story. Set hard caps at the orchestration layer, not just at the billing dashboard.
- **The memory layer is where your competitive moat lives — and where most teams skimp.** Vector search alone is not a memory system. You need structured recall, session continuity, and domain-specific embedding strategies. This is the hardest layer to rebuild once you realize you need it.
- **Multi-model routing sounds simple, gets messy in practice.** Route by task type and latency tolerance, not by arbitrary cost rules. Re-rank retrieval results with a cheap model before sending to an expensive reasoning model.
- **>40% of agentic AI projects will be canceled by end of 2027** (Gartner) — not because the technology fails, but because teams build the monolith, hit the cost wall, and pull the plug before finding the stratified pattern that would have worked.
