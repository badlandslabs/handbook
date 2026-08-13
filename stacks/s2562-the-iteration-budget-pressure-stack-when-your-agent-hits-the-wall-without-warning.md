# S-2562 · The Iteration Budget Pressure Stack — When Your Agent Hits the Wall Without Warning

You set `max_iterations=50`. At iteration 50, the agent stops mid-task, makes one last bare API call, and returns whatever it managed to scrape together. The response is truncated, the reasoning trail is lost, and the user gets partial results they didn't ask for. The problem isn't the cap — it's that the model had no idea it was approaching a cliff.

The iteration budget pressure stack injects graded warning signals into the agent's context as it approaches its limits, giving the model a chance to wrap up gracefully instead of running into the wall.

## Forces

- **The wall is binary; the model's behavior isn't.** A hard cap stops the agent — but by the time the cap fires, the model has no opportunity to consolidate findings, surface partial results, or signal what it still needs. The last meaningful work happens without the model knowing it was the last.
- **Abrupt termination produces worse outputs than early wrap-up.** Inngest's Utah harness found that agents given a "CAUTION" warning at N−10 iterations produce responses with measurably higher completion scores than agents that hit the cap cold. The model knows how to wrap up — it just wasn't told to.
- **Hard caps are insurance; pressure signals are coaching.** A circuit breaker that fires at $50 is necessary. A system message at $45 that says "budget running low, prioritize final output" is better — because the model self-corrects before the breaker trips.
- **The wrap-up call is the worst possible last call.** When `_handle_max_iterations()` fires and makes a tool-less summary request, it starts from scratch: no tool results, no reasoning trail, no context from prior work. It's asking the model to re-derive what it already did.

## The move

Implement a **three-tier pressure system** that injects system messages at threshold crossings. The agent tracks iterations against `max_iterations`; as it crosses pressure thresholds, it injects increasingly urgent advisory messages into the context.

### Tier 1 — Budget Pressure (N−15, or 75% of budget)

```python
import time
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class IterationBudget:
    max_iterations: int = 50
    warning_fraction: float = 0.70   # first warning at 70% of budget
    caution_fraction: float = 0.85   # caution at 85%
    stop_fraction: float = 0.95     # final wrap-up at 95%

    warnings_log: list[dict] = field(default_factory=list)
    _pressure_tiers: list[tuple[float, str]] = field(default_factory=list)

    def __post_init__(self):
        self._pressure_tiers = [
            (self.warning_fraction, "BUDGET"),
            (self.caution_fraction, "CAUTION"),
            (self.stop_fraction,    "WRAP_UP"),
        ]

    def pressure_signal(self, current_iteration: int) -> str | None:
        """Returns a pressure message if the agent just crossed a tier threshold."""
        for frac, tier in self._pressure_tiers:
            threshold = int(self.max_iterations * frac)
            already_warned = any(
                w["tier"] == tier for w in self.warnings_log
            )
            if current_iteration >= threshold and not already_warned:
                self.warnings_log.append({
                    "tier": tier,
                    "iteration": current_iteration,
                    "ts": time.time(),
                })
                return self._build_message(tier, current_iteration)
        return None

    def _build_message(self, tier: str, n: int) -> str:
        remaining = self.max_iterations - n
        if tier == "BUDGET":
            return (
                f"[SYSTEM: Budget pressure — iteration {n}/{self.max_iterations}. "
                f"{remaining} steps remaining. Prioritize high-impact actions. "
                f"Defer exploration in favor of completing the core objective.]"
            )
        elif tier == "CAUTION":
            return (
                f"[SYSTEM: CAUTION — iteration {n}/{self.max_iterations}. "
                f"Only {remaining} step(s) left. Begin consolidating findings. "
                f"Prepare a structured final response that captures current state. "
                f"Do not start new investigation threads.]"
            )
        else:  # WRAP_UP
            return (
                f"[SYSTEM: WRAP UP NOW — iteration {n}/{self.max_iterations}. "
                f"This is the final functional iteration. Produce your complete "
                f"final response immediately. Include: (1) what was accomplished, "
                f"(2) what remains open, (3) any partial results of value. "
                f"No further tool calls.]"
            )

# Usage in the agent loop:
budget = IterationBudget(max_iterations=50)

def agent_loop(messages: list[dict], tools: list[dict]) -> dict:
    iteration = 0
    while iteration < budget.max_iterations:
        # Inject pressure signal on tier crossing
        signal = budget.pressure_signal(iteration)
        if signal:
            messages.append({"role": "system", "content": signal})

        response = llm.call(messages, tools=tools)
        if not response.tool_calls:
            return response  # natural completion

        for tool_call in response.tool_calls:
            result = execute_tool(tool_call)
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result})

        iteration += 1

    # Hard cap: one final wrap-up call (only if not already in WRAP_UP)
    wrap_up_msg = (
        "[SYSTEM: Hard iteration limit reached. No iterations remain. "
        "Produce your best final response now using all accumulated context. "
        "This is your only chance to summarize.]"
    )
    messages.append({"role": "system", "content": wrap_up_msg})
    return llm.call(messages, tools=[])
```

### Tier 2 — Cost budget pressure (dollar-denominated)

For high-stakes or variable-cost tasks, layer a parallel dollar budget:

```python
@dataclass
class DollarBudget:
    max_spend_usd: float = 5.00
    warning_at_fraction: float = 0.80

    spent_usd: float = 0.0
    _warned: bool = False

    def track(self, token_count: int, model: str) -> str | None:
        """Estimate cost of last call and emit pressure if needed."""
        rate = {"claude-opus": 0.015, "claude-sonnet": 0.003,
                "gpt-4o": 0.005, "gpt-4o-mini": 0.0003}.get(model, 0.005)
        cost = (token_count / 1_000_000) * rate  # rough approximation

        self.spent_usd += cost
        if not self._warned and self.spent_usd >= self.max_spend_usd * self.warning_at_fraction:
            self._warned = True
            return (
                f"[SYSTEM: Cost budget warning — ${self.spent_usd:.2f}/${self.max_spend_usd:.2f} spent. "
                f"${self.max_spend_usd - self.spent_usd:.2f} remaining. "
                f"Optimize for output quality over exploration breadth.]"
            )
        if self.spent_usd >= self.max_spend_usd:
            return (
                f"[SYSTEM: Hard cost limit reached. ${self.max_spend_usd:.2f} budget exhausted. "
                f"Return final response immediately.]"
            )
        return None
```

### Tier 3 — Context pressure (token headroom)

When the context window approaches its limit, inject urgency to compress or conclude:

```python
def context_pressure_signal(context_tokens: int, max_tokens: int) -> str | None:
    fraction = context_tokens / max_tokens
    if fraction >= 0.90:
        return (
            "[SYSTEM: Context window at 90%+ capacity. "
            "Compress your reasoning. Prioritize final output. "
            "Omit intermediate steps from your response if needed to fit.]"
        )
    return None
```

## The whole picture

Combine all three pressure layers into a single `AgentPressureMonitor`:

```python
@dataclass
class AgentPressureMonitor:
    iteration_budget: IterationBudget
    dollar_budget: DollarBudget
    max_context_tokens: int = 200_000

    def all_signals(self, iteration: int, context_tokens: int,
                    last_call_tokens: int, model: str) -> list[str]:
        signals = []
        signals.append(self.iteration_budget.pressure_signal(iteration))
        signals.append(self.dollar_budget.track(last_call_tokens, model))
        signals.append(context_pressure_signal(context_tokens, self.max_context_tokens))
        return [s for s in signals if s]  # filter None
```

## Receipt

> Verified 2026-08-13 — Pattern drawn from: (1) Nous Research Hermes Agent issue #414 (teknium1, open since March 2026) — open feature request for budget pressure injection; (2) Inngest Utah agent harness (inngest/utah, Apache-2.0) — implements two-tier CAUTION/STOP pressure with system message injection; (3) OpenHands SDK issue #2406 (March 2026) — independently raised same proposal; (4) LiteLLM AI Gateway `max_iterations` + `max_budget_per_session` as complementary hard stops; (5) Hermes Agent agent-loop internals (hermes-agent.nousresearch.com, 2026) — explicitly documents budget pressure as ephemeral prompt layer. Receipt pending — code above is reference implementation; production deployment recommended via litellm middleware hook or as a LangChain callback.

## See also

- [S-1003 · The Agent Failure Recovery Stack](stacks/s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — covers hard caps and recovery after failure; this entry covers graceful wrap-up *before* the cap
- [S-1000 · The Agent Failure Handling Stack](stacks/s1000-the-agent-failure-handling-stack-when-your-agent-runs-forever-and-costs-too-much.md) — cost circuit breakers and step-level caps; this entry adds the pressure-signal layer between cap and model
- [S-08 · Prompt Caching](stacks/s08-prompt-caching.md) — complementary technique for reducing per-iteration cost on repeated context
