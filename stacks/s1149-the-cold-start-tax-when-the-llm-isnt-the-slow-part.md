# S-1149 · The Cold-Start Tax — When the LLM Isn't the Slow Part

You profile your agent's latency. The LLM call takes 800ms. You declare victory. Meanwhile, your users wait 90 seconds from request to first token — because the tool registry took 30 seconds to load, the vector store client took 20 seconds for its first connection, the prompt cache took 15 seconds to prime on a fresh container, and your framework took 10 seconds to validate every tool schema against a JSON schema validator loading on first use. The model was never the bottleneck. You were optimizing the wrong thing.

## Forces

- **The cold start is invisible in steady state.** Load tests against a warm pool look great. Dashboards plotted on the median look great. The people who notice are the users who hit the first request after a deploy, an autoscaling event, or a low-traffic stretch where everything got recycled.
- **Agent latency decomposes into far more components than the LLM call.** The tool registry load, the vector store client handshake, the prompt cache prime, the framework's first-use schema validation — each happens once per cold start, not once per request, making them invisible in aggregate statistics but catastrophic in tail latency.
- **Warm pools solve latency at the cost of idle compute.** Pre-warmed sandboxes cut cold start to near zero, but every idle sandbox burns money. The trade-off becomes acute at scale: 1,000 idle microVMs at $0.001/hr each is $240/month in zombie compute.
- **Sandbox cold start compounds with agent orchestration.** A planner-worker setup that spawns a new sandbox per sub-task multiplies the cold-start tax by the fan-out factor. A 5-subtask parallel plan with 2-second-per-sandbox overhead adds 10 seconds before the first tool call fires.
- **JSON schema validation is the hidden tax on tool-heavy agents.** A 40-tool MCP registry validated against a complex schema on every cold start can consume 10-15% of your total cold-start budget. This is invisible in p50 latency but dominant in p99.

## The move

**Profile before you optimize.** Instrument every component of your agent's initialization path. Separate cold-start latency from steady-state latency in your observability stack. Without this decomposition, you're guessing.

### The Agent Latency Decomposition

Agent latency is not one number — it is a stack of sequential and parallel phases:

```
Request → Orchestration Init (framework bootstrap, tool registry load)
        → Tool Client Init (vector store, MCP server handshake, SDK clients)
        → Prompt Cache Prime (fill cache with system prompt, retrieval context)
        → Schema Validation (tool schema validation on first use)
        → LLM Call N (first token)
        → Tool Calls (each with potential sub-warm or cold invoke)
        → Response Synthesis
```

The LLM call is typically the *fastest* phase in a cold-start scenario. The infrastructure phases are 10-50x slower than the model inference.

### Phase-Specific Mitigations

**Tool registry load → lazy-load + cache.** Load tools on-demand, not at startup. Cache the resolved tool schemas in a local LRU. A 40-tool registry loaded lazily on first use, instead of eagerly at startup, can save 10-30 seconds on cold start.

**Vector store client → connection pooling + warm-up.** Maintain a pool of pre-connected vector store clients. On cold start, borrow from the pool instead of opening a new connection. Verify connection health before lending — a stale connection is worse than a new one.

**Prompt cache prime → structured pre-fill.** Use the model's prompt caching API to pre-fill only the stable parts of the system prompt (instructions, tool schemas, retrieval context skeleton). Cache misses on the dynamic parts are fine — that's just normal inference. Cache misses on the static parts are pure waste.

**JSON schema validation → compile schemas, validate once.** First-use schema validation against complex schemas is expensive. Compile schemas to a normalized form on startup. Validate against the compiled form. For MCP registries with 40+ tools, this alone can eliminate 5-15% of cold-start overhead.

**Sandbox provisioning → snapshot-based resume.** For sandboxed tool execution (Python interpreter, shell tools), use microVM snapshots. Instead of booting a fresh VM per invocation, restore from a pre-booted snapshot. Platforms like E2B, Firecracker, and Modal support snapshot-based resume with sub-second restore times vs 10-30 second cold boots. This is the highest-impact lever for code-interpreter agents.

### The Warm Pool Sizing Problem

Warm pools solve cold start but introduce idle cost. Size them with a traffic-aware autoscaler:

```
Desired warm pool size = Peak QPS × Mean task duration × Safety factor
                       + Queue depth × Isolation budget
```

- **Peak QPS × Mean task duration**: the number of concurrent in-flight tasks at peak
- **Safety factor** (1.2-1.5×): absorbs burst traffic without cold-start spikes
- **Queue depth × Isolation budget**: if tasks can queue, the pool must absorb queue depth without spawning cold sandboxes

Monitor pool utilization. A pool running at <20% average utilization is a cost leak. A pool that's consistently at 100% (no warm instances available) means cold starts are happening under load — the pool is undersized.

### Steady-State vs. Cold-Start Observability

Standard APM tools give you LLM latency and throughput. They don't give you cold-start attribution. You need:

- **Cold-start flag on every span**: mark whether this request hit a warm or cold path
- **Phase breakdown per cold start**: instrumentation that isolates registry load, client init, cache prime, schema validation, and first LLM call as separate spans
- **p99 by cold/warm split**: if p99 is bad only on cold paths, your warm pool is undersized or your cold path has regressions
- **Deploy-triggered cold start detection**: auto-detect cold-start spikes following deploys or scaling events

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import SpanKind

tracer = trace.get_tracer(__name__)

async def agent_dispatch(request):
    ctx = get_or_create_sandbox_context(request.session_id)
    is_cold = ctx.is_cold_start

    with tracer.start_as_current_span("agent.init", kind=SpanKind.INTERNAL) as span:
        span.set_attribute("cold_start", is_cold)

        if is_cold:
            with tracer.start_as_current_span("init.tool_registry"):
                tool_registry = await ctx.load_tool_registry()
            with tracer.start_as_current_span("init.vector_client"):
                vs_client = await ctx.get_vector_client()  # pooled
            with tracer.start_as_current_span("init.prompt_cache_prime"):
                await ctx.prime_prompt_cache(system_prompt, retrieval_ctx)
            with tracer.start_as_current_span("init.schema_validation"):
                await ctx.validate_schemas(tool_registry)

        with tracer.start_as_current_span("agent.llm_call"):
            response = await llm.arun(prompt, tools=ctx.tools)

    return response
```

## Receipt

> Verified 2026-07-15 — Based on: Tian Pan, "The 90-Second Cold Start for Production Agents" (tianpan.co, May 2, 2026); Zylos Research "AI Agent Sandbox & Code Execution Isolation" (Feb 2026); AppScale Blog "Stateful AI Agent Sandbox Sessions: Pause, Resume & Snapshot" (June 27, 2026); Blaxel.ai "Keep AI Sandboxes Warm Without Paying for Idle Compute" (2026). Key data: 30s tool registry + 20s vector store + 15s cache prime + 10s schema validation = 75s non-LLM cold-start overhead confirmed from production telemetry. E2B/Firecracker snapshot restore: sub-second vs 10-30s cold boot. Token optimization research (unerr.dev, June 2026) confirms agents spend 76.1% of tokens on read-type operations — the cold-start problem compounds with every tool call that triggers a new sandbox.

## See also

- [S-245 · Agent Stack Stratification](s245-agent-stack-stratification.md) — the four layers this cold-start problem crosses
- [S-361 · Agent Stack Stratification: Sandboxing as Infrastructure](s361-agent-stack-stratification-sandboxing-infrastructure-prerequisite.md) — the sandbox provisioning layer
- [S-1013 · The Trace Replay Harness](s1013-the-trace-replay-harness-when-your-agent-breaks-in-production-and-you-cannot-reproduce-it.md) — tracing that would surface cold-start phases
