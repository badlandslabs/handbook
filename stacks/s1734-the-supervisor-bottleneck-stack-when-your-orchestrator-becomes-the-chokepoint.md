# S-1734 · The Supervisor Bottleneck Stack · When Your Orchestrator Becomes the Chokepoint

You have three specialist agents. They each return a paragraph. Your supervisor synthesizes them into a report. This works for three agents. Then five. Then twelve. Then the supervisor starts dropping output, returning half-formed responses, or hallucinating sections it claims workers produced. You did everything right — the pattern is the production standard — and the system is silently degrading.

## Forces

- **Reliability compounds against you.** Five agents at 95% individual reliability deliver roughly 77% end-to-end success. More agents means more probabilistic handoffs, not more robustness.
- **Supervisor context window is a hard ceiling.** Every worker result must route back through the supervisor to synthesize. At 6+ workers, this becomes the structural bottleneck — not a bug, a physics constraint.
- **Free-for-all systems are fast but undebuggable.** When agents call each other peer-to-peer with no central router, you get infinite loops, contradictory mutations, and untraceable decisions. The supervisor pattern exists because chaos is worse than bottleneck.
- **The dangerous failures are silent.** Multi-agent systems rarely throw exceptions. They return confident, plausible answers built on a broken sub-task. Standard monitoring misses this entirely.
- **Cost runaway is a first-class risk.** Agents in unbounded cycles can burn a month's token budget in minutes.

## The Move

The supervisor-worker pattern is the right default — but only if you design for its bottleneck from the start.

- **Route tasks with structured output schemas, not natural language.** Workers return typed Pydantic objects, not free text. This lets the supervisor validate completeness before synthesis and distinguishes "empty result" from "error result."
- **Validate at every inter-agent boundary.** Every handoff is a trust boundary. Insert a critic step or schema check before the supervisor synthesizes. A pipeline that only checks "is this valid JSON" catches nothing about factual drift.
- **Implement max-iteration limits with hard stops.** Supervisors that loop indefinitely are a real production failure. Cap iterations and emit structured failure signals instead.
- **Scope workers to single responsibilities.** One worker, one task. The supervisor should never need to ask a worker "what did you actually do?" — the interface should make that unambiguous.
- **Collapse parallel results before synthesis.** If three workers ran in parallel, summarize their outputs into a unified brief before passing to the supervisor. Don't let the supervisor's context absorb all raw worker output.
- **Instrument the handoff itself.** Log not just what workers returned but what the supervisor received and synthesized. You cannot debug silence.

## Evidence

- **Engineering blog:** The supervisor pattern is the production standard for multi-agent systems. A central supervisor LLM classifies each incoming task and routes to specialist workers — each with scoped context and narrow tool access. The pattern gives you one place to add guardrails and one place to observe the full plan. — [Databricks/BASF Coatings deployment](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)
- **Research:** The MAST taxonomy (Berkeley, NeurIPS 2025) analyzed 1,642 execution traces across 7 MAS frameworks and identified 14 failure modes in 3 categories: specification issues, inter-agent misalignment, and task verification. ChatDev achieved only 33.33% correctness on the ProgramDev benchmark. The study found that MAS failures require more complex solutions than better models or faster message buses — the problems are architectural. — [MAST paper, arXiv:2503.13657](https://arxiv.org/html/2503.13657v2)
- **Practitioner analysis:** Supervisor-worker fails structurally when every worker's output routes back through the supervisor's context window before synthesis. At 6+ workers, this creates the coordinator bottleneck — the supervisor starts truncating, dropping, or reinterpreting worker results silently. Mitigation: pre-collapse parallel results and pass structured briefs, not raw outputs. — [Utilix multi-agent failure modes guide](https://www.utilix.tech/blog/multi-agent-orchestration-patterns-failure-modes)

## Gotchas

- **Do not give workers peer-to-peer calling rights.** This is the fastest path to infinite loops and contradictory outputs. The supervisor routes; workers return.
- **Empty worker output is not a success signal.** A worker that returns nothing should produce a structured `error` field, not an empty string. The supervisor treating empty as success is the #1 silent production bug.
- **The supervisor bottleneck is not a tuning problem.** You cannot prompt-engineer your way out of a saturated context window. You need architectural changes: result summarization, parallel collapse, or moving to a hierarchical supervisor (supervisor → sub-supervisor → workers).
- **More agents does not mean more reliability.** The math is against you. Add agents only when task complexity genuinely requires specialized handling, not because it seems more capable.
