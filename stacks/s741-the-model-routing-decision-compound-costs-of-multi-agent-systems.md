# S-741 · The Model Routing Decision: Compound Costs of Multi-Agent Systems

The moment you wire three agents together, your inference bill stops being predictable. Every retry, every chained call, every "let me think about this" step multiplies — and most teams discover their actual cost only after they hit a $2,847/month surprise. The gap between naive multi-agent deployments and optimized ones is an 87% cost reduction, achieved not by cutting features but by routing tasks to the right model tier.

## Forces

- **The all-Opus trap**: The instinct to reach for the most capable model on every step is financially lethal — a single 11-agent production workload ran $2,847/month before optimization, $370/month after — [Vincent van Deth, AI Architect](https://vincentvandeth.nl/blog/real-cost-ai-agents-production), December 2025
- **The compounding architecture**: Agents retry on failure, chain calls together, and run sub-agents in parallel — costs compound non-linearly in ways that single-LLM deployments never do — [Xcapit COO analysis](https://www.xcapit.com/en/blog/real-cost-ai-agents-production), November 2025
- **The 5–15x prototype-to-production gap**: Development environments show token costs at face value; production adds retry overhead, observability infra, and reliability engineering that multiplies by 5–15x — [Xcapit](https://www.xcapit.com/en/blog/real-cost-ai-agents-production)
- **The median is a lie**: Most teams optimize after the sticker shock, not before. The median agentic workflow costs 10–50x more per task than a well-optimized version — [Othi.com analysis](https://www.othi.com/blog/2026-05-11-agentic-ai-cost-optimization), 2026

## The move

**Build a model routing layer into your orchestration graph from day one, not as an afterthought.**

- **Route by task type, not by budget**: Architecture decisions, code reviews, and multi-step reasoning stay on premium models (Opus-class, 10% of dispatches). Standard code generation goes to mid-tier (Sonnet-class, 50%). Simple implementation and formatting goes to fast/cheap (Haiku/Flash-class, 30%). Classification and routing go to the fastest available (10%). The dispatches redistribute to match the actual complexity distribution — [Vincent van Deth](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Add a lightweight V8-style dispatcher**: A small classifier agent that reads the task context and routes to the appropriate model tier. Contributes to cost reduction by reducing per-dispatch token count before the main model even runs — [Vincent van Deth](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Implement semantic caching at the orchestration layer**: Cache semantically similar task contexts, not just exact-match prompts. Reduces redundant LLM calls by 30–60% on workloads with repeated or similar task patterns — [Xcapit](https://www.xcapit.com/en/blog/real-cost-ai-agents-production)
- **Cost-budget every agent step**: Tag each node in your orchestration graph with an expected token budget. Fail fast and reroute if a step exceeds budget rather than letting the model run to completion on an expensive model — [Xcapit](https://www.xcapit.com/en/blog/real-cost-ai-agents-production)
- **Account for retry compounding**: Design with the assumption that 10–20% of agent calls will retry. Budget for retries in your cost model — they compound faster than linear because a retry often triggers the same retry — [Vincent van Deth](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Monitor at the task-type level, not the aggregate level**: Aggregate cost dashboards hide which agent types are burning budget. Break down spend by task category (reasoning, generation, classification, retrieval) and route anomalies to the right owner — [Xcapit](https://www.xcapit.com/en/blog/real-cost-ai-agents-production)

## Evidence

- **Case study (individual AI architect):** Running 11 AI agents in production: $2,847/month on all-Opus routing → $370/month after 3 months of multi-model routing (Opus 10%, Sonnet 50%, Codex 30%, Flash 10%). 87% reduction, same workload — [Vincent van Deth](https://vincentvandeth.nl/blog/real-cost-ai-agents-production), December 2025
- **Industry data (Xcapit COO analysis):** Production cost breakdown for mid-complexity agents (1,000–5,000 sessions/day): Token/API 30–50%, compute 20–35%, observability 10–20%, hidden costs 15–25%. Total: $7,050–$21,100/month. Most teams discover hidden costs only at scale — [Xcapit](https://www.xcapit.com/en/blog/real-cost-ai-agents-production), November 2025
- **Market context (FinOps Foundation):** Enterprise AI spending doubled in 2025. Only 63% of organizations track AI spend. ~40% of enterprises spend $250K+/year on language models. Enterprise LLM spend hit $8.4B in H1 2025 — [FinOps Foundation via Xcapit](https://www.xcapit.com/en/blog/real-cost-ai-agents-production), 2025

## Gotchas

- **Reranking before routing can eat your savings**: A cross-encoder reranker adds an extra LLM call per retrieval. If you're routing expensive models through rerankers, the reranker's cost can exceed the routing savings. Profile before committing — [onseok](https://onseok.github.io/posts/building-production-rag-system/), March 2026
- **Cheap models fail more on ambiguous tasks**: Classification routing is reliable; boundary cases routed to a cheap tier will escalate to retry cycles that eliminate the cost advantage. Build a confidence threshold into your dispatcher — [Vincent van Deth](https://vincentvandeth.nl/blog/real-cost-ai-agents-production)
- **Observability costs are real and recurring**: Budget 10–20% of your total agent spend on monitoring. Teams that skip this to cut costs end up paying more in incident response — [Xcapit](https://www.xcapit.com/en/blog/real-cost-ai-agents-production)
- **Multi-agent inference compounds to $5–8 per complex task**: A 4-agent workflow running optimized model routing still costs $5–8 per task. Don't let per-call pricing create false economies at the workflow level — [RaftLabs](https://www.raftlabs.com/blog/multi-agent-systems-guide), November 2025
