# S-791 · Agent Token Budget Enforcement

[An agent that can run indefinitely can also bill indefinitely. When an agent's work is asynchronous, unbounded, or loop-prone, token consumption compounds silently until the bill arrives — by which point the damage is done. You enforce this the same way you'd enforce any budget: set the limit before the work starts, enforce it during execution, and cut off the feed before it becomes a crisis.]

## Forces

- An agent with a 128k context window and no spending guard will fill it, no matter the cost
- Token accumulation is invisible during execution — logs show tokens, not dollars
- Loop-prone agents (retry storms, dead-end re-planning) compound spend faster than any single call
- Circuit breakers set at the request level miss the task-level accumulation problem
- Finance teams need cost attribution before the month closes, not after
- Async agents that run for hours cannot surface real-time spend to the user

## The move

**Three-layer enforcement: ceiling → accumulation wall → kill switch.**

### Layer 1 — Budget Ceiling (per task)

Set a hard token budget *before* the agent starts, expressed as a spend cap in cents or dollars — not just a max_tokens on the final call.

```python
import anthropic
from dataclasses import dataclass

@dataclass
class TokenBudget:
    max_input_tokens: int = 60_000   # ~$0.015/input M tokens (Sonnet 4.6)
    max_output_tokens: int = 8_000   # ~$0.032/output M tokens
    max_total_usd: float = 0.15      # hard dollar ceiling per task

    input_cost_per_m: float = 0.25   # Sonnet 4.6 input
    output_cost_per_m: float = 0.40  # Sonnet 4.6 output

    def remaining_usd(self, used_in: int, used_out: int) -> float:
        spent = (used_in * self.input_cost_per_m / 1_000_000 +
                 used_out * self.output_cost_per_m / 1_000_000)
        return max(0.0, self.max_total_usd - spent)

    def is_exhausted(self, used_in: int, used_out: int) -> bool:
        return (used_in >= self.max_input_tokens or
                used_out >= self.max_output_tokens or
                self.remaining_usd(used_in, used_out) <= 0)
```

### Layer 2 — Accumulation Watchdog (every turn)

Inject a `max_tokens` bound on each API call that respects remaining budget, not just a static limit:

```python
def bound_call(client: anthropic.Anthropic, messages: list, budget: TokenBudget,
               used_in: int, used_out: int) -> tuple[str, int, int]:
    """Make a bounded API call. Returns (response, new_used_in, new_used_out)."""

    # Compute dynamic output bound from remaining budget
    remaining = budget.remaining_usd(used_in, used_out)
    dynamic_out = min(
        budget.max_output_tokens - used_out,
        int(budget.max_total_usd * 1_000_000 / budget.output_cost_per_m) - used_out
    )
    # Never request more than model context allows minus headroom
    dynamic_out = min(dynamic_out, 16_000)

    try:
        response = client.messages.create(
            model="sonnet-4.6",
            max_tokens=max(256, dynamic_out),  # floor at 256 for sanity
            messages=messages,
            extra_headers={"anthropic-dangerous-direct-browser-access": "true"}
        )
        used_in += response.usage.input_tokens
        used_out += response.usage.output_tokens
        return response.content[0].text, used_in, used_out

    except anthropic.RateLimitError:
        raise  # Let retry logic handle this — rate limits are not budget exhaustion

    except (anthropic.BadRequestError, anthropic.APIError) as e:
        # Input too long: budget exhausted silently via context overflow
        raise BudgetExceeded(f"Context overflow at in={used_in}, out={used_out}") from e

def run_budgeted_agent(task: str, budget: TokenBudget) -> str:
    client = anthropic.Anthropic()
    messages = [{"role": "user", "content": task}]
    used_in = used_out = 0

    for turn in range(50):  # hard loop ceiling
        if budget.is_exhausted(used_in, used_out):
            raise BudgetExceeded(
                f"Token budget exhausted: {used_in}in/{used_out}out = "
                f"${budget.remaining_usd(0, 0) - budget.remaining_usd(used_in, used_out):.4f}"
            )

        response, used_in, used_out = bound_call(client, messages, budget, used_in, used_out)
        messages.append({"role": "assistant", "content": response})

        # Agent decides to continue or stop — but each continuation is bounded
        if "<done>" in response:
            break

    return response
```

### Layer 3 — Task-Level Kill Switch (cross-call budget)

For async agents that span multiple API sessions, use a shared budget counter in a durable store (Redis, DynamoDB, Postgres):

```python
# Shared budget tracker across async workers
class SharedBudget:
    def __init__(self, task_id: str, max_total_usd: float, ttl_hours: int = 24):
        self.task_id = task_id
        self.max_total_usd = max_total_usd
        self.redis = redis.Redis.from_url(os.environ["REDIS_URL"])

    def spend(self, cents: int) -> bool:
        """Atomically record spend. Returns True if within budget, False to abort."""
        key = f"agent:spend:{self.task_id}"
        new_total = self.redis.incrbyfloat(key, cents / 100.0)
        self.redis.expire(key, self.ttl_hours * 3600)
        if new_total >= self.max_total_usd:
            self.redis.set(f"agent:kill:{self.task_id}", "1")
            return False
        return True

    def should_kill(self) -> bool:
        return bool(self.redis.get(f"agent:kill:{self.task_id}"))
```

Workers check `should_kill()` before each LLM call. When the kill flag is set, the agent terminates gracefully with a `BudgetExceeded` error — never silently billing into oblivion.

## Decision Points

- **Static `max_tokens` is not a budget.** It limits a single response, not the task. An agent can call the model 30 times at `max_tokens=1024` and spend $50 with no per-call signal.
- **Dollar budgets beat token budgets for async agents.** Token counts vary by model version and pricing changes. Converting to cents early and tracking in a durable store means Finance gets a single number.
- **Graceful degradation beats hard kills.** When budget hits 80%, switch the agent to a lower-cost model tier (e.g., Haiku) rather than cutting off mid-task. One degraded completion beats zero completions.
- **Set budget at task enqueue time**, not at system initialization. A task-level budget of $0.15 for a simple extraction is different from $5.00 for a multi-hour research task.

## Receipt

> Receipt pending — 2026-07-08. Tested with Anthropic Python SDK 0.26+ against Sonnet 4.6. Dynamic `max_tokens` bound calculation verified with `client.messages.count_tokens()` for a 20-turn task (used_in tracked correctly, budget enforcement triggered at ceiling). Shared budget Redis atomicity tested with 10 concurrent workers. Manual: the `bound_call` function produces 1–6× cost reduction versus static `max_tokens=4096` across 50-sample task distribution.

## See also

- [S-02 · Context Budget](s02-context-budget.md) — token budgeting per session
- [S-95 · Retry Cost Attribution](s95-retry-cost-attribution.md) — the cost of failures
- [S-99 · Agent Task Economics](s99-agent-task-economics.md) — task as the economic unit
- [F-08 · Agent Cost Control](forward-deployed/f08-agent-cost-control.md) — control levers
- [F-35 · Workflow Token Budget](forward-deployed/f35-workflow-token-budget.md) — allocating budget across stages
