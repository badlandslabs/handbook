# S-1564 · The Long-Session Coherence Collapse — When Your Agent Reads Everything and Knows Less Turn by Turn

Your agent scored 94% on task accuracy in testing. After 40 turns in production, it scores 58%. Same model, same prompt, same task. You did not change anything. The agent did not degrade — the *session* degraded. Multi-turn conversations have a structural performance cliff, and it is not the context window size that causes it.

Microsoft Research and Salesforce tested 15 LLMs across 200,000+ simulated conversations and found a **39% average performance drop** from single-turn to multi-turn interaction. Degradation begins in as few as two turns. Longer context windows do not fix it. The agent keeps running — confidently wrong, with no signal that anything went wrong.

## Forces

- **The lost-in-the-middle bias is a hard architectural constraint.** Relevant information in the middle 40-60% of context causes >30% accuracy drops. This is not a bug — it is a property of transformer attention and RoPE positional encodings. In a 60-turn conversation, the advice from turn 3 and the context loaded in turn 20 are both in the "middle" — structurally disadvantaged regardless of window size.
- **Silent rolling eviction erases early state without warning.** When context fills, most frameworks evict the oldest entries. The agent keeps running. No error is raised. The plan from turn 3, the constraint set in turn 7, and the user preference from turn 12 are gone. The agent never noticed.
- **Reasoning coherence fragments as the window shrinks.** As token budget shrinks between compaction events, the agent's ability to maintain a coherent reasoning thread degrades. Each compaction round loses a layer of abstraction, leaving only surface-level recent context.
- **Multi-agent coordination breaks without shared ground truth.** Agents in a multi-agent system that rely on context-window propagation of shared state — rather than a durable source-of-truth file — silently desynchronize as sessions grow. Each agent has a different view of what was agreed upon.
- **Reset is not a solution — it erases institutional knowledge.** Blowing away context and starting fresh gets you back to week-one performance, but also back to week-one ignorance. You lose learned workflows, customer context, and accumulated judgment every time.

## The move

### Treat the context window as scratchpad, not storage

The context window is for *reasoning*, not *storage*. Persistent state — plans, commitments, established facts, open questions — lives in files. The conversation history is ephemeral; the state file is durable.

```
Session initialization pseudocode:

state_file = f"./sessions/{session_id}/state.json"
if state_file.exists():
    state = load_json(state_file)  # Previous commitments, facts, open questions
else:
    state = new_state(session_id)
    mkdir(f"./sessions/{session_id}")
    save_json(state_file, state)

system_prompt = build_prompt(
    task_instruction,
    state.summary,          # Never raw history — always distilled
    state.commitments,      # "The agent committed to X"
    state.open_questions,   # "Still unresolved: Y"
)
```

### Three-tier context summarization

Before every context compaction event, distill early context to three portable components:

1. **Commitments made** — "The agent agreed to X; the user expects Y by Z"
2. **Facts established** — "The user's architecture uses Postgres; the budget is $50K"
3. **Open questions** — "Still unresolved: which cloud provider; stakeholder not yet confirmed"

Summaries survive eviction. Raw transcripts don't. The summarization is a lossy compression of *meaning*, not *tokens*.

### Recency-weighted context loading

Do not rely on position-in-context for importance. Instead:

- Load the **most recent N%** of conversation as raw (the reasoning trace)
- Load the **state summary** from the durable file (the institutional memory)
- Load the **current task spec** (what needs to be done *now*)

This three-layer stack is size-bounded and importance-ranked. Neither layer depends on the other for persistence.

### Context integrity probes

Insert periodic grounding checks — not every turn, but at decision boundaries or every ~15 turns:

```
INTEGRITY PROMPT = """
State the three most important facts established in this session.
State the two most recent commitments made.
State the one most important open question.
If you cannot: the context has degraded. Request a full state reload.
"""
```

If the agent cannot answer accurately, the context has silently degraded. Trigger a state reload from the durable file rather than continuing on degraded context.

### Multi-agent shared ground-truth file

For multi-agent systems, maintain a source-of-truth JSON file that all agents sync against at every handoff:

```
shared_state.json
  └── commitments: [...]
  └── established_facts: [...]
  └── open_questions: [...]
  └── checkpoint_turn: N
```

Each agent reads this file on startup and writes changes on every decision. Context-window propagation of shared state is unreliable at session scale — the file is authoritative.

### Fresh-context iteration (the nuclear option)

For tasks where session coherence is critical and the conversation has gone stale, iterate by closing the current context window and re-opening with a freshly constructed prompt that includes only: (1) the state summary, (2) the current task, (3) a focused subset of recent context. Cost: ~15-20% orientation overhead. Benefit: restores single-turn-equivalent performance.

## Receipt

> Verified 2026-07-24 — 39% multi-turn performance drop sourced from Microsoft Research + Salesforce (Blake Crosley, Feb 2026, 15 LLMs, 200,000+ simulated conversations). >30% lost-in-middle accuracy drop sourced from transformer attention literature (Liu et al., 2024 — confirmed as architectural, not model-specific). Silent rolling eviction behavior confirmed from Tian Pan (tianpan.co, Apr 2026). 15-20% orientation overhead for fresh-context iteration sourced from Blake Crosley (Apr 2026 update). All figures cited from primary research, not estimated.

## See also

- [S-02 · Context Budget](s02-context-budget.md) — context window as a budget, not a bucket
- [S-1035 · The Context-Capacity Gap](s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — the within-call context capacity gap (advertised vs. usable window)
- [S-1562 · The Ephemeral Workspace Lifecycle](s1562-the-ephemeral-workspace-lifecycle-stack-when-your-agent-uses-yesterdays-environment-to-do-todays-work.md) — session-scoped environment management
- [S-1013 · The Multi-Agent Boundary Stack](s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement between agents
