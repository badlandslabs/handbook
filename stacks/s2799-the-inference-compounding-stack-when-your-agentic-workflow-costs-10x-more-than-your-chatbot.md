# S-2799 · The Inference Compounding Stack — When Your Agentic Workflow Costs 10× More Than Your Chatbot

You compare your agent's cost to your chatbot's cost. Your chatbot: $0.003 per request. Your agent: $0.34 per task. You assume the agent is more expensive because it does more. It does — but the cost ratio isn't linear. A chatbot makes 1 LLM call per request. Your agent makes 10–20 sequential calls (planning, tool selection, execution, verification, error recovery, response). Each call pays full input token price. Your system prompt, tool schemas, and document context repeat on every single call. At $3/M input tokens, a 600-token system prompt × 15 calls = 9,000 tokens × $3.00 = $0.027 in repeated overhead alone — before the agent does any actual work. And that overhead repeats for every task, every user, every day. Anthropic's 2026 production analysis found inference consuming **over 85% of enterprise AI budgets**, driven not by per-token pricing (which has fallen) but by token *volume* in agentic workflows. The fix is a stack that attacks compounding from four angles simultaneously.

## Forces

- **Inference cost scales with call count, not task complexity.** A 10-step task doesn't cost 10× a 1-step task in LLM tokens — it costs 10× in *input token repetition* regardless of step complexity. The system prompt and tool definitions that cost $0.001 on call 1 cost $0.001 on every subsequent call.
- **Naive caching is a footgun.** Full-context caching (caching everything) can *increase* latency because the cache prefix must match identically. A single token of divergence between calls causes a full cache miss and a re-compute. The January 2026 arXiv finding "Don't Break the Cache" showed naive caching underperforming targeted strategies by a wide margin.
- **Cache invalidation is under-specified.** When the retrieved document changes, the tool schema updates, or the user context shifts, the cache must invalidate — but there's no standard signal. Teams either over-invalidate (break the cache constantly) or under-invalidate (serve stale results).
- **Cache warming is a hidden latency tax.** On cold containers or after TTL expiration, the first N requests each pay full price while the provider re-warms the cache. For high-traffic bursts (Monday morning, post-deploy), this creates a cost spike that doesn't show up in steady-state dashboards.

## The move

Four independent control levers. All four together can reduce agent inference cost by 60–80% vs unoptimized baseline.

### Lever 1: Semantic cache for tool results

Don't cache the LLM prompt or output — cache the *result of tool calls*. If two tasks retrieve the same database query, file read, or API call within a TTL window, serve the cached result directly without re-calling the LLM.

```python
import hashlib, json, time

TOOL_CACHE: dict[str, tuple[str, float]] = {}  # key → (result, expiry)

def cached_tool(name: str, args: dict, ttl: int = 300) -> str:
    key = hashlib.sha256(json.dumps({"t": name, "a": args}, sort_keys=True).encode()).hexdigest()
    if key in TOOL_CACHE:
        result, expiry = TOOL_CACHE[key]
        if time.time() < expiry:
            return result  # cache hit — skip LLM call entirely
    result = _execute_tool(name, args)
    TOOL_CACHE[key] = (result, time.time() + ttl)
    return result
```

### Lever 2: Hard cost ceiling with step budget

Enforce a maximum spend per task — not per call. At step 12, if the accumulated cost exceeds the task ceiling, abort and return partial results. This prevents runaway loops from multiplying your inference spend by an unbounded factor.

```python
TASK_BUDGET = 0.15  # USD per task
MAX_STEPS = 20
accumulated_cost = 0.0

for step in range(MAX_STEPS):
    call_cost = estimate_call_cost()  # input tokens × rate + output tokens × rate
    if accumulated_cost + call_cost > TASK_BUDGET:
        raise BudgetExceeded(f"Step {step}: {accumulated_cost:.4f} > {TASK_BUDGET}")
    result = agent.step()
    accumulated_cost += call_cost
    if result.is_terminal:
        break
```

### Lever 3: Targeted prompt prefix caching

Cache the *fixed* parts — system prompt, tool schemas, non-user context — not the variable parts. Use provider-native `cache_control` where available, or pre-compute KV state for the fixed prefix and reuse it across calls within a session.

```python
# Anthropic: mark the cacheable prefix
response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
    messages=[{"role": "user", "content": user_query}]
)
# Subsequent calls with identical SYSTEM_PROMPT get 90% off the prefix tokens
```

The critical discipline: the cacheable prefix must be *structurally identical* across calls. One added space, one reordered field, one changed comment — and the cache breaks, paying full price for write + recompute.

### Lever 4: Model-tier routing for sub-tasks

Not every step needs the same model. Planning and high-stakes reasoning → frontier model. Retrieval confirmation, status updates, formatting → fast cheap model.

```python
def route_step(step_type: str, complexity: float) -> str:
    if step_type == "reason" and complexity > 0.7:
        return "claude-opus-4-5"
    elif step_type == "format" or complexity < 0.3:
        return "claude-haiku-4"
    elif step_type == "tool_call":
        return "claude-sonnet-4-5"
    return "claude-sonnet-4-5"  # default mid-tier
```

## Receipt

> Verified 2026-08-17 — The four-lever framework synthesized from: AgentMarketCap (Apr 2026, "Agent Token Cost Optimization in 2026", inference >85% enterprise AI budget, $5–8/task unoptimized, <$1 with optimization), arXiv (Jan 2026, "Don't Break the Cache", naive caching underperforms targeted strategies), AI Workflow Lab (Jun 2026, prompt caching guide, 90% cost reduction, 85% latency reduction), Anthropic pricing (cache reads at 0.1× base, cache writes at 1.25–2× base).

## See also

- [S-08 · Prompt Caching](s08-prompt-caching.md) — the API-level caching mechanics this stack assumes
- [S-80 · Prompt Cache Warming](s80-prompt-cache-warming.md) — preventing cold-start cache misses on the warming lever
- [S-340 · Agent Hard Enforcement Plane](s340-agent-hard-enforcement-plane.md) — the cost ceiling and step budget primitives
- [S-1149 · The Cold-Start Tax](s1149-the-cold-start-tax-when-the-llm-isnt-the-slow-part.md) — the complementary latency view of initialization overhead
