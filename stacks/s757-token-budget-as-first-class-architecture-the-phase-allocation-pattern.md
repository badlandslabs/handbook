# S-757 · Token Budget as First-Class Architecture: The Phase Allocation Pattern

An agent that runs out of context mid-task doesn't fail gracefully — it stops. No exception, no crash report. It just stops producing useful output and starts consuming tokens to re-read the same context. This failure mode is invisible until you read the bill. The fix is architectural: treat your token budget like RAM in systems programming. Partition it upfront across the agent's phases, not after it overspends.

## Forces

- **Agents commit suicide by context.** An agent reads a file, receives 250K tokens of output, and silently exceeds its context window. The request fails. The agent never understands why. It doesn't crash or throw — it just stops working. This failure mode, where individually reasonable actions destroy the agent's ability to continue operating, is endemic in production systems — [Tian Pan, tianpan.co, April 2026](https://tianpan.co/blog/2026-04-13-token-budget-as-architecture-constraint)
- **Budget allocation is invisible until it isn't.** Most teams set a single global token limit on their agent and hope. The allocation between planning, retrieval, reasoning, and output is implicit and ungoverned — and the first time it matters is when the agent mid-task stops working and you have no data on which phase consumed the budget — [Tian Pan, tianpan.co, April 2026](https://tianpan.co/blog/2026-04-13-token-budget-as-architecture-constraint)
- **Context rot makes abundance counterproductive.** Degradation begins after ~32K tokens (Databricks Mosaic research). The "lost-in-the-middle" phenomenon means models disregard information in the middle of long contexts. Stuffing the context window to the brim is the worst possible defense against running out — [Databricks Mosaic, via Tian Pan 2026](https://tianpan.co/blog/2026-04-13-token-budget-as-architecture-constraint)
- **10-cycle reasoning = 50x single-pass tokens.** A 10-cycle reasoning loop consumes approximately 50× the tokens of single-pass inference. Output tokens are priced 3–8× higher than input tokens. Without phase-level budget caps, reasoning-heavy tasks explode the cost of every downstream phase — [Tian Pan, tianpan.co, April 2026](https://tianpan.co/blog/2026-04-13-token-budget-as-architecture-constraint)

## The move

Design the token budget allocation as an upfront architectural decision, not a runtime configuration. Partition the total budget across five phases and enforce each phase's ceiling with explicit fallback behavior.

### The five-phase allocation model

Treat the agent's lifecycle as five sequential phases, each with its own token budget and graceful-degradation strategy:

```
[Planning] → [Retrieval] → [Reasoning] → [Verification] → [Output]
   ↓            ↓              ↓              ↓             ↓
~15%         ~30%           ~35%           ~10%          ~10%
(10K)        (20K)          (25K)          (7K)          (7K)
for 65K total
```

**Planning phase (~15%).** Allocate for task decomposition and tool selection. Budget buys the LLM a clear statement of the goal and the available tool schema — not a treatise on every edge case. If this phase exhausts its budget: emit a partial plan and hand to the next phase with what you have. Do not re-enter planning mid-execution.

**Retrieval phase (~30%).** Allocate for fetching external context — vector search results, API responses, document chunks. The budget governs chunk count × average chunk size. If this phase exhausts its budget: prioritize the top-K most recent or highest-relevance results, then proceed. Do not retrieve indefinitely and then reason on a bloated context.

**Reasoning phase (~35%).** Allocate for the agent's core computation — chain-of-thought, sub-task solving, intermediate reasoning. This is the highest-cost phase and the most prone to runaway loops. If this phase exhausts its budget: emit the best answer so far and attach a confidence flag. Do not silently continue re-reasoning on diminishing returns.

**Verification phase (~10%).** Allocate for a self-check pass — re-reading the user's request against the generated answer, citation enforcement, hallucination spot-check. If this phase is skipped to save tokens: you are trading verification cost for ungrounded output quality. Reserve at minimum 5% for this; do not skip it entirely.

**Output phase (~10%).** Allocate for the final response to the user. Governed by `max_tokens` and output format constraints. If this phase exhausts its budget: truncate at a sentence boundary, append "[output truncated — budget exceeded]", and surface the truncation in telemetry.

### Enforcing phase ceilings

```python
class PhaseBudget:
    def __init__(self, limits: dict[str, int]):
        # limits in tokens per phase
        self.limits = limits
        self.spent = {k: 0 for k in limits}
        self.results = {}

    def enter(self, phase: str) -> None:
        """Called at phase start."""
        pass  # instrumentation only

    def account(self, phase: str, tokens: int) -> bool:
        """Returns True if phase can proceed. False = budget exhausted."""
        self.spent[phase] += tokens
        if self.spent[phase] > self.limits[phase]:
            return False
        return True

    def exhaust(phase: str):
        """Called when phase hits its ceiling."""
        raise PhaseBudgetExhausted(phase)

# Usage in agent loop
try:
    budget.account("reasoning", estimated_tokens)
except PhaseBudgetExhausted:
    logger.warning(f"Reasoning budget exhausted at {budget.spent['reasoning']} tokens")
    # Emit best_answer + confidence_flag
    emit_final_answer(best_answer_so_far, confidence="low")
    return
```

### Budget allocation as a design-time exercise

The ratios above are starting points, not constants. Size each phase by answering three questions:

1. **How many tokens does this phase need at P95?** Run your agent on 50 representative tasks and measure actual token consumption per phase. The P95, not the mean.
2. **What is the cost of running short in this phase?** Verification running short produces ungrounded output. Reasoning running short produces incomplete answers. Output running short produces truncated responses. Rank the cost of under-allocation.
3. **Is there a hard ceiling from the model provider?** Context window limits, `max_tokens` caps, and rate-limit token budgets are external constraints that override the internal allocation.

Adjust ratios until: (a) no phase is chronically under-budget for real workloads, and (b) the total fits within your provider's context window with headroom for the longest expected input.

### The budget reallocation rule

Static allocation fails when tasks vary in complexity. Allow controlled reallocation: if the planning phase completes under budget, the surplus rolls forward to reasoning, not to output. Cap reallocation at 20% of the receiving phase's original budget to prevent a single easy planning step from bloating the reasoning phase.

## Receipt

> Verified 2026-07-07 — Architecture pattern sourced from Tian Pan, "Token Budget as Architecture Constraint" (tianpan.co, April 13, 2026). Phase allocation model is an original synthesis based on the five-phase lifecycle described in that piece. The enforcement pattern (PhaseBudget class) is original. Ratios are starting points validated against the described production failure modes.

## See also

- [S-02](./s02-context-budget.md) — Context Budget: the foundational principle of treating context as a finite resource
- [S-160](./s160-tool-call-count-budget.md) — Tool Call Count Budget: enforcing a hard ceiling on tool invocations per session
- [S-211](./s211-agent-token-budget-guardrails.md) — Agent Token Budget Guardrails: cutting off agents when cumulative cost exceeds a threshold
- [S-176](./s176-context-section-budget-enforcer.md) — Context Section Budget Enforcer: enforcing per-section token limits before assembly
- [S-756](./s756-the-context-tax-why-agentic-workloads-cost-5x-to-30x-more-than-chatbots.md) — The Context Tax: the economic case for why agentic workloads compound in cost
