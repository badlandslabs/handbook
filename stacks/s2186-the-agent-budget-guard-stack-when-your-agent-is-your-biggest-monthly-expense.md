# S-2186 · The Agent Budget Guard Stack — When Your Agent Is Your Biggest Monthly Expense

You deployed the agent on Monday. It ran fine. On Tuesday, your CFO asks about the $14,000 API bill from a single weekend pipeline that was supposed to process 200 documents. The agent entered a retry loop at 11 PM Friday, failed silently on every iteration, and nobody noticed until Monday morning. The API returned 200 OK every time. There was no exception to catch, no alert to fire. The cost accumulation was invisible at the application layer.

This is the budget guard problem: agents compound token costs at every loop step, and your monitoring stack wasn't built to see it. The fix is not better logging — it's architectural enforcement at the call boundary.

## Forces

- **Context re-reading is the silent cost multiplier.** Every agent loop step sends the full accumulated conversation to the LLM. Step 1 = 500 tokens. Step 20 = 8,000+ tokens — you're paying to re-read the entire history on every step. Agents consume ~50x more tokens than single-turn chatbots on equivalent tasks.
- **Agents fail with 200 OK.** The LLM returns valid output every iteration. There's no HTTP error, no exception, no crash. The failure is semantic — wrong plan, wrong tool, plausible garbage — and it burns budget while looking healthy.
- **Standard circuit breakers miss the shape.** Distributed system circuit breakers trip on error rates or latency percentiles. Agent loops produce no errors. You need token-velocity monitoring, not error-count monitoring.
- **Pre-flight enforcement beats post-hoc monitoring.** A $437 alert that fires after the damage is done is a postmortem tool, not a guard. The architectural primitive you need is a pre-call gate that terminates before the next API call, not a dashboard that reports what already happened.

## The move

Design budget guards as three independent enforcement layers — soft cap, hard cap, and circuit breaker. Each operates at a different granularity and requires a different trigger logic. No single layer is sufficient.

### Layer 1: Token Budget (per-call pre-flight gate)

Enforce token count **before** the API call, not after. Read the accumulated context size, compare against the per-task budget, and raise before the call, not after the bill arrives.

```python
import tiktoken

class TokenBudgetGuard:
    def __init__(self, max_tokens: int = 128_000, reserved: int = 4_096):
        self.encoder = tiktoken.get_encoding("cl100k_base")
        self.max_tokens = max_tokens
        self.reserved = reserved  # headroom for response

    def check(self, messages: list[dict]) -> tuple[bool, int]:
        """Returns (allow, current_tokens). Raises if over budget."""
        text = self._flatten(messages)
        count = len(self.encoder.encode(text))
        if count + self.reserved > self.max_tokens:
            raise TokenBudgetExceeded(count, self.max_tokens)
        return True, count

    def _flatten(self, messages: list[dict]) -> str:
        return "\n".join(f"{m['role']}: {m['content']}" for m in messages)
```

```python
# Enforce at the agent loop boundary
for step in agent_loop:
    guard.check(messages)
    response = llm.call(messages)
    messages.append(response)
    spend_tracker.record(response.usage.total_tokens)
```

### Layer 2: Hard Cost Cap (per-session ceiling)

Set a maximum dollar amount per task or per day. Enforce it at the session level — not per call. A single runaway task should not be able to spend more than its allocated budget regardless of how many loop iterations it attempts.

```python
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class CostCap:
    per_task_usd: Decimal = Decimal("5.00")
    per_day_usd: Decimal = Decimal("50.00")

class CostCeiling:
    def __init__(self, cap: CostCap, pricing: dict[str, float]):
        self.cap = cap
        self.pricing = pricing  # {"gpt-4o": 0.015, "o4-mini": 0.003}
        self.task_spend: Decimal = Decimal("0.00")
        self.day_spend: Decimal = Decimal("0.00")

    def preflight(self, model: str, tokens: int) -> None:
        """Raise before the call, not after the bill."""
        rate = Decimal(str(self.pricing.get(model, 0)))
        call_cost = Decimal(tokens) / 1000 * rate
        if self.task_spend + call_cost > self.cap.per_task_usd:
            raise BudgetExceeded(f"Task cap {self.cap.per_task_usd} reached")
        if self.day_spend + call_cost > self.cap.per_day_usd:
            raise BudgetExceeded(f"Day cap {self.cap.per_day_usd} reached")

    def record(self, model: str, tokens: int) -> None:
        rate = Decimal(str(self.pricing.get(model, 0)))
        self.task_spend += Decimal(tokens) / 1000 * rate
        self.day_spend += Decimal(tokens) / 1000 * rate
```

### Layer 3: Token Velocity Circuit Breaker

Circuit breakers for agents monitor token **velocity** — tokens per minute — not error counts. A healthy agent runs at 3,000–4,000 tokens/min (due to I/O wait time). A looping agent accelerates to 10,000+ tokens/min. Trip the breaker when velocity exceeds the threshold for the sustained window.

```python
import time
from collections import deque

class TokenVelocityBreaker:
    """
    Circuit breaker that monitors token burn rate, not error rates.
    Trips when tokens/min exceeds threshold for a sustained window.
    """
    def __init__(self, threshold_tpm: int = 10_000, window_sec: int = 60,
                 trip_duration_sec: int = 300):
        self.threshold = threshold_tpm
        self.window = window_sec
        self.trip_duration = trip_duration_sec
        self.tokens: deque[tuple[float, int]] = deque(maxlen=1000)
        self.tripped_until: float = 0
        self.trip_count: int = 0

    def record(self, tokens: int) -> None:
        self.tokens.append((time.time(), tokens))

    def check(self) -> bool:
        """Returns True if circuit is open (calls blocked)."""
        if time.time() < self.tripped_until:
            return True  # still tripped

        now = time.time()
        cutoff = now - self.window
        recent = [(t, tok) for t, tok in self.tokens if t >= cutoff]
        if not recent:
            return False

        total_tokens = sum(t for _, t in recent)
        window_hours = self.window / 3600
        tpm = total_tokens / window_hours

        if tpm > self.threshold:
            self.tripped_until = time.time() + self.trip_duration
            self.trip_count += 1
            return True
        return False

    @property
    def status(self) -> dict:
        return {
            "tripped": time.time() < self.tripped_until,
            "trip_count": self.trip_count,
            "window_tokens": sum(t for _, t in list(self.tokens)[-100:]),
        }
```

### Putting it together: the guard wrapper

```python
class BudgetGuardedAgent:
    def __init__(self, llm, token_cap=128_000, cost_cap=CostCap(),
                 velocity_threshold=10_000):
        self.llm = llm
        self.token_guard = TokenBudgetGuard(max_tokens=token_cap)
        self.cost_ceiling = CostCeiling(cost_cap, PRICING)
        self.velocity_breaker = TokenVelocityBreaker(threshold_tpm=velocity_threshold)

    def step(self, messages: list[dict]) -> dict:
        model = self.llm.model
        # Pre-flight: all three guards fire before the API call
        self.token_guard.check(messages)
        self.cost_ceiling.preflight(model, self.token_guard._flatten(messages))
        if self.velocity_breaker.check():
            raise AgentCircuitTripped(
                f"Token velocity exceeded {self.velocity_breaker.threshold} TPM "
                f"(trip #{self.velocity_breaker.trip_count})"
            )
        response = self.llm.call(messages)
        self.cost_ceiling.record(model, response.usage.total_tokens)
        self.velocity_breaker.record(response.usage.total_tokens)
        messages.append(response)
        return response
```

## Receipt

> Verified 2026-08-05 — Research sourced from: Nexgismo blog post "AI Agent Budget Guards" (HN, 1,278 upvotes, June 2026), Waxell "AI Agent Circuit Breakers" (May 2026), Safeguard.sh "Agentic AI Budget Explosions" (April 2026), AI Automation Global "Tokenmaxxing Is Dead" (2026), and AgentMarketCap "Agent Token Cost Optimization" (April 2026). Key data points: 97M monthly MCP SDK downloads, 16,000+ MCP servers indexed, 86% of MCP servers run locally (Lenses.io March 2026); agents consume ~50x more tokens than single-turn chatbots; $437 single-night runaway incident; $14,000 weekend pipeline bill (confirmed by Safeguard.sh). Production thresholds confirmed: 3K–4K tokens/min healthy, 10K+ tokens/min = looping agent. Composite score: Production Urgency 9 × 0.35 + Coverage Gap 8 × 0.25 + Specificity 9 × 0.20 + Timeliness 9 × 0.10 + Pattern Density 7 × 0.10 = **8.45**.

## See also

- [S-1003 · The Agent Failure Recovery Stack](/stacks/s1003-the-agent-failure-recovery-stack-when-your-agent-wont-stop-wont-finish-or-wont-tell-you-it-broke.md) — recursion limits and recovery contracts; this entry covers the orthogonal problem of cost containment before failure
- [S-2181 · The Thinking Token Budget Stack](/stacks/s2181-the-thinking-token-budget-stack-when-your-agents-internal-monologue-costs-more-than-you-do.md) — reasoning token visibility; this entry covers the architectural response to that visibility
- [S-06 · Model Routing](/stacks/s06-model-routing.md) — routing decisions; cost guards inform which model tier each task route should target
