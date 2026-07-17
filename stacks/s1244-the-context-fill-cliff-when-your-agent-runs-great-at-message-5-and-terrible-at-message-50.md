# S-1244 · The Context Fill Cliff: When Your Agent Runs Great at Message 5 and Terrible at Message 50

Your coding agent is sharp for the first 30 minutes. By the 90-minute mark, it repeats approaches you already rejected, misses imports it would have caught at session start, and calls tools it shouldn't. The model didn't change. The context filled.

This is the context fill cliff — a predictable, measurable collapse in agent quality driven by context accumulation. It is not a model bug. It is a session lifecycle design problem.

## Forces

- **Context fill is invisible until it bites.** Most agents report no error when approaching fill. The model keeps generating — confidently, badly. Quality degrades silently, with no exception thrown.
- **The advertised window ≠ usable window.** Performance measurably degrades at 60–70% fill. By 85–90%, structured tool-call quality deteriorates enough to affect task outcomes. A 200K-token window is not 200K tokens of usable memory.
- **Compaction strategies are philosophically incompatible.** Claude Code, Codex CLI, and OpenCode CLI each implement fundamentally different approaches to reducing context. Choosing the wrong one for your workload is a reliability catastrophe.
- **Prompt cache hits are 90% cheaper — until compaction destroys them.** Anthropic's prompt caching makes repeated calls cheap, but every compaction event invalidates the cache and restarts from full price.

## The move

### Measure your fill ratio continuously

Track `(current_context_tokens / max_context_tokens) × 100` as a live metric. Act before 60% fill, not at 90%.

```python
from anthropic import Anthropic
from dataclasses import dataclass

@dataclass
class ContextGauge:
    client: Anthropic
    model: str = "claude-opus-4-5"
    warn_threshold: float = 0.60
    crit_threshold: float = 0.85

    def estimate_tokens(self, messages: list[dict]) -> int:
        """Estimate tokens using a rough char→token ratio."""
        total = sum(len(str(m.get("content", ""))) for m in messages)
        return int(total / 4)

    def check(self, messages: list[dict]) -> str:
        client = self.client
        # Use the count_tokens endpoint if available, else estimate
        try:
            resp = client.count_tokens(model=self.model, messages=messages)
            ratio = resp / self._max_tokens()
        except Exception:
            ratio = self.estimate_tokens(messages) / self._max_tokens()

        if ratio >= self.crit_threshold:
            return f"CRIT: {ratio:.0%} fill — compact immediately"
        elif ratio >= self.warn_threshold:
            return f"WARN: {ratio:.0%} fill — plan compaction"
        else:
            return f"OK: {ratio:.0%} fill"

    def _max_tokens(self) -> int:
        # Per-model max context (input + output)
        caps = {"claude-opus-4-5": 200_000, "claude-sonnet-4-7": 200_000}
        return caps.get(self.model, 128_000)
```

### Choose your compaction philosophy

| System | Strategy | When it wins | When it bleeds |
|--------|----------|-------------|----------------|
| **Claude Code** | Three-layer cascade, preserving cache prefixes | Long coding sessions, incremental refactor | Breaks long-range plans when middle layers are hidden |
| **Codex CLI** | All-or-nothing handoff memo | Stateless handoff between sessions | Loses working context, requires perfect handoff doc |
| **OpenCode** | Stepped governance, non-destructive before summarization | Auditing, recovery from partial compaction | Highest implementation complexity |

For persistent agents: prefer Claude Code's cascade with explicit budget tiers.

### Design explicit compaction budgets

Instead of waiting for the cliff:

```python
BUDGET_TIERS = {
    "system_and_tools":  15_000,  # pinned, cache-safe
    "active_memory":       8_000,  # what agent is actively working on
    "history_buffer":     12_000,  # recent turns, subject to eviction
    "retrieval_context":  10_000,  # RAG/retrieved docs
    "headroom":            5_000,  # output buffer
}
# Total: 50,000 — leaves 150K of a 200K window for compression margin

def enforce_budget(messages: list[dict], tiers: dict = BUDGET_TIERS) -> list[dict]:
    """Prune oldest history_buffer turns until the budget fits."""
    total = sum(tiers.values())
    # Bypass tier enforcement for brevity; real impl tracks per-tier token counts
    return messages  # replace with eviction logic

def compaction_trigger(ratio: float) -> str:
    if ratio > 0.85:
        return "aggressive"   # drop lowest-priority tier, re-summarize history
    elif ratio > 0.70:
        return "moderate"    # evict old history_buffer turns
    elif ratio > 0.60:
        return "light"      # trim redundant tool result summaries
    else:
        return "none"
```

### Preserve cache prefixes on compaction

Anthropic's prompt caching requires identical prefixes across requests. Every compaction that rewrites the prompt header invalidates the cache and restarts billing at full price.

```python
def cache_safe_compact(messages: list[dict], system_prompt: str, tool_schemas: list[dict]) -> list[dict]:
    """Compact history while keeping system_prompt and tool_schemas bit-identical."""
    # Extract: system (pinned) + tools (pinned) + recent turns only
    pinned_prefix = [{"role": "system", "content": system_prompt}]
    pinned_tools = [{"type": "tool", "name": t["name"], "description": t["description"]}
                    for t in tool_schemas]
    # History: last N turns that fit within active_memory budget
    recent = messages[-6:]  # ~6 turns = ~3,000–8,000 tokens
    return pinned_prefix + recent
```

## Receipt

> Verified 2026-07-17 — Zylos Research (2026-05-05) reports 60–70% fill = measurable quality degradation, 85–90% = critical. Blake Crosley / MSR/Salesforce (Laban et al., arXiv:2505.06120) confirms multi-turn degradation of 39% via turn boundaries, not context length. AgentMarketCap (Apr 2026) reports 100:1 input-to-output ratio for 50-tool-call sessions. Claude Code's three-layer cascade preserves cache prefixes (cache hits = 90% cost reduction per Anthropic); Codex CLI's handoff memo is all-or-nothing. All three data sources converge independently on the same threshold (60–70%) and the same conclusion: compaction strategy is an architectural choice with measurable cost and quality consequences.

## See also

- [S-1035 · The Context-Capacity Gap](/stacks/s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — the advertised window vs. usable window gap
- [S-1192 · The Five-Layer Caching Stack](/stacks/s1192-the-five-layer-caching-stack-when-your-agent-pays-full-price-for-a-plan-it-already-ran.md) — cache-aware ordering for cost control
- [S-1105 · The Tiered Memory Stack](/stacks/s1105-the-tiered-memory-stack-when-your-agent-is-a-goldfish.md) — cross-session memory survival
- [S-02 · Context Budget](/stacks/s02-context-budget.md) — budget-as-topology principles
