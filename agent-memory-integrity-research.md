# Agent Memory Integrity Research — 2026-07-16

## Primary Source
**SSGM: Governing Evolving Memory in LLM Agents: Risks, Mechanisms, and the Stability and Safety Governed Memory Framework**
arXiv:2603.11768v2 [cs.AI] | Lam, Li, Zhang, Zhao — Jinan University | May 19, 2026

## Key Findings

### The Core Problem
Dynamic memory systems introduce a feedback loop where errors can accumulate — unlike static RAG. The prevailing focus on "retrieval accuracy" is insufficient; the next generation of memory systems must prioritize memory integrity and safety.

### Three Critical Failure Points (unique to evolving memory)
1. **Memory Poisoning** during input ingestion — malicious content internalized as valid knowledge
2. **Semantic Drift** during consolidation updates — repeated summarization gradually distorts facts
3. **Conflict/Hallucination** during retrieval — competing memory entries produce contradictory outputs

### The Stability-Plasticity Dilemma
Granting agents autonomy to rewrite their own memory introduces the stability-plasticity dilemma into artificial systems. Continuous refinement of memory creates risks: agents may gradually distort facts through repeated summarization (semantic drift), reinforce suboptimal workflows (procedural drift), or internalize hallucinations and injections as valid knowledge.

### SSGM Framework Core Mechanisms
1. **Consistency Verification** — verify before consolidation; governance happens at the write path, not just read
2. **Temporal Decay Modeling** — memory value degrades over time structurally, not just via TTL
3. **Dynamic Access Control** — access to memory entries changes based on context and trust level

### Key Insight
The critical distinction: **static RAG** has no feedback loop (what you read is what was stored), **evolving memory** introduces a temporal feedback loop where errors compound. This is why "retrieval accuracy" benchmarks are insufficient for agentic memory.

### Supporting Sources
- Mnemoverse AI Memory Landscape 2026: Production agents need memory across tool calls, document chains, and multi-step decisions. ECAI benchmark demonstrates memory architecture choice has meaningful impact on retrieval quality.
- Vektor Memory State of AI Agent Memory 2026: Mem0 has broadest integration surface; Zep's Graphiti for temporal reasoning; Cognee for graph-native entity relationships. Outcome-weighted retrieval (surfacing memories that led to good results) is largely unexplored in production.
- XTrace (Jul 15, 2026): "RAG is great for reading a library, but it can't write an autobiography" — the shift from static retrieval to dynamic memory management.
- CallSphere: Ebbinghaus-style time-decay curves auto-evict stale entries; TTL tiers for different fact lifetimes.
- A-MEM (Passion Labs): Stores self-contained chunks, links by content similarity, continuously updates connections.

## Deduplication
- S-820: Memory Poisoning Defense — covers input ingestion poisoning, NOT consolidation drift or retrieval conflicts
- S-1002: Memory Consolidation Debt — covers the debt problem, NOT governance mechanisms or temporal decay
- S-1043: Dreaming Pattern — covers consolidation cycle design, NOT integrity verification or access control
- I-079: Agentic Memory Confabulation — covers self-reinforcing false beliefs, NOT temporal decay or access control
- I-076: Agent Drift — covers semantic drift in multi-agent coordination, NOT memory evolution governance
- I-181: Behavioral Telemetry — covers outcome detection, NOT memory-level integrity enforcement

## Novel Angle
The SSGM insight: memory evolution and execution must be **decoupled**. Current systems either freeze memory (no evolution) or evolve freely (no governance). The third path — governance-gated evolution — is not covered in any existing entry. This is the specific gap.
