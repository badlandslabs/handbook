# [S-827] · The Context Sprawl Pattern

When multiple agents give different answers to the same business question — because each built its own isolated reality.

## Situation

Your finance team and your ops team both deployed AI agents to answer "What was our revenue last quarter?" The finance agent says $4.2M. The ops agent says $4.7M. Neither is wrong — they just read from different databases, applied different date cutoffs, and cached results at different times. No one caught this until the CFO cited the ops number in a board meeting.

This is not a data quality problem. It is not a model problem. It is **context sprawl** — the silent accumulation of isolated semantic layers across an agent fleet.

## Forces

- Every agent team independently decides what ground truth to trust and when to refresh it
- Agents are deployed faster than any shared context infrastructure can keep pace with
- Context conflicts are invisible until they cause a visible business error
- Governance tools (agent registries, RBAC) address identity sprawl but not semantic fragmentation
- Shared context infrastructure introduces coupling that slows agent deployment — the incentive is to skip it
- At scale (150,000+ agents per Fortune 500 by 2028, Gartner), context sprawl becomes structurally inevitable without a shared layer

## The move

**Build a shared semantic grounding layer — not a database, a contract.**

The pattern has three components:

**1. The Canonical Entity Registry**

Define the authoritative set of business entities (revenue, customer, order, invoice) and their computation rules. Every agent queries this registry for entity definitions, not raw tables.

```
# Canonical entity: "revenue"
# Computation rule: net of returns, in USD, closed deals only
# Data sources: [salesforce.deals, stripe.charges]
# Refresh cadence: T+1 08:00 UTC
# Owner: finance-data-team
# Contact: #data-catalog-finance

Entity: revenue.last_quarter
  computed_from: deals.closed_at ∈ [Q_start, Q_end]
  filters: deal.stage == "Closed Won", deal.currency == "USD"
  exclusions: returns.refunded == true
  freshness: T+1 08:00 UTC
  owner: finance-data-team
  version: 2026-Q2-v3
```

**2. The Semantic Gateway**

Every agent routes entity requests through a thin proxy layer that enforces:
- Entity definitions are fetched from the registry (not hardcoded)
- Stale data (beyond `freshness` TTL) triggers a re-query or explicit override flag
- Responses include `entity_version`, `data_freshness`, and `source_uri` metadata
- Conflicts between agents on the same entity surface as a version mismatch, not silent divergence

```
# Agent asks: "What was revenue last quarter?"
# Gateway intercepts, resolves against registry:

def resolve_entity(query: str, agent_id: str) -> EntityResult:
    entity = registry.resolve(query)  # → revenue.last_quarter
    if is_stale(entity.freshness):
        trigger_background_refresh(entity)
        return cached_with_warning(entity)
    return entity.compute()
```

**3. Context Conflict Alerts**

Automated detection when two agents return conflicting values for the same entity:
- Periodic reconciliation job: query canonical registry, compare agent responses
- Alert fires when `|agent_a.value - agent_b.value| > threshold`
- Threshold is entity-specific: revenue gets a 0.01% tolerance; headcount gets 5%

**4. The Shared Memory Graph (optional layer)**

For complex multi-hop reasoning, maintain a lightweight knowledge graph of entity relationships. Agents contribute observations to the graph; the graph resolves conflicts via provenance-weighted consensus. This connects to Entity Grounding (S-378) but focuses on the multi-agent inconsistency problem rather than hallucination.

```
# Shared memory graph entry
(:Revenue {quarter: "Q2-2026", value: 4200000, unit: "USD",
          sources: ["salesforce", "stripe"],
          conflict_status: "resolved",  # vs "diverging"
          computed_at: "2026-07-07T08:00:00Z",
          ttl_hours: 24})
```

## Receipt

> Verified 2026-07-08 — Sources: Atlan AI Labs (2026) measured 38% SQL accuracy improvement when grounding agents in governance metadata vs raw schema. AgentInventor (April 2026) reported that 88% of agents never reach production; context conflicts are a primary silent failure mode identified in post-mortems. Zylos Research (March 2026) documented the two-axis sprawl problem: identity sprawl (covered by governance tools) and context sprawl (not covered). The canonical entity registry pattern is consistent with existing handbook entries S-378 (Entity Grounding), S-799 (Cross-Agent Trace Correlation), and S-818 (Longitudinal Eval Stack).

## See also

- [S-378 · Entity Grounding: Knowledge Graphs as Verifiable Memory](stacks/s378-entity-grounding-knowledge-graphs-as-verifiable-memory.md) — the grounding technique; this entry covers multi-agent divergence
- [S-799 · Cross-Agent Trace Correlation](stacks/s799-cross-agent-trace-correlation-reconstructing-causal-chains-across-delegation-boundaries.md) — tracing which agent said what; this entry covers why they said different things
- [S-646 · Agent Drift in Multi-Agent Systems](stacks/s646-agent-drift-in-multi-agent-systems.md) — behavioral drift over time; this entry covers simultaneous semantic divergence across agents
- [S-368 · Agent Span Tracing: Observable Agent Sessions](stacks/s368-agent-span-tracing-observable-agent-sessions.md) — the observability foundation this pattern builds on
