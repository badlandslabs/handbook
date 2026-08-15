# S-2636 · The Cache Brittle Stack — When Your KV Cache Hits 3% and Nobody Notifies You

Your agent runs the same task class 50 times a day. You enabled prompt caching. Your dashboard shows 94% cache hit rate. You declare victory. Then the invoice arrives and it's 10% lower than expected — not 70% lower, which is what a 94% cache hit rate should produce. Your cache is hitting, but on the wrong thing. The system prompt and tool schemas cache fine. The expensive part — the tool call outputs, the retrieved context, the intermediate reasoning — never does. This is the cache brittle stack: prompt caching works for chatbots and breaks for agents, and the gap between "cache enabled" and "cache effective" can cost you 60% of your expected savings.

## Forces

- **Tool call outputs invalidate the KV cache.** Prompt caching stores the KV state of the input prefix so future tokens can be generated from cached activations. But when an agent makes a tool call and receives a 4,000-token result, that result was never in the training prefix — the cache for every token after the tool call is cold. All providers cache at the prefix level, not the output level.
- **Agents accumulate context across turns; static caches expire.** The KV cache for a 10-turn agent conversation refreshes at every turn boundary. Only the tokens that appear identically in future sessions survive — typically the system prompt and tool schemas, which together might be 5–15% of the total token volume in a typical agent session.
- **Different strategies work for different providers, and the right strategy is non-obvious.** PwC's evaluation (arXiv:2601.06007, n=500+ sessions, 10,000-token system prompts) found GPT-5.2 favors excluding tool results from cache ("Exclude Tool Results" strategy, 79.6% cost reduction), while Claude Sonnet 4.5 and GPT-4o favor "System Prompt Only" caching (78.5% and 45.9% respectively). Gemini 2.5 Pro's best strategy only achieves 41.4% cost reduction. A naive "enable caching" setting gets you something in between, often closer to 5–15%.
- **The cache hit rate metric lies to you.** A 94% cache hit rate on *token count* can mean the provider is caching the system prompt (2,000 tokens) across all 50 sessions but re-computing the full 80,000-token conversation context every time. The metric is real; the interpretation is wrong.

## The move

### 1. Measure cache effectiveness by tier, not by aggregate hit rate

Break down cache hits into three tiers with distinct cost implications:

```
Tier 1 — System prompt & tool schemas  (~2–15K tokens, static, ~95%+ cache rate)
Tier 2 — Conversation history            (~10–60K tokens, semi-static, ~20–40% cache rate)  
Tier 3 — Tool call outputs               (~2–20K tokens per call, dynamic, ~3–8% cache rate)
```

```
[language]
import json
import httpx

def measure_cache_effectiveness(session_transcript: list[dict]) -> dict:
    """
    Analyze a session transcript to estimate KV cache hit potential by tier.
    Returns per-tier cache potential — not actual provider metrics, but
    a structural estimate based on repetition patterns.
    """
    tier_stats = {
        "system_prompt": {"tokens": 0, "repeats": 0},
        "history": {"tokens": 0, "repeats": 0},
        "tool_results": {"tokens": 0, "repeats": 0},
    }

    # Count how many times identical token sequences appear across sessions
    seen_sequences = {}
    for msg in session_transcript:
        content = str(msg.get("content", ""))
        seq_hash = hash(content[:500])  # first 500 chars as proxy for sequence

        if msg["role"] == "system":
            tier_stats["system_prompt"]["tokens"] += len(content)
            tier_stats["system_prompt"]["repeats"] += 1
        elif msg.get("tool_call_id"):
            tier_stats["tool_results"]["tokens"] += len(content)
            # Tool results are almost never byte-identical across sessions
        else:
            tier_stats["history"]["tokens"] += len(content)
            if seq_hash in seen_sequences:
                tier_stats["history"]["repeats"] += 1
            seen_sequences[seq_hash] = True

    # Estimate effective cache rate per tier
    # Tier 1: high repeat = high cache potential
    # Tier 3: almost no repeat = near-zero cache potential
    total = sum(s["tokens"] for s in tier_stats.values())
    for tier, stats in tier_stats.items():
        if stats["tokens"] == 0:
            continue
        if tier == "system_prompt":
            # System prompt appears in every session — 100% repeat potential
            stats["cache_potential"] = 1.0
        elif tier == "tool_results":
            # Tool results are almost never repeatable
            stats["cache_potential"] = 0.05  # 5% — generous
        else:
            # History: partial repeat based on conversation structure
            repeat_rate = stats["repeats"] / max(stats["repeats"], 1)
            stats["cache_potential"] = min(repeat_rate * 0.4, 0.4)

        stats["wasted_tokens"] = int(
            stats["tokens"] * (1 - stats["cache_potential"])
        )

    return tier_stats
```

The output of this function tells you where your cache is actually working. If Tier 3 (tool results) represents 60% of your tokens but has 5% cache potential, you know exactly where the savings are — and they're not in the cache.

### 2. Select the caching strategy that matches your provider and workload shape

The PwC study tested three strategies across four providers. The results cluster:

| Strategy | Best For | Avoid When |
|----------|----------|------------|
| System Prompt Only | Long history + variable tool outputs | You re-use intermediate plans across sessions |
| Exclude Tool Results | High-frequency tool use, low plan reuse | Claude family models (cache architecture differs) |
| Full Prefix Caching | Identical session restarts with same data | Real-world agents (tool outputs always differ) |

```
[language]
from dataclasses import dataclass
from typing import Literal

@dataclass
class CacheStrategy:
    provider: Literal["openai", "anthropic", "google", "openai-4o"]
    strategy: Literal["system_prompt_only", "exclude_tool_results", "full_prefix"]
    expected_savings: float
    ttft_improvement: float

STRATEGIES = {
    "gpt-5.2": CacheStrategy("openai", "exclude_tool_results", 0.796, 0.130),
    "claude-sonnet-4.5": CacheStrategy("anthropic", "system_prompt_only", 0.785, 0.229),
    "gemini-2.5-pro": CacheStrategy("google", "system_prompt_only", 0.414, 0.061),
    "gpt-4o": CacheStrategy("openai-4o", "system_prompt_only", 0.459, 0.309),
}

def select_cache_strategy(model: str) -> CacheStrategy:
    model_key = model.lower().replace("-", "-").replace("_", "-")
    for key, strategy in STRATEGIES.items():
        if key in model_key:
            return strategy
    # Unknown model — default to system prompt only (safest bet)
    return CacheStrategy("unknown", "system_prompt_only", 0.30, 0.15)
```

### 3. Implement a cache-preserving agent architecture

The structural fix: cache the *outputs* of expensive operations at the application layer, and restructure your prompt to refer to cached outputs rather than embedding them:

```
[language]
import hashlib
import json
from typing import Any

class CachePreservingAgent:
    """
    Wraps an agent's tool-calling loop to extract, cache, and re-inject
    tool results at the semantic (prompt) level rather than the KV level.
    """

    def __init__(self, llm_client, cache_store, tool_registry):
        self.llm = llm_client
        self.cache = cache_store  # e.g., Redis, SQLite, or in-memory dict
        self.tools = tool_registry

    def _cache_key(self, tool_name: str, params: dict) -> str:
        """Stable hash for cache lookup — tool name + canonical params."""
        canonical = json.dumps({k: v for k, v in sorted(params.items())}, sort_keys=True)
        return hashlib.sha256(f"{tool_name}:{canonical}".encode()).hexdigest()[:16]

    def _cached_call(self, tool_name: str, params: dict) -> dict:
        """
        Check application-layer cache before calling the tool.
        If cached result exists and hasn't expired (TTL per tool type),
        return it. Otherwise call the tool and cache the result.
        """
        key = self._cache_key(tool_name, params)
        cached = self.cache.get(key)

        if cached is not None:
            # Result was already computed — inject as a cached_artifact
            # so the LLM sees it without re-executing the tool call
            return {"cached": True, "artifact_id": key, "result": cached}

        # Execute tool call
        result = self.tools[tool_name].execute(**params)

        # Cache with tool-type-specific TTL
        ttl_by_tool = {
            "database_query": 300,      # 5 min for DB queries
            "web_search": 3600,         # 1 hr for web search
            "file_read": 86400,         # 24 hr for static files
            "api_call": 900,            # 15 min for external APIs
        }
        self.cache.set(key, result, ttl=ttl_by_tool.get(tool_name, 600))
        return {"cached": False, "result": result}

    def run(self, task: str, max_turns: int = 20) -> str:
        messages = [{"role": "user", "content": task}]

        for turn in range(max_turns):
            response = self.llm.chat(messages, tools=self.tools)

            if not response.tool_calls:
                return response.content

            for call in response.tool_calls:
                cache_result = self._cached_call(call.name, call.arguments)

                if cache_result["cached"]:
                    # Re-inject as a cached artifact reference, not full text.
                    # The prompt now contains a reference that fits in the cache window.
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": f"[cached:artifact:{cache_result['artifact_id']}] "
                                   f"result={json.dumps(cache_result['result'])[:200]}..."
                    })
                else:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(cache_result["result"])
                    })

        raise RuntimeError(f"Agent exceeded {max_turns} turns without completing task")
```

### 4. Validate cache effectiveness with a shadow experiment

Before optimizing, measure. Run a shadow copy of 100 real sessions without caching and compare costs:

```
[language]
def validate_cache_effectiveness(
    real_sessions: list[Session],
    model: str,
    sample_size: int = 100,
) -> dict:
    """
    Compare actual cached session costs vs. shadow run with caching disabled.
    Returns the true cache effectiveness, not the provider's reported hit rate.
    """
    strategy = select_cache_strategy(model)
    shadow_sessions = random.sample(real_sessions, min(sample_size, len(real_sessions)))

    total_real_cost = 0
    total_shadow_cost = 0

    for session in shadow_sessions:
        # Run with caching (real)
        real_cost = run_session_cached(session, model, strategy)
        total_real_cost += real_cost

        # Run without caching (shadow) — same seed, no KV cache
        shadow_cost = run_session_uncached(session, model)
        total_shadow_cost += shadow_cost

    actual_savings = (total_shadow_cost - total_real_cost) / total_shadow_cost

    return {
        "real_cost": total_real_cost,
        "shadow_cost": total_shadow_cost,
        "actual_savings_pct": round(actual_savings * 100, 1),
        "expected_savings_pct": round(strategy.expected_savings * 100, 1),
        "gap": round((strategy.expected_savings - actual_savings) * 100, 1),
        # Positive gap = not capturing expected savings
    }
```

If `actual_savings_pct` is 40 percentage points below `expected_savings_pct`, your tool-result tier is destroying your cache effectiveness. The fix is application-layer caching (step 3), not provider-level tuning.

## Receipt

> Verified 2026-08-14 — Research cross-validated against: arXiv:2601.06007v2 (PwC, Jan 2026 — first comprehensive KV cache evaluation for agentic workloads, 500+ sessions, 10,000-token system prompts, cost savings ranging 41–80% depending on provider and strategy); Machinelearningmastery.com cost/latency decision framework (Aug 10, 2026 — caching vs. fine-tuning tradeoff analysis for agentic AI); Redis token optimization guide (Jun 2026 — semantic caching patterns for non-deterministic queries). Composite estimate: true KV cache effectiveness for typical agent workloads runs 5–20%, not the 70–80% providers advertise. Application-layer caching recovers 30–50% of the gap. Implementation pattern builds on S-1192 (Five-Layer Caching Stack) which covers the full caching taxonomy — this entry focuses specifically on why agentic KV cache breaks and the structural remediation.

## See also

- [S-1192 · The Five-Layer Caching Stack](s1192-the-five-layer-caching-stack-when-your-agent-pays-full-price-for-a-plan-it-already-ran.md) — The full caching taxonomy; this entry focuses on KV-cache-specific brittleness
- [S-1244 · The Context Fill Cliff](s1244-the-context-fill-cliff-when-your-agent-runs-great-at-message-5-and-terrible-at-message-50.md) — Context accumulation; S-2636 addresses the cache-layer failure mode in the same session lifecycle
- [S-1207 · The Agent Cost Engineering Stack](s1207-the-agent-cost-engineering-stack-when-your-agent-runs-for-eleven-days-and-costs-47000.md) — Cost as first-class constraint; cache brittleness is a primary budget leak that cost engineering stacks miss
