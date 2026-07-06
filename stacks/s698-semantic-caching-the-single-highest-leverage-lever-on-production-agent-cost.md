# S-698 · Semantic Caching: The Single Highest-Leverage Lever on Production Agent Cost

A production customer-support agent answers 10,000 tickets per day. Many ask the same thing phrased differently — "where's my order," "track my package," "delivery status." Without caching, every variation costs the same. With semantic caching, the second and third phrasing hits cache and costs 10× less. The gap between teams spending $0.15/task and $0.015/task is usually not model choice or prompt engineering — it is caching architecture.

## Forces

- **Exact-match caching fails for natural language.** Two users asking for the same thing rarely type identical prompts. Traditional key-value cache hit rates in agent systems run under 15% without semantic matching.
- **Repetition is predictable in agentic workloads.** System prompts, tool schemas, retrieval context, and domain-specific question patterns repeat constantly — but as prefix blocks, not exact strings.
- **Multi-tier caching compounds returns.** Semantic caching (meaning-match), prefix/prompt caching (KV reuse), and inference caching (result reuse) stack. Each layer multiplies the previous.
- **Naive full-context caching can increase latency.** Academic study (arXiv 2601.06007, "Don't Break the Cache," 2026) found that blindly caching the entire context window paradoxically increases TTFT because stale cache entries force recomputation. Cache boundaries matter.
- **Cache invalidation in agentic systems is harder than traditional caches.** Conversations have state. If a cached response depends on mutable context (user session data, tool state), stale reads create silent failures.

## The Move

Implement a three-tier caching architecture, tuned to agentic workload patterns.

### Tier 1 — Prompt/Prefix Caching (highest leverage, lowest effort)

- Leverage provider-native prefix caching: Anthropic (90% cost reduction on cached prefix, 85% latency reduction), OpenAI (50% cost reduction automatic).
- Structure prompts so the static portion (system instructions, tool schemas, RAG context) comes first as a stable prefix — this maximizes cache reuse.
- Anthropic breakeven is ~1.4 reads per cached write on the 5-minute tier. For any agent with repeated system prompts, this clears immediately.
- OpenAI 24-hour extended cache retention is optimal for batch agents and slow-burn pipelines that revisit the same prefix across a day — no write premium.

### Tier 2 — Semantic Caching (covers paraphrased queries)

- Use embeddings + vector similarity (threshold ~0.85 cosine similarity) to match semantically equivalent prompts.
- ProjectDiscovery case: cache hit rate improved from 7% to 84% (+77pp) with semantic caching, producing a 59% overall cost reduction and serving 9.8 billion tokens from cache.
- Store cache entries with: embedding vector, original prompt, response, TTL, and a semantic hash for fast lookup.
- Set similarity threshold high enough to avoid false positives contaminating agent decisions — test against your specific domain.

### Tier 3 — Result/Inference Caching (exact-match on outputs)

- Cache final responses keyed to a hash of (prompt + relevant context flags).
- Invalidate on context changes: user session state, tool schema version, retrieval index version.
- Use for non-temporal responses: FAQ lookups, policy answers, knowledge-base queries.

### Guardrails for Cache Correctness

- Treat cached reads as fast-path only — always have a synchronous fallback to fresh inference.
- Log cache hit/miss with semantic reason (exact match, semantic match, prefix match) separately; this surfaces which tier is performing.
- For agents making downstream decisions (routing, classification), require cache TTL ≤ 1 hour and flag stale reads in observability.
- Test cache boundaries quarterly. Agent prompts change, and a drifting system prompt will silently poison prefix caches.

## Evidence

- **Benchmarking report:** ProjectDiscovery achieved 7% → 84% cache hit rate (+77 percentage points) and −59% total cost reduction after deploying semantic caching across 10,000-token system prompts — 9.8 billion tokens served from cache. — [Ivern AI, "AI Agent Cost Per Task in 2026," April 2026](https://ivern.ai/blog/ai-agent-cost-benchmark-report-2026)
- **Academic study:** "Don't Break the Cache" (arXiv 2601.06007, 2026) tested caching across 500+ agent sessions with 10,000-token system prompts: naive full-context caching reduced API costs 41–80% and improved TTFT 13–31%, but paradoxically increased latency in some cases due to cache thrash. Strategic boundary control outperformed full-context caching. — [Digital Applied, "Prompt Caching in 2026"](https://www.digitalapplied.com/blog/prompt-caching-2026-cut-llm-costs-engineering-guide)
- **Production cost analysis:** Token/API spend is 30–50% of total production agent cost; observability/monitoring adds 10–20%; model cascading combined with semantic caching reduces token costs 40–70% without meaningful quality degradation. — [Xcapit, "The Real Cost of Running AI Agents in Production," November 2025](https://www.xcapit.com/en/blog/real-cost-ai-agents-production)
- **Provider benchmarks:** Anthropic prefix caching: 90% cost reduction, 85% latency reduction. OpenAI automatic caching: 50% cost reduction (enabled by default on newer models). Cache reads at $0.30/M tokens vs $3.00/M fresh (Anthropic). — [Introl Blog, "Prompt Caching Infrastructure," March 2026](https://introl.com/blog/prompt-caching-infrastructure-llm-cost-latency-reduction-guide-2025)
- **Industry data:** 31% of LLM queries in production agent systems exhibit semantic similarity — massive inefficiency without caching. — [Introl Blog](https://introl.com/blog/prompt-caching-infrastructure-llm-cost-latency-reduction-guide-2025)

## Gotchas

- **Cache poisoning from prompt drift.** If your agent's system prompt changes weekly, a prefix cache with a 24-hour TTL will serve stale responses until expiry. Monitor cache entropy — sudden increases signal prompt instability.
- **Semantic cache hallucinations.** A cached response from an earlier model version may be lower quality than what the current model would produce. Pin cache entries to model version, or set aggressive TTLs for high-stakes outputs.
- **Multi-agent cache coherency.** When multiple agents share a cache (common in orchestrator-worker patterns), one agent's invalidation may not propagate to others. Use a shared cache namespace with centralized invalidation.
- **TTFT paradox in prefix caching.** While prefix caching reduces total inference cost, it can increase time-to-first-token in high-contention scenarios where cache lookups compete with inference queue priority. Profile TTFT separately from cost.
- **Testing against live traffic only.** Cache hit rate varies wildly by use case. A FAQ agent might hit 80%; a code-generation agent might hit 5%. Build the cache architecture, then measure before assuming it will help your workload.
