# S-1492 · The Context Dump Fallacy Stack — When More Context Makes Your Agent Worse

You have a multi-agent system. Agent A finishes a task and hands off to Agent B. Engineer instinct: include everything Agent A knows. So you dump the full conversation history, all intermediate outputs, all tool results, all reasoning traces. Agent B gets 50 pages of context. It produces worse output than it would have with just the original task brief.

This is the Context Dump Fallacy: the mistaken belief that transferring more raw context improves downstream reasoning quality. In practice, unstructured context dumps increase noise, bury critical decisions, and degrade the receiver's ability to reason clearly. The receiving agent is not a human who can scan for relevance — it is an LLM whose attention diffuses across the window.

## Forces

- **More context feels safer.** Engineers reason: "the agent needs to know everything to do the job right." The intuition maps from human collaboration (more context = better decisions) to agent collaboration where the cost of irrelevant tokens is not just waste but active degradation.
- **Structured handoffs feel risky.** Typed handoff schemas, decision logs, and annotated summaries feel like over-engineering. The original task brief already had the information. The agent should be able to figure it out.
- **Information theory says noise is not free.** Claude Shannon's 1948 paper established that channel capacity is finite and noise degrades signal. Unstructured context dumps inject noise proportional to the irrelevant fraction of the transfer. The receiver's context window is a noisy channel, and the signal-to-noise ratio determines output quality.
- **Agents can't self-filter at handoff.** A human receiving a 50-page context dump can scan for relevance. An LLM absorbs all tokens into its attention context — irrelevant tokens compete with relevant ones for the same finite reasoning capacity. The agent doesn't "ignore" noise; it processes it at a cost.

## The Move

**Pass structured decisions, not raw context.** The handoff message should contain three components:

1. **Decision log** — what Agent A decided and why, not just what it produced. The rationale is the signal; the output is the artifact.
2. **Structured state snapshot** — typed key-value facts about the task state, not transcript excerpts. `{findings: [...], rejected_approaches: [...], next_agent_task: "..."}`.
3. **Confidence markers** — where Agent A was uncertain, which findings are verified vs. inferred, what remains unresolved. This lets Agent B allocate reasoning budget intelligently.

**Key principle: intent over transcript.** The question is never "what did Agent A know?" but "what does Agent B need to decide correctly?"

```python
# Context Dump Fallacy — naive handoff
handoff = {
    "conversation_history": full_messages,       # noise
    "all_tool_results": all_tool_outputs,       # noise
    "reasoning_trace": complete_chain,           # mostly noise
    "original_task": original_brief              # signal
}

# Structured decision handoff
handoff = {
    "decisions": [
        {"what": "searched GitHub API", "why": "no local cache hit", "confidence": "high"},
        {"what": "filtered to Python repos", "why": "user referenced Python", "confidence": "medium"},
        {"what": "skipped archived repos", "why": "activity < 2024", "confidence": "high"},
    ],
    "state": {
        "repo_count": 3,
        "top_repo": "owner/repo",
        "findings_summary": "...",
        "unresolved": ["whether rate-limit applies to user tokens"]
    },
    "next_task": "Summarize findings for non-technical stakeholder"
}
```

## Receipt

> Verified 2026-07-22 — Corbits blog (May 28, 2026): multi-agent systems fail at handoffs, not at individual agents. Each agent produces reasonable output in isolation; the chain loses the thread at transfer points. XTrace blog (July 21, 2026): "context dump fallacy" named and formalized. Shannon information theory cited as the theoretical foundation. Signal Stack (2026): real-world case where a research agent produced confident "research complete" text with zero tool calls — failure to pass structured tool-call evidence meant the downstream agent had no signal to detect the absence.

## See also

- [S-1013 · The Multi-Agent Boundary Stack](/stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state disagreement between agents; this entry is the handoff mechanism failure that precedes state disagreement
- [S-1019 · The Ghost Loop Stack](/stacks/s1019-the-ghost-loop-stack-when-your-agent-decides-its-own-workflow-and-nobody-traced-it.md) — implicit workflow decisions with no audit trail; handoff logs are the antidote to ghost loops
- [S-1085 · The Three-Tier Memory Stack](/stacks/s1085-the-three-tier-memory-stack-why-your-agent-forgets-and-how-to-stop-it.md) — episodic/semantic/procedural memory for agents; structured handoff is the real-time equivalent of semantic memory injection
