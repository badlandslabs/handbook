# S-1094 · The Context Budget Stack — When You're Out of Room at 60% Capacity

Your agent hit the context limit at turn 47. You upgrade to a model with a 200K-token window. You hit it again at turn 51. The problem was never the window size — it was that you never tracked what you were spending tokens on. Every production agent needs a context budget: an explicit accounting of what's in the window, what it's costing, and what gets evicted when space runs out.

## Forces

- **Context grows monotonically; performance degrades non-linearly.** As context length increases, effective attention spreads thinner. Models begin deprioritizing the middle of the context well before the window is full — often at 50–60% capacity. A 100K-token context can perform worse than a curated 30K-token one, while costing 3× more in API calls.
- **Silent eviction is the norm.** Most agent frameworks quietly drop the oldest context entries when space runs out. The agent keeps running. No error. No signal. Just degraded performance that nobody notices until a user reports it.
- **Token cost is invisible until it's a line item.** Without per-turn token accounting, teams don't know that a 200-turn debugging session cost $4.70 in context — versus $0.30 for the actual task. Cost compounding hides in the noise of "normal operation."
- **The right eviction policy depends on the step type.** A tool-result log from step 3 is worthless by step 40. A system constraint must survive to the last turn. A shared memory summary needs to be authoritative, not overwritten by a noisy intermediate state. One eviction policy fits nothing.

## The Move

Treat the context window as a managed budget — not a storage bin. Every token in the context has an owner, a cost, and a time-to-live.

### 1. Tag every context slot by role and age

Partition the context into labeled segments with explicit lifetimes:

```
┌─────────────────────────────────────────────────────────────────┐
│ SYSTEM PROMPT                    │ ~2K tokens │ NEVER evict     │
├─────────────────────────────────────────────────────────────────┤
│ TASK CONTEXT (instructions,       │ ~8K tokens │ Evict last     │
│ goals, constraints)               │             │                 │
├─────────────────────────────────────────────────────────────────┤
│ WORKING MEMORY (current session, │ ~16K tokens │ LRU eviction   │
│ tool results, intermediate state) │             │                 │
├─────────────────────────────────────────────────────────────────┤
│ ARCHIVAL SUMMARIES (compressed    │ ~4K tokens │ Keep, refresh   │
│ past sessions)                    │             │ periodically    │
├─────────────────────────────────────────────────────────────────┤
│ RETRIEVAL CONTEXT (RAG hits,      │ Variable    │ Highest        │
│ documents)                        │             │ eviction        │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Instrument token burn per turn

Before every LLM call, log:

```python
import tiktoken
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TurnBudget:
    turn_number: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    context_utilization_pct: float
    evicted_slots: list[str]
    timestamp: datetime

def check_context_budget(messages: list, model: str) -> TurnBudget:
    enc = tiktoken.encoding_for_model(model)
    total_tokens = sum(len(enc.apply_chat_template([m])) for m in messages)
    max_tokens = {"gpt-4o": 128_000, "claude-3-5-sonnet": 200_000}[model]
    utilization = (total_tokens / max_tokens) * 100

    # Warn at 60%, evict at 80%, hard-stop at 95%
    if utilization >= 95:
        raise ContextBudgetExceeded(f"At {utilization:.0f}% — evict before continuing")
    elif utilization >= 80:
        trigger_compaction()
    elif utilization >= 60:
        log_warning(f"Context at {utilization:.0f}% — plan eviction")

    return TurnBudget(
        turn_number=len(messages),
        input_tokens=total_tokens,
        output_tokens=0,
        cost_usd=total_tokens * COST_PER_1K_TOKENS,
        context_utilization_pct=utilization,
        evicted_slots=[],
        timestamp=datetime.now()
    )
```

### 3. Define eviction policies by slot type

```python
EVICTION_POLICIES = {
    "tool_result": {
        "max_age_turns": 10,       # Drop after N turns
        "max_age_seconds": 3600,   # Or N seconds of wall time
        "priority": "high_evict"
    },
    "retrieval_chunk": {
        "max_age_turns": 3,
        "relevance_threshold": 0.7,  # Evict chunks below this relevance score
        "priority": "highest_evict"
    },
    "task_context": {
        "max_age_turns": None,    # Never evict — survives whole session
        "priority": "never_evict"
    },
    "system_constraint": {
        "max_age_turns": None,
        "priority": "never_evict"
    },
    "session_summary": {
        "max_age_turns": 50,
        "refresh_trigger": "utilization_crosses(60%)",
        "priority": "late_evict"
    },
}

def compaction_pass(context_slots: list[ContextSlot]) -> list[ContextSlot]:
    """Run before every LLM call when utilization >= 60%."""
    kept = []
    for slot in context_slots:
        policy = EVICTION_POLICIES.get(slot.type, EVICTION_POLICIES["tool_result"])
        if policy["priority"] == "never_evict":
            kept.append(slot)
        elif should_evict(slot, policy):
            evicted.append(slot)   # Log for observability
        else:
            kept.append(slot)
    return kept
```

### 4. Budget-aware routing: summary vs. full context

Before each step, decide whether to pass the full history or a compressed summary:

```python
def budget_aware_routing(messages: list, model: str, step_type: str) -> list:
    utilization = estimate_context_utilization(messages, model)

    if step_type in {"planning", "safety_check", "final_answer"}:
        # These steps need full fidelity — compact aggressively if needed
        return messages

    if utilization > 80 and step_type == "tool_call":
        # Tool selection only needs: system prompt + current goal + available tools
        return prune_to_essential(messages, keep={"system", "task", "tools"})

    if utilization > 60:
        # Check if a session summary exists and is fresh (< 20 turns old)
        summary = get_fresh_summary(messages)
        if summary:
            return [system_prompt, summary] + recent_turns(messages, n=5)

    return messages
```

### 5. Set a cost ceiling per task

```python
TASK_BUDGETS = {
    "quick_reply":      {"max_tokens": 2_000,  "max_cost_cents": 0.5},
    "code_review":      {"max_tokens": 16_000, "max_cost_cents": 4.0},
    "multi_step_task":  {"max_tokens": 80_000, "max_cost_cents": 20.0},
    "deep_investigation": {"max_tokens": 150_000, "max_cost_cents": 50.0},
}

def run_with_budget(agent, task, task_type):
    budget = TASK_BUDGETS[task_type]
    spent = 0
    for turn in agent.run(task):
        spent += turn.cost_usd
        if spent > budget["max_cost_cents"]:
            raise BudgetExceeded(f"Ran {spent:.2f}c over {budget['max_cost_cents']}c limit")
        if turn.total_tokens > budget["max_tokens"]:
            raise BudgetExceeded(f"Ran {turn.total_tokens} tokens over {budget['max_tokens']} limit")
    return turn
```

## Receipt

> Verified 2026-07-14 — Chroma's Context Rot research (2026) confirms performance degrades as input length grows across every major model family. Anthropic's eval data shows context editing + memory lift yields +39% relative improvement over baseline. Claude Code triggers auto-compaction at 95% context utilization. The token budget concept maps directly to production failure modes observed in long-horizon agent deployments.

## See also

- [S-1035 · The Context-Capacity Gap](stacks/s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — the capacity problem (what the window can hold vs. what it actually uses)
- [S-1020 · The Tiered Memory Stack](stacks/s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — cross-session memory architecture
- [S-157 · Context Carry Cost Tracker](stacks/s157-context-carry-cost-tracker.md) — token-level cost accounting per context slot
