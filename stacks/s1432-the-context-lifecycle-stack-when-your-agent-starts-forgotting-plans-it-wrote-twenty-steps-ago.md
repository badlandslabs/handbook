# S-1432 · The Context Lifecycle Stack — When Your Agent Starts Forgetting Plans It Wrote Twenty Steps Ago

You gave your agent a ten-step plan. Steps 1-7 went perfectly. By step 8, it asked you to re-explain the task. By step 12, it was contradicting the plan it had written. The context window was only 60% full. The model didn't change. The agent wasn't overloaded. The context lifecycle was never managed — and plans, written early and referenced late, are the first thing to get buried.

This is not a memory problem. Memory lives outside the context window. The context window is working memory: what the model can attend to *right now*. Plans, goals, sub-task outputs, intermediate reasoning — these are all context-resident. And context management has become load-bearing.

## Forces

- **Plans are context-time objects, not persistent state.** LLM agents do not internalize plans into weights. Plans must remain in context or be re-read from external storage. The moment an eviction strategy removes a plan without replacing it, the agent loses the thread. (Mehta & Datta, arXiv:2606.22953, June 2026)
- **Naive summarization is unpredictable and lossy.** When frameworks compact context, they pause the agent, summarize the transcript, and replace it. The summarizer's instantaneous salience judgment may evict exactly the piece the agent needs next — a plan fragment, a constraint, a dependency link. Context loss becomes plan loss.
- **Context windows are large but not infinite.** 200K–1M token windows feel roomy until a long-horizon task accumulates 89 steps across 80M tokens of history. The agent needs an *effectively unbounded* working horizon, which requires deliberate lifecycle management, not just a bigger window.
- **Four compaction strategies exist; knowing which to apply when is the actual problem.** Provider-native summarization, structured anchored compaction with persistent templates, external memory offload (MemGPT/Letta), and retrieval-augmented episodic memory — each wins in different regimes. A single strategy applied uniformly across a session fails.
- **Context rot is invisible.** Unlike a crash or error log, context degradation looks like the agent getting confused, repeating itself, or producing plausible-but-wrong answers. Without active lifecycle hooks, you don't know it's happening until the task fails.

## The move

Manage the context window as a first-class lifecycle system — not as a buffer that fills and then gets summarized. Three layers:

### 1. Annotate as you go — typed, dependency-linked episodes

The agent annotates its own trajectory during execution. Each episode is typed: `planning`, `retrieval`, `reasoning`, `tool_call`, `review`, `output`. Episodes carry dependency links: this `tool_call` produced output consumed by this `reasoning`. This structure is the substrate for eviction policy.

```
# Episode annotation schema (simplified)
episode = {
  "id": "ep_047",
  "type": "reasoning",
  "depends_on": ["ep_044", "ep_045"],  # tool outputs consumed
  "produces_for": ["ep_048", "ep_050"], # downstream consumers
  "tokens": 320,
  "age_turns": 3,
  "salience_score": 0.87  # LLM-assessed at write time
}
```

### 2. Structured eviction policy — not just "when full, summarize"

A deterministic, LLM-free policy evicts content in graduated priority order. From Semenov & Dorofeev's CWL scheme (arXiv:2606.11213, May 2026):

| Eviction priority | What gets evicted | Trigger |
|---|---|---|
| 1 (first) | Completed episode chains with no open dependents | `age > 3 turns AND dependents_complete` |
| 2 | Old tool outputs already consumed by reasoning | `produced_for.all(consumed=True)` |
| 3 | Reasoning trails for completed sub-tasks | `subtask.status == done AND age > 1` |
| 4 | Pruned exploration context (dead ends, abandoned paths) | explicit `prune` tag |
| Preserve | Active reasoning, open planning, user turns | `status == open` |

This preserves user turns, active reasoning, and the current plan while systematically clearing completed work. No LLM is consulted during eviction — the policy is deterministic.

### 3. Three-tier compaction strategy selection

Apply the right compaction strategy at the right lifecycle stage:

```
class ContextLifecycleManager:
    def select_compaction(self, budget_remaining_pct: float,
                          session_age_turns: int,
                          has_active_plan: bool) -> str:
        if budget_remaining_pct > 0.70:
            return "none"  # room to breathe
        elif budget_remaining_pct > 0.40:
            if has_active_plan:
                return "structured_prune"  # evict completed branches
            else:
                return "tiered_summarize"  # preserve structure
        else:
            return "critical_anchors"  # plan + user + current task only

    def structured_prune(self, ctx, episodes):
        """Evict completed episode chains — preserve open ones."""
        completed = [e for e in episodes
                     if e['depends_on']
                     and all(dep['status'] == 'done' for dep in e.deps)
                     and e['produces_for']
                     and all(dep['status'] == 'done' for dep in e.consumes)]
        return ctx.remove(completed)

    def critical_anchors(self, ctx):
        """Emergency: preserve only plan, user, current task."""
        return ctx.retain(
            types=['planning', 'user_turn', 'current_task'],
            replace_with='[...N completed steps summarized...]'
        )
```

### 4. Plan persistence layer — externalize what must survive

Because plans are context-time objects, active plans must be persisted externally and re-injected at retrieval points. This is not the same as memory — it's a narrower, more deliberate mechanism:

```
plan_store = {
    "plan_id": "task_14",
    "plan": "Step 1: fetch schema → Step 2: validate → Step 3: migrate",
    "current_step": 3,
    "status": "active",
    "last_used_turn": 12
}

# On every tool call boundary, re-inject if plan not in context
if "plan_id" not in ctx.active_plan_ids and plan_store["status"] == "active":
    ctx.inject(plan_store["plan"], tag="active_plan")
```

This is the fix for the Mehta & Datta finding: plans must be treated as externally persisted state, not as content that lives and dies in the context window.

## Tradeoffs

- **Annotation overhead.** Typed episode annotation adds code to every tool call and reasoning step. The payoff — structured eviction that doesn't lose active work — is worth it for long-horizon tasks.
- **Policy tuning.** The eviction priority order and age thresholds are task-dependent. A 50-step research task has different completed-chain patterns than a 5-step data pipeline. Start with the CWL defaults, tune triggers per workload type.
- **Summarization still needed for emergency recovery.** When structured eviction can't keep up (truly massive sessions), tiered summarization is the fallback — but it's now a safety net, not the primary strategy.

## Receipt

> Verified 2026-07-21 — arXiv:2606.11213 (Semenov & Dorofeev, May 2026) describes CWL achieving 89 sequential tasks across 80M tokens with no measurable degradation vs. isolated sessions. arXiv:2606.22953 (Mehta & Datta, June 2026) validates that plan persistence requires external storage. Anthropic's "Effective Context Engineering for AI Agents" (Sept 2025) provides the practitioner framework. Production validation: CWL's structured eviction vs. naive summarization baseline showed 23% accuracy improvement on multi-step task continuation in the paper's benchmark suite.

## See also

- [S-02 · Context Budget](s02-context-budget.md) — the foundational principle: treat the context window as a budget, not a bucket
- [S-1000 · The Context Exhaustion Stack](s1000-the-context-exhaustion-stack-when-your-agent-silently-degrades-as-the-window-fills.md) — when the window fills and the agent degrades silently
- [S-1430 · The Memory Quality-Gated Eviction Stack](s1430-the-memory-quality-gated-eviction-stack-when-your-memory-grows-to-infinity-and-your-agent-gets-dumber.md) — garbage collection for vector-stored long-term memory (not the context window)
