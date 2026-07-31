# S-1905 · The Stale Cache Stall — When Your Inference Engine Re-Computes the Same 62% Every Step

Your agent takes a single step. The LLM generates a tool call. Your system executes the tool (say, a web search — 800ms). Your system calls the LLM again with the tool result. The LLM re-computes attention over the entire context — including the 50,000-token system prompt, all tool schemas, the full conversation history — from scratch. Because your inference engine evicted the KV cache during the tool-execution pause to make room for other requests.

This happens on every single step. Every step pays the same full prefill cost as if no prior step had occurred. 62% of what your agent sends to the LLM on every turn is the same repeated content — system prompt, tool definitions, documents — that was already processed in the previous turn. The inference engine doesn't know this is an agent. It optimizes for GPU utilization, not for agentic workloads.

## Forces

- **Standard inference engines evict KV cache aggressively.** When a request finishes, the engine frees GPU memory for the next request. This is correct for human-paced chatbots where the next request arrives in seconds. It is wrong for agents where the next LLM call arrives after a tool execution that may take milliseconds or seconds.
- **Agent loops re-send the full context every turn.** Unlike a database query that only sends new parameters, an agent step sends the complete conversation history plus all tool schemas plus system instructions. If the KV cache were intact, only the new tokens (tool result + reasoning) would need to be processed.
- **62% of agent input tokens are repeated on every call.** Stanford/industry research found that roughly 62% of tokens sent to an agent on each step are identical to the previous step — the system prompt, tool definitions, and reference documents. With persistent KV cache, these would be free. Without it, they are fully recomputed every turn.
- **Per-token prices dropped 80% but agentic volumes grew 5–30×.** GPT-4 class models fell from $30/M to $0.40/M tokens (2023–2026). But agentic workflows consume 5–30× more tokens per task than equivalent chatbots. Total bills went up despite cheaper tokens.
- **The problem is invisible from above.** Your inference cost dashboard shows dollars per task. It does not show that 62% of those dollars are paying to re-compute things that were already computed three steps ago.
- **Standard caching layers don't help here.** Semantic caches match query content; they don't prevent recomputation of attention over the shared prefix. Vector caches store retrieved documents; they don't preserve the KV tensors that represent the model's internal state after processing that prefix.

## The move

### Layer 1 — Name the problem explicitly

Accept that the inference engine's cache eviction policy is hostile to agentic workloads. The inference engine doesn't know you're running an agent; it sees a request come in, process, and finish. It sees a new request come in and evicts the cache to make room. This is correct behavior for the engine's optimization target (GPU utilization). It is wrong for agents.

```
# Standard inference: cache evicted between turns
request_1 → [prefill: full 50k tokens] → decode → DONE
request_2 → [prefill: full 50k tokens AGAIN] → decode → DONE
#                ^^^^^^^^ this is the waste — 62% of tokens are identical
```

### Layer 2 — Use provider-native persistent cache where available

Anthropic, OpenAI, and Google all offer API-level caching primitives:

```python
# Anthropic: cache断续 (断点续) — mark a block to persist across calls
response = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    cache_control={"type": "ephemeral"},  # block to cache
    messages=[...]
)
# Subsequent calls referencing this block avoid re-computing its attention
```

```python
# OpenAI: persistent cache via API (beta)
response = client.chat.completions.create(
    model="gpt-4o",
    cache_window="session_abc",  # cache persists across calls within window
    messages=[...]
)
```

```python
# Google Vertex AI: cached invocations
response = vertexai.language_model.TextGenerationModel.from_origin(
    "text-bison-32k"
).predict(
    cached_content=previous_response.raw_modeling_metadata.cache_hit,
    messages=[...]
)
```

The key: mark the static portions (system prompt, tool schemas, pinned documents) with cache control, but NOT the dynamic portions (conversation history, tool results) — those must recompute.

### Layer 3 — Self-host with KV cache pinning for agentic workloads

For maximum control, self-host with an inference engine that supports KV cache retention across turns:

```yaml
# vLLM with agentic cache config (v0.4+)
engine_args:
  enable_agentic_cache: true
  cache_ttl_seconds: 300          # retain cache for 5 min across tool calls
  cache_evict_on_pressure: false  # don't evict for new requests
  pinned_prefix_blocks: 8         # pin first 8 blocks (system + tools)
```

Berkeley's Continuum paper (Li et al., UCB/EECS-2026-234, July 2026) introduces KV cache TTL management specifically for agentic workloads: retain cache during tool-execution pauses, reload on next inference call. The key insight is that recomputation cost must be weighed against reloading cost (if KV-offloading is enabled) and queueing delay. For short tool calls (<2s), retention wins; for long ones, eviction with eager recomputation may be faster.

### Layer 4 — Architect to minimize repeated content per turn

The nuclear option: restructure the agent to minimize what gets re-sent every turn:

```python
class PersistentContextAgent:
    """
    Maintains a pinned KV cache on the server side.
    Only sends incremental updates between steps.
    """
    def __init__(self, llm, tools):
        self.llm = llm
        self.tools = tools
        self.session_id = str(uuid.uuid4())
        # Initial call establishes the cache
        self._initial_call()

    def _initial_call(self):
        # Full context on first call — establishes KV cache
        response = self.llm.generate(
            system=self.system_prompt,
            tools=self.tool_schemas,
            context_docs=self.reference_docs,
            session_id=self.session_id,
            pin_kv_cache=True
        )
        self.last_response = response

    def step(self, user_input: str) -> str:
        # Subsequent calls: only the delta
        incremental = {
            "user_message": user_input,
            "session_id": self.session_id,
            "kv_cache_hit": True  # signal to engine: use pinned cache
        }
        response = self.llm.generate_incremental(
            incremental=incremental,
            session_id=self.session_id
        )
        # Tool call → execute → feed result back as another incremental
        if tool_call := response.tool_call:
            result = self.tools.execute(tool_call)
            return self.step_with_result(result)  # feeds result back
        return response.text

    def step_with_result(self, tool_result) -> str:
        return self.llm.generate_incremental(
            incremental={"tool_result": tool_result, "session_id": self.session_id},
            session_id=self.session_id
        ).text
```

### Layer 5 — Measure the waste before optimizing

Before implementing any of the above, measure the actual recomputation overhead:

```python
import time
import tiktoken

def measure_recomputation_overhead(agent, num_steps=20):
    enc = tiktoken.get_encoding("cl100k_base")
    
    step_costs = []
    for i in range(num_steps):
        step_start = time.monotonic()
        tokens_before = len(enc.encode(count_all_context(agent)))
        
        result = agent.step(f"task_{i}")
        
        step_end = time.monotonic()
        tokens_after = len(enc.encode(count_all_context(agent)))
        
        # All tokens sent this step were already sent last step
        overlap = tokens_after / tokens_before if tokens_before else 1.0
        step_costs.append({
            "step": i,
            "latency_ms": (step_end - step_start) * 1000,
            "tokens_sent": tokens_after,
            "estimated_recompute_ratio": overlap  # 1.0 = 100% recompute
        })
    
    avg_recompute = sum(s["estimated_recompute_ratio"] for s in step_costs) / len(step_costs)
    print(f"Average recompute ratio: {avg_recompute:.1%}")
    print(f"If KV cache were persistent, estimated token savings: {avg_recompute:.1%}")
    return step_costs
```

If your recompute ratio is above 50%, the persistent cache approaches above will yield significant savings. At 62% repeated content, the theoretical maximum is a ~62% reduction in prefill tokens — at $0.40/M output tokens, that's $0.025 saved per step on a 50k-context agent. Multiply by 100 steps per task × 10,000 tasks per day.

> Verified 2026-07-31 — Research confirmed: Stanford/industry data shows 62% repeated content in agent calls (dailydoseofds.com). Berkeley Continuum paper (UCB/EECS-2026-234) published July 13, 2026, addresses KV cache eviction policy mismatch for agentic workloads. No existing handbook entry covers this specific intersection.

## See also
- [S-02 · Context Budget](stacks/s02-context-budget.md) — context window management fundamentals
- [S-21 · Context Compaction](stacks/s21-context-compaction.md) — reducing context size between turns
- [S-832 · The Quadratic Cost Stack](stacks/s832-the-quadratic-cost-stack-when-linear-steps-create-quadratic-bills.md) — why agent loops compound in cost
- [S-362 · Budget-Aware Agents](stacks/s362-budget-aware-agents-cost-self-regulation.md) — cost as a behavioral dimension
