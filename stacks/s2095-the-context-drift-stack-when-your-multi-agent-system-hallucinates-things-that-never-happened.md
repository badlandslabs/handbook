# S-2095 · The Context Drift Stack — When Your Multi-Agent System Hallucinates Things That Never Happened

Your two agents seem aligned. One does research, one synthesizes. But the synthesizer produces facts the researcher never asserted. You blame the model. You switch to a bigger one. The hallucinations persist. The problem is not the model — it is the gap between what each agent believes is true about the shared world at the moment they collaborate.

## Forces

- **Multi-agent hallucination is not a model deficiency.** You can swap in a better model and still get hallucinations. The root cause is distributed: agents operating concurrently accumulate different beliefs about shared state. This class of failure is orthogonal to capability.
- **More agents means more drift surface.** Each additional agent multiplies the number of pairwise knowledge-state divergences. The failure mode scales with agent count, not linearly but combinatorially.
- **Naive synchronization makes it worse.** Full broadcast — sharing all context with all agents — causes a "contamination effect" where agents incorporate each other's errors, compounding hallucination rather than correcting it. Indiscriminate context sharing increased hallucination rates 34% above no-sync in multi-agent evaluations.
- **Token overhead compounds the cost.** Multi-agent systems use 15× more tokens than single-agent chat interactions. Blind synchronization approaches pay this cost without proportional quality gains.
- **Task domain changes the brittleness.** Full-broadcast contamination is severe in open-ended tasks (travel planning, multi-hop reasoning) but negligible in structured software tasks where error cascades self-correct. The mitigation depends on the task profile.

## The move

Frame multi-agent hallucination as a distributed systems problem: context drift. Then apply selective synchronization — not broadcast — using a lightweight divergence metric.

**Detect before syncing.** Compute a Context Divergence Score (CDS) between agent pairs. This is a lightweight scalar quantifying knowledge-state discrepancy across three dimensions:

- **Spatial:** agents hold different beliefs about the same environment or world state
- **Temporal:** agents operate with information from different timestamps; "current" state differs
- **Task:** agents accumulate different task histories, making the same input resolve differently

**Sync selectively, not universally.** The Shared State Verification Protocol (SSVP) verifies shared state only when CDS exceeds a threshold. This avoids the contamination effect of full-broadcast while catching the divergence that causes hallucinations. It achieved a 5.9% absolute hallucination reduction vs. no-sync with 58% fewer API calls compared to full-broadcast.

**Default to isolation.** Most production multi-agent deployments are actually supervisor + isolated specialist patterns — not peer collaboration. The supervisor decomposes tasks and routes to specialists who return results; the supervisor integrates. This limits drift surface because agents never run concurrently with shared context.

**Gate on task type.** When you do need concurrent peer collaboration, apply SSVP in open-ended or domain-critical tasks (research, planning, creative synthesis). In structured, well-defined software tasks, the contamination effect is minimal — save the synchronization overhead.

## Evidence

- **Research paper:** "Hallucination as Context Drift: Synchronization Protocols for Multi-Agent LLM Systems" — Rodrigues (Celabe), arXiv:2606.21666, Jun 2026. Formal framework defining context drift across three dimensions (spatial/temporal/task). Introduces CDS and SSVP. SSVP achieved HR: 0.463 (−5.9% vs no-sync, d=0.30) and significantly lower hallucination than full-broadcast (p=0.0005, d=1.47) using 58% fewer API calls. Full-broadcast contamination effect: 34% higher hallucination than no-sync in open-ended tasks. — [https://arxiv.org/abs/2606.21666](https://arxiv.org/abs/2606.21666)
- **Field note:** "Multi-Agent Orchestration Infrastructure: Lessons from Production" — Kriksciunas, TURION.AI, Mar 2026. Supervisory patterns (LangGraph, CrewAI hierarchical mode) are the dominant production architecture. Pipeline (sequential specialists) for fixed-order workflows. Bounded peer collaboration only for tasks requiring genuine concurrent reasoning. — [https://turion.ai/blog/multi-agent-orchestration-infrastructure-production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Industry analysis:** "Multi-Agent Systems: Orchestration Patterns That Survived Production" — NiteAgent, May 2026. Token overhead: 15× more than chat interactions; token usage explains 80% of multi-agent performance variance. Single-agent consistently matches or outperforms multi-agent on multi-hop reasoning when reasoning tokens are held constant. — [https://niteagent.com/blog/multi-agent-production-2026/](https://niteagent.com/blog/multi-agent-production-2026/)

## Gotchas

- **Swapping the model does not fix drift.** If your multi-agent system hallucinates despite using a frontier model, context drift is the likely cause, not capability. More tokens or a better model amplifies the problem if synchronization is naive.
- **The contamination effect is counterintuitive.** You would expect that sharing more context between agents would reduce hallucination. In open-ended multi-agent tasks, it does the opposite — each agent propagates its own errors into others, and the errors compound.
- **CDS is cheap but not free.** Computing pairwise divergence adds overhead, but SSVP's 58% API call reduction vs. full-broadcast means selective sync is cheaper than broadcast. Budget for the CDS computation infrastructure.
- **Software tasks are resilient.** The contamination effect does not replicate in structured software tasks (SWE-bench domain). If your multi-agent is doing code generation, the drift surface is smaller and naive approaches may suffice. If it's doing research or planning, SSVP-level discipline is warranted.
