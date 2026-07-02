# Knowledge Pulse

> Institutional memory for the handbook chapter writer cron job.
> Updated after each run. Used to rank ideas, kill duplicates, and distill patterns.

## Ideas Bank

| ID | Title | Tags | Urgency | Gap | Specificity | Timeliness | Density | Composite | Status | Discovered | LastSeen |
|----|-------|------|---------|-----|-------------|------------|---------|-----------|--------|------------|----------|
| I-001 | Agentic Compensation Keys | idempotency, side-effects, retry, compensation, autonomous | 9 | 9 | 9 | 9 | 7 | **8.75** | WRITTEN — S-352 | 2026-07-02 | 2026-07-02 |

*Composite = Urgency×0.35 + Gap×0.25 + Specificity×0.20 + Timeliness×0.10 + Density×0.10*

## Pattern Log

| Pattern | Description | Supporting Idea IDs | Notes |
|---------|-------------|---------------------|-------|
| Compensation vs Idempotency | Idempotency prevents duplicate execution; compensation handles correctly-executed wrong-intent actions. These require separate key mechanisms. | I-001 | Core insight: the compensation key encodes the *reversal action*, not the original. |
| Three-Layer Key Model | Intent key / Execution key / Compensation key — each encodes a different phase and survives agent restarts. | I-001 | Deterministic hashing from action metadata (not UUIDs) so any process can find and operate. |
| Phase-State Machines | Action records need explicit lifecycle states (PENDING → COMMITTED → COMPENSATING → COMPENSATED) to survive distributed retries and multi-agent handoffs. | I-001 | Analogous to saga pattern in distributed transactions. |
| Blast Radius Isolation | Compensation actions must themselves be idempotent. Using the compensation key as the idempotency key for the reversal prevents double-credit. | I-001 | Confirmed via Cordum's production guide. |

*When a pattern accumulates 3+ supporting ideas, synthesize a synthesis note below.*

## Synthesis Notes

*Add synthesized insights here when pattern density ≥ 3*

## Deduplication Index

*Keyword → idea ID mapping. Updated after each run.*
```
ai-agent → I-001
llm → 
evaluation → 
reliability → I-001
cost → 
mcp → 
multi-agent → I-001
sandbox → 
guardrails → 
routing → 
memory → 
rag → 
tracing → 
synthetic-data → 
fine-tuning → 
idempotency → I-001
side-effect → I-001
compensation → I-001
retry → I-001
circuit-breaker → 
```

## Recent Decisions

| Run Date | Idea ID | Decision | Rationale |
|----------|---------|----------|-----------|
| 2026-07-02 | I-001 | WRITTEN — S-352 | Compensation keys (distinct from idempotency keys) cover the layer above: reversing correctly-executed wrong-intent actions. All existing entries (S-93, S-181, F-107) cover prevention/deduplication — none cover autonomous reversal. Gap confirmed by Cordum, AgentMarketCap, Stackwell production guides. |

## Meta

- Created: 2026-07-02
- Last Updated: 2026-07-02
- Total ideas discovered: 1
- Total patterns distilled: 4
