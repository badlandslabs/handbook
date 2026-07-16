# S-1168 · The Append-Only Cost Ledger — When You Can't Tell Who Spent What in Your Agent Fleet

When your agent fleet generates a $40K monthly bill and you can't attribute a single dollar to a team, a tenant, or a task — you have an Agent FinOps problem. Controlling cost is not the same as accounting for it. Budget caps (S-791) stop overspend; cost attribution explains where it went and why. In autonomous fleets where agents spawn, delegate, and re-delegate work, traditional cloud billing tags don't reach the right granularity. You need an append-only cost ledger: every token, model call, and GPU cycle traced to its originating agent, tenant, task, and tool at the span level.

## Forces

- **Token layers compound invisibly.** A single agent turn consumes prompt tokens, tool-output tokens (often 5,000–50,000 chars returned from `file_read`), memory tokens, and completion tokens. Aggregating into a single input/output bucket hides the actual cost driver — almost always tool output, not the prompt.
- **Agent delegation severs billing context.** When Agent A spawns Agent B, the cost accrues to A's infrastructure budget. Without explicit trace propagation, the ledger shows one blob of spend with no owner.
- **Retroactive tagging misses everything.** Attaching billing tags to API responses in post-processing never captures tool-call costs, intermediate LLM calls, or memory compaction operations. The data simply isn't there to tag.
- **Cache accounting breaks naive math.** Prompt caching (S-08) means identical context chunks cost different amounts across calls. A `total_tokens × list_price` calculation over-reports spend by 40%+ on cache-heavy workloads.
- **Multi-tenant fleets need chargeback, not just monitoring.** Shared infrastructure serving 50 tenants requires per-tenant cost attribution as an engineering primitive, not a monthly reconciliation exercise.

## The move

### 1. Instrument at request creation, not log parsing

Attach all attribution dimensions at span creation time — before the LLM call happens:

```python
span = tracer.start_span("llm inference")
span.set_attribute("agent.id", agent_context.agent_id)
span.set_attribute("tenant.id", agent_context.tenant_id)
span.set_attribute("task.id", task_id)
span.set_attribute("model.name", model_name)
span.set_attribute("prompt.version", prompt_version)
# Cost is estimated before the call, confirmed after
span.set_attribute("token.estimate.prompt", estimated_prompt_tokens)
span.set_attribute("token.estimate.cache_write", cache_write_tokens)
```

Retroactive attribution from parsed logs always misses tool-call overhead and intermediate calls. The ledger is only as honest as its instrumentation.

### 2. Separate four token layers

| Layer | Source | Why it matters |
|-------|--------|----------------|
| **Prompt tokens** | User input + system prompt | First-pass cost; directly optimizable via compression |
| **Tool tokens** | Tool definitions + tool output | Often 10–50× the prompt. The hidden cost driver. |
| **Memory tokens** | Conversation history, retrieved context | Grows superlinearly (S-09). Compaction changes this layer mid-session. |
| **Response tokens** | Model completion | 3–5× more expensive per token than input across all providers. |

Tag each layer separately. Aggregate into `total_tokens` only for billing reconciliation — never for optimization decisions.

### 3. Build an append-only cost event schema

```python
@dataclass
class CostEvent:
    event_id: str           # UUID — idempotency key
    trace_id: str           # W3C traceparent for cross-agent correlation
    agent_id: str           # Originating agent (not parent span's agent if delegated)
    tenant_id: str          # Multi-tenant isolation key
    task_id: str            # Business-level task (for ROI analysis)
    model: str              # e.g. "claude-sonnet-4-20250514"
    layer: str              # "prompt" | "tool_output" | "memory" | "response"
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int   # Cache hit — cheaper
    cache_write_tokens: int  # Cache miss — written to cache
    latency_ms: int
    timestamp: datetime     # UTC — append-only, never updated
    release_bundle: dict     # {"prompt_version": "...", "model_version": "...", "tool_manifest_version": "..."}
```

Append-only: never UPDATE cost events, only INSERT new correction events. This preserves audit trail integrity for regulatory chargeback (EU AI Act Article 12 requires traceability).

### 4. Propagate cost context through agent delegation

When Agent A delegates to Agent B, inject the cost context into the A2A message, not just the W3C traceparent:

```json
{
  "a2a_task_delegation": {
    "delegator_agent_id": "agent-alpha-prod",
    "tenant_id": "tenant-acme",
    "task_id": "task-abc-123",
    "cost_context": {
      "budget_remaining": 0.0034,
      "cost_ceiling_usd": 0.01,
      "attribution_tags": {"product_line": "enterprise", "region": "us-east"}
    }
  }
}
```

This ensures the cost ledger shows `agent-alpha-prod → agent-beta-1` handoff with proper tenant attribution, not anonymous compute.

### 5. Per-tool-call cost granularity

Tool calls are where most agent spend actually happens. Instrument at the tool invocation level:

```python
async def tracked_tool_call(tool_name: str, agent_id: str, tenant_id: str, task_id: str):
    span = tracer.start_span(f"tool.{tool_name}")
    span.set_attribute("tool.name", tool_name)
    span.set_attribute("agent.id", agent_id)
    span.set_attribute("tenant.id", tenant_id)
    # ... then execute
```

Aggregate tool costs by `tool.name` to surface the "expensive tools" — usually `file_read`, `web_search`, or `code_execute` returning large payloads.

### 6. Detect noisy agents with burn-rate scoring

Not all overspend is configuration error. Some agents loop, some produce redundant tool calls, some retrieve unnecessarily large documents. Compute a burn-rate score per agent:

```
burn_rate = (total_cost_usd / task_count) / median_agent_burn_rate
```

Agents with `burn_rate > 2σ` above the fleet median are flagged as noisy. Common causes: excessive tool-output passthrough (reading 50K-token files and dumping them into context), redundant sub-agent spawning, and missing context windows that cause repeated retrieval.

### 7. Version your cost model

LLM pricing changes. Model version changes. Cache pricing changes. A cost figure recorded in January is not comparable to one recorded in July without version context:

```python
@dataclass
class CostModelVersion:
    version: str               # "gcp-2026-q2"
    effective_date: date
    input_price_per_1m: float
    output_price_per_1m: float
    cache_read_discount: float  # e.g. 0.10 = 90% off
    models: dict               # model_name -> pricing_tier
```

Record `cost_model_version` on every cost event. Reconcile historical figures against the current model for accurate trend analysis.

## Receipt

> Verified 2026-07-15 — Research conducted via Digital Applied (April 14, 2026), AppScale (June 7, 2026), DoiT/Attribute acquisition analysis (July 2026), AgentMarketCap (April 2026), Braintrust (2026). DoiT research: 80% of enterprises had AI cost overruns in the past year. Organizations with the most sophisticated governance had the highest overrun rates — indicating that naive instrumentation over-reports without proper attribution. Digital Applied: naive `total_tokens × list_price` over-reports by 40%+ on cache-heavy workloads. AgentMarketCap: input token prices dropped 85% since GPT-4 (~$30/M → <$3/M); output tokens remain 3–5× more expensive, making response-token optimization the primary cost lever. No existing handbook entry covers per-agent/per-tenant cost attribution — S-791 covers budget enforcement, S-99 covers task economics, but neither covers trace-level cost accounting with chargeback.

## See also

- [S-791 · Agent Token Budget Enforcement](s791-the-agent-token-budget-enforcement-stack-when-your-agent-runs-all-night-and-the-bill-runs-all-month.md) — enforcing cost ceilings
- [S-99 · Agent Task Economics](s99-agent-task-economics.md) — cost control levers
- [S-1166 · Cross-Agent Trace Fragmentation](s1166-the-cross-agent-trace-fragmentation-problem-when-every-agent-traces-itself-but-nobody-traces-the-handoff.md) — W3C trace propagation (same propagation pattern, applied to cost context)
- [F-29 · Cost Attribution](../forward-deployed/f29-cost-attribution.md) — API call tagging for billing analysis (call-level, not agent-level)
