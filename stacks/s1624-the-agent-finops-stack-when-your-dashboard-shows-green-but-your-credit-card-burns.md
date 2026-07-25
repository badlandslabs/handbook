# S-1624 · The Agent FinOps Stack — When Your Dashboard Shows Green But Your Credit Card Burns

Your cost dashboard is green. Your token counter says 2.3M/month — well within budget. You get the invoice: $47,000 for the month. The agent looped for 11 days before anyone noticed. The dashboard was accurate. It was also useless — because it showed what had already happened, not what was actively happening. This is the FinOps enforcement gap: **observability without intervention is just expensive history**.

## Forces

- **Agents have no natural cost ceiling.** Unlike a database query (which times out) or a recursive function (which stack-overflows), an agent loop can run indefinitely, each turn producing plausible-but-wrong outputs that keep the loop alive. The loop only stops when someone notices or the API key runs out.
- **Cost dashboards measure, they don't intervene.** A dashboard showing $12,000 in spend does not prevent the next 8 hours of $15,000/hour looping. The gap between "knowing" and "stopping" is where incidents live.
- **Agent costs are compositionally opaque.** A single run includes: planning tokens, retrieval tokens, tool-call tokens, synthesis tokens, retry tokens, and loop tokens. Each layer compounds. Traditional cloud FinOps (compute, storage, network) cannot attribute these — you need a purpose-built agent cost model.
- **Cost attribution without enforcement is theater.** BCG's 2026 analysis confirms: the unit of management is cost-per-outcome, not cost-per-token. But if you can't stop a runaway outcome, attribution just produces better-formatted invoices for incidents you still couldn't prevent.

## The move

### Layer 1 — Pre-Call Token Budget Enforcer (Enforcement, not alerting)

Inject a cost gate between the agent's decision layer and the model call. The gate checks before every LLM call:

```python
class AgentFinOpsGate:
    def __init__(self, max_cost_cents: int, max_tokens_per_run: int,
                 velocity_threshold_cents_per_min: float = 50.0):
        self.max_cost_cents = max_cost_cents
        self.max_tokens_per_run = max_tokens_per_run
        self.velocity_threshold = velocity_threshold_cents_per_min
        self.run_cost_cents: float = 0.0
        self.run_tokens: int = 0
        self.last_check = time.monotonic()
        self._spend_history: list[tuple[float, float]] = []  # (timestamp, cost)

    def pre_call(self, estimated_tokens: int, model: str) -> None:
        # 1. Hard ceiling check
        projected_total = self.run_cost_cents + self._token_cost(estimated_tokens, model)
        if projected_total > self.max_cost_cents:
            raise AgentBudgetExceeded(
                f"Pre-call gate: {projected_total:.2f}c > {self.max_cost_cents}c limit"
            )
        # 2. Token ceiling check
        if self.run_tokens + estimated_tokens > self.max_tokens_per_run:
            raise AgentBudgetExceeded(
                f"Token ceiling: {self.run_tokens + estimated_tokens} > {self.max_tokens_per_run}"
            )
        # 3. Cost velocity circuit breaker
        self._check_velocity()

    def post_call(self, actual_cost_cents: float, actual_tokens: int) -> None:
        self.run_cost_cents += actual_cost_cents
        self.run_tokens += actual_tokens
        now = time.monotonic()
        self._spend_history.append((now, actual_cost_cents))
        # Keep last 5 minutes of history
        cutoff = now - 300
        self._spend_history = [(ts, c) for ts, c in self._spend_history if ts >= cutoff]

    def _check_velocity(self):
        if not self._spend_history:
            return
        elapsed = (self._spend_history[-1][0] - self._spend_history[0][0]) / 60
        if elapsed < 0.5:  # Don't trigger on cold starts
            return
        recent = sum(c for _, c in self._spend_history)
        rate = recent / max(elapsed, 0.1)
        if rate > self.velocity_threshold:
            raise AgentCostVelocityBreach(
                f"Circuit breaker: {rate:.1f}c/min > {self.velocity_threshold}c/min threshold"
            )

    def _token_cost(self, tokens: int, model: str) -> float:
        rates = {"gpt-4o": 0.015, "gpt-4o-mini": 0.003, "claude-sonnet": 0.015}
        return tokens * rates.get(model, 0.015) / 1_000_000 * 100  # cents
```

The gate raises an exception — it does not log and continue. This is the critical difference from alerting. An alert at 80% of budget lets the agent spend the remaining 20%. A hard pre-call gate stops the next call before it fires.

### Layer 2 — Workflow-Level Cost Attribution (The FinOps grain)

Cost visibility requires attribution at the grain that drives decisions. BCG's RoAI metric (Return on AI = Economic Return / Human Cost + Token Cost) only works if you can compute it:

| Attribution grain | Why it matters | What it surfaces |
|---|---|---|
| Per workflow run | Compare "email triage" vs "code review" ROI | Power-user workflows driving 80% of cost |
| Per user / session | Detect abuse, set per-user ceilings | Users triggering runaway loops |
| Per model tier | Validate routing decisions | GPT-4o being used where Haiku suffices |
| Per tool-call category | Identify expensive retrieval patterns | RAG calls at $0.002 each compounding |
| Per outcome type | Compute actual cost-per-result | "Complex" queries costing 40× more |

The practical implementation wraps every agent run in a `CostContext` that attributes spend to these grains in real time:

```python
@dataclass
class CostContext:
    workflow: str           # "customer_support_triage_v2"
    user_id: str            # "user_00a1f2"
    model_tier: str         # "gpt-4o-mini"
    session_id: str         # UUID
    task_type: str          # "classification" | "generation" | "retrieval"
    start_time: datetime
    cost_cents: float = 0.0
    tokens: int = 0
    tool_calls: int = 0

class AttributedAgentRunner:
    def run(self, ctx: CostContext, agent_fn, *args):
        span = tracer.start_span("agent.run", attributes={
            "workflow": ctx.workflow, "user_id": ctx.user_id,
            "model_tier": ctx.model_tier, "task_type": ctx.task_type
        })
        gate = AgentFinOpsGate(
            max_cost_cents=ctx.session_budget_cents or 500,
            max_tokens_per_run=ctx.session_token_limit or 200_000
        )
        try:
            result = agent_fn(gate=gate, *args)
            ctx.cost_cents = gate.run_cost_cents
            ctx.tokens = gate.run_tokens
            ctx.outcome = "success"
        except AgentBudgetExceeded as e:
            ctx.outcome = "budget_exceeded"
            ctx.partial_result = getattr(result, "partial", None)
            ctx.cost_cents = gate.run_cost_cents
            raise
        finally:
            # Emit to cost warehouse for attribution analysis
            cost_warehouse.record(ctx)
            span.set_attribute("cost_cents", ctx.cost_cents)
            span.set_attribute("outcome", ctx.outcome)
        return result
```

### Layer 3 — Cost Velocity Circuit Breaker

A step cap stops the agent from continuing. A velocity circuit breaker stops it when spend rate becomes anomalous — catching loops that haven't hit the absolute ceiling but are clearly pathological:

- **Baseline rate**: Track rolling average cost per minute over first 3 minutes of a run
- **Anomaly threshold**: 3× baseline rate over any 5-minute window
- **Action**: Hard halt + partial result capture + alert + human review queue

The velocity approach catches slow-burning loops (8 hours at $5/min = $2,400) that a hard ceiling of $10,000 would let run. It also distinguishes "expensive but legitimate" from "expensive and wrong" — a research agent doing genuine deep work at $3/min is fine; one that just entered a retry spiral at $8/min is not.

### Layer 4 — Outcome-Linked Cost Ceiling

The hardest budget is not a token limit — it's a value threshold. Set a maximum cost-per-outcome and enforce it:

```python
def cost_per_outcome_gate(workflow: str, outcome_type: str,
                          max_cost_cents: int) -> None:
    """
    Before starting an agent run, validate that the expected value
    justifies the maximum possible spend.
    """
    thresholds = {
        ("support_triage", "low"): 50,    # $0.50 max
        ("support_triage", "high"): 500,  # $5.00 max
        ("code_review", "any"): 200,
        ("market_research", "any"): 2000,
    }
    limit = thresholds.get((workflow, outcome_type), 500)
    if max_cost_cents > limit:
        raise BudgetPolicyViolation(
            f"Policy: {workflow}/{outcome_type} capped at {limit}c, "
            f"caller requested {max_cost_cents}c"
        )
```

## Receipt

> Receipt pending — 2026-07-25. The pattern is validated across multiple production deployments documented by Waxell (April 2026), BCG (2026), NextPage IT (June 2026), and i10x.ai (2026). The $47,000 loop incident (4 LangChain agents, 11 days, Waxell) specifically identifies missing pre-call cost enforcement as the root cause. The token budget pre-call gate, cost velocity circuit breaker, and workflow attribution stack are all implemented patterns from these sources.

## See also

- [S-340 · Agent Hard Enforcement Plane](s340-agent-hard-enforcement-plane.md) — hard cost caps and loop bounds (this entry extends S-340 with FinOps-specific attribution and velocity detection)
- [S-1027 · The Scaffold Stack](s1027-the-scaffold-stack-when-your-agent-loops-forever-and-charges-your-budget.md) — loop detection patterns (complementary: scaffold detects loops; FinOps enforces cost ceiling on loops)
- [S-1039 · The Specialist Router Stack](s1039-the-specialist-router-stack-when-your-agent-runs-everything-through-opus-and-bills-you-for-it.md) — model routing for cost optimization (adjacent: routing chooses cheap models; FinOps enforces the resulting budget)
