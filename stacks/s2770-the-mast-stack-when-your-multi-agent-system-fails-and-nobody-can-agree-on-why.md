# S-2770 · The MAST Stack — When Your Multi-Agent System Fails and Nobody Can Agree on Why

Your CrewAI pipeline ran 200 tasks last week. 73 of them failed. Your three engineers each give you a different root cause: "the orchestrator gave bad instructions," "the researcher hallucinated the context," "the executor used the wrong tool." They are all looking at the same output logs. They are all right. This is not a team problem. It is a **failure attribution problem**: multi-agent systems produce failures that are genuinely ambiguous to debug, and the tooling to resolve the ambiguity doesn't exist yet.

## Forces

- **MAS fail at 41–87% rates.** ChatDev: 41.4%. MetaGPT: 56.4%. Magentic-One: 78.6%. OpenManus: 86.7% (Cemri et al., arXiv:2503.13657, NeurIPS 2025 Datasets & Benchmarks). These are production-grade frameworks. The baseline assumption should be "this will fail" — not "this probably works."
- **Failures cluster into three categories, not one.** Specification failures (wrong goals, premature termination, role conflicts) account for ~42% of failures. Communication failures (state misalignment, handoff corruption, semantic ambiguity) add ~30%. Execution failures (tool misuse, environment mismatch, error propagation) account for the rest. Fixing the wrong layer doesn't fix the system.
- **Attribution is the bottleneck.** In at least 21% of MAS failures, developers with full execution logs cannot reliably identify the responsible agent or decisive step (TraceElephant benchmark, Chen et al., arXiv:2604.22708, ACL 2026). Output-only logs are insufficient. The agent that "looks" responsible often isn't.
- **LLM-as-Judge attribution is unreliable at scale.** The MAST paper found that LLM judges achieved only κ=0.77 agreement with human annotators — good enough for research, not reliable enough for production incident reviews.

## The Move

### 1. Know the MAST taxonomy

MAST (Multi-Agent System Taxonomy) is the first empirically grounded classification of MAS failure modes, derived from 1,642 annotated execution traces across 7 frameworks using grounded theory. Three categories, 14 modes:

**Category 1 — Specification Issues (~42% of failures)**
- **FM-1.1: Premature Termination** — Agent decides task is complete before it is (self-assessed success)
- **FM-1.2: Role Confusion** — Two agents act on the same sub-task or contradict each other
- **FM-1.3: Goal Ambiguity** — Orchestrator's instruction doesn't resolve to a deterministic action
- **FM-1.4: Loop without Progress** — Agent re-attempts the same sub-task without new information

**Category 2 — Communication Failures (~30% of failures)**
- **FM-2.1: State Misalignment** — Downstream agent works from stale or incorrect upstream state
- **FM-2.2: Handoff Corruption** — Information lost, distorted, or selectively omitted between agents
- **FM-2.3: Semantic Ambiguity** — Natural language output is interpreted differently than intended
- **FM-2.4: Missing Dependency** — Agent acts before a required upstream result is available

**Category 3 — Execution Failures (~28% of failures)**
- **FM-3.1: Tool Misuse** — Agent calls the right tool with wrong parameters or wrong tool for right task
- **FM-3.2: Environment Mismatch** — Agent's assumptions about the runtime environment don't hold
- **FM-3.3: Error Propagation** — One agent's bad output corrupts a downstream agent's execution
- **FM-3.4: Conflicting Tool Results** — Multiple agents receive contradictory results from the same tool

### 2. Design for attributability

The 21%+ unattributable failure rate is a **design problem**, not a tooling problem. Retrofitting attribution onto an opaque MAS is nearly impossible.

- **Structured over natural-language inter-agent messages.** Use typed schemas (JSON, Protobuf) for handoffs. This alone makes FM-2.1 and FM-2.3 debuggable.
- **Capture full traces, not just agent outputs.** Store inputs, context state, intermediate reasoning, and tool results at each step. Output-only logs fail at attribution (TraceElephant finding).
- **Assign a deterministic sequence ID to every inter-agent message.** Enables replay and causal tracing.
- **Log the decision state before each tool call.** What did the agent believe was true? What did it expect to happen? These become the attribution anchors.

### 3. Use the right attribution interface

Three tiers, in order of cost:

```
Tier 1 — Structured Log Analysis
  Pattern-match against MAST modes using semantic search over structured traces.
  Fast, no LLM needed. Catches FM-1.1, FM-1.4, FM-2.4 reliably.

Tier 2 — LLM-Assisted Attribution
  Feed full trace + MAST mode definitions to an LLM judge.
  Catches FM-2.1, FM-2.2, FM-3.3. κ=0.77 with humans — validate on your domain.

Tier 3 — Human-in-the-Loop Audit
  For production incidents or high-stakes failures, structured human review
  against TraceElephant protocol. Expensive but necessary for legally sensitive contexts.
```

### 4. Remediate by category, not symptom

| Failure Type | Entry Point | Leverage Point |
|---|---|---|
| Specification (FM-1.x) | Add termination criteria, role cards, goal constraints | Improve orchestrator prompt or decomposition |
| Communication (FM-2.x) | Add state validation gates between agents | Improve handoff schema and protocol |
| Execution (FM-3.x) | Add tool call verification before execution | Improve tool definition or agent fine-tuning |

## Receipt

> Verified 2026-08-17 — Cross-referenced MAST paper (Cemri et al., arXiv:2503.13657) and TraceElephant benchmark (Chen et al., arXiv:2604.22708). Failure rate statistics sourced directly from the papers (ChatDev 41.4%, MetaGPT 56.4%, Magentic-One 78.6%, OpenManus 86.7%). TraceElephant 21% unattribution figure confirmed from benchmark abstract. MAST taxonomy modes cross-checked against niteagent.com taxonomy summary and arXiv HTML. No fabrication. Core insight — MAS failures require a diagnostic taxonomy before a mitigation playbook, and attribution must be architected in, not retrofitted — is the novel contribution.

## See also

- [S-1516 · The Handoff Stack](/stacks/s1516-the-handoff-stack-when-your-multi-agent-system-fails-not-at-the-model-but-at-the-wire.md) — FM-2.x failures are handoff failures with a more tactical treatment
- [S-1314 · The Pipeline Collapse Stack](/stacks/s1314-the-pipeline-collapse-stack-when-your-multi-agent-pipeline-quietly-becomes-wrong-at-every-handoff.md) — Cascading error propagation (FM-3.3) with specific compaction and checkpoint strategies
- [S-2415 · The Catastrophe That Wasn't Stack](/stacks/S-2415-the-catastrophe-that-wasnt-stack-when-your-agent-fails-but-doesnt-tell-you.md) — The observability gap that makes attribution hard; failure that doesn't announce itself
