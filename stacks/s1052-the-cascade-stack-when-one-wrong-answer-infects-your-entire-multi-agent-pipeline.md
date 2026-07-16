# S-1052 · The Cascade Stack — When One Wrong Answer Infects Your Entire Multi-Agent Pipeline

Your multi-agent triage → research → drafting pipeline worked in the pilot. Three weeks into production, a customer-support escalation email arrives with a fabricated policy citation and an unauthorized refund authorization. The research agent found the citation in a scraped forum post. The drafting agent trusted it. The approval agent approved. One hallucinated fact propagated through three systems, each doing exactly what it was designed to do. No error was raised. No tool failed. This is not a bug in any single agent — it is a structural property of how agents trust each other.

## Situation

A research agent ingests a document, extracts a claim, and passes it to a drafting agent as a verified fact. The drafting agent treats it as authoritative. A reviewer agent checks style and tone — not factual accuracy. The claim ships. The same architecture handles 500 tasks a day correctly. On the one that matters, the failure was invisible.

## Forces

- **Agents trust inter-agent channels as verified.** Unlike external tools, an agent's output from a sibling or downstream agent carries the implicit endorsement of your system — even though no verification occurred. This trust is architectural, not enforced
- **Cascade failure is silent; cost overhead is not.** The 15× token premium of multi-agent systems announces itself in billing dashboards. The single corrupted output propagating through three agents announces nothing — it looks like correct behavior at every checkpoint
- **Accuracy gains from multi-agent are marginal and fragile.** Princeton NLP research (2025–2026) shows single agents match or outperform multi-agent on 64% of benchmarked tasks, adding ~2.1 percentage points of accuracy at roughly 2× cost. That slim margin is vulnerable to a single false premise collapsing the entire pipeline
- **No agent owns end-to-end truth.** Fact-checking, style-review, and routing agents each have a narrow window into the pipeline. None has the full context to catch a claim that is plausible within the drafting agent's context but wrong in the real world
- **Naive retry and rollback don't help.** Retrying a drafting agent that received a corrupted input just produces a faster version of the same wrong answer

## The move

Build three independent architectural controls that break the cascade — not as optional hardening, but as the default pipeline structure.

**1. Trust walls: the checkpoint validation gate**

Insert a stateless verification agent at every handoff between pipeline stages. Not a reviewer — a falsifier. Its sole job is to attempt to disprove the output from the upstream agent using independent tooling (web search, database lookup, knowledge graph query). If it finds a contradiction, the handoff is rejected and the upstream agent re-runs with the contradiction as context.

```
[Research Agent] → [Checkpoint Falsifier] → (pass) → [Drafting Agent]
                       ↓
                  (contradiction found)
                       ↓
               [Research Agent] re-run with correction
```

**2. Provenance tags: every inter-agent claim carries its source**

Agent outputs that cross a handoff boundary must include structured provenance: the source tool, the retrieval timestamp, and a confidence interval. The downstream agent reads provenance tags, not bare claims. This shifts the trust model from "my colleague agent said it" to "a specific query to a specific source produced it."

```json
{
  "claim": "Refund policy allows 30-day returns",
  "provenance": {
    "source": "internal_kb",
    "query": "refund policy return window",
    "retrieved_at": "2026-07-13T14:23:11Z",
    "confidence": "high"
  }
}
```

Downstream agents that receive a claim without provenance tags treat it as unverified — a human-in-the-loop trigger, not a silent pass.

**3. Pessimistic consensus: require three independent extraction paths**

For any factual claim that will drive a consequential action (financial, legal, operational), require three agents operating with independent retrieval contexts to reach agreement. One research agent with access to your internal KB, one with web search, one with a structured database. If all three converge on the same claim, it is treated as verified. If they diverge, the divergence is surfaced to a human.

This is not majority voting — it is adversarial corroboration. The goal is not consensus; it is forcing independent error sources to accidentally agree, which is far more unlikely than two biased extractors agreeing.

**4. The rollback frontier: what state do you restore?**

When a cascade is detected mid-pipeline, the rollback target is the first agent that produced corrupted context, not the most recent. Identify the provenance chain explicitly so you can unwind to the actual root cause rather than the most recent visible symptom.

## Receipt

> Verified 2026-07-13 — Research confirmed cascade failure mechanics from: (1) NiteAgent production incident reports (cascade from scraped forum → document drafting → approval without fact-check), (2) beam.ai 2026 multi-agent patterns analysis documenting atomic falsehood propagation as the #1 multi-agent production failure mode, (3) Princeton NLP 2025 multi-agent accuracy benchmarks showing 2.1pp accuracy gain at 2× cost — margin easily wiped by one cascade event. Architectural countermeasures (trust walls, provenance tags, pessimistic consensus) drawn from S-380 (antagonistic validation), S-974 (lethal trifecta read-path hardening), and S-1008 (orchestration pattern matching).

## See also

- [S-380 · Antagonistic Validation: Team of Rivals Architecture](s380-antagonistic-validation-team-of-rivals-architecture.md) — structural opposition as a reliability pattern; the checkpoint falsifier is a narrow form of this
- [S-974 · The Lethal Trifecta: When Capability Convergence Creates Catastrophic Agent Risk](s974-the-lethal-trifecta-when-capability-convergence-creates-catastrophic-agent-risk.md) — the read-axis of the cascade; addresses untrusted content ingestion, not propagation
- [S-1008 · The Orchestration Pattern Match Stack: When Chains, Agents, and Hierarchies All Look Equally Right](s1008-the-orchestration-pattern-match-stack-when-chains-agents-and-hierarchies-all-look-equally-right.md) — Princeton NLP data on single vs multi-agent accuracy; the cost/accuracy tradeoff that makes cascade risk disproportionate
- [S-1022 · The Agent Drift Stack: When Your Multi-Agent System Changes Without Changing](s1022-the-agent-drift-stack-when-your-multi-agent-system-changes-without-changing.md) — temporal cousin; drift degrades multi-agent quality silently over time, cascade degrades it instantly on a single task
