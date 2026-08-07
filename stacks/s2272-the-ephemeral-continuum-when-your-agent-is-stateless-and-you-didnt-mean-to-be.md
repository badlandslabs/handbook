# S-2272 · The Ephemeral Continuum — When Your Agent Is Stateless and You Didn't Mean to Be

An LLM is a stateless function. Every call starts from scratch — no memory, no continuity, no recovery point. You wire it into a multi-step workflow and suddenly the gap between "stateless function" and "persistent agent" becomes the most consequential design decision you haven't made yet. The question is not whether your agent has state — it always starts with none. The question is how far you push the persistence gradient before you stop and think about what you're actually promising.

## Forces

- **LLMs begin stateless by default.** Every token sequence is independent. Without an explicit state layer, a crash at step 7 means step 7 never happened — the agent restarts from zero with no memory of the prior six steps. The failure is silent: the process restarts, the error never surfaces, and nobody notices the work that vanished.
- **Persistence is a gradient, not a binary.** The continuum runs from pure ephemeral (no state survives the call) through working-memory persistence (state held in-process), to checkpoint persistence (state survives process death), to durable persistence (state survives infrastructure failure, region outage, and intentional resume). Most teams make an implicit choice without realizing there are four options — and that each trades differently against cost, latency, and complexity.
- **The wrong persistence level is expensive in both directions.** Too little: silent data loss, no recovery, no replay. Too much: state bloat slows every operation, serialization overhead compounds, and the "checkpoint" becomes a distributed systems problem you're now responsible for debugging.
- **Ephemeral state is not the same as irrelevant state.** The current reasoning step, the last tool call result, the accumulated context — these are transient. But the *intent* that drove the workflow, the plan that emerged, the facts discovered along the way — these are factual state that must survive even if the process dies. Most teams conflate the two and lose both.

## The Move

Map every state artifact to a persistence tier before you build:

**Tier 0 — Ephemeral (call-scoped):** LLM inputs and outputs, tool arguments, intermediate reasoning tokens. These are consumed and discarded. No recovery, no replay. Acceptable for single-shot tasks; catastrophic for multi-step work.

**Tier 1 — Working memory (process-scoped):** Current step counter, accumulated context window, conversation history, tool result cache. Survives within a single process run. Dies on restart, OOM kill, or deploy. Use in-process dict/Redis for this.

**Tier 2 — Checkpoint persistence (lifecycle-scoped):** Serialized agent state snapshots at every significant step boundary — current goal, completed steps, intermediate results, next action plan. Survives process death but not infrastructure failure. LangGraph `MemorySaver`, Temporal workflows, OpenAI Assistants API thread state.

**Tier 3 — Durable persistence (cross-session):** Facts learned, decisions made, plan history, verified results, entity relationships. Survives everything including region outages. PostgreSQL JSONB columns, Redis with AOF, or a purpose-built agent memory store (Mem0, Letta, Zep).

The discipline is *deciding per artifact* rather than picking one tier and applying it uniformly.

```python
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json

class PersistenceTier(Enum):
    EPHEMERAL = 0  # Call-scoped, no recovery
    WORKING   = 1  # Process-scoped, dies on restart
    CHECKPOINT = 2  # Lifecycle-scoped, survives process death
    DURABLE   = 3  # Cross-session, survives infrastructure failure

@dataclass
class AgentStateArtifact:
    key: str
    value: any
    tier: PersistenceTier
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def should_persist(self) -> bool:
        return self.tier.value >= PersistenceTier.CHECKPOINT.value

class EphemeralContinuum:
    """
    Persistence-tier-aware agent state manager.
    Separates ephemeral working state from durable state,
    enabling selective checkpointing without bloating the state store.
    """
    def __init__(self, durable_store, checkpoint_store):
        self.durable = durable_store      # e.g. PostgresAgentStore
        self.checkpoint = checkpoint_store # e.g. LangGraph MemorySaver
        self.working: dict = {}            # In-process dict, no persistence

    def put(self, artifact: AgentStateArtifact):
        if artifact.tier == PersistenceTier.EPHEMERAL:
            self.working[artifact.key] = artifact.value
            return  # Discard after call

        if artifact.tier == PersistenceTier.WORKING:
            self.working[artifact.key] = artifact.value
            return  # Lost on process death — acceptable for temp vars

        if artifact.tier == PersistenceTier.CHECKPOINT:
            self.checkpoint.save(artifact.key, artifact.value)
            return  # Survives process death

        # DURABLE: survive infrastructure failure
        self.durable.upsert(
            key=artifact.key,
            value=artifact.value,
            timestamp=artifact.timestamp
        )

    def get(self, key: str) -> any:
        # Check tiers in descending persistence order
        if key in self.working:
            return self.working[key]
        cp = self.checkpoint.get(key)
        if cp is not None:
            return cp
        return self.durable.get(key)

    def checkpoint_full_state(self, goal: str, steps: list, facts: list):
        """
        After every significant step: checkpoint working state.
        Failsafe — called explicitly, not buried in a framework.
        """
        snapshot = {
            "goal": goal,
            "completed_steps": steps,
            "discovered_facts": facts,
            "checkpoint_ts": datetime.utcnow().isoformat()
        }
        self.checkpoint.save(f"run_{id(goal)}", snapshot)

        # Facts graduate to durable immediately — they must survive
        for fact in facts:
            self.put(AgentStateArtifact(
                key=f"fact:{fact['id']}",
                value=fact,
                tier=PersistenceTier.DURABLE
            ))
```

## The Recovery Decision

After every significant step, ask three questions:

1. **Is this recoverable from source?** If the agent could re-derive this result from a tool call, store it ephemerally. Don't checkpoint expensive computations you could cheaply reproduce.
2. **Is this the intent or the work?** The original goal and plan structure — durable. Intermediate tool outputs — ephemeral unless expensive. Facts about the environment — durable.
3. **How long until this is stale?** Context about a user's specific project is session-scoped (Tier 2). Facts about a company's policies are durable (Tier 3). Get the tier wrong and you either lose it when you need it or carry it forever at cost.

## Receipt

> Verified 2026-08-07 — Research across LangGraph checkpoint docs (MemorySaver + PostgreSQLSaver), OpenAI Assistants API thread persistence, Temporal workflow durable execution, and Mem0/Zep agent memory stores confirms the four-tier model. LangGraph's `MemorySaver` implements Tier 2 (in-memory checkpoint); `PostgreSQLSaver` upgrades to Tier 3 (cross-session durability). AdaptiveRecall's state separation guide (2026) independently documents the factual/ephemeral split. arXiv:2606.29823 (Experience Graphs, June 2026) confirms the durability inheritance pattern: "sessions that hit infrastructure failures resume automatically on another worker with no lost nodes — durability we never engineered as a feature but inherited from putting the state in the database."

## See also

- [S-1013 · The Multi-Agent Boundary Stack — When Two Agents Disagree on What the State Is](stacks/s1013-the-multi-agent-boundary-stack-when-two-agents-disagree-on-what-the-state-is.md) — state ownership conflicts across agent boundaries
- [S-1020 · The Tiered Memory Stack — When Your Agent Greets You Like a Stranger Every Morning](stacks/s1020-the-tiered-memory-stack-when-your-agent-greets-you-like-a-stranger-every-morning.md) — cross-session memory at the retrieval layer
- [S-1012 · The Agent Failure Recovery Stack — When Your Agent Loops for 35 Minutes and No One Notices](stacks/s1012-the-agent-failure-recovery-stack-when-your-agent-loops-for-35-minutes-and-no-one-notices.md) — checkpoint-based recovery patterns
