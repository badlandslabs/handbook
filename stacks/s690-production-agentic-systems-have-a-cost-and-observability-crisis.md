# S-690 · Production Agentic Systems Have a Cost and Observability Crisis

[Multi-agent AI systems are shipping to production faster than the infrastructure to understand what they cost or why they fail. The numbers are real — and most teams are running blind on both.]

## Forces

- **Cost scales superlinearly with steps.** Every additional tool call, retrieval hop, or agent handoff multiplies token spend. A 4-step agent costs 10-50× more per execution than a well-tuned single-step pipeline. Teams don't discover this until the first invoice.
- **The observability gap is a debugging crisis.** Multi-agent architecture adoption jumped from 23% to 72% of enterprises in one year (2024→2025), yet only 37.3% of those teams run online production evaluations. Traces are collected; patterns are not detected.
- **API cost dominates but isn't the whole story.** API spend is 60-80% of total operating cost, but orchestration overhead, vector DB queries, and caching infrastructure add a 20-40% complexity tax that doesn't show up in token math.
- **Production evals gate answers, not just agents.** Most teams instrument their agent but forget to gate the answer. The result: systems that run fast and confidently ship wrong outputs.

## The Move

**Measure cost per execution end-to-end from day one, and instrument production evals before you instrument traces.**

1. **Log cost per run at the session level**, not just the model level. Track: input tokens, output tokens, retrieval calls, tool executions, and infra overhead per complete agent run.
2. **Implement a faithfulness/self-check loop** inside the agent, not after it. Agentic RAG systems make 3-8 LLM calls and 2-6 retrievals per turn — a judge model gating the final answer catches hallucinations that tracing alone won't.
3. **Use semantic caching to collapse redundant LLM calls.** The median agentic workflow has 40-60% repeated query overlap in production. Caching at the semantic level cuts cost by 40-70% without touching model quality.
4. **Adopt OpenTelemetry for distributed traces across multi-agent runs.** Every agent handoff is a span. Without this, debugging a 6-agent coordination failure means reading 6 separate logs.
5. **Evaluate the answer, not just the trajectory.** Traces confirm the agent did what you coded. Evals confirm the agent produced a correct and faithful result. Both are required.
6. **Tier your models by task complexity.** Route simple classification/retrieval to 2-3B local models; reserve GPT-4o/Claude Sonnet for synthesis and reasoning. Model cascading across a task can cut cost 60% with no quality regression on well-scoped tasks.

## Evidence

- **Cost analysis — 4 real systems, 6 months:** Inventiple tracked 4 production agentic systems (October 2025 – April 2026). Support triage (LangGraph, single agent, 3 tools): $0.012/run, 12K runs/month. Sales research crew (CrewAI, 3 agents): $1.40/run, 3.2K runs/month. API costs were 60-80% of total. Semantic caching alone delivered 40-70% cost reduction on systems with high query overlap. — [Inventiple — Agentic AI Production Cost: 6 Months of Real Data](https://www.inventiple.com/blog/agentic-ai-production-cost-analysis)
- **Observability gap — enterprise survey data:** Multi-agent architecture adoption jumped from 23% to 72% of enterprises between 2024 and 2025. Yet only 37.3% of those teams run online production evaluations. LangSmith is the dominant enterprise tracing tool; LangFuse is preferred for open-source stacks; Arize Phoenix targets local/dev-phase observability. — [AgentMarketCap — Agent Observability in 2026](https://agentmarketcap.ai/blog/2026/04/11/agent-observability-distributed-tracing-langfuse-arize-opentelemetry-2026)
- **MCP becomes boring infrastructure:** MCP (Model Context Protocol) reached 97M monthly SDK downloads by March 2026, up from ~100K at launch in November 2024. Over 5,800 MCP servers and 300+ client applications in production. Adopted by OpenAI, Google, Microsoft, AWS, and Salesforce within 13 months. Donated to Linux Foundation's Agentic AI Foundation in December 2025. 78% of enterprise AI teams have MCP-backed agents in production as of mid-2026. — [Deepak Gupta Research — MCP Enterprise Adoption](https://guptadeepak.com/research/mcp-enterprise-guide-2025), [andrew.ooo — MCP Enterprise Adoption July 2026 State](https://andrew.ooo/answers/mcp-model-context-protocol-enterprise-adoption-july-2026)
- **YC bets on agents:** Y Combinator's Spring 2025 batch had 70 AI agent startups out of 144 total companies (nearly 50%). YC invested $500K per agentic startup. Categories span healthcare appeals, robot programming, legal, customer ops, and marketing. — [B17 News — YC Demo Day AI Agent Startups](https://b17news.com/the-10-most-exciting-ai-agent-startups-at-y-combinators-demo-day-for-its-first-ever-spring-cohort/), [PitchBook — YC AI Agents Nearly 50% of Batch](https://pitchbook.com/news/articles/y-combinator-is-going-all-in-on-ai-agents-making-up-nearly-50-of-latest-batch)

## Gotchas

- **Logging traces ≠ knowing if the answer is right.** Teams instrument LangSmith or Phoenix, get beautiful span visualizations, and never run a single production eval. The answer quality problem is independent of the trajectory correctness problem.
- **Agentic RAG latency compounds silently.** Classic RAG: 1 LLM call + 1 retrieve. Agentic RAG: 3-8 LLM calls + 2-6 retrieves per turn. Latency budgets that worked for single-step retrieval will explode without deliberate concurrency or latency-gated fallbacks.
- **Caching that ignores semantic similarity flops.** Exact-match caching misses 40-60% of repeated work. Use embedding-based similarity thresholds (e.g., cosine > 0.92) to catch near-duplicate queries.
- **Cost anomalies don't surface without per-run attribution.** Monthly aggregate cost tells you nothing. Per-session, per-agent, per-tool-call breakdowns are what enable optimization.
- **MCP server security needs active management.** Research found 43% of MCP servers have command injection flaws; the exploit probability exceeds 92% with 10 plugins. Treat MCP servers as untrusted network endpoints.
