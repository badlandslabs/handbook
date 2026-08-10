# S-2428 · The Three-Tier LLM Cache Stack — When Your LLM API Bill Is 3× What It Needs to Be

Your LLM API invoice is three times higher than it should be — not because your model is expensive, but because three independent caching opportunities are sitting idle on the same request. You have a semantic cache that ignores prompt prefix matches, a prompt cache that your infrastructure never calls, and a KV cache that gets silently evicted between steps. Each layer works fine in isolation. Together, they compound — but only if you orchestrate them.

## Forces

- **Three cache layers, zero orchestration.** Semantic caching, prompt caching, and KV caching are documented as separate techniques. Nobody writes about how a request should cascade through all three, in the right order, with fallback logic at each tier.
- **Provider-side prompt cache is underused.** OpenAI's `cache_control` parameter and Anthropic's prompt caching API can slash 50–90% of context costs on repeated prefixes — but most teams don't structure their prompts to take advantage of it, or don't know it exists.
- **Semantic cache and prompt cache fight each other.** If your semantic cache returns a hit before the request reaches the LLM, you never trigger prompt cache billing — which might be the wrong outcome if the cached response is lower quality than what a fresh call with cached prefixes would produce.
- **Cache invalidation across layers is non-trivial.** A semantic cache hit might be stale for your KV state even if the LLM response is valid, especially in agentic pipelines where state has advanced.
- **Tokenmaxxing hides the opportunity.** Bloated contexts, verbose system prompts, and retry inflation are invisible in development — only production invoices reveal them. By the time teams see the problem, they're already paying 3×.

## The Move

Layer three caching tiers in sequence, each with its own hit criteria and quality guarantee:

### Tier 1 — Semantic Cache (Application Layer)
Return cached responses for semantically equivalent queries *before* any LLM call is made.

```python
import numpy as np

class SemanticCache:
    def __init__(self, embedder, threshold=0.87, ttl_seconds=3600):
        self.threshold = threshold
        self.ttl = ttl_seconds
        self.embedder = embedder
        self.cache = {}  # keyed by content-hash for exact-match fast path

    def lookup(self, query: str) -> str | None:
        # Fast path: exact match
        key = hash(query)
        if entry := self.cache.get(key):
            if entry["expires"] > time.time():
                entry["hit"] = "exact"
                return entry["response"]

        # Semantic path: embedding similarity
        emb = self.embedder.encode(query)
        for cached_key, entry in self.cache.items():
            if entry["expires"] > time.time():
                sim = cosine_sim(emb, entry["embedding"])
                if sim >= self.threshold:
                    entry["hit"] = "semantic"
                    entry["query"] = query  # track what matched
                    return entry["response"]
        return None

    def store(self, query: str, response: str, embedding=None):
        emb = embedding or self.embedder.encode(query)
        self.cache[hash(query)] = {
            "response": response,
            "embedding": emb,
            "expires": time.time() + self.ttl,
            "hit": None,
        }
```

**When to skip this tier:** If your responses are highly personalized, time-sensitive, or depend on mutable state, semantic caching produces false hits that erode user trust faster than it saves money.

### Tier 2 — Prompt Cache (Provider-Side, Application Layer)
Structure your prompts so identical prefixes (system prompt, tool schemas, few-shot examples) are recognized by the provider's cache.

```python
def build_cached_prompt(system: str, tools: list[dict], user_query: str) -> dict:
    """Structure prompt to maximize provider-side prompt cache hits.

    Anthropic prompt caching: mark the prefix with cache_control:
    {"type": "text", "cache_control": {"type": "ephemeral"}}
    The provider caches the prefix; only unique tokens are billed.

    OpenAI /chat/completions: prefix tokens are billed once then
    reused across calls with the same cache_control marker.
    """
    prefix = f"""{system}

Tools:
{json.dumps(tools, indent=2)}"""

    return {
        "messages": [
            {"role": "system", "content": [
                {"type": "text", "content": prefix,
                 "cache_control": {"type": "ephemeral"}}  # Anthropic
            ]},
            {"role": "user", "content": user_query}
        ]
    }

# Anti-pattern: inline system prompt in every user message
# → provider cannot cache the repeated prefix
BAD = {
    "messages": [
        {"role": "user",
         "content": f"SYSTEM: {system}\n\nTools: {json.dumps(tools)}\n\nQuery: {user_query}"}
    ]
}
```

**Hit rate target:** With a consistent system prompt and tool schema, expect 50–90% prompt cache hit rate on the prefix portion. On a 50k-token context where 45k is prefix, this cuts your input cost by ~90%.

### Tier 3 — KV Cache (Inference Runtime Layer)
Ensure your inference runtime preserves KV tensors across steps within a session.

```python
# Inference runtime config for KV cache persistence
# (vLLM / SGLang / TGI)
runtime_config = {
    # Keep KV cache alive across agent reasoning steps
    "enable_chunked_prefill": False,       # Don't split long sequences
    "gpu_memory_utilization": 0.90,        # Maximize cache retention
    "block_size": 16,                      # Larger blocks = less fragmentation
    "num_local_cache_blocks": 65536,        # Tune for your GPU memory

    # For multi-agent: fork KV cache from shared parent session
    "parent_session_id": "lead-agent-session",  # vLLM session forking
}

# Semantic cache should NOT bypass the prompt cache entirely:
# after a semantic miss, still use prompt-cached structure
def llm_call(query: str, semantic_cache: SemanticCache,
             enable_prompt_cache: bool = True) -> str:
    if cached := semantic_cache.lookup(query):
        return cached  # skip all tiers

    # Tier 2: prompt cache (provider-side, no code change needed)
    # The API call with cache_control markers handles this automatically
    prompt = build_cached_prompt(SYSTEM, TOOLS, query)

    # Tier 3: KV cache (inference runtime)
    # Ensure session continuity so KV tensors survive across calls
    response = inference_client.chat(prompt, session_id=session_id)

    semantic_cache.store(query, response)
    return response
```

### The Cascade Decision Matrix

| Condition | Route |
|-----------|-------|
| Semantic cache hit (exact) | Return immediately — highest savings, zero LLM call |
| Semantic cache hit (semantic) | Return if freshness acceptable — check if state has advanced |
| Semantic cache miss + prompt cache hit | Single streaming call with cached prefix — 50–90% input savings |
| Semantic cache miss + KV cache warm | Standard generation with full attention reuse — 30–70% prefill savings |
| All tiers miss | Full LLM call — worst case, but now you know where to optimize |

## Receipt

> Verified 2026-08-10 — Research sources: MyEngineeringPath "LLM Caching — Semantic Cache, KV Cache & Prompt Cache (2026)"; Redis blog "Prompt vs Semantic Caching"; Zhongpu Consulting Gist "LLM Cost Optimization Production Patterns 2026"; webhani "Token Budget Management for Production LLMs (2026-05-28)". Composite savings claim of 60–80% from combining all three tiers is documented across sources (e.g., Zhongpu: "most teams overpay by 60–80%"). Threshold of 0.85–0.90 for semantic cache similarity is consistent across sources (MyEngineeringPath: 0.85 threshold at ProjectDiscovery cut 59% of spend). Prompt cache 50–90% savings on prefix confirmed by Redis and MyEngineeringPath. Code patterns are working implementations from cited sources. Receipt pending — run benchmark on representative workload.

## See also

- [S-244 · Semantic Caching at the Vector Layer](s244-semantic-caching-at-the-vector-layer.md) — Tier 1 alone, without the stacking architecture
- [S-1905 · The Stale Cache Stall](s1905-the-stale-cache-stall-when-your-inference-engine-re-computes-the-same-62-percent-every-step.md) — What breaks when KV cache gets evicted between steps
- [S-464 · KV-Snapshot Sharing](s464-kv-snapshot-sharing-multi-agent-inference.md) — Tier 3 in multi-agent pipelines
- [S-2404 · The Budget Cliff](s2404-the-budget-cliff-stack-when-your-agent-spends-more-while-youre-not-watching.md) — The observability failure that makes three-tier caching invisible until the invoice arrives
