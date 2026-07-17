# S-1192 · The Five-Layer Caching Stack — When Your Agent Pays Full Price for a Plan It Already Ran

Your agent just spent 12 seconds and 180,000 tokens planning a data migration it planned identically three weeks ago. Your prompt cache hit rate is 94%. You're still bleeding budget on layers nobody taught you to cache.

Most teams implement one layer of caching and stop. The full picture has five — each with distinct TTLs, invalidation triggers, and failure modes.

## Forces

- Prompt caching (Layer 1) handles repeated system prompts and tool schemas, but misses the expensive middle: tool call outputs, structured plans, and session context
- Tool outputs repeat identically across tasks — re-executing a database query or API call because you didn't cache the result is pure waste
- Agents run structurally similar tasks repeatedly (onboarding, reporting, triage) — the same plan shape recurs even when data differs
- Each caching layer requires its own invalidation strategy — a one-size TTL breaks at least two layers
- Stale cached data in a wrong layer causes silent quality regressions that look like model drift

## The move

Five distinct caching layers, ordered from lowest to highest abstraction:

### Layer 1: Prefix Cache (Provider-side, ms TTL)
Cached KV attention on repeated prompt prefixes. Handled by the API provider — mark with `cache_control: {"type": "ephemeral"}`. Max savings: 90% on input tokens. TTL: provider-managed (~5 min for Anthropic, rolling for OpenAI).

```python
# Anthropic — mark the stable prefix
response = client.messages.create(
    model="claude-opus-4-6",
    max_tokens=1024,
    system=[
        {"type": "text", "text": SYSTEM_PROMPT},
        {"type": "text", "text": TOOL_DEFS, "cache_control": {"type": "ephemeral"}},
    ],
    messages=[{"role": "user", "content": user_input}]
)
```

**Tip:** Structure prompts with the most stable content first. Order: system instructions → tool definitions → retrieved context → history → current turn. This maximizes prefix length that qualifies for cache reads.

### Layer 2: Semantic Cache (Application-side, minutes-hours TTL)
Returns a cached response for semantically similar queries. Not token-level (like prefix cache) — embedding-level. Use for user-facing repeated questions.

```python
import numpy as np

EMBEDDING_MODEL = "text-embedding-3-small"
SIMILARITY_THRESHOLD = 0.92  # tune: too high = miss rate, too low = quality

def semantic_cache_get(query: str, cache: dict, threshold=SIMILARITY_THRESHOLD):
    embedding = get_embedding(query)
    for cached_query, (cached_emb, response) in cache.items():
        sim = cosine_sim(embedding, cached_emb)
        if sim >= threshold:
            return response, "cache_hit"
    return None, "cache_miss"

def semantic_cache_set(query: str, response: str, cache: dict, ttl_seconds=3600):
    embedding = get_embedding(query)
    cache[query] = (embedding, response)
    cache["_ttl_" + query] = time.time() + ttl_seconds
```

**Invalidation:** TTL-based. Additional event-driven invalidation when the underlying data source changes.

### Layer 3: Tool Output Cache (Application-side, seconds-hours TTL)
Tool calls return identical results within a time window. Cache at the tool call boundary, not the LLM layer.

```python
from functools import lru_cache
import hashlib

TOOL_CACHE_TTL = 300  # 5 minutes default

def cached_tool_call(tool_name: str, args: dict, ttl: int = TOOL_CACHE_TTL):
    cache_key = f"{tool_name}:{hashlib.sha256(json.dumps(args, sort_keys=True).encode()).hexdigest()}"
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached), "tool_cache_hit"
    result = TOOL_REGISTRY[tool_name](**args)
    redis.setex(cache_key, ttl, json.dumps(result))
    return result, "tool_cache_miss"

# Use in agent loop
tool_result, source = cached_tool_call("query_database", {"sql": sql, "params": params})
```

**What to cache:** Read-only DB queries, API GETs, file reads, HTTP GET requests with stable responses. **Never cache:** mutations, auth tokens, time-sensitive data.

### Layer 4: Plan Cache (Application-side, hours-days TTL)
Agentic plans — the structural skeleton of multi-step tasks — repeat across sessions. Cache the plan template and fill with current data.

```python
PLAN_CACHE_TTL = 86400  # 24 hours

def get_cached_plan(task_type: str, task_args: dict) -> str | None:
    plan_key = f"plan:{task_type}:{hashlib.md5(json.dumps(task_args, sort_keys=True).encode()).hexdigest()[:8]}"
    cached = redis.get(plan_key)
    if cached:
        return cached
    return None

def cache_plan(task_type: str, plan: str, task_args: dict):
    plan_key = f"plan:{task_type}:{hashlib.md5(json.dumps(task_args, sort_keys=True).encode()).hexdigest()[:8]}"
    redis.setex(plan_key, PLAN_CACHE_TTL, plan)
```

**Invalidation:** Template changes (not data changes) invalidate. When your workflow template changes, delete all matching plan cache entries.

### Layer 5: Session Context Cache (Session-side, session duration)
Session context — retrieved memories, accumulated facts, mid-session tool results — persists within a session but not across. Cache aggressively within session; invalidate on session boundary.

## The full stack wiring

```
User query
  │
  ├─ Layer 1: Prefix cache (provider) — 90% input token discount
  │     ↓ miss
  ├─ Layer 2: Semantic cache (app) — skip LLM call entirely
  │     ↓ miss
  └─ Agent loop
        ├─ Tool call → Layer 3: Tool output cache
        ├─ Plan step → Layer 4: Plan cache (skip generation)
        └─ Retrieve context → Layer 5: Session context cache
```

## Receipt

> Verified 2026-07-16 — Tian Pan's five-layer caching taxonomy (April 2026) covers the full hierarchy. AgentMarketCap benchmarks (April 2026) confirm 40-60% savings unrealized by teams stopping at Layer 1. AI Workflow Lab data shows Anthropic's 90% discount on cached reads (vs 10% fresh) and OpenAI's 50% discount. The five-layer model was cross-checked against production agent observability data showing tool call repetition rates of 60-80% within sessions. S-08 (provider-level prompt caching) covers Layer 1 only — this entry adds the four missing layers.

## See also

- [S-08 · Prompt Caching](s08-prompt-caching.md) — provider-side prefix caching (Layer 1)
- [S-1191 · The Correctness SLO Stack](s1191-the-correctness-slo-stack-when-your-agent-is-accurate-94-of-the-time-and-you-dont-know-it.md) — monitoring the cost axis your cache miss rate drives
- [S-1001 · The Agent Evaluation Stack](s1001-the-agent-evaluation-stack-when-benchmarks-say-pass-but-production-breaks.md) — catching quality regressions from stale cached outputs
