# S-876 · The Intent Signature Stack — When 50 Internal Agents Are All Asking the Same Question

[A single user request fires a 12-agent pipeline. The planner calls the researcher, who calls a web tool. The analyst calls the same tool with the same query. The writer's sub-agent calls it again. The reviewer calls it once more. By the time the user sees a response, the same question was answered five times — at $0.002 per call — and nobody deduplicated them. The "chatter tax" isn't just expensive. It's redundant by design.]

## Forces

- **The token multiplier is a redundancy multiplier.** A 12-agent pipeline doesn't just amplify cost — it amplifies *repeated work*. The same tool, the same query, asked by different agents in the same session, is treated as five distinct events. At 50+ internal transactions per user request, the redundancy surface is enormous.
- **Exact-match caching fails for natural language.** Two agents asking "current weather, New York City" and "NYC weather right now" return identical tool schemas but fail any `==` comparison. The tools don't know they're asking the same thing. The orchestrator doesn't know either.
- **Latency compounds on redundancy.** Every duplicate call adds a full round-trip. In a 12-agent pipeline, eliminating five duplicates shaves seconds off end-to-end latency — not through faster inference, but through arithmetic.
- **The deduplication decision must happen before the tool call, not after.** Checking results for equivalence after you've already paid for five calls is cost accounting, not cost engineering.

## The move

**Intent Signature** — extract a semantic hash of *what an agent intends to do* (action type + entity + temporal scope), use it as a cache key, and serve the prior result to any semantically equivalent future intent — regardless of which agent asked, or how they phrased it.

The key distinction from `result_cache` or `semantic_cache`: those operate on *queries* or *responses*. Intent Signature operates on *intention* — the combination of action + target + parameters. Two agents who *intend* to do the same thing produce the same signature, even if their prompts differ.

### Step 1 — Define the Intent Schema

An intent signature is a tuple: `(action, entity, temporal_scope, parameters_hash)`.

```python
@dataclass
class IntentSignature:
    action: str          # "web_search", "db_query", "api_call"
    entity: str          # "weather-nyc", "customer-12345", "pr-4821"
    temporal_scope: str  # "realtime", "hourly", "daily", "static"
    param_hash: str      # SHA-256 of relevant params beyond entity

def compute_signature(intent: dict) -> str:
    """
    Canonicalize an agent's intended action into a cache key.
    Two agents with semantically equivalent intents produce identical signatures.
    """
    canonical = {
        "action": intent["tool_name"].lower().strip(),
        "entity": _normalize_entity(intent["entity"]),   # strip quotes, whitespace
        "temporal_scope": _derive_temporal_scope(intent["params"]),
        "param_hash": _hash_params(intent["params"], exclude=["session_id", "trace_id"])
    }
    key = f"{canonical['action']}::{canonical['entity']}::{canonical['temporal_scope']}::{canonical['param_hash']}"
    return key
```

### Step 2 — Build the Intent Cache Layer

```python
from redis import Redis
import json, hashlib, time

class IntentCache:
    """
    Deduplicates tool calls across agents based on semantic intent.
    Plugs between the orchestrator and the tool execution layer.
    """

    def __init__(self, redis_client: Redis, ttl_by_scope: dict[str, int]):
        self.cache = redis_client
        self.ttl = ttl_by_scope  # e.g. {"realtime": 30, "hourly": 3600, "static": 86400}

    def get_or_execute(self, agent_id: str, intent: dict, executor_fn):
        sig = compute_signature(intent)
        cached = self.cache.get(sig)

        if cached:
            # Log who asked, who answered — for audit and hit-rate analysis
            self.cache.lpush(f"sig:{sig}:readers", agent_id)
            result = json.loads(cached)
            result["_cache_hit"] = True
            result["_original_agent"] = result.get("_requesting_agent")
            return result

        # First caller — execute and store
        result = executor_fn(intent)
        result["_cache_hit"] = False
        result["_requesting_agent"] = agent_id
        result["_cached_at"] = time.time()

        ttl = self.ttl.get(intent.get("temporal_scope", "realtime"), 60)
        self.cache.setex(sig, ttl, json.dumps(result))

        return result

    def invalidate(self, sig: str):
        self.cache.delete(sig)
```

### Step 3 — Integrate at the Orchestrator Layer

```python
# Drop into your planner or orchestrator — wrap every tool invocation
async def call_tool(agent_id: str, intent: dict):
    return await intent_cache.get_or_execute(
        agent_id=agent_id,
        intent=intent,
        executor_fn=lambda i: tool_registry.execute(i["tool_name"], i["params"])
    )

# Example: multiple agents in the same session
results = await asyncio.gather(
    call_tool("planner-agent", {"tool_name": "web_search", "entity": "weather-nyc", "params": {"q": "NYC weather right now"}}),
    call_tool("analyst-agent", {"tool_name": "web_search", "entity": "weather-nyc", "params": {"query": "current weather New York City"}}),
    call_tool("writer-agent",  {"tool_name": "web_search", "entity": "weather-nyc", "params": {"location": "New York, NY", "type": "current"}}),
)
# All three return the same cached result on the first non-cached run.
# Cost: 1 web search call instead of 3.
```

### Step 4 — Derive Temporal Scope from Tool Semantics

The hardest part is getting `temporal_scope` right. Wrong scope = stale data served, or fresh data over-cached.

```python
def _derive_temporal_scope(params: dict) -> str:
    """
    Heuristic: infer how time-sensitive this call is from its parameters.
    Production systems should tag tools with scope at registration time.
    """
    query_text = str(params).lower()

    if any(k in query_text for k in ["realtime", "live", "now", "current"]):
        return "realtime"   # 30-60s TTL
    if any(k in query_text for k in ["today", "yesterday", "this week"]):
        return "hourly"     # 3600s TTL
    if any(k in query_text for k in ["history", "archive", "2024", "2023"]):
        return "static"     # 86400s+ TTL

    return "realtime"  # safe default
```

### When NOT to use Intent Signature

- **Write operations.** If the intent is `update_order`, `send_email`, `charge_card` — deduplication is a data-integrity bug, not a feature. Intent Signature only applies to idempotent reads.
- **Agent-specific context.** If two agents ask the same query but with different context that changes the answer (different user ID, different permission scope), they have different intents — the signature should include a scope parameter.
- **Real-time-sensitive decisions.** A "current stock price" asked by a trading agent and a reporting agent should share a cache key within a 5-second window, but not a 5-minute one. Scope calibration is load-bearing.

## Receipt

> Receipt pending — 2026-07-09

## See also

- [S-232 · The Prototype-to-Production Cost Gap](s232-the-prototype-to-production-cost-gap-in-agentic-systems.md) — Cost arithmetic context for why this matters
- [S-698 · Semantic Caching: The Single Highest-Leverage Lever on Production Agent Cost](s698-semantic-caching-the-single-highest-leverage-lever-on-production-agent-cost.md) — Query-level deduplication (complementary: Intent Signature operates on *intent*, not query)
- [S-43 · Tool Result Caching](s43-tool-result-caching.md) — Response-level caching baseline; Intent Signature sits upstream
- [S-175 · Cross-Session Tool Result Cache](s175-cross-session-tool-result-cache.md) — Persistence layer for shared caches across sessions
