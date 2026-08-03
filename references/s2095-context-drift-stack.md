# Evidence Bank: S-2095 — Context Drift Stack

## Sources

| Source | Type | URL |
|--------|------|-----|
| Rodrigues, "Hallucination as Context Drift: Synchronization Protocols for Multi-Agent LLM Systems" | arXiv:2606.21666 | https://arxiv.org/abs/2606.21666 |
| Kriksciunas, "Multi-Agent Orchestration Infrastructure: Lessons from Production" | Blog (TURION.AI) | https://turion.ai/blog/multi-agent-orchestration-infrastructure-production |
| NiteAgent, "Multi-Agent Systems: Orchestration Patterns That Survived Production" | Industry Analysis | https://niteagent.com/blog/multi-agent-production-2026/ |
| Tran & Kiela, "The Hidden Cost of Multi-Agent Systems" | arXiv:2604.02460 | (cited by NiteAgent) |

## Key Evidence

### Context Drift Framework (Rodrigues, Jun 2026)
- Three dimensions of context drift: spatial, temporal, task
- Context Divergence Score (CDS): lightweight pairwise knowledge-state metric
- SSVP: Selective synchronization when CDS exceeds threshold
- Results: HR 0.463 (−5.9% vs no-sync, d=0.30), 58% fewer API calls vs full-broadcast
- Contamination effect: full-broadcast hallucination rate 34% higher than no-sync in open-ended tasks
- Contamination effect NOT replicated in software domain (HR < 0.2 across all conditions)

### Production Patterns (Kriksciunas, TURION.AI, Mar 2026)
- Supervisor + Specialists: dominant production multi-agent pattern
- Pipeline (sequential): for fixed-order multi-step workflows
- Bounded collaboration: only for tasks requiring genuine concurrent reasoning
- "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count"

### Token Overhead (NiteAgent, May 2026)
- 15× token overhead vs single-agent chat
- Token usage explains 80% of performance variance (Tran & Kiela)
- Single-agent matches/outperforms multi-agent on multi-hop reasoning (reasoning tokens controlled)
