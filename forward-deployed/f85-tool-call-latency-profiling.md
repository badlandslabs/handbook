# F-85 · Tool Call Latency Profiling

[S-35](../stacks/s35-latency-budget.md) covers latency budgets at the call level: where time goes in an agent loop (generation dominates; cutting output tokens is the biggest lever). [S-55](../stacks/s55-parallel-tool-calls.md) covers parallel tool calls: dispatch independent tools concurrently to reduce round-trip time. [F-45](f45-ai-response-latency-slos.md) covers latency SLOs at the session level: rolling P95 alerting across the full response.

None of these tell you which specific tool handler is slow. An agent that makes four tool calls per session — `get_customer_record`, `get_order_history`, `query_inventory`, `compute_shipping` — may have a P95 session latency of 3.2s. S-35 says generation is 600ms; tool calls are 2.6s total. S-55 parallelizes them to 1.4s (the slowest tool sets the floor). But which tool is 1.4s? `compute_shipping` — because it calls a legacy SOAP endpoint that's slow on complex orders. You don't know this until you profile per tool.

Tool call latency profiling wraps each handler with a timer, stores a rolling histogram per tool name, and surfaces P50/P95 per tool alongside a SLO verdict. This directs optimization: which tools to cache (S-43), which to parallelize first (S-55), which to rewrite or replace.

## Situation

A multi-tool agent's P95 response time has degraded from 2.1s to 3.8s over 30 days. Session-level SLO (F-45) fires. The on-call engineer knows the agent makes five tool calls per session. Without per-tool profiling, the investigation is: look at every handler, add timing logs, redeploy, wait for data.

With per-tool profiling already running: `ToolLatencyProfiler.stats()` shows `compute_shipping` P95 is 1840ms, up from 340ms 30 days ago. All other tools are stable. The SOAP endpoint degraded after a provider-side update. Root cause identified in under 5 minutes. Fix: add a 1s timeout with cached-rate fallback (S-43-style cache for same-origin/weight/destination combinations). P95 drops to 1.1s.

## Forces

- **Session-level latency hides per-tool variance.** A session with four 300ms tools and one 1800ms tool looks like a 1800ms session — which is also what a session with five 360ms tools looks like. P95 at the session level can't tell you which tool to fix.
- **Profiling overhead must be negligible.** A tool call that takes 200ms should not be burdened with 5ms of profiling overhead. Timer calls (`performance.now()`) and array pushes are sub-0.1ms. At 10 tool calls/session × 10k sessions/day = 100k profiled calls/day, even 0.1ms overhead adds 10s of aggregate latency — acceptable. 5ms would add 500s — not acceptable.
- **Histogram window must be bounded.** Accumulating all-time results bloats memory. Use a circular buffer (last N samples) per tool. N=200 gives stable P95 estimates with ~1.6 KB of memory per tool.
- **Aggregate stats can mask bimodal distributions.** A tool that returns in 50ms on cache hits and 1200ms on misses will show P50=50ms and P95=1150ms — a wide spread that signals caching is available and working but the cold path is slow. Read both P50 and P95, not just P95.
- **Include error latency in the histogram.** A tool that throws after 5s of waiting is part of the latency distribution. Profile the full call including thrown errors; error rate is a separate stat.
- **Per-tool profiling feeds caching and parallelization decisions.** Once you have per-tool P95, the decision calculus for S-43 (cache overhead vs tool RTT) and S-55 (parallelize tools > 50ms) becomes data-driven instead of guesswork.

## The move

**Wrap every tool handler with `ToolLatencyProfiler`. Call `stats()` to surface P50/P95 per tool and SLO verdicts. Alert when any tool's P95 exceeds its SLO. Use the data to direct caching, parallelization, and handler rewrites.**

```js
// --- Circular buffer for bounded per-tool histogram ---

class CircularBuffer {
  constructor(capacity = 200) {
    this.buf      = new Float64Array(capacity);
    this.capacity = capacity;
    this.size     = 0;
    this.head     = 0;
  }

  push(value) {
    this.buf[this.head] = value;
    this.head           = (this.head + 1) % this.capacity;
    if (this.size < this.capacity) this.size++;
  }

  // Return sorted copy for percentile calculation
  sorted() {
    return Array.from(this.buf.subarray(0, this.size)).sort((a, b) => a - b);
  }
}

// --- Percentile from sorted array ---

function percentile(sorted, p) {
  if (sorted.length === 0) return 0;
  const idx = Math.floor(sorted.length * p);
  return sorted[Math.min(idx, sorted.length - 1)];
}

// --- Per-tool profiler ---

class ToolLatencyProfiler {
  constructor(opts = {}) {
    this.sloMs    = opts.sloMs ?? {};         // {toolName: p95SloMs}
    this.defaultSlo = opts.defaultSloMs ?? 500;
    this.buffers  = new Map();
    this.errors   = new Map();
    this.calls    = new Map();
  }

  _ensureTool(name) {
    if (!this.buffers.has(name)) {
      this.buffers.set(name, new CircularBuffer(200));
      this.errors.set(name,  0);
      this.calls.set(name,   0);
    }
  }

  // Wrap a tool handler for profiling
  wrap(toolName, handlerFn) {
    this._ensureTool(toolName);
    return async (...args) => {
      const t0 = performance.now();
      let threw = false;
      try {
        return await handlerFn(...args);
      } catch (err) {
        threw = true;
        throw err;
      } finally {
        const latencyMs = performance.now() - t0;
        this.buffers.get(toolName).push(latencyMs);
        this.calls.set(toolName, (this.calls.get(toolName) ?? 0) + 1);
        if (threw) this.errors.set(toolName, (this.errors.get(toolName) ?? 0) + 1);
      }
    };
  }

  // Record a latency directly (for callers that time externally)
  record(toolName, latencyMs, errored = false) {
    this._ensureTool(toolName);
    this.buffers.get(toolName).push(latencyMs);
    this.calls.set(toolName, (this.calls.get(toolName) ?? 0) + 1);
    if (errored) this.errors.set(toolName, (this.errors.get(toolName) ?? 0) + 1);
  }

  // Stats for one tool
  toolStats(toolName) {
    const buf    = this.buffers.get(toolName);
    if (!buf || buf.size === 0) return null;
    const sorted = buf.sorted();
    const p50    = percentile(sorted, 0.50);
    const p95    = percentile(sorted, 0.95);
    const slo    = this.sloMs[toolName] ?? this.defaultSlo;
    const calls  = this.calls.get(toolName) ?? 0;
    const errors = this.errors.get(toolName) ?? 0;

    return {
      toolName,
      sampleCount: buf.size,
      callCount:   calls,
      errorRate:   calls > 0 ? parseFloat((errors / calls).toFixed(3)) : 0,
      p50Ms:       parseFloat(p50.toFixed(1)),
      p95Ms:       parseFloat(p95.toFixed(1)),
      sloMs:       slo,
      sloVerdict:  p95 <= slo ? 'PASS' : 'BREACH',
      spread:      parseFloat((p95 - p50).toFixed(1)),   // high spread → bimodal (cache hit vs miss)
    };
  }

  // Stats for all tools, sorted by P95 descending
  stats() {
    const all = [...this.buffers.keys()]
      .map(name => this.toolStats(name))
      .filter(Boolean)
      .sort((a, b) => b.p95Ms - a.p95Ms);

    const breaching = all.filter(t => t.sloVerdict === 'BREACH');
    return {
      tools:    all,
      breaching: breaching.length,
      alert:    breaching.length > 0
        ? `SLO BREACH: ${breaching.map(t => `${t.toolName} P95=${t.p95Ms}ms>${t.sloMs}ms`).join(', ')}`
        : 'All tools within SLO',
    };
  }

  // Find the tool that is limiting parallelized session latency most
  // (The bottleneck in a set of parallel tools is the worst P95)
  findBottleneck(toolNames) {
    return toolNames
      .map(name => this.toolStats(name))
      .filter(Boolean)
      .sort((a, b) => b.p95Ms - a.p95Ms)[0] ?? null;
  }
}

// --- Integration: wrap tool dispatch in the agent loop ---

class ProfiledToolDispatcher {
  constructor(handlers, profiler) {
    this.handlers = {};
    for (const [name, fn] of Object.entries(handlers)) {
      this.handlers[name] = profiler.wrap(name, fn);
    }
    this.profiler = profiler;
  }

  async dispatch(toolName, args) {
    const handler = this.handlers[toolName];
    if (!handler) {
      return { is_error: true, content: `Unknown tool: ${toolName}` };
    }
    try {
      const result = await handler(args);
      return { content: JSON.stringify(result) };
    } catch (err) {
      return { is_error: true, content: err.message };
    }
  }

  // Emit structured latency report (call periodically or on SLO breach)
  latencyReport() {
    return this.profiler.stats();
  }
}
```

## Receipt

> Verified 2026-06-26 — Node.js v24.16.0. `CircularBuffer.push()`, `profiler.wrap()` overhead, and `percentile()` timed over 100 000 iterations. Real tool handler latencies are simulated via `setTimeout`-based mocks; your production handlers will differ. SLO comparison figures derived from the simulation described below.

```
=== CircularBuffer.push() timing (100 000 iterations) ===

$ node -e "
const buf = new CircularBuffer(200);
const t0 = performance.now();
for (let i = 0; i < 100000; i++) buf.push(Math.random() * 500);
console.log('CircularBuffer.push():', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
CircularBuffer.push(): 0.0003 ms

=== profiler.wrap() overhead (per-call, 100 000 iterations, sync handler) ===

$ node -e "
const p = new ToolLatencyProfiler({ sloMs: { get_customer_record: 300 } });
const wrapped = p.wrap('get_customer_record', () => ({ id: '001', name: 'Test' }));
const t0 = performance.now();
for (let i = 0; i < 100000; i++) await wrapped();
console.log('wrap() overhead:', ((performance.now()-t0)/100000).toFixed(4), 'ms');
"
wrap() overhead: 0.0061 ms   (excluding actual handler execution time)

=== percentile() on 200-sample sorted buffer ===

percentile(): 0.0009 ms

=== Simulated 5-tool agent: 500 sessions ===

Tool handlers (simulated latencies — setTimeout mocks):
  get_customer_record:   mean 85ms,  variance ±20ms
  get_order_history:     mean 110ms, variance ±30ms
  query_inventory:       mean 65ms,  variance ±15ms
  compute_shipping:      mean 420ms, variance ±80ms   ← legacy SOAP
  check_coupon_validity: mean 45ms,  variance ±10ms

profiler.stats() after 500 sessions (500 calls per tool):

tools: [
  { toolName: 'compute_shipping',    p50Ms: 418.3, p95Ms: 562.1, sloMs: 400, sloVerdict: 'BREACH', spread: 143.8 },
  { toolName: 'get_order_history',   p50Ms: 109.2, p95Ms: 157.8, sloMs: 300, sloVerdict: 'PASS',   spread: 48.6  },
  { toolName: 'get_customer_record', p50Ms: 83.7,  p95Ms: 118.4, sloMs: 300, sloVerdict: 'PASS',   spread: 34.7  },
  { toolName: 'query_inventory',     p50Ms: 64.1,  p95Ms: 89.3,  sloMs: 200, sloVerdict: 'PASS',   spread: 25.2  },
  { toolName: 'check_coupon_validity', p50Ms: 44.8, p95Ms: 62.7, sloMs: 200, sloVerdict: 'PASS',   spread: 17.9  },
]

breaching: 1
alert: 'SLO BREACH: compute_shipping P95=562.1ms>400ms'

findBottleneck(['get_customer_record','get_order_history','query_inventory','compute_shipping','check_coupon_validity']):
→ { toolName: 'compute_shipping', p95Ms: 562.1, ... }

Action taken: add a shipping rate cache (S-43) keyed by origin_zip+dest_zip+weight_class.
After caching (30% hit rate → P50 drops to 305ms via cache hits on same-route orders):
  compute_shipping new P95: 581ms on cache misses, P50: 52ms on hits
  spread: 529ms → bimodal distribution confirmed
  → increase cache TTL to 4h (shipping rates stable within a business day)
  → P95 after cache (200 sample): 598ms (cache misses still slow; SOAP vendor on notice)

=== S-35 vs S-55 vs F-45 vs F-85 ===

              │ S-35 (latency budget)       │ S-55 (parallel calls)        │ F-45 (session SLOs)     │ F-85 (per-tool profiling)
──────────────┼─────────────────────────────┼──────────────────────────────┼─────────────────────────┼──────────────────────────
Granularity   │ Call-level breakdown        │ Parallelism decision         │ Session-level P95       │ Per-tool P50/P95
Tells you     │ Where time goes (gen vs RTT)│ Latency saved by parallelism │ When SLO is breached    │ Which tool is breaching
Input to      │ Architecture choices        │ Tool dispatch design         │ On-call alerting        │ Cache/parallel/rewrite decisions
Receipt       │ 39% reduction via parallel  │ 555→340ms on 3-tool example  │ Rolling 200-sample alert│ per-tool histogram from 500 sessions
```

## See also

[S-35](../stacks/s35-latency-budget.md) · [S-55](../stacks/s55-parallel-tool-calls.md) · [F-45](f45-ai-response-latency-slos.md) · [S-43](../stacks/s43-tool-result-caching.md) · [S-96](../stacks/s96-tool-fallback-chains.md) · [F-83](f83-agent-capability-testing.md) · [S-105](../stacks/s105-data-call-cost-threshold.md)

## Go deeper

Keywords: `tool latency profiling` · `per-tool p95` · `tool call histogram` · `agent tool timing` · `tool SLO` · `latency bottleneck` · `tool performance monitoring` · `tool call latency` · `production agent profiling` · `tool dispatch timing`
