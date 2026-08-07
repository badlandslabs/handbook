# S-2298 · The KV Cache Topology Mismatch Stack — When Your Agent Is Slow Not Because the Model Is Slow, But Because the Inference Engine Is Caching the Wrong Thing

Your agent runs fine for the first few turns. Then, at turn 7, latency doubles. At turn 15, it triples. You profile the LLM call — model inference time is unchanged. The bottleneck is the KV cache: your inference engine evicted the prefix your agent needed most, and is recomputing it from scratch on every call. This is not a model problem. It is a cache topology problem.

LLM inference engines — vLLM, SGLang, TensorRT-LLM — use Least Recently Used (LRU) eviction for KV cache to maximize GPU memory utilization under load. When GPU memory fills, the engine evicts the least-recently-accessed cache entry. This works well for standard request-response workloads where the "recent" entry is almost always the one you need next.

Agentic workloads break this assumption. Agents interleave LLM calls with tool execution — file I/O, API calls, database queries. Tool calls introduce pauses ranging from milliseconds to minutes. During those pauses, LRU treats the cached entry as "stale" and evicts it. When the agent resumes, the inference engine must recompute the full context prefix from scratch, defeating the entire purpose of KV caching.

The result: agents using tool-calling loops suffer 40%+ throughput degradation from premature KV cache eviction, even when GPU headroom exists. The cache is full — but it's full of the wrong things.

## Forces

- **LRU is time-based; agentic workflows are intent-based.** LRU evicts by recency of access. A tool-call pause does not mean the context prefix is irrelevant — it means the agent is working. LRU cannot distinguish between "I haven't used this cache entry in 30 seconds because I was thinking" and "I haven't used this cache entry in 30 seconds because nobody needs it."

- **Inference engines optimize for GPU utilization, not cache hit rate.** vLLM's PagedAttention and SGLang's KV cache management prioritize keeping GPU busy. Evicting a cached prefix that will be needed in the next turn is "correct" from a memory-utilization perspective but catastrophic from a throughput perspective.

- **The pause distribution is long-tailed.** Most tool calls resolve in milliseconds, but some — file operations, web searches, database queries — can take seconds to minutes. LRU has no model of which pauses are "safe" to wait through before evicting.

- **Application-layer caching does not solve this.** Semantic caching, result caching, and prefix caching all operate above the inference layer. They cache outputs or results, not intermediate KV state. The inference engine's KV cache is invisible to the application layer.

## The move

Three complementary strategies address the topology mismatch at different layers.

**1. KV Cache TTL with Agentic Awareness (inference layer)**

Set per-entry time-to-live on KV cache entries that accounts for tool-call durations. Instead of LRU, use a TTL policy that distinguishes between pauses caused by inference and pauses caused by tool calls. The Continuum paper (Berkeley EECS-2026-234, Li et al., July 2026) demonstrates that TTL-based eviction with agentic pause detection recovers 40%+ of the throughput lost to premature eviction. The key signal: track inter-call intervals. If the gap between two LLM calls exceeds the median tool-call duration by 3x, treat it as a "potential tool pause" rather than an idle period, and extend the TTL accordingly.

```python
import time
from dataclasses import dataclass, field
from collections import deque

@dataclass
class AgenticKVCachePolicy:
    """KV cache eviction policy aware of agentic tool-call patterns."""
    median_tool_duration_ms: float = 200.0
    ttl_extension_factor: float = 3.0
    recent_calls: deque = field(default_factory=deque)
    
    def should_evict(self, entry_age_ms: float, last_access_ms: float) -> bool:
        # Standard LRU: evict least recently accessed
        if last_access_ms > 0:
            return False  # don't evict recently accessed
        
        # Agentic TTL: if the gap between LLM calls matches tool-call 
        # duration patterns, extend the TTL instead of evicting
        tool_call_gap_threshold = self.median_tool_duration_ms * self.ttl_extension_factor
        
        if self._is_in_tool_pause():
            # We're likely in a tool-call pause — extend TTL
            return False
        
        return True  # evict under normal LRU rules
    
    def _is_in_tool_pause(self) -> bool:
        """Detect if current pause matches expected tool-call duration."""
        if len(self.recent_calls) < 2:
            return False
        # Check if last inter-call gap matches tool-call duration pattern
        gaps = [self.recent_calls[i] - self.recent_calls[i-1] 
                for i in range(1, len(self.recent_calls))]
        avg_gap = sum(gaps) / len(gaps)
        return avg_gap > self.median_tool_duration_ms * 2
```

**2. Workflow-Aware Cache Prioritization (orchestration layer)**

Structure agent prompts so that the most cacheable prefix — the system prompt, task instructions, tool definitions — is semantically distinct from turn-specific context. TokenRouter (GouBuliya/TokenRouter, Apache 2.0) implements this by maximizing structural cache hits: it identifies which prompt segments are fixed across calls (system prompt, tool schemas) versus variable (user input, tool results) and routes requests to maximize cache reuse of fixed segments.

```python
def partition_for_cache_optimization(messages: list[dict]) -> dict:
    """Partition agentic messages into cacheable vs. per-turn segments."""
    fixed_segments = []
    variable_segments = []
    
    for msg in messages:
        if msg["role"] == "system":
            # System prompts are maximally cacheable — same across all calls
            fixed_segments.append(msg)
        elif msg["role"] == "assistant" and "tool_calls" not in msg:
            # Assistant reasoning that established the plan
            fixed_segments.append(msg)
        else:
            # Tool results, user inputs — unique per turn
            variable_segments.append(msg)
    
    return {
        "cacheable": fixed_segments,      # target 90%+ cache hit rate
        "per_turn": variable_segments,    # unavoidable cache miss
    }
```

**3. Disaggregated Prefix Preloading (infrastructure layer)**

Preload the KV state for fixed prompt segments (system instructions, tool schemas) into GPU memory at agent initialization. The "Continuum" approach uses checkpoint/restore semantics: when an agent enters a tool-call pause, checkpoint its KV state rather than letting LRU evict it. On resume, restore from checkpoint instead of recomputing from scratch.

```python
# Pseudocode: KV state checkpoint during tool-call pause
async def agent_loop_with_kv_checkpoint(agent, task):
    while not task.complete:
        # LLM inference step
        response = await llm.forward(agent.kv_state)
        
        if response.requires_tool_call():
            # Tool call incoming — checkpoint KV state before pause
            agent.checkpoint_kv_state()   # persist to CPU/NVMe
            
            result = await execute_tool(response.tool_call)
            
            # Resume from checkpoint, not cold start
            agent.restore_kv_state()       # ~10ms vs. ~2s full recompute
            agent.kv_state.append(result)
        else:
            task.complete = True
```

## Receipt

> Verified 2026-08-07 — Berkeley EECS-2026-234 "Continuum" (July 13, 2026) provides the quantitative basis: LRU eviction causes 40%+ throughput degradation in agentic tool-calling workloads vs. TTL-aware eviction. TokenRouter GitHub repo (4 stars, Apache 2.0, 2026-04-27) demonstrates structural cache optimization at the API gateway layer achieving up to 90% cache hit rates on fixed prompt segments. Redis token-budget-aware reasoning guide (Jeff Mills, 2026-07-28) confirms that KV cache optimization is now a first-class production concern alongside token budget management. The three-layer approach (TTL-aware eviction → workflow-aware prioritization → prefix preloading) is the current state of the art per the Berkeley paper's evaluation.

> Tradeoffs: KV checkpointing adds ~10ms per tool call (acceptable for long tool operations, problematic for sub-100ms calls). TTL extension requires tuning per workload — too aggressive and you OOM, too conservative and you get LRU behavior. TokenRouter's structural optimization requires request deduplication at the gateway level, which adds latency for the first call of each type.

## See also

- [S-1192 · The Five-Layer Caching Stack](stacks/s1192-the-five-layer-caching-stack-when-your-agent-pays-full-price-for-a-plan-it-already-ran.md) — Application-layer caching (semantic, tool-output, plan cache). Different layer, complementary.
- [S-1902 · The Disaggregated Inference Stack](stacks/s1902-the-disaggregated-inference-stack-when-your-agent-queue-stalls-because-one-prompt-poisoned-the-batch.md) — Inference engine architecture for agentic workloads. Adjacent concern.
- [S-1000 · The Context Exhaustion Stack](stacks/s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — Context window eviction policies. Covers application-layer context management; this entry covers inference-layer KV state.
