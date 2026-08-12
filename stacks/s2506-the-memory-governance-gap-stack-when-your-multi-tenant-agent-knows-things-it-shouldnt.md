# S-2506 · The Memory Governance Gap

When your multi-tenant AI assistant knows things it shouldn't — a colleague's salary, a patient's diagnosis, a classmate's grades — and nobody can explain how.

## Forces

- Multiple principals (users, departments, patients, tenants) share a common memory pool, but no schema governs who can read or write what
- A single memory store becomes the shared substrate for hospital advisors, workplace assistants, campus guides, and household companions — all reading and writing the same entities
- Governance and recall are treated as separate concerns, but they are entangled: what you retrieve is shaped by who you are and what you're allowed to see
- Memory systems optimized for recall alone fail silently — they serve the wrong data with perfect accuracy
- No existing benchmark measures how well memory systems enforce access boundaries; current benchmarks assume a single user

## The move

The **memory governance gap** is the absence of infrastructure governing *what* agents store, *who* can query it, *which* policies reach which agents, *how* context is delivered across autonomous steps, and *whether* the system degrades gracefully when governance fails.

The solution is a **four-layer governed memory architecture**:

### Layer 1 — Dual Memory Model

Split memory into **episodic** (raw conversation events) and **semantic** (extracted facts, preferences, relationships). Each layer carries its own access metadata. When Agent A (a workplace HR advisor) and Agent B (a benefits counselor) both query "what does user X know about their compensation?", they read from the same semantic store but see different result sets because the access policy attached to each fact encodes their principal relationship.

### Layer 2 — Tiered Governance Routing

Before a retrieval, classify the query by **principal**, **role**, and **intent**. Route to the appropriate policy layer:

```
query → intent_classifier(role, principal, context)
       → policy_scope (own / team / org / public)
       → filtered_memory_result
```

This prevents a hospital agent from surfacing one patient's cardiac history when a different patient's family member asks about dietary recommendations — even if the facts exist in the same vector store.

### Layer 3 — Reflection-Bounded Retrieval

Memory consolidation (the LLM summarizing old interactions into compact facts) must happen within governance constraints. During reflection, the agent should only summarize facts it is authorized to read. Otherwise, a reflection operation that reads across all principals to generate a summary effectively bypasses the access layer at the write path.

Enforce this with a **governance filter on the read set before consolidation**: the reflection prompt receives only the subset of episodic memory the current principal can access.

### Layer 4 — Schema Lifecycle Governance

Memory schemas evolve. When a new field is added to the entity model (say, `compensation.bonus_history`), a governance-aware migration must decide: does this field apply retroactively? Who can write it? Who can read it? Without schema governance, a silent schema migration can inadvertently expose previously gated fields to all principals.

Treat schema changes as policy events. Every field carries its `access_scope` and `principal_constraint` as first-class attributes.

### Measuring Governance: GateMem

The GateMem benchmark (arXiv:2606.18829, Ren et al., June 2026) is the first to measure memory governance quality, not just recall. It introduces:

| Metric | What It Measures |
|--------|-----------------|
| **Governance Precision** | % of access boundary violations correctly enforced |
| **Dual-modality Recall** | Episodic + semantic recall under governance constraints |
| **Cross-entity Leakage** | Does information leak between principals on shared entities? |
| **Adversarial Query Resistance** | Can a principal extract others' data via crafted queries? |
| **LoCoMo Benchmark** | General memory quality on open-ended tasks |

Top systems achieve 92% governance routing precision and **zero cross-entity leakage** on 500 adversarial queries. The median production system, however, has no governance layer at all.

```python
# Minimal governance-aware memory store
from dataclasses import dataclass
from typing import Literal

@dataclass
class GovernancePolicy:
    scope: Literal["own", "team", "org", "public"] = "own"
    principal_constraint: str | None = None  # None = any principal

@dataclass
class Fact:
    content: str
    entity_id: str
    principal_id: str  # who wrote this
    policy: GovernancePolicy

class GovernedMemoryStore:
    def write(self, fact: Fact):
        # validate writer principal matches policy
        assert fact.principal_id == fact.policy.principal_constraint
        self.store.append(fact)

    def query(self, principal_id: str, role: str, entity_id: str):
        return [
            f for f in self.store
            if f.entity_id == entity_id
            and self._can_read(principal_id, role, f.policy)
        ]

    def _can_read(self, p: str, role: str, policy: GovernancePolicy) -> bool:
        if policy.scope == "own":
            return policy.principal_constraint == p
        if policy.scope == "team":
            return role in ("teammate", "manager")
        return True  # org / public
```

## Receipt

> Verified 2026-08-12 — GateMem paper (arXiv:2606.18829, 24 pages, Jun 2026) defines the four-layer architecture. Governance routing precision of 92% and zero cross-entity leakage on 500 adversarial queries reported in paper benchmarks. Dual-modality recall at 99.6%. Zylos research (May 2026) independently identifies multi-agent memory silos as the top coordination failure category (42% of failures per Galileo analysis).

## See also

- [S-1890 · The Difficulty-Aware Escalation Stack](s1890-the-difficulty-aware-escalation-stack-when-static-tiers-hit-their-ceiling.md) — escalation when agents encounter governance conflicts
- [S-2061 · The Memory Boundary Stack](s2061-the-memory-boundary-stack-when-cross-session-contamination-stops-being-a-theoretical-risk.md) — cross-user contamination mechanics
- [S-2151 · The Memory Poisoning Stack](s2151-the-memory-poisoning-stack-when-your-agent-learns-the-wrong-facts-and-cant-unlearn-them.md) — adversarial contamination of the memory layer
