# F-199 · Per-Task Cost Attribution

[F-81](f81-cost-attribution-by-user-action.md) tracks spend by user action (full_draft, quick_query). [F-95](f95-tool-invocation-cost-attribution.md) identifies which specific tools inject the most tokens per call. [F-88](f88-session-cost-ceiling.md) caps a session in dollar terms. None attributes cost at the level of a customer-visible unit of work — the thing the customer believes they bought. When you need to charge per "resolved issue," "enriched lead," or "research brief," tokens and session IDs are the wrong unit. This is per-task cost attribution.

## Forces

- **The bill doesn't match the work.** Token counts and API invoices arrive at the infrastructure level. Customer bills need to arrive at the product level. These two currencies don't map without a translation layer.
- **A single session contains multiple tasks.** A customer support agent might handle three separate issues in one session. Session-level cost tells you nothing about which issue drove which spend.
- **Agent loops make boundaries ambiguous.** Unlike a stateless API call, an agent decides how many steps to take. The task boundary isn't known at the start — it has to be inferred from outcome signals.
- **Cost-per-token is not cost-per-value.** A task that resolves on the first try and a task that requires three retries consume very different token budgets for the same customer-visible outcome. Billing per token penalizes hard problems; billing per task aligns cost with value.

## The move

The pattern has three layers: **task scoping** (define and track the unit of work), **cost accumulation** (capture every cost driver under a task ID), and **outcome reconciliation** (compare spend to value and surface it to the customer).

### Layer 1: Task Scoping

A task is a customer-intended unit of work, not a technical one. Define it by its boundary signals:

```
Task starts → user submits a distinct request / triggers a distinct goal
Task ends   → agent produces a terminal output OR user confirms resolution
```

In simple implementations, one user message = one task. In complex multi-turn sessions, use intent detection to segment. The task ID propagates through the entire call chain:

```python
# Pseudocode — task-scoped cost tracking
class TaskCostAccumulator:
    def __init__(self, task_id: str, customer_id: str, task_type: str):
        self.task_id = task_id
        self.customer_id = customer_id
        self.task_type = task_type
        self.started_at = time.time()
        self.token_cost = 0.0
        self.tool_calls = []
        self.model_calls = 0

    def record_model_call(self, input_tokens: int, output_tokens: int,
                          model: str, provider: str):
        rate_in  = PRICING[provider][model]["in"]
        rate_out = PRICING[provider][model]["out"]
        cost = (input_tokens * rate_in + output_tokens * rate_out) / 1_000_000

        self.token_cost += cost
        self.model_calls += 1
        emit_task_event(
            event="model_call",
            task_id=self.task_id,
            customer_id=self.customer_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
            model=model,
            provider=provider,
            timestamp=time.time()
        )

    def record_tool_call(self, tool_name: str, tokens_in: int, tokens_out: int,
                        duration_ms: int, success: bool):
        # External API costs, infrastructure costs
        tool_cost = estimate_tool_cost(tool_name, tokens_in, tokens_out, duration_ms)
        self.tool_calls.append({
            "tool": tool_name,
            "cost": tool_cost,
            "success": success,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out
        })
        emit_task_event(
            event="tool_call",
            task_id=self.task_id,
            tool=tool_name,
            cost_usd=tool_cost,
            success=success
        )

    def finalize(self, outcome: str, quality_score: float = None):
        # outcome: "resolved", "escalated", "partial", "failed"
        total = self.token_cost + sum(t["cost"] for t in self.tool_calls)
        emit_task_event(
            event="task_completed",
            task_id=self.task_id,
            customer_id=self.customer_id,
            task_type=self.task_type,
            outcome=outcome,
            total_cost_usd=total,
            quality_score=quality_score
        )
        return {
            "task_id": self.task_id,
            "cost_usd": total,
            "outcome": outcome,
            "model_calls": self.model_calls,
            "tool_calls": len(self.tool_calls)
        }
```

### Layer 2: Cost Accumulation with Cross-Cutting Concerns

Inject the accumulator into your agent framework at the orchestration layer. Every model call and every tool call routes through it:

```python
# Hook into your agent framework
class TaskScopedAgent:
    def __init__(self, agent_id: str, customer_id: str):
        self.agent_id = agent_id
        self.customer_id = customer_id
        self.current_task = None

    def start_task(self, user_message: str, task_type: str) -> str:
        task_id = f"{self.customer_id}-{uuid.uuid4().hex[:8]}"
        self.current_task = TaskCostAccumulator(task_id, self.customer_id, task_type)
        return task_id

    def call_model(self, messages: list, model: str, provider: str = "openai"):
        # Count tokens before call (using tiktoken or provider API)
        input_tokens = count_tokens(messages, model)
        response = model_provider[provider].chat.completions.create(
            model=model, messages=messages, ...
        )
        output_tokens = count_tokens(response, model)
        if self.current_task:
            self.current_task.record_model_call(input_tokens, output_tokens, model, provider)
        return response

    def call_tool(self, tool_name: str, **kwargs):
        result = execute_tool(tool_name, **kwargs)
        tokens_in = count_tool_input(kwargs)
        tokens_out = count_tool_output(result)
        duration_ms = result.get("_latency_ms", 0)
        if self.current_task:
            self.current_task.record_tool_call(
                tool_name, tokens_in, tokens_out, duration_ms, result.get("_success", True)
            )
        return result

    def complete_task(self, outcome: str, quality_score: float = None):
        if self.current_task:
            summary = self.current_task.finalize(outcome, quality_score)
            self.current_task = None
            return summary
        return None
```

### Layer 3: Outcome Reconciliation — The Meter That Matters

Token-level accounting is infrastructure. Customer-facing billing needs value alignment. Map tasks to the customer's unit of work:

```
Support agent   → task_type="ticket_resolution"   → bill per resolved ticket
Research agent  → task_type="brief_generation"    → bill per brief with quality ≥ threshold
Sales agent     → task_type="lead_enrichment"      → bill per enriched record
Finance agent   → task_type="reconciliation"      → bill per reconciled batch
```

Build a reconciliation table that catches bill shock before it reaches the customer:

```python
def build_task_invoice_line(task_summary: dict, customer_contract: dict) -> dict:
    rate_per_task = customer_contract["rate_per_task"][task_summary["task_type"]]
    outcome = task_summary["outcome"]

    # Partial credit for failed/partial outcomes
    if outcome == "failed":
        credits = customer_contract.get("fail_credits", 1.0)  # full credit
        billable = 0
    elif outcome == "partial":
        credits = customer_contract.get("partial_credits", 0.5)
        billable = rate_per_task * credits
    else:
        billable = rate_per_task

    cost = task_summary["cost_usd"]
    margin = billable - cost

    return {
        "task_id": task_summary["task_id"],
        "outcome": outcome,
        "cost_usd": round(cost, 4),
        "billable_usd": round(billable, 2),
        "margin_usd": round(margin, 2),
        "cost_efficiency": round(cost / billable, 2) if billable > 0 else None
    }
```

### The Contrarian Insight

The counterintuitive part: **over-attributing is worse than under-attributing.** If you track cost at the per-token level and expose every token to the customer, you will have a billing system that is technically accurate and commercially useless. Customers don't buy tokens. They buy resolved tickets, enriched leads, and research briefs. The discipline is not measuring more — it's measuring the right thing.

The second counterintuitive point: **retry cost is a quality signal, not a billing penalty.** A task that costs $0.50 because it retried twice may represent harder-than-average work, not inefficiency. Your billing logic should account for this rather than penalizing the outcome.

## Receipt

> Receipt pending — 2026-07-20. The code patterns are drawn from production implementations documented in Iterathon's "AI Agent Cost Tracking 2026" guide and BuildMVPFast's "Metered Billing for AI Agents" (April 2026). Verification against a live agent implementation running task-scoped cost accumulation is needed.

## See also

- [F-81 · Cost Attribution by User Action](f81-cost-attribution-by-user-action.md) — the user-action level this extends from
- [F-95 · Tool Invocation Cost Attribution](f95-tool-invocation-cost-attribution.md) — the tool-level granularity below this layer
- [F-88 · Session Cost Ceiling](f88-session-cost-ceiling.md) — dollar-level caps that pair with task-level attribution
- [S-103 · Cost-Aware Context Management](../stacks/s103-cost-aware-context-management.md) — token-level cost discipline upstream of attribution
