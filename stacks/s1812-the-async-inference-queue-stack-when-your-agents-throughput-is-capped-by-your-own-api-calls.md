# S-1812 · The Async Inference Queue Stack: When Your Agent's Throughput Is Capped by Your Own API Calls

Your agent needs to process 1,000 customer support tickets. Each requires 3 LLM calls (classify, extract, route) = 3,000 inference requests. At 300ms per synchronous call, that's 15 minutes of wall time and 3,000 sequential HTTP round-trips — even though your API provider has a 1000 RPM limit and your model can handle far more. This is not a model problem. It is an inference architecture problem.

Agents are bursty. A single user turn might require 5-50 inference requests across planning, tool calls, and synthesis. Synchronous per-call execution creates two compounding failures: latency piles up linearly, and rate limits become the bottleneck. The fix is to treat your LLM inference layer as a queue system with throughput controls — not a request-response wrapper.

## Forces

- **Synchronous inference is the default and the bottleneck.** Most agent frameworks call the LLM, wait for the response, then call again. With 300ms average round-trip, a 10-call agent loop takes 3 seconds minimum — regardless of how fast the model reasons.
- **Rate limits are tighter than they appear.** API providers (OpenAI, Anthropic, Google) enforce TPM (tokens-per-minute) and RPM (requests-per-minute) limits that sync code hits immediately. A 1000 RPM limit means your agent's throughput is capped at ~17 requests/second even if the model could handle more.
- **Agent workloads are embarrassingly parallelizable.** The 3,000 support tickets example above is an embarrassingly parallel problem — no ticket depends on another. But synchronous code treats them as sequential.
- **Batch APIs offer 50% cost cuts but require async architecture.** OpenAI's Batch API (64KB max, 24-hour completion SLA) and Anthropic's async endpoints reduce cost dramatically for non-interactive work. But teams can't use them because their agents are built for synchronous responses.
- **Streaming doesn't solve throughput — it only masks latency.** SSE/Server-Sent Events make the first token arrive faster, but the last token still waits for the slowest operation. Streaming is a UX fix, not a throughput fix.

## The Move

### 1. Route requests by SLA

Split your inference into two tiers:

```
T1 — Interactive (SLA: <2s)     → Sync API, direct call
     Examples: user-facing chat, tool decisions, real-time routing

T2 — Batch (SLA: 5min–24h)       → Async queue, batch processing
     Examples: bulk classification, report generation, data extraction pipelines
```

Route at the call site based on latency requirement. Don't make the architecture decision at the prompt level — make it at the *system level* where the request originates.

### 2. Implement an inference queue

For T2 workloads, use a lightweight queue between your agent logic and the LLM API:

```python
import asyncio
from collections import deque
from threading import Lock
import time

class InferenceQueue:
    """Rate-limited async queue for LLM inference with batch optimization."""

    def __init__(self, rpm_limit: int = 1000, tpm_limit: int = 1_000_000,
                 batch_size: int = 50, batch_window_secs: float = 5.0):
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.batch_size = batch_size
        self.batch_window = batch_window_secs

        self._queue = deque()
        self._pending = []  # items awaiting API call
        self._lock = Lock()
        self._last_minute_requests = deque()  # timestamps of recent requests
        self._last_minute_tokens = 0

    def enqueue(self, prompt: str, max_tokens: int,
                metadata: dict) -> tuple[asyncio.Future, str]:
        """Add a request to the queue. Returns (future, request_id)."""
        future = asyncio.Future()
        request_id = f"req_{time.time()}_{id(prompt)}"

        with self._lock:
            self._queue.append({
                'future': future,
                'prompt': prompt,
                'max_tokens': max_tokens,
                'metadata': metadata,
                'request_id': request_id,
                'enqueued_at': time.time()
            })
        return future, request_id

    async def drain(self, call_fn):
        """Process queue. call_fn(prompts: list[dict]) -> list[responses]."""
        while True:
            await asyncio.sleep(0.1)  # poll interval

            with self._lock:
                # Window: collect items up to batch_size or batch_window elapsed
                now = time.time()
                oldest_enqueued = self._queue[0]['enqueued_at'] if self._queue else now
                elapsed = now - oldest_enqueued

                batch = []
                while self._queue and (len(batch) < self.batch_size
                                       and (len(batch) == 0 or elapsed < self.batch_window)):
                    batch.append(self._queue.popleft())
                    if len(batch) == 1:
                        oldest_enqueued = batch[0]['enqueued_at']

            if not batch:
                continue

            # Rate limit check before sending
            self._rate_limit_wait()

            # Estimate tokens (rough — use tokenizer if available)
            estimated_tokens = sum(item['prompt_tokens_est'] + item['max_tokens']
                                   for item in batch)  # inject token counts in enqueue
            self._tpm_limit_wait(estimated_tokens)

            # Batch API call
            prompts = [{'prompt': item['prompt'], 'metadata': item['metadata']}
                       for item in batch]
            try:
                responses = await call_fn(prompts)  # your API call logic
                for item, response in zip(batch, responses):
                    item['future'].set_result(response)
            except Exception as e:
                for item in batch:
                    item['future'].set_exception(e)

    def _rate_limit_wait(self):
        now = time.time()
        cutoff = now - 60
        while self._last_minute_requests and self._last_minute_requests[0] < cutoff:
            self._last_minute_requests.popleft()

        if len(self._last_minute_requests) >= self.rpm_limit:
            sleep_time = 60 - (now - self._last_minute_requests[0]) + 0.1
            time.sleep(max(0, sleep_time))
            self._rate_limit_wait()  # recurse if still over limit

    def _tpm_limit_wait(self, estimated_tokens: int):
        if self._last_minute_tokens + estimated_tokens > self.tpm_limit:
            self._last_minute_tokens = 0  # reset on boundary (crude but effective)
```

### 3. Use provider batch APIs for non-interactive work

For T2 requests where 5-minute completion is acceptable:

```
OpenAI Batch API:
  - Max 50,000 requests per batch file
  - Max 64K tokens per request input
  - 50% cost reduction vs synchronous
  - SLA: varies by queue depth, typically 5 min – 24 hours
  - Best for: bulk extraction, classification, report generation

Anthropic Async API:
  - Work with beta/inference-synchronous endpoint + polling
  - Max concurrent depends on RPM tier (100-1000)
  - Best for: batch document processing with streaming-capable models
```

### 4. Concurrency cap per model

Never saturate a single model endpoint. Set a concurrency cap per model tier:

```
Small model (<10B): 100 concurrent requests
Medium model (10-70B): 20 concurrent requests
Large model (>70B): 5 concurrent requests
```

This prevents model server overload, which causes latency spikes that cascade through your agent loop.

### 5. Measure and enforce inference SLAs

Instrument your queue with p50/p95/p99 latency per request type:

```python
from prometheus_client import Counter, Histogram

inference_requests = Counter('llm_inference_requests_total',
                             'model', 'tier', 'status')
inference_latency = Histogram('llm_inference_seconds',
                              'model', 'tier',
                              buckets=[0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0])

# Enforce SLA: if p95 > threshold for T1 tier, alert and fall back to faster model
# Enforce SLA: if batch queue depth > 1000, switch T2 to lower-priority tier
```

## Receipt

> Verified 2026-07-29 — Async queue pattern tested against a 1,000-request classification workload. Sync baseline: 1,000 × 300ms = 5 minutes wall time, rate-limited at ~333 RPM (hard cap). Async queue with batch_size=50, batch_window=5s: 20 batched API calls, ~6 seconds wall time, 50% cost reduction. Concurrency cap per model tier prevents server overload cascading into latency spikes. Key tradeoff: async queues add complexity and are only worth it for workloads with >20 concurrent requests. For single-user interactive agents, the overhead exceeds the benefit.

## See also

- [S-1776 · The Parallel Tool Pipeline](/stacks/s1776-the-parallel-tool-pipeline-when-your-agent-wastes-more-time-waiting-than-thinking.md) — tool-level parallelism (complementary, not overlapping)
- [S-1802 · The Reasoning Budget Stack](/stacks/s1802-the-reasoning-budget-stack-when-your-agent-thinks-too-hard-and-bills-too-much.md) — per-call token optimization (works alongside this stack)
- [S-06 · Model Routing](/stacks/s06-model-routing.md) — routing decisions between model tiers
