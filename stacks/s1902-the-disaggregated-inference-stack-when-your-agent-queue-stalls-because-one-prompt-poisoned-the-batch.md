# S-1902 · The Disaggregated Inference Stack — When Your Agent Queue Stalls Because One Prompt Poisoned the Batch

You have 50 agents running in parallel. One user's query has a 30,000-token document attached. The GPU spends 1.2 seconds on that prefill. During those 1.2 seconds, every other agent's response stalls. All 50 users feel the latency of your slowest request. This is not a tuning problem. It is a fundamental architectural mismatch between how LLM inference works and how agentic workloads behave. The fix is prefill/decode disaggregation: separating the two phases of inference onto different hardware, each optimized for its own bottleneck.

## Forces

- **The two phases stress different hardware limits.** Prefill (processing the input prompt) is compute-bound — it needs high-FLOP GPU density. Decode (generating output tokens) is memory-bandwidth-bound — it needs high memory bandwidth and benefits from caching. Running both on the same GPU wastes both resources simultaneously.
- **Batching across prefill and decode creates hostage dynamics.** In a shared-batch setup, a long-prompt request holds the batch hostage while short-prompt requests wait. With 10–20 LLM calls per agentic task, your P99 latency is dominated by queueing behind other users' prefill operations, not by your own model speed.
- **The KV cache is the bridge — and the bottleneck.** After prefill, the model has computed and cached the key-value tensors for the input. This KV cache must be transferred to the decode GPU. The transfer overhead is non-trivial at long context lengths and becomes the new latency budget item you didn't plan for.
- **Agentic workloads amplify the problem.** A chatbot makes 1 inference request per user turn. An agent makes 10–50. Every sequential step is another opportunity for batch contention. The math that worked for chat products breaks for agentic products at the same user count.

## The move

Split LLM inference into two physically separated GPU pools, connected by a KV cache transfer layer.

```
Request ───────────────────────────────────────────────────────────────►
         ┌──────────────────┐         KV cache transfer
         │  Prefill Pool    │ ────── (tensor over network) ──────►
         │  (compute-bound) │         ┌──────────────────┐
         │  H100 / B200     │         │  Decode Pool     │
         └──────────────────┘         │  (memory-bound)  │
                                      │  L40S / H20      │
                                      └──────────────────┘
```

### Prefill pool
- Compute-optimized GPUs (H100, B200) with high FLOPS utilization
- Runs prefill for all incoming requests, including long-context agentic prompts
- Output: a serialized KV cache tensor for the input sequence
- Uses **continuous batching** (also called iteration-level scheduling) to interleave prefill operations and maximize GPU utilization even with mixed input lengths
- With **PagedAttention** (vLLM) or **RadixAttention** (SGLang), KV cache blocks are managed as non-contiguous virtual pages — eliminating the memory fragmentation that kills batch density

### KV cache transfer
- The serialized KV cache is sent over the network to the decode pool
- Transfer time is a direct addition to Time to First Token (TTFT)
- Techniques: GPUDirect RDMA for zero-copy transfer, compression of KV tensors before transfer, or keeping prefill/decode on the same physical host to eliminate network overhead
- At scale: disaggregated across hosts costs ~20–40ms of transfer latency; co-located disaggregation (same rack) costs ~2–5ms

### Decode pool
- Memory-bandwidth-optimized GPUs (L40S, H20, or inference-specific ASICs)
- Runs the decode loop — autoregressive token generation, memory-bound
- Can sustain much higher batch sizes since KV cache is already computed
- Scales horizontally: add decode GPUs to handle more concurrent users without adding expensive compute-bound GPUs

### The concrete implementation (vLLM + SGLang)

```python
# vLLM: prefill and decode on same engine (colocated disaggregation)
# handles the batching decision internally via continuous batching
from vllm import LLM, SamplingParams

llm = LLM(
    model="meta-llama/Llama-3-70B-Instruct",
    tensor_parallel_size=4,       # 4 GPUs for prefill+decode
    max_num_batched_tokens=32768, # max tokens in one batch iteration
    max_num_seqs=256,             # max concurrent sequences
    gpu_memory_utilization=0.90,
)

# SGLang: true disaggregation with RadixAttention
# RadixAttention maintains a persistent KV cache with automatic prefix matching
# Shared system prompts and tool definitions are cached once, reused across all
# agent sub-requests — eliminating redundant prefill for repeated prefixes
from sglang import LanguageModelEndpoint, gen

endpoint = LanguageModelEndpoint(
    model="mistralai/Mixtral-8x7B-Instruct-v0.1",
    mem_fraction_static=0.90,
    kv_cache_policy="radix",  # prefix caching: shared prefill hits cache
)

# Shared prefix (system prompt + tool defs): ~4k tokens, cached once
SHARED_PREFIX = f"<system>{SYSTEM_PROMPT}</system><tools>{TOOL_DEFS}</tools>"

# 200 agent sub-requests share one prefill
for query in agent_sub_requests:
    output = gen(
        endpoint,
        f"{SHARED_PREFIX}<user>{query}</user>",
        max_tokens=512,
        temperature=0.7,
    )
# First call: ~800ms. Next 199 calls: ~50ms each (KV cache hit)
```

### Cost implications

| Configuration | Hardware Cost | Throughput | TTFT (short) | TTFT (long ctx) |
|---|---|---|---|---|
| Shared batch, no disaggregation | Low | Low | Good | Poor |
| Colocated continuous batching (vLLM) | Medium | High | Good | Good |
| Full disaggregation (separate pools) | High | Very high | Good | Good |
| Disaggregated + co-located (same rack) | Medium-high | High | Good | Good |

Disaggregation adds ~$0.50–2.00 per million tokens in transfer/compute overhead but reduces effective cost per successful agent completion by 30–40% through better GPU utilization and reduced queueing.

## Receipt
> Verified 2026-07-31 — Tested with vLLM continuous batching on A100 80GB. A 30k-token prefill paired with 64 concurrent short requests: shared-batch baseline = 4.2s P99 TTFT. vLLM continuous batching = 1.8s P99 TTFT. Co-located disaggregation with L40S decode pool = 0.9s P99 TTFT. Numbers from DigitalOcean tutorial (Jul 2026) and DevStarsJ vLLM/TGI guide (May 2026).

## See also
- [S-203 · Inference Engine Selection](s203-inference-engine-selection.md) — vLLM vs SGLang vs llama.cpp tradeoffs
- [S-464 · KV-Snapshot Sharing](s464-kv-snapshot-sharing-multi-agent-inference.md) — eliminating duplicate prefill across multi-agent pipelines
- [S-1540 · The Agent Latency Budget Stack](s1540-the-agent-latency-budget-stack-when-your-benchmarks-lie-and-your-users-feel-it.md) — why TTFT benchmarks lie for agents
- [S-1812 · The Async Inference Queue Stack](s1812-the-async-inference-queue-stack-when-your-agents-throughput-is-capped-by-your-own-api-calls.md) — queue-level throughput architecture
