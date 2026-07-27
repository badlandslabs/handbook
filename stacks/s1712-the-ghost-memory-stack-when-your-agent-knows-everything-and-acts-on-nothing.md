# S-1712 · The Ghost Memory Stack — When Your Agent Knows Everything and Acts on Nothing

Your agent has the user's address in memory — three addresses, actually. The one from January, the one from April, and the one they updated last Tuesday. The user asks where to ship their order. The agent, acting in good faith, ships to the January address. The user moved. The package is gone. The agent is confused: it retrieved the right information, the vector similarity was high, and every fact was accurate at the time it was stored. The failure wasn't the data. The failure was that the memory bank had no mechanism to determine *which fact should answer this question right now*. This is ghost memory: a state coordination failure, not a retrieval failure.

## Forces

- **Persistent memory introduces temporal multiplicity.** Long-term agent memory accumulates facts over time. When a user fact changes — an address, a name, a policy, a team member — the old fact doesn't disappear. It coexists with the new one. Vector retrieval sees them all as equally relevant. Neither timestamps nor embedding similarity resolve which is live.
- **Simple deletion loses history.** The naive fix is to overwrite old facts. But then you lose institutional knowledge — the history of changes, the reasoning behind them, the record of past states that might be legally or operationally required. Ghost memory is not solved by amnesia.
- **Timestamps don't solve it.** A fact with a recent timestamp is not necessarily the live fact. The user may have updated a phone number, then reverted it, then updated it again. The most recent write is not always the authoritative current state. And in multi-agent systems, different agents may write at different times with different clocks.
- **The LLM can't distinguish state roles during retrieval.** Standard retrieval returns evidence sorted by relevance. It returns the evidence — all evidence — and the LLM must decide what to use. But the LLM has no explicit state role metadata. It sees facts, not temporal states.

## The Move

### Understand the Three Roles

Every fact in a stateful memory system has one of three temporal roles:

1. **Live fact** — the fact that should answer the question *right now*
2. **Historical fact** — a fact that was true and is still recorded for history, audit, or continuity
3. **Transition fact** — a fact recorded during a change event (e.g., "updating address from X to Y"), useful for understanding the delta but not answering the current state question

Ghost memory occurs when these roles are mixed during evidence construction — when a historical address is retrieved alongside the live address and the model has no signal to prefer one.

### Add State Semantics to Memory (A-TMA Pattern)

The **Adaptive Temporal Memory Alignment (A-TMA)** framework adds a state-aware overlay to existing memory pipelines without replacing them. Three changes:

**1. State-role tagging at write time.** When a memory write occurs, tag it with a state role and, for live facts, the version of the entity being described:

```
memory.write({
  content: "User address: 742 Evergreen Terrace",
  state_role: "live",        // live | historical | transition
  entity_type: "user_address",
  entity_id: "user_123",
  version: "v3",             // monotonically increasing
  timestamp: 1751059200,
  change_event: null        // set if transition fact
})
```

On update, the previous live fact is automatically re-tagged to `historical` and linked to the change event.

**2. State-role filter at retrieval time.** Query the memory bank with a state role filter:

```
memory.query(
  query="where should we ship",
  entity_filter="user_address",
  state_role="live",         // retrieve only live facts by default
  include_history=False
)
```

This separates the retrieval path. You can separately query for history when needed (audit, debugging, user review) but the default path returns only live facts.

**3. State-aware evidence construction.** When both live and historical facts are retrieved (e.g., for a "why did this change?" query), annotate each fact with its state role before passing to the LLM:

```
Evidence:
- [LIVE] User address: 742 Evergreen Terrace (updated 2026-07-25)
- [HISTORICAL] User address: 123 Main St (was live until 2026-04-03)
```

This lets the LLM reason about state explicitly rather than inferring it from context.

### Implement the Temporal Memory Gate

The Temporal Memory Gate is a lightweight middleware layer (drop-in compatible with LlamaIndex, LangChain, CrewAI backends per OWASP Agent Memory Guard v0.3.0+) that enforces state-role discipline at the retrieval boundary:

```python
class TemporalMemoryGate:
    def __init__(self, memory_store, default_role="live"):
        self.store = memory_store
        self.default_role = default_role

    def retrieve(self, query, user_id, role=None):
        role = role or self.default_role
        facts = self.store.get_by_role(
            entity_id=user_id,
            state_role=role,
            entity_type="user_fact"
        )
        return self._annotate_with_state(facts)

    def write(self, fact, role="live"):
        if role == "live":
            # Demote existing live facts to historical
            existing = self.store.get_live(entity_id=fact.entity_id)
            for old in existing:
                old.state_role = "historical"
                old.change_event = fact.change_event
                self.store.put(old)
        self.store.put(fact)
```

### Handle Transition Facts Explicitly

Change events are first-class citizens. Store them with a structured schema:

```
change_event: {
  type: "update",
  field: "address",
  from: { value: "123 Main St", version: "v2" },
  to: { value: "742 Evergreen Terrace", version: "v3" },
  reason: "user_updated_profile",
  agent_id: "agent_abc"
}
```

This makes it possible to answer both "what is the current address?" (live fact) and "why did the address change?" (change event chain) without ambiguity.

### Provide a Memory Audit Interface

Enterprise agents need to surface memory state to human operators. Build a management UI (Microsoft Agent Framework's memory management panel pattern) that shows:

- All live facts for a given entity — and their sources
- Historical versions with timestamps and change events
- Transition facts awaiting confirmation
- Explicit "forget this fact" / "confirm this fact as live" controls

This is the human-in-the-loop gate for memory integrity. The agent can't self-correct ghost memory without visibility.

## See Also

- [S-1579 · Clock-In/Clock-Out](/stacks/s1579-the-clock-in-clock-out-stack-when-your-agent-wakes-up-knowing-nothing.md) — session boundary continuity
- [S-1331 · Epistemic Memory](/stacks/s1331-the-epistemic-memory-stack-when-your-agent-stores-facts-beliefs-and-opinions-in-the-same-drawer.md) — distinguishing fact types at the epistemic level
- [S-1189 · Memory Integrity Gate](/stacks/s1189-the-memory-integrity-gate-when-your-agents-memory-starts-lying-to-itself.md) — memory evolution and governance

## Receipt

> Verified 2026-07-27 — Source: arXiv:2607.01935v2 (Shi, Tang, Tung — NUS, July 8, 2026), OWASP ASI06 (May 2026), OWASP Agent Memory Guard v0.3.0 (Q2 2026), Microsoft Foundry Blog (June 3, 2026). Ghost memory confirmed as distinct from S-1579 (session amnesia), S-1331 (epistemic conflation), and S-1189 (evolution governance). A-TMA provides the reference architecture.
