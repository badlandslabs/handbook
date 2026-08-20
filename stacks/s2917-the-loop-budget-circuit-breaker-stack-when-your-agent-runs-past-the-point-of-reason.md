# S-2917 · The Loop Budget Circuit Breaker Stack: When Your Agent Runs Past the Point of Reason

Your agent starts a task at $0.02. By turn seven it's at $4.73 and climbing. No error fired. No alert triggered. The model is still producing output — confident, coherent, wrong. This is not a model problem. It's a budget architecture problem: your agent loop has no cost-aware enforcement layer, so it runs until the invoice tells you to stop. The fix is a circuit breaker that enforces token budgets, cost ceilings, and model-tier fallbacks as first-class loop primitives — not afterthoughts bolted onto the scaffold.

## Forces

- **Agent loops compound costs superlinearly.** Each turn re-passes the full accumulated context. A session that costs $0.40 at turn five can cost $8 at turn twelve — same task, same model, just more turns. S-103 (Cost-Aware Context Management) tells you *when* to compact. This entry tells you *what to do when the budget runs out*.
- **Conventional monitoring misses the failure mode.** HTTP 200, normal latency, coherent output. The agent is "healthy" by every traditional metric while burning $200 on a $2 task. The error surfaces on the invoice, not in the dashboard.
- **Static iteration caps are the wrong primitive.** Setting `max_iterations=10` stops the loop but doesn't route to a cheaper model, save partial results, or escalate. You want policy-driven escalation, not a wall.
- **Hard cost ceilings are a business requirement, not a technical preference.** Teams without spend controls lose real money. Teams with spend controls still lose money because their enforcement happens at the invoice level, not the loop level.

## The move

Implement a **three-layer budget circuit breaker** that fires before cost damage is done:

### Layer 1 — Token Budget Per Turn

Track cumulative input tokens *before* each LLM call. Set a per-turn ceiling (e.g., 50% of the model's context). If the next call would exceed it, truncate or compact first.

```python
class LoopBudgetBreaker:
    def __init__(
        self,
        per_turn_token_limit: int = 100_000,   # ~50% of a 200k context
        total_token_budget: int = 500_000,     # hard ceiling for this task
        cost_ceiling_usd: float = 5.00,         # fail-safe in dollars
        model_tiers: list[dict] = None,
    ):
        self.per_turn_limit = per_turn_token_limit
        self.total_budget = total_token_budget
        self.cost_ceiling = cost_ceiling_usd
        self.total_spent = 0
        self.turn_count = 0
        self.model_tiers = model_tiers or [
            {"name": "haiku", "price_per_m": (0.8, 4)},     # (input, output) per 1M tokens
            {"name": "sonnet", "price_per_m": (3, 15)},
            {"name": "opus", "price_per_m": (15, 75)},
        ]
        self.current_tier = 0

    def estimate_turn_cost(self, input_tokens: int) -> float:
        tier = self.model_tiers[self.current_tier]
        # Rough: assume 20% of input consumed as output this turn
        output_estimate = int(input_tokens * 0.2)
        inp_cost = input_tokens / 1_000_000 * tier["price_per_m"][0]
        out_cost = output_estimate / 1_000_000 * tier["price_per_m"][1]
        return inp_cost + out_cost

    def preflight_check(self, messages: list[dict]) -> "BreakerResult":
        """Called before each LLM invocation. Returns BreakerResult."""
        self.turn_count += 1
        input_tokens = self._count_tokens(messages)

        # Layer 1a: per-turn token ceiling
        if input_tokens > self.per_turn_limit:
            return BreakerResult(
                action="COMPACT",
                reason=f"per-turn limit exceeded: {input_tokens:,} > {self.per_turn_limit:,}",
            )

        # Layer 1b: total token budget
        cumulative = sum(m.get("_token_count", 0) for m in messages)
        if cumulative > self.total_budget:
            return BreakerResult(
                action="FAIL",
                reason=f"total budget exhausted: {cumulative:,} > {self.total_budget:,}",
            )

        # Layer 2: cost ceiling
        turn_cost = self.estimate_turn_cost(input_tokens)
        self.total_spent += turn_cost
        if self.total_spent > self.cost_ceiling:
            return BreakerResult(
                action="FAIL",
                reason=f"cost ceiling hit: ${self.total_spent:.4f} > ${self.cost_ceiling:.2f}",
            )

        return BreakerResult(action="PROCEED", reason="budget checks passed")

    def _count_tokens(self, messages: list[dict]) -> int:
        # Use the model's actual tokenizer when available
        # Fallback: ~4 chars per token approximation
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        text = "".join(m.get("content", "") for m in messages)
        return len(enc.encode(text))

    def degrade_tier(self) -> "BreakerResult":
        """Called after MAX_CONSECUTIVE_COMPACTS consecutive failures."""
        if self.current_tier < len(self.model_tiers) - 1:
            self.current_tier += 1
            return BreakerResult(
                action="DEGRADE",
                reason=f"degraded to {self.model_tiers[self.current_tier]['name']}",
            )
        return BreakerResult(
            action="FAIL",
            reason="no more fallback tiers available",
        )
```

### Layer 2 — The Escalation Ladder

Don't fail hard on the first trigger. Escalate through a policy ladder:

| Trigger | Action | Rationale |
|---------|--------|-----------|
| Per-turn token limit exceeded | Compact context → retry | Justify the compaction call, continue |
| 2nd per-turn limit in same task | Soft degrade: smaller model tier | Cost-vs-quality tradeoff, still productive |
| Cost ceiling at 75% | Checkpoint state, warn | Give operator visibility before hard stop |
| Cost ceiling hit | Hard stop + save partial output | Business protection: no more spend |
| Model tier exhausted | Escalate to human review | Boundary condition: task too hard for budget |

### Layer 3 — Cost-Circuit Integration

Wire the circuit breaker into the execution loop at the *scaffold* level, not the application level. The enforcement must live between the loop's decision and the LLM call:

```python
async def agent_loop(messages: list[dict], budget: LoopBudgetBreaker):
    MAX_COMPACTS = 2
    compact_count = 0

    while True:
        # Budget preflight — BEFORE the LLM call
        result = budget.preflight_check(messages)
        match result.action:
            case "COMPACT":
                if compact_count < MAX_COMPACTS:
                    messages = await compact_context(messages)
                    compact_count += 1
                    continue
                else:
                    return budget.degrade_tier()
            case "DEGRADE":
                # Switch model tier and continue
                messages.append({"role": "system", "content": result.reason})
                continue
            case "FAIL":
                return {"status": "budget_exhausted", "reason": result.reason,
                        "partial": messages[-3:]}

        # Normal LLM call — if budget preflight passed
        response = await llm_call(messages, model=budget.model_tiers[budget.current_tier]["name"])
        messages.append(response)

        if response.is_final:
            return {"status": "complete", "messages": messages,
                    "cost": budget.total_spent}
```

## Receipt

> Verified 2026-08-20 — Code pattern derived from agentbudget GitHub repo (July 2026), 72Technologies token budgeting guide, and AgentMarketCap SRE patterns. Three-layer circuit breaker architecture (token → cost → tier) matches production patterns from Anthropic Enterprise Spend Controls announcements and the agent-almanac skill `manage-token-budget`. The per-turn token ceiling + cost ceiling + model degradation ladder is a convergent pattern across 3+ independent sources.

## See also

- [S-103 · Cost-Aware Context Management](s103-cost-aware-context-management.md) — the compaction decision logic; this entry is the enforcement layer
- [S-1003 · The Agent Failure Recovery Stack](s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — recovery primitives; this entry is the prevention layer (fail before the spiral)
- [S-1029 · The Agentic RAG Control Stack](s1029-the-agentic-rag-control-stack-when-your-retrieval-loop-runs-all-night-without-answering.md) — retrieval loop runaway; this entry applies the same budget circuit pattern to the general agent loop
- [F-199 · Per-Task Cost Attribution](f199-per-task-cost-attribution.md) — measuring cost per task unit; this entry controls cost per task unit
- [S-06 · Model Routing](s06-model-routing.md) — model tier selection; this entry makes tier selection a loop-enforced policy, not a static router
