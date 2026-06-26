# S-21 · Context Compaction

When a session nears the context limit, summarize the old turns into a compact state and continue in a fresh window — so the agent keeps the thread without dragging the whole transcript.

## Forces
- Quality drops *before* the window fills — context rot degrades recall and instruction-following well short of the limit ([S-13](s13-context-engineering.md))
- A hard overflow fails loud and mid-action, leaving half-written state behind
- Old turns are mostly noise; a few decisions and the live task carry the work
- Summarizing is lossy — drop the wrong fact and the agent quietly forgets a rule it agreed to

## The move
- **Compact proactively, not reactively.** Trigger at a fill threshold (~70–80%), not at the limit. Recovering from a context failure costs far more than summarizing early.
- **Decide what survives.** Keep: architectural decisions, active goals, open tasks, file paths in play, error states. Drop: resolved sub-steps, dead-end tool outputs, boilerplate, superseded code. The hard part is not summarizing — it's choosing what survives.
- **Use provider-native compaction where it exists,** but know the tradeoff: server-side compaction is transparent to the run yet hides *what* was cut, so the agent loses visibility into its own state.
- **Combine, don't rely on one lever.** Pair compaction with external memory files ([S-09](s09-memory-systems.md)) for durable state and sub-agent delegation ([S-05](s05-multi-agent-patterns.md)) for bounded subtasks that return only a summary.
- **Cap recursion.** Compacting a compacted state compounds loss. Bound the depth.

This is [Law 2](../laws.md) (tokens are the budget) made continuous — you defend the budget across a long run, not just at the first call.

## Receipt
> Verified 2026-06-25 — a real compaction run against llama3.2 via Ollama (localhost:11435): a 6-turn project conversation, then a compact-and-continue in a fresh window.

```
history input tokens before compaction: 2653  (budget 1200)
--- compacted state (one summarize call) ---
- Refund cap without human approval: $50
- Refunds over $50 require a manager token
- Every refund is logged to the audit table
- Language: TypeScript / Runtime: AWS Lambda / Timeout: 30s
compacted state = 52 output tokens
--- continue on fresh window seeded with ONLY the summary ---
Q: "A $50 refund came in — does it need a manager token?"
A: "A $50 refund does not need a manager token; the cap without
    approval is $50, inclusive." (correct — preserved from turn 1)
```

The point the run makes: a **2653-token** history collapsed into a **52-token** compact state, and a fresh window carrying only that state still answered correctly from a rule set six turns back — the decisions survived the cut. Caveat: this run *chose* to preserve the refund rules; a summarizer that dropped them would have failed silently, which is exactly the risk. The bridge's per-call input counts were internally inconsistent, so the clean anchors are the two measured numbers (2653 raw, 52 compacted), not the intermediate call costs.

## See also
[S-13](s13-context-engineering.md) · [S-02](s02-context-budget.md) · [S-09](s09-memory-systems.md) · [S-05](s05-multi-agent-patterns.md) · [S-08](s08-prompt-caching.md)

## Go deeper
Keywords: `context compaction` · `context rot` · `context folding` · `compaction API` · `KV cache handoff` · `proactive summarization` · `auto-compact`
