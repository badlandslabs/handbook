# S-2712 · The Agent Semantic Cache Stack — When Your Agent Makes the Same LLM Call It Made 5 Minutes Ago

Your customer support agent handles 50,000 conversations a month. Across those conversations, the same 12 questions get asked repeatedly — "how do I reset my password," "what is my order status," "can I cancel." You are paying full price for each one. Your agent is also sending the same 4,000-token tool manifest and 2,000-token system prompt on every single call. Anthropic's prompt caching handles the prefix — but it doesn't handle the 200 different phrasings of "reset my password" that arrive every hour. You need semantic caching, and you need it at the agent level, not just the prefix level.

## Forces

- **Agents repeat calls that differ only in phrasing.** A human asks "how do I reset my password" and an hour later "I can't log in, need a new password." These are the same semantic query. Without semantic caching, you pay full price for both.
- **Agentic loops amplify redundancy.** A 20-turn agent reasoning loop re-sends near-identical tool contexts and planning prompts on every iteration. The same sub-problem recurs across steps. Without caching, each recurrence is a fresh LLM call.
- **Prompt caching and semantic caching are different tiers.** Prompt caching discounts repeated input tokens at ~90% off via prefix matching. Semantic caching eliminates the entire LLM call for semantically equivalent queries. They stack; they don't replace each other.
- **Hit rate is not the number vendors advertise.** The "95% accuracy" in caching product docs means *correctness of cached responses*, not *how often the cache is hit*. Actual production hit rates are 10–70% depending on workload — FAQ: 40–70%, open-ended chat: 10–30%, classification: 50–80%.
- **Agent-specific queries are harder to cache than chatbot queries.** Tool-use queries have higher variability than simple questions. The wrong cache hit on a tool-call decision can be catastrophically wrong.

## The move

**Stack three caching layers, each covering a different redundancy pattern:**

1. **Exact-hash cache (the free layer).** SHA-256 match on the full request. Costs nothing to implement and covers ~18% of real production traffic — identical API calls from integrations, retries, and repeated user actions. Every request goes here first.

2. **Semantic cache (the main layer).** Embed the query → store in vector DB with response → check similarity on new requests. Threshold 0.8 cosine similarity for most workloads. When similarity exceeds threshold, return the cached response without an LLM call. GPTCache (Zilliz, 193 citations, actively maintained) is the standard open-source implementation. Redis + HNSW also works. This layer covers the paraphrases that exact matching misses.

3. **Prompt/prefix cache (the infrastructure layer).** Anthropic, OpenAI, and Google all offer prefix caching that discounts repeated input tokens by ~90%. Mark tool definitions, system prompts, and shared document contexts with `cache_control: {type: "ephemeral"}` (Anthropic) or equivalent. This layer doesn't eliminate calls — it discounts the ones that get through.

**Critical: distinguish cacheable from non-cacheable agent decisions.**

| Call Type | Cacheable? | Risk |
|---|---|---|
| FAQ / knowledge lookup | Yes — highest value | Low (wrong answer = inconvenience) |
| Tool selection decision | Risky — context matters | Medium (wrong tool = wasted step) |
| Reasoning step in a plan | No — sequential dependency | N/A |
| User summarization | Yes — stateless | Low |
| Stateful workflow mutation | No — side effects | High (corrupt state) |

**Set cache invalidation explicitly.** Semantic cache TTL should be workload-appropriate: 24h for FAQ, 1h for product catalogs, none (permanent) for historical knowledge. Invalidate on: product updates, policy changes, tool schema changes.

**Measure the right metric.** Track *cache hit rate by query type*, not aggregate. A 35% overall hit rate with 68% on FAQ and 8% on open-ended tasks tells you where to optimize. Aggregate hit rate hides the signal.

## Evidence

- **arXiv paper (Dec 2024, 2411.05276):** GPT Semantic Cache reduced API calls by up to 68.8% with hit rates of 61.6–68.8% and >97% positive hit accuracy at 0.8 similarity threshold. Used embedding + Redis HNSW ANN indexing. — https://arxiv.org/abs/2411.05276

- **Blog post (Tian Pan, Apr 2026):** "Semantic Caching for LLMs: The Cost Tier Most Teams Skip" — documents real production hit rate variance: FAQ/customer support 40–70%, EdTech 45%, classification/intent routing 50–80%, open-ended chat 10–30%. Notes that teams stacking exact hash + semantic + prefix caching typically see 70–80% effective token spend reduction vs naive per-request inference. — https://tianpan.co/blog/2026-04-10-semantic-caching-llm-production

- **GitHub (Zilliz/GPTCache):** Open-source semantic cache for LLM applications, 193 citations, active maintenance. Supports embedding generation (OpenAI API or local ONNX), Redis vector storage, HNSW-based ANN indexing, and LLM response storage. Handles the full pipeline from query embedding to response retrieval. — https://github.com/zilliztech/gptcache

## Gotchas

- **Wrong cache hit on agent decisions can be worse than a cache miss.** A cached "use tool X" decision from 10 minutes ago may be contextually wrong now. Gate caching behind query type: cache reads freely for knowledge lookups, gate it for tool-selection and stateful mutations.
- **Embedding model drift silently corrupts cache behavior.** If you upgrade your embedding model, old embeddings won't match new ones correctly. Re-index or set a TTL that forces refresh before the next model change.
- **Similarity threshold tuning is workload-specific.** 0.8 is a starting point, not a universal truth. Too high = low hit rate. Too low = semantically wrong matches returned as correct. Profile against your actual query distribution.
- **The "95% accuracy" vendor claim is about match correctness, not hit rate.** Teams buy semantic caching products expecting 95% of requests to be cached. Actual cacheable fraction depends on your query repetition — measure it from production logs before committing to a caching product.
