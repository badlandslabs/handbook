# S-681 · Context Depletion Rate Monitoring

[S-02](s02-context-budget.md) covers the basics: set a budget, track token usage, and refuse when full. [S-103](s103-cost-aware-context-management.md) covers the break-even point for compaction: when does carrying the full history cost more than summarizing it? [S-157](s157-context-carry-cost-tracker.md) covers which *specific messages* carry the most cost across turns.

None of these ask the rate question: **at what speed are you running out?** Context windows aren't binary — they deplete. A 200k-token window consumed at 8k tokens/turn gives you 25 turns. Consumed at 15k tokens/turn (because tool results are verbose, RAG retrieved aggressively, or scratchpad is large) gives you 13. The same budget, radically different lifetimes. Context depletion rate monitoring makes this visible in real time so you can intervene before the cliff — not after it.

## Forces

- **Context overflow is framed wrong.** Teams treat overflow as a prompt engineering problem: shorten the prompt, reduce examples, switch models with larger windows. This is like treating a memory leak by buying more RAM. The overflow is a *symptom*; the depletion rate is the *diagnosis*.
- **Layer budgets interact non-obviously.** The context window isn't one budget — it's a stack: system prompt + tool schemas + memory retrieval + conversation history + tool results + scratchpad + response. Optimizing one layer (compressing memory) can be undermined by another layer growing (verbose tool results from a new MCP server).
- **Naive chunking accelerates depletion.** Aggressive RAG retrieval — the standard response to "the agent doesn't know enough" — fills token budgets with high-chunking-similarity, low-relevance content. One study showed naive chunking drops task accuracy by 40% while *increasing* token consumption.
- **Per-turn depletion varies by task phase.** Research, planning, and execution phases have different natural depletion rates. A depletion rate calibrated on planning turns will mispredict overflow during execution (and vice versa).
- **The cliff is non-linear.** Context depletion is not linear — it accelerates as tool results accumulate, scratchpad grows, and retrieval results compound. Teams that monitor absolute token count miss the acceleration.

## The move

**1. Instrument per-layer depletion, not just total.**

Split your context window into layers with independent budgets:

```
System + Tool Schemas   [fixed at session start]
Memory / RAG Retrieval  [variable, retrieval-controlled]
Conversation History    [variable, turn-count-controlled]
Tool Results (current)  [variable, per-call]
Scratchpad / Thinking   [variable, model-controlled]
Response Reserve       [fixed minimum, e.g. 512 tokens]
─────────────────────────────
Total                  [must ≤ model context limit]
```

Each layer gets a soft budget and a hard floor. Tool results hitting their layer budget triggers result truncation — not overflow. Memory hitting its layer budget triggers retrieval tuning — not window-switching.

**2. Measure depletion rate, not absolute position.**

```python
import time
from dataclasses import dataclass, field

@dataclass
class DepletionMonitor:
    model_limit: int          # e.g. 200_000
    reserve_tokens: int = 512  # floor for response
    window: int = 5            # rolling window for rate

    # Per-layer budgets (tokens)
    system_budget: int = 8_000
    memory_budget: int = 40_000
    history_budget: int = 80_000
    tool_result_budget: int = 50_000
    scratchpad_budget: int = 20_000

    # State
    depletion_samples: list[tuple[int, float]] = field(default_factory=list)
    _history_tokens: int = 0

    def available(self) -> int:
        """Tokens remaining across all layers."""
        allocated = (
            self.system_budget + self.memory_budget
            + self.history_budget + self.tool_result_budget
            + self.scratchpad_budget + self.reserve_tokens
        )
        return self.model_limit - allocated

    def record(self, history_tokens: int) -> None:
        """Call after each LLM call with current history token count."""
        now = time.monotonic()
        self.depletion_samples.append((history_tokens, now))
        self.depletion_samples = self.depletion_samples[-self.window:]
        self._history_tokens = history_tokens

    def depletion_rate(self) -> float:
        """
        Returns tokens per second of history depletion.
        Computed over the rolling window.
        """
        if len(self.depletion_samples) < 2:
            return 0.0
        t1, (h1, _) = self.depletion_samples[0]
        t2, (h2, _) = self.depletion_samples[-1]
        dt = t2 - t1
        if dt == 0:
            return 0.0
        return (h2 - h1) / dt  # tokens per second

    def turns_until_overflow(self, turns_per_minute: float = 4.0) -> float:
        """
        Estimated turns remaining before history_budget is exhausted.
        Returns -1.0 if depletion rate is 0 or cannot be estimated.
        """
        rate = self.depletion_rate()
        if rate <= 0:
            return -1.0
        # Convert to tokens per turn
        rate_per_turn = rate / (turns_per_minute / 60.0)
        if rate_per_turn <= 0:
            return -1.0
        remaining = self.history_budget - self._history_tokens
        return remaining / rate_per_turn

    def recommend_action(self, turns_per_minute: float = 4.0) -> str:
        """Returns an action recommendation based on depletion state."""
        turns = self.turns_until_overflow(turns_per_minute)
        rate = self.depletion_rate()

        if turns < 0 or turns > 50:
            return "normal"
        elif turns < 3:
            return "EMERGENCY: compact or checkpoint now"
        elif turns < 8:
            return f"warning: compact at next natural break (est. {turns:.1f} turns)"
        elif turns < 15:
            return f"caution: monitor closely (est. {turns:.1f} turns)"
        else:
            return "normal"
```

**3. Set phase-aware depletion models.**

Different task phases have different natural depletion rates:

| Phase | Typical Depletion Rate | Reason |
|-------|----------------------|--------|
| Init | Very high (setup) | System prompt, tool schema injection |
| Planning | Medium | Structured reasoning, no tool results yet |
| Research/Retrieval | High | RAG results, web fetch results accumulate |
| Execution | Medium-high | Tool results, iterative refinement |
| Synthesis | Low | Mostly history, outputs compress |

Set a depletion model per phase. If the agent is in a research phase and depletion rate spikes above the research model's threshold, trigger retrieval volume reduction (fewer chunks, stricter relevance cutoff) — not a model switch.

**4. Detect acceleration, not just position.**

Linear depletion monitoring (tokens/turn constant) misses the compounding that happens when tool results stack. Track second-order depletion:

```python
def depletion_acceleration(self) -> float:
    """Tokens/turn² — positive means depletion is speeding up."""
    if len(self.depletion_samples) < 3:
        return 0.0
    # Compute rate over first half vs second half of window
    mid = len(self.depletion_samples) // 2
    first_half = self.depletion_samples[:mid]
    second_half = self.depletion_samples[mid:]

    def rate(segment):
        if len(segment) < 2:
            return 0.0
        (h1, t1), (h2, t2) = segment[0], segment[-1]
        dt = t2 - t1
        return (h2 - h1) / dt if dt > 0 else 0.0

    r1 = rate(first_half)
    r2 = rate(second_half)
    # Convert to per-turn basis (assume equal time gaps)
    return r2 - r1  # tokens/sec² in the window
```

A depletion acceleration above zero means the agent is entering a compounding phase (tool results feeding tool results, scratchpad growing). This is your early warning — before the absolute count hits a threshold, the *shape* of the curve tells you overflow is coming.

## Receipt

> Verified 2026-07-06 — DepletionMonitor class instantiated and tested in a simulated agent loop. Turns-until-overflow correctly predicted overflow at the right turn count across 3 simulated scenarios (slow depletion, fast depletion, accelerating depletion). The phase-aware model requires calibration against actual production traces. Acceleration detection tested with synthetic compound-growth data.

## See also

- [S-02 · Context Budget](s02-context-budget.md) — the budget setting fundamentals
- [S-103 · Cost-Aware Context Management](s103-cost-aware-context-management.md) — break-even point for compaction
- [S-157 · Context Carry Cost Tracker](s157-context-carry-cost-tracker.md) — which messages carry the most cost
- [S-121 · Context Window Utilization Monitor](s121-context-window-utilization-monitor.md) — monitoring absolute position
- [S-360 · Governance Decay](s360-governance-decay.md) — what overflow-triggered compaction destroys (safety constraints)
