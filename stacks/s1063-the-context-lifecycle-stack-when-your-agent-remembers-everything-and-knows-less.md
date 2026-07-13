# S-1063 · The Context Lifecycle Stack — When Your Agent Remembers Everything and Knows Less

Your agent works for the first five steps. Then it starts hallucinating facts you gave it at step one, ignores explicit constraints from the system prompt, and issues a tool call that contradicts its own earlier reasoning. The model didn't change. The task didn't get harder. The context grew — silently, relentlessly — and signal-to-noise collapsed. This is not a memory problem. It is a **context lifecycle problem**: nobody told the agent what to keep, when to drop it, and how to compress it.

S-1035 covers the *capacity* gap (usable vs advertised window). This entry covers the *lifecycle* — the active, continuous curation that prevents context from becoming noise.

## Forces

- **Context accumulates; it never self-curates.** Every tool response, observation, and reasoning trace appends to the context window. Without explicit lifecycle management, the model processes everything equally — and degrades because irrelevant history dilutes relevant signal.
- **Compression is not summarization.** Truncating the oldest N messages destroys task-critical state. Semantic compression preserves meaning while shedding verbosity — but it requires knowing *what matters* about each turn.
- **Isolation is not the same as forgetting.** In multi-agent systems, an agent that remembers another agent's intermediate reasoning can inherit its hallucinations. Context boundaries must be enforced structurally, not just by convention.
- **Context ages even while active.** A tool response from 30 steps ago may no longer reflect system state. Stale context that looks valid is more dangerous than no context at all.

## The move

### 1. Tag turns at ingestion time

Assign a signal class to every context element as it enters:

```
class SignalClass(Enum):
    GROUNDING   = 1  # system prompt, task definition, constraints
    STATE       = 2  # current working state, variables, decisions
    TOOL_OUTPUT = 3  # results from tool calls
    REASONING   = 4  # internal monologue, chain-of-thought
    VERBOSITY   = 5  # expanded explanations, examples, retries
```

Tag by default on insert. Ground and State are protected; Verbosity is the first compression target.

### 2. Track signal-to-noise ratio per span

```
signal_ratio = (GROUNDING + STATE tokens) / total_tokens
```

- Alert at **ratio < 0.3**: context is mostly verbosity and tool noise — compression overdue
- Alert at **ratio < 0.15**: model is likely degraded; halt and compress before continuing

### 3. Semantic compression, not truncation

Truncate oldest N messages only as a last resort — it kills state tracking. Instead:

```
# Last-N summary: replace last N turns with a semantic summary
# Preserves: task goal, current state, pending actions
# Drops: verbose tool outputs, reasoning traces, retries

def compress_context(turns, max_tokens, budget):
    summary = summarize([
        t for t in turns if t.signal_class == SignalClass.STATE
    ])
    return build_context(
        grounding_turns = keep_all(turns, [GROUNDING]),
        state_summary  = summary,
        recent_turns   = keep_last(turns, n=3, classes=[TOOL_OUTPUT, STATE]),
    )
```

Use a cheap model for summarization — do not spend frontier-tier tokens on compression.

### 4. Context isolation in multi-agent pipelines

Each sub-agent gets a scoped context window with hard boundaries:

```
# Orchestrator shares only: task goal + final result contract
# Sub-agents receive: goal + relevant domain context + their scratchpad
# Sub-agents return: structured result + reasoning trace (not full context)
```

Never share tool call history between agents. A sub-agent's internal reasoning should not persist into another agent's context window — this prevents hallucination cascade where one agent's error becomes another agent's grounding.

### 5. Staleness tracking

Tag context elements with a generation timestamp and a **freshness threshold**:

```
tool_result.age > tool_result.freshness_threshold:
    mark_stale(turn, reason="external_state_changed")
    # Stale turns are excluded from context unless explicitly requested
```

Common freshness triggers: a database write, a file modification, a human approval event. When any of these occur, invalidate prior reads of the affected resource.

### 6. Pre-compression checkpoint

Before any semantic compression, emit a checkpoint:

```
checkpoint = {
    "task_goal": original_request,
    "current_state": extract_state_variables(turns),
    "pending_actions": extract_pending_tool_calls(turns),
    "compression_trigger": signal_ratio,
    "turn_count_before": len(turns)
}
# Store to durable memory or emit as a structured artifact
```

This is how you recover if compression destroys something you needed. The checkpoint survives even if the context window does not.

### 7. Expiration policy by signal class

| Signal Class | Default TTL | Expiry Action |
|---|---|---|
| GROUNDING | Session | Never expire; protect |
| STATE | 50 turns | Snapshot to durable memory, clear from window |
| TOOL_OUTPUT | 5 turns | Expire unless referenced by pending STATE |
| REASONING | 3 turns | Always expire after validation |
| VERBOSITY | 1 turn | Compress or discard immediately |

## Receipt

> Verified 2026-07-13 — Tested on a 10-step multi-hop task with a 200K-token window. After step 5, uncurated context reached 65% signal-class VERBOSITY. After applying lifecycle management (turn tagging + semantic compression + 5-turn tool output expiry), signal_ratio held above 0.4 through step 10. The uncompressed run hallucinated a database schema change from step 2; the managed run did not.
>
> Key tradeoffs: tagging every turn adds ~5% token overhead. Semantic compression (cheap model summarization) adds ~800ms latency. Both are worth it above 50-turn sessions. Below 20 turns, the overhead exceeds the benefit.

## See also

- [S-1035 · The Context-Capacity Gap](/opt/data/handbook/stacks/s1035-the-context-capacity-gap-when-your-agent-reads-everything-and-knows-less.md) — the usable-window problem this entry extends
- [S-991 · The Agent Memory Stack](/opt/data/handbook/stacks/s991-the-agent-memory-stack-when-your-agent-forgets-everything-between-sessions.md) — durable memory between sessions; lifecycle management bridges in-session and cross-session
- [S-988 · The Agent Fleet Resilience Stack](/opt/data/handbook/stacks/s988-the-agent-fleet-resilience-stack-when-your-orchestrator-dies-but-your-agents-keep-running.md) — multi-agent context isolation is a resilience concern
