# S-2650 · The Agentic Spend Attribution Stack — When the Invoice Lands but Nobody Knows Why

You deploy three agents owned by three teams. Finance asks why the bill is 3× last month. Engineering's answer: one number from one provider. The agentic system's cost trace looks nothing like a traditional software bill — one user click can branch into a planner call, a retrieval pass, two sub-agent tasks, a verification step, and a synthesis call. The invoice arrives as one line item. Attribution is a guess.

This is the agentic spend attribution problem: agentic workloads break FinOps allocation models at the root, and without a trace-to-team attribution pipeline, every cost governance conversation ends in speculation.

## Forces

- **One action, N calls.** A single user click in an agentic system can trigger a planner, a retrieval system, two sub-agents, a verification pass, and a synthesizer. Traditional cost-per-request models collapse because there is no single request — there is a graph. FinOps LLM (May 2026) documents that a single user action can produce 15–30 discrete LLM calls, each with its own token cost.
- **The invoice has no structure.** Cloud billing exports show spend by provider, model, and time. They do not show spend by team, feature, agent, or user action. Teams that ship agents have no accountability contract with the finance teams that fund them because attribution is absent by design.
- **Attribution gaps compound at scale.** In 2026, Uber burned through its 2026 AI coding budget in four months (Airia, May 2026). The engineering team's answer to "why" was a billing dashboard — a lagging indicator that describes the damage, not a governance structure that prevents it. Without per-agent spend attribution, scaling agents scales the mystery, not the control.
- **Trace data exists; it's just not wired up.** Every major observability platform (Langfuse, Arize Phoenix, Honeycomb, Datadog) can emit spans with metadata. Every LLM call carries a model and token count. The missing piece is the schema that maps trace spans to the organizational hierarchy (team → feature → agent → task → user action).

## The Move

### 1. Instrument at the trace span level

Every LLM call emits a span. Tag it with the attribution metadata at the point of dispatch:

```python
def llm_call(messages, model, tags: dict):
    span = tracer.start_span("llm.call")
    span.set_tags({
        "team": tags.get("team"),           # "platform", "growth", "support"
        "feature": tags.get("feature"),     # "code-review", "ticket-routing"
        "agent_id": tags.get("agent_id"),   # "reviewer-v2", "router-alpha"
        "task_type": tags.get("task_type"), # "planner", "executor", "verifier"
        "parent_action": tags.get("action"), # "user-click", "scheduled-job"
        "session_id": tags.get("session"),
    })
    with span:
        response = model.call(messages)
        span.set_tag("tokens.in", response.usage.prompt_tokens)
        span.set_tag("tokens.out", response.usage.completion_tokens)
        span.set_tag("cost.usd", calculate_cost(model, response.usage))
        return response
```

This is the atomic unit. Everything downstream depends on this.

### 2. Build the attribution hierarchy

Map trace spans to the organizational structure. The standard hierarchy:

```
User Action
  └─ Session / Conversation
       └─ Top-level Agent
            ├─ Planner Call (task_type: planner)
            ├─ Sub-Agent A (task_type: executor, agent_id: ...)
            │    ├─ Tool Call 1
            │    └─ Tool Call 2
            ├─ Sub-Agent B (task_type: executor, agent_id: ...)
            └─ Synthesis Call (task_type: synthesizer)
```

Use the parent span ID to reconstruct the call tree. Roll up cost by any dimension in the hierarchy. The power move: join spend to your sprint/issue tracker via the `feature` tag, so cost per feature maps to engineering capacity.

### 3. Establish per-agent budget quotas

With trace attribution in place, enforce budget quotas at the agent level — not at the total spend level:

```python
class AgentBudgetGuard:
    def __init__(self, agent_id: str, daily_limit_usd: float, alert_threshold: float = 0.7):
        self.agent_id = agent_id
        self.daily_limit = daily_limit_usd
        self.alert_threshold = alert_threshold

    def check(self, current_spend_usd: float) -> str:
        ratio = current_spend_usd / self.daily_limit
        if ratio >= 1.0:
            return "BLOCK"  # stops the agent, not just an alert
        elif ratio >= self.alert_threshold:
            return "ALERT"  # notifies, keeps running
        return "OK"

    def record(self, cost_usd: float):
        # Write to a shared budget state store (Redis, DynamoDB)
        # Read-compete-write to update rolling daily spend
        pass
```

The critical distinction: `BLOCK` returns a typed error the agent can handle (fall back to simpler logic, defer to human, skip the step). `ALERT` is a non-blocking notification. The S-2595 entry on token budget enforcement covers the runtime enforcement mechanics; this entry covers the *attribution layer that feeds those budgets*.

### 4. Generate the attribution report

A weekly report that Finance can actually use:

```python
def attribution_report(spans, window_days=7):
    df = pd.DataFrame([{
        "team": s.tag("team"),
        "feature": s.tag("feature"),
        "agent": s.tag("agent_id"),
        "task_type": s.tag("task_type"),
        "cost_usd": s.tag("cost.usd"),
        "tokens_in": s.tag("tokens.in"),
        "tokens_out": s.tag("tokens.out"),
    } for s in spans])

    return {
        "by_team": df.groupby("team")["cost_usd"].sum().sort_values(ascending=False),
        "by_feature": df.groupby("feature")["cost_usd"].sum().sort_values(ascending=False),
        "by_agent": df.groupby("agent")["cost_usd"].sum().sort_values(ascending=False),
        "cost_per_action_type": df.groupby("parent_action")["cost_usd"].mean(),
        "top_10_costly_traces": df.nlargest(10, "cost_usd")[
            ["team", "feature", "agent", "task_type", "cost_usd"]
        ],
    }
```

### 5. Wire it to chargeback

The end state: each team's weekly report shows their agent spend against their allocated budget, with anomaly flags for traces that exceed 2σ of the team mean. Finance gets per-feature cost breakdown instead of "Anthropic: $X." Engineering gets feedback that closes the loop — if the "code review" agent is 4× the budget of "ticket routing," a product decision can be made about which is worth it.

## Receipt

> Verified 2026-08-14 — Pattern validated against FinOps LLM's attribution taxonomy (finopsllm.com/research/agent-spend-attribution, updated July 2026) and TechTarget's Agentic AI FinOps guide (May 2026). Budget guard logic is the S-2595 enforcement pattern applied at the attribution layer. Attribution schema is consistent with OpenTelemetry semantic conventions for LLM spans.

## See also

- [S-2595](s2595-the-token-budget-enforcement-stack-when-your-alert-arrives-after-the-invoice.md) · Token Budget Enforcement — runtime enforcement that attribution feeds into
- [S-1130](s1130-the-trace-attributed-cost-optimization-stack-when-cheaper-models-cost-more.md) · Trace-Attributed Cost Optimization — per-span cost data that makes model routing decisions tractable
- [S-1011](s1011-the-rate-limited-multi-agent-pattern-when-all-your-agents-attack-your-api-quota-together.md) · Rate-Limited Multi-Agent — the coordination failure that per-agent quotas prevent
- [F-81](../forward-deployed/f81-cost-attribution-by-user-action.md) · Cost Attribution by User Action — the finer-grained layer below agent attribution
- [S-1000](s1000-the-agent-failure-handling-stack-when-your-agent-runs-forever-and-costs-too-much.md) · Agent Failure Handling — the cost explosion from unhandled failures that attribution makes visible
