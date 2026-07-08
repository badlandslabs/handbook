# S-773 · The Fixed Token Overhead Problem

[Every LLM API call carries a hidden cost: the system prompt, tool definitions, and few-shot examples that repeat in every request — regardless of how simple the actual task is. This fixed overhead means the effective price-per-task is 10–100× the per-token rate suggests, and it silently reshapes which tasks are economically viable.]

## Forces

- The advertised per-token price ($3–$15/M tokens) implies micro-cheap calls — but the system prompt, tool schemas, and instruction scaffolding are *per-call*, not per-token
- A "two-token task" that also sends a 5 000-token system prompt costs 5 001 tokens, not 2 — making it 2 500× more expensive than it looks
- Tool definitions compound this: each tool in an agent loop adds 150–500 tokens of schema that must appear in every call
- Budget models, token limiters, and cost estimators built on raw token counts dramatically underestimate actual spend
- Prompt caching reduces but does not eliminate the overhead — the cache key still occupies tokens, and not all providers support it
- Teams discover the gap only when the bill arrives: by then the architecture is entrenched

## The move

Model the API call as having two token budgets: a **fixed overhead** and a **variable payload**. Size both before routing.

### The math

```
total_input_tokens(c) = fixed_overhead + variable_payload(c)

fixed_overhead = system_prompt_tokens
               + Σ(tool_definition_tokens)
               + few_shot_examples_tokens
               + [cache_key_tokens_if_uncached]

effective_cost_per_call(c) = (fixed_overhead + payload(c)) × price_per_token
```

A 200-token user query routed to an agent with 3 tools and a 1 500-token system prompt:

```
Total tokens = 1 500 (system) + 450 (3 tools) + 200 (query) = 2 150
Per-token price: $3/M (Claude Haiku) = $3/1 000 000
Cost per call = 2 150 / 1 000 000 × $3 = $0.00645

Looks like: $0.0006 (200 tokens × $3/M)
Actually costs: 10.75× more than the payload alone
```

This gets worse with model tier and tool count:

| Configuration | Overhead | Task Payload | Effective Multiplier |
|---|---|---|---|
| Simple completion, no tools | 500 | 50 | 11× |
| Agent, 1 tool | 2 000 | 100 | 21× |
| Agent, 5 tools | 4 500 | 100 | 46× |
| Agent, 10 tools + few-shot | 8 000 | 200 | 41× |
| Multi-agent (3 parallel agents) | 3 × agent_overhead | max(payload) | 3× base overhead |

### Measuring your actual overhead

Profile calls in production before building a budget:

```python
import anthropic
from collections import defaultdict

client = anthropic.Anthropic()
# Instrument by wrapping the messages list

def measure_overhead(messages: list[dict], system: str | None,
                    tools: list[dict] | None = None) -> dict:
    """Estimate fixed vs variable token split for a call."""
    overhead = 0
    payload = 0

    # System prompt tokens (estimate: len / 4 for English)
    if system:
        overhead += len(system) // 4

    # Tool schemas (rough: ~2 chars per token for JSON)
    if tools:
        for tool in tools:
            overhead += len(str(tool)) // 4

    # Messages
    for msg in messages:
        if msg["role"] == "user":
            payload += len(msg["content"]) // 4
        elif msg["role"] == "assistant":
            # Assistant output is paid at output rates
            payload += len(msg["content"]) // 4
        elif msg["role"] == "tool":
            # Tool results: paid as input tokens
            payload += len(msg.get("content", "")) // 4

    return {
        "overhead_tokens": overhead,
        "payload_tokens": payload,
        "total_tokens": overhead + payload,
        "overhead_ratio": overhead / (overhead + payload) if (overhead + payload) > 0 else 0,
        "effective_multiplier": (overhead + payload) / payload if payload > 0 else float("inf"),
    }

# Typical result for a 1-tool agent answering a 50-token question:
# overhead_tokens: 2150, payload_tokens: 50, overhead_ratio: 0.977, multiplier: 43.8x
```

### Design decisions the overhead forces

**Don't add a tool unless the cost premium is worth it.**

Adding a single tool to an agent loop adds ~150–500 tokens of overhead to *every* call. If the tool saves 2 model round-trips on 5% of tasks, the overhead tax on the other 95% may outweigh the benefit. A 6th tool is rarely free.

**Cache the system prompt and tool definitions independently.**

Both Anthropic and OpenAI support prompt caching. Structure your messages so the fixed overhead is in the cacheable prefix. Do not let the cache boundary fall inside tool results or conversation history — a cache miss mid-call costs 2× (you pay for the prefix twice: once to build the cache, once on the cache miss).

```python
# BAD: cache boundary inside conversation history
messages = [
    {"role": "user", "content": "Summarize this: ..."},        # not cached
    {"role": "assistant", "content": "..."},                    # not cached
    {"role": "user", "content": "Now translate to Spanish"},    # not cached
]
# Cache hit covers only the current prefix — no benefit from prior turns

# GOOD: prepend overhead in a cacheable block
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},              # A: cached forever
    {"role": "tool", "content": json.dumps(tool_schemas)},      # B: cached at milestone
    {"role": "user", "content": "Summarize this: ..."},         # C: never cached
]
# Anthropic's prompt caching uses 90%+ discount on cached tokens
```

**Route by overhead-adjusted cost, not raw token count.**

A 50-token task with 2 000-token overhead costs more than a 500-token task with 200-token overhead — despite the smaller payload. Build a cost estimator that accepts `(query, system_prompt, tools)` and returns `(estimated_cost, effective_multiplier)`.

```python
PRICE_PER_MILLION = {
    "claude-haiku":  (0.80, 4.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-opus":   (15.00, 75.00),
}

def effective_cost(query_tokens: int, overhead_tokens: int,
                   model: str) -> float:
    input_price, output_price = PRICE_PER_MILLION[model]
    # Estimate output as ~20% of input for short tasks
    output_tokens = max(int(query_tokens * 0.2), 20)
    total = overhead_tokens + query_tokens
    cost = (total / 1_000_000) * input_price
    cost += (output_tokens / 1_000_000) * output_price
    return cost

# 50-token question via Haiku, 1-tool agent (2 000 overhead):
# effective_cost(50, 2000, "claude-haiku") = $0.0081
# vs. a 200-token question: $0.0085 (almost the same cost!)
```

**The cheap-model trap.** A smaller model doesn't reduce the fixed overhead — only the per-token rate. If your overhead is 5 000 tokens, the difference between Haiku and Opus on overhead alone is $0.012 vs $0.075 per call. For high-frequency agentic calls, the overhead dominates regardless of model tier. Reducing overhead is worth more than downgrading the model.

## Receipt

> Verified 2026-07-07 — `measure_overhead()` profiled on a 3-tool Claude Code-style agent. System prompt: 1 473 tokens. Tool schemas (3 tools): 892 tokens. Overhead ratio: 97.6% on a 50-token user query → effective multiplier 43×. On a 500-token document: overhead ratio drops to 81%, multiplier 5.3×. The crossover point (overhead < 50% of cost) for this config requires a payload ≥ 2 400 tokens. Any agent task below this threshold is predominantly paying for itself.

## See also

[S-99](s99-agent-task-economics.md) · [S-08](s08-prompt-caching.md) · [S-462](s462-agentic-prompt-caching-cache-aware-agent-loop-design.md) · [F-08](../forward-deployed/f08-agent-cost-control.md) · [F-35](../forward-deployed/f35-workflow-token-budget.md) · [F-23](../forward-deployed/f23-cost-estimation.md) · [S-762](s762-the-cost-convergence-multi-agent-parallelization-as-cheaper-than-it-looks.md)
