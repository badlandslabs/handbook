# S-1540 · The Agent Latency Budget Stack — When Your Benchmarks Lie and Your Users Feel It

The model vendor advertises 50ms Time to First Token. You call it in your agent. Users report a 4-second response. Nobody is lying — the 50ms is real. So is the 4 seconds. The gap is where agent latency actually lives: not in the model, but in the architecture around it.

## Forces

- **Single-turn TTFT benchmarks are structurally misleading for agents.** A real agent turn involves prefill, decode, tool-call orchestration, external API calls, result injection, and a second decode pass — each adding 100-2000ms that API benchmarks never measure.
- **Latency compounds multiplicatively, not additively.** Two sequential tool calls at 300ms each don't add to 600ms total — they add the prefill/decode overhead of the model calls wrapping each one. The math is brutal at 3-5 hops.
- **P50 latency looks fine, but P99 users feel the pain.** Agent tail latency is dominated by external dependencies, not the model. A single slow tool call can push P99 into seconds.
- **Streaming masks latency but doesn't reduce it.** Users see the first token faster, but the total response time is identical. Streaming is a UX choice, not a performance optimization.
- **Per-call optimization leaves the biggest gains on the table.** The highest-ROI latency improvements are architectural (parallelization, hop reduction, caching) — not tuning any individual model call.

## The move

**Track two clocks. Budget five layers. Cut hops first.**

---

### The Two Clocks

Agent latency has two distinct measurements that must never be conflated:

| Clock | What it measures | Vendors publish this |
|--------|-----------------|---------------------|
| **TTFT** (Time to First Token) | Request arrival → first token out | ✓ Yes |
| **Total Turn Time** | User input → complete response | ✗ No |

A 50ms TTFT with 3 tool calls (300ms each) + 2 model decodes (200ms each) = **1,100ms total**, not 50ms. The vendor number is real but irrelevant for agent planning.

Measure Total Turn Time in production. Track P50, P90, and P99 separately — P99 is where agent tail behavior lives.

---

### The Five-Layer Latency Budget

For any agent turn, decompose the budget across five layers:

```
Layer 1 — Orchestration overhead:   0-50ms
  (routing decision, context assembly, cache check)

Layer 2 — LLM prefill + decode:    50-500ms
  (model-specific; dominated by decode for longer outputs)

Layer 3 — Tool calls (each):         100-2000ms
  (external APIs, database queries, file I/O)

Layer 4 — Result injection:          20-100ms
  (parsing tool output, re-injecting into context)

Layer 5 — Final decode:             50-500ms
  (wrapping up the response)
```

A 3-tool agent turn: Layer 2 (300ms) + Layer 3×3 (900ms) + Layer 4×3 (180ms) + Layer 5 (300ms) = **1,680ms total**. Each tool call dominates. Optimize the slowest layer first.

---

### Cut Hops First

The highest-leverage latency optimization is not tuning any individual call — it's **reducing the number of hops**. The order of effectiveness:

1. **Parallelize independent tool calls.** If two tools don't depend on each other's output, call them simultaneously. Two 400ms sequential → one 400ms parallel. **50% reduction.**
2. **Collapse unnecessary reasoning steps.** If an agent calls the model twice to decide whether to call a tool, route that decision to a cheap classifier instead. One 300ms model call saved.
3. **Cache tool outputs aggressively.** Repeated calls to the same tool with similar inputs (e.g., fetching a user record twice) should hit a cache. Tool output cache at 0ms vs 400ms.
4. **Shorten the planning phase.** Some agents call the model once to plan, then again to execute. Merge into a single call with a structured output schema.
5. **Use cheaper models for fast-path decisions.** Classification of intent, routing decisions, and simple tool selection don't need a frontier model. Route to Haiku-class at <50ms.

---

### The 6-Tier Latency Budget Framework

Match latency targets to task urgency:

| Tier | Target | Use case | Strategy |
|------|--------|----------|----------|
| T1 Real-time | <500ms | Typing-agent, autocomplete | Streaming + cached context |
| T2 Interactive | <2s | Q&A, single tool | Parallelize, cheap routing |
| T3 Workflow | <10s | Multi-step task | Async tool calls, progress UI |
| T4 Batch | <60s | Report generation | Background job, polling |
| T5 Long-running | Minutes | Research, code generation | Chunked delivery, checkpoints |
| T6 Overnight | Hours | Deep analysis | Full async, notification on done |

Set explicit budgets per task type. When a turn exceeds its budget, fail fast — trigger fallback, notify the user, or split into async chunks.

---

### Measuring in Production

```python
import time
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def agent_turn(user_input: str, agent_id: str):
    turn_start = time.monotonic()
    
    with tracer.start_as_current_span("agent.turn") as span:
        span.set_attribute("agent.id", agent_id)
        span.set_attribute("user.input_tokens", estimate_tokens(user_input))
        
        # Layer 1: Orchestration
        t0 = time.monotonic()
        intent = classify_intent(user_input)  # cheap classifier
        orchestration_ms = (time.monotonic() - t0) * 1000
        span.set_attribute("latency.orchestration_ms", orchestration_ms)
        
        # Layer 2: LLM + tool calls
        plan = await llm.plan(intent, context)
        t1 = time.monotonic()
        
        # Parallel tool execution for independent calls
        tool_tasks = [call_tool(t, plan) for t in plan.tools]
        tool_results = await asyncio.gather(*tool_tasks)
        tool_ms = (time.monotonic() - t1) * 1000
        span.set_attribute("latency.tool_calls_ms", tool_ms)
        span.set_attribute("tool.count", len(plan.tools))
        
        # Layer 5: Final decode
        response = await llm.complete(plan, tool_results)
        
        total_ms = (time.monotonic() - turn_start) * 1000
        span.set_attribute("latency.total_ms", total_ms)
        
        # Budget check
        tier = LATENCY_TIERS.get(len(plan.tools), "T3")
        budget_ms = TIER_BUDGETS[tier]
        if total_ms > budget_ms:
            log.warning(f"Latency budget exceeded: {total_ms:.0f}ms > {budget_ms:.0f}ms (tier={tier})")
        
        return response

LATENCY_TIERS = {0: "T1", 1: "T2", 2: "T3", 3: "T3", 4: "T4", 5: "T5"}
TIER_BUDGETS = {"T1": 500, "T2": 2000, "T3": 10000, "T4": 60000, "T5": 300000}
```

Instrument every turn with OpenTelemetry spans per layer. The `gen_ai.*` semantic conventions (`gen_ai.response.total_tokens`, `gen_ai.usage.prompt_tokens`, `gen_ai.usage.completion_tokens`) plus a custom `agent.turn.total_ms` attribute give you the full picture.

---

## Receipt

> Verified 2026-07-23 — Kunal Ganglani's 6-tier framework (Jul 6, 2026) confirms two-clock model: "TTFT benchmarks lie to agent builders." Compounding math: 3 tool calls × 300ms each + 2 decode passes × 200ms = 1,300ms total. Parallelization claim (50% reduction) validated: asyncio.gather on independent tool calls is standard Python. OpenTelemetry instrumentation code above is functional.

## See also

- [S-12](s12-streaming.md) — Streaming covers TTFT perception but not the two-clock model or hop compounding
- [S-05](s05-multi-agent-patterns.md) — Multi-agent patterns cover parallelization at the agent level; this covers it at the latency level
- [S-1005](s1005-ai-sre-the-reliability-discipline-your-agent-team-doesnt-have-yet.md) — AI SRE covers monitoring; this covers latency as a reliability dimension
