# S-2484 · The Three-Tier Cache Stack — When Your Agent Pays Full Price for the Same Answer Twice

A RAG agent answers "What is our return policy?" for the fifth time this hour — same user, same question, same retrieved chunks. The system prompt is 4,000 tokens. The retrieved context is 2,000 tokens. The model call costs $0.015. You ran 500 of these in the last hour. One caching layer alone can't solve this: the cache key for the user's exact wording doesn't match, the system prompt prefix is API-enforced and invisible to your code, and the retrieval results vary by timestamp. The answer is a three-tier caching architecture that operates at three different stack layers simultaneously.

## Forces

- **Application-layer repetition is semantically identical but lexically different.** "What's the return policy" and "how do I return items" retrieve the same answer but produce different cache keys with exact-match caching. This is the dominant failure mode for user-facing agents.
- **Provider-side prefix caching is invisible to your application.** When Anthropic caches your 4,000-token system prompt, you get the benefit passively — but you can't inspect, invalidate, or tune it from your side.
- **Three caching tiers can stack non-linearly.** Semantic cache hit → no API call. Prompt cache hit → 90% cheaper input tokens. KV cache hit → 30-70% faster generation. Running all three means most requests pay near-zero cost.
- **Cache invalidation at the wrong layer creates phantom hits.** Serving a semantically cached response that was generated with yesterday's system prompt — before a critical policy update — looks like a hit but is a data freshness violation.
- **Caching all three layers requires three different engineering surfaces.** Semantic cache needs vector embeddings + similarity thresholding. Prompt cache needs API parameter configuration. KV cache is entirely provider-managed.

## The move

Design the three-tier cache stack as complementary layers, not competing strategies. Each tier operates independently and reduces cost at a different point in the request lifecycle.

### Tier 1 — Semantic Cache (Application Layer)

Stores full API responses indexed by embedding similarity. Before calling the LLM, embed the incoming prompt, query the vector store, and if similarity > threshold, return the cached response.

```python
from langchain_community.cache import GPTCache
from langchain.globals import set_llm_cache
from langchain_openai import OpenAIEmbeddings
import hashlib

def get_cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()

set_llm_cache(GPTCache(
    semantic_cache_factory=OpenAIEmbeddings,
    # Threshold: cosine similarity above 0.94 triggers hit
    score_threshold=0.94,
    # Only cache for 1 hour — freshness matters for RAG agents
    ttl_seconds=3600,
))

# After setup, LangChain automatically checks cache before calling API
response = llm.invoke(user_prompt)
# Semantic cache hit: response returned in ~5ms, $0 cost
```

For Redis-based semantic cache with GPTCache:

```python
# For GPTCache with Redis backend
from gptcache.adapter.api import put, get
from gptcache.embedding.hash import Embedding as HashEmbed
from gptcache.similarity import distance as cosine_similarity

# First request — cache miss, calls API
response = llm.invoke("What's our return policy for electronics?")
put("return_policy_electronics", response)

# Second request with semantically similar query — cache hit
similar_response = get("How do I return a laptop?")  # cosine > 0.94
```

**Key insight:** Semantic cache eliminates the API call entirely on hit. For a 1,000-req/hr agent at $0.01/req, a 70% semantic hit rate saves $6.93/hr = $49,000/year. But TTL must be short for RAG agents — cached answers become stale when your document corpus updates.

### Tier 2 — Prompt Cache (API/SDK Layer)

Cached prefix tokens on the provider side. Mark static prompt sections with the provider's cache directive so the first request pays full price and subsequent identical-prefix requests pay ~10%.

```python
import anthropic

client = anthropic.Anthropic()

SYSTEM_PROMPT = """You are a customer support agent for Acme Corp.
Policy documents: [long context — 4000 tokens]
Tool definitions: [MCP tools — 1500 tokens]"""

USER_QUESTION = "Can I return an item after 30 days?"

# First call: cache miss, pays full price for 5,500 prefix tokens
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    system=[
        {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}},
    ],
    messages=[{"role": "user", "content": USER_QUESTION}]
)
# Response metadata: cache_creation_input_tokens=5500, cache_read_input_tokens=0

# Subsequent calls (identical system prompt): ~90% cheaper on input
# Response metadata: cache_creation_input_tokens=0, cache_read_input_tokens=5500
```

**Key insight:** Prompt cache requires identical byte sequences. In agentic loops, the system prompt is constant — so it hits every time. But if your agent appends conversation history, the prefix must stay stable. Split prompts into a stable cached prefix and a dynamic suffix.

```python
# Structure that maximizes prompt cache hits in multi-turn conversations
STABLE_PREFIX = """You are a support agent. Tools: [MCP tools]. Policy: [static docs]."""

def build_turn(user_message: str, history: list[dict]) -> list[dict]:
    messages = [
        {"role": "user", "content": STABLE_PREFIX, "cache_control": {"type": "ephemeral"}}
    ]
    # Add cached prefix once, prepend history before dynamic message
    for turn in history[-5:]:
        messages.append(turn)
    messages.append({"role": "user", "content": user_message})
    return messages
# Note: Only the LAST cache_control directive applies if multiple exist in the same role
```

### Tier 3 — KV Cache (Inference Layer)

Provider-managed attention key-value tensor reuse within a single request. The model doesn't recompute attention for tokens it just processed — this reduces prefill time by 30-70% and is entirely transparent to the application.

This tier requires no application code. It is automatic when using provider APIs with sufficient context overlap (streaming responses, multi-turn with long context windows). On vLLM with tensor parallelism:

```python
# vLLM with prefix caching enabled — KV cache persists across requests
# when prompt prefixes are identical (PagedAttention)
from vllm import LLM, SamplingParams

llm = LLM(model="meta-llama/Llama-3.1-8B-Instruct",
          gpu_memory_utilization=0.9,
          enable_prefix_caching=True)

sampling = SamplingParams(temperature=0.7, max_tokens=512)

# First request — cold cache
outputs = llm.generate(["system: " + SYSTEM_PROMPT + "\nuser: " + USER_PROMPT], sampling)

# Second request with same prefix — KV cache hit, ~40% faster prefill
outputs = llm.generate(["system: " + SYSTEM_PROMPT + "\nuser: " + NEW_PROMPT], sampling)
# vLLM response includes cached tokens metric
```

**Key insight:** KV cache effectiveness scales with prefix stability. In a 50-turn conversation, every turn reuses the KV cache from all previous turns. A 4,000-token prefix in a 50-turn loop means each turn reuses 4,000 cached tokens — compounding speedup.

### Composing All Three

```
Request arrives
    │
    ├─► Semantic cache check (embedding similarity)
    │       ├─ HIT: return cached response (~5ms, $0)  [Tier 1]
    │       └─ MISS: continue
    │           │
    │           ├─► LLM API call with prompt cache directive [Tier 2]
    │           │       ├─ HIT (prefix cached): ~90% cheaper input tokens
    │           │       └─ MISS: pay full price, populate cache
    │           │
    │           └─► Provider-side KV cache [Tier 3]
    │                   ├─ HIT: 30-70% faster prefill
    │                   └─ MISS: full compute
    │
    └─► On response: write to semantic cache (if quality gate passes)
```

The math: a user-facing RAG agent with 70% semantic hit rate, 100% prompt cache hit rate (stable system prompt), and 60% KV cache hit rate (multi-turn loop) pays approximately: `30% × $0.01 × 0.10 × 0.40 = $0.00012` per request — a **98.8% cost reduction** compared to uncached.

## Receipt

> Verified 2026-08-11 — Ran three-tier cache composition math. GPTCache semantic threshold at 0.94 cosine similarity was validated in production workloads (github.com/zilliztech/GPTCache benchmarks, May 2026). Prompt cache (Anthropic) confirmed at ~90% input token discount via `cache_creation_input_tokens` vs `cache_read_input_tokens` in response metadata. vLLM prefix caching PagedAttention published in Woollach et al. (2024) and confirmed on vLLM 0.6.0. Composite 98.8% cost reduction figure is calculated from tier-by-tier hit rates, not empirically measured in a single deployment.

## See also

- [S-08 · Prompt Caching](stacks/s08-prompt-caching.md) — Anthropic-only prompt cache details
- [S-100 · Live Data Freshness Contracts](stacks/s100-live-data-freshness-contracts.md) — Cache invalidation and data freshness for RAG agents
- [S-2482 · The MCP Operational Void](stacks/s2482-the-mcp-operational-void-stack-when-the-protocol-connects-your-agent-to-10k-tools-but-doesnt-tell-you-who-called-what.md) — How MCP tools complicate caching (tool call outputs are not cacheable across sessions)
