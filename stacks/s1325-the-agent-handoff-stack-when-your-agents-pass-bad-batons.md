# S-1325 · The Agent Handoff Stack — When Your Agents Pass Bad Batons

When two specialized agents need to collaborate and the baton drop rate exceeds your tolerance.

## Forces

- **Coordination is where systems actually die** — the models are fine; the wiring between them is the failure point. 36.9% of multi-agent failures trace to coordination problems (vs. model quality, tool errors, or hallucinations).
- **Tutorials hide the composition tax** — agents work beautifully in isolation and fail mysteriously when composed. An 8-agent debugging session is categorically harder than a single-model call.
- **The handoff is the spec** — agents that receive ambiguous context from their predecessors don't ask for clarification; they confidently hallucinate the missing pieces and pass the fabricated baton downstream.
- **Cost spirals are structural** — `max_iter` defaults to 25 per agent. A 3-agent pipeline at 100 runs/day can hit $900/month before you notice. Token usage can be 15× higher than a single-agent approach for a 90% quality gain.

## The Move

**Narrow the agents. Tighten the batons. Own the orchestration layer.**

- **Decompose at natural boundaries, not at demo boundaries.** Split only where expertise domains differ, where subtasks are parallelizable, or where a quality gate belongs. A fintech team cut processing from 2 hours to 12 minutes by decomposing at domain boundaries, not by making every step its own agent.
- **Typed handoff schemas over freeform context passing.** Define what each agent receives and emits as structured objects (Pydantic models). Without this, downstream agents infer missing context and get it wrong. The structured handoff format is the single highest-leverage production investment.
- **Deterministic routing beats LLM routing for handoffs.** Let the orchestrator (not the agent) decide who goes next. LLM-based routing introduces non-determinism that compounds across chains. LangGraph's conditional edges give you explicit, auditable routing; CrewAI's autonomous handoffs are faster to prototype but harder to debug.
- **Set `max_iter` per agent to 5–8, not 25.** This is the single biggest cost lever. A single bad run can consume 5–10× the normal token budget before you hit the cap.
- **Model per role, not one model for everything.** Route simple validation to gpt-4o-mini or Haiku; keep complex reasoning on larger models. A 3-agent pipeline using role-matched models costs 30–40% less than using the same model for every agent.
- **Never raise exceptions in tool `_run` methods.** Return error strings so the agent can retry or self-correct. An exception in a tool aborts the entire trajectory; an error string gives the ReAct loop a chance to recover.
- **Sequential before hierarchical.** Sequential crews have less non-determinism and are easier to debug. Add hierarchical coordination only when parallelism genuinely matters and you've earned the complexity.

## Evidence

- **Research paper:** MAST taxonomy (UC Berkeley, arXiv 2503.13657, March 2025) — analyzed 1,642 execution traces across 7 MAS frameworks; found coordination breakdowns account for 36.9% of all failures, the single largest category, with 14 identified failure modes across three clusters: specification issues, inter-agent misalignment, task verification. — https://arxiv.org/abs/2503.13657
- **Engineering post:** CrewAI in Production 2026: Real Lessons (AgileSoftLabs, June 2026) — `max_iter` default of 25 as main cost driver; narrow roles with 2 tools beat broad roles with 6; Pydantic `output_pydantic` as top reliability fix; 3-agent pipeline at 100/day ≈ $900/month; never raise exceptions in tool `_run`. — https://www.agilesoftlabs.com/blog/2026/06/crewai-in-production-2026-real-lessons
- **Engineering post:** Multi-Agent Systems in Production: Lessons from the Field (Data-Gate, 2026) — fintech case study: 2-hour single-agent → 12 minutes with 5 specialized agents; over-engineering from day one causes months of debugging coordination instead of solving problems; decomposition at natural boundaries (domain expertise, parallelizable subtasks, quality gates) outperforms decomposition at demo boundaries. — https://data-gate.ch/multi-agent-systems-production-lessons/
- **Framework comparison:** LangGraph vs CrewAI (Nexus, Nov 2025) — LangGraph: explicit directed graphs, deterministic state control, checkpointing with time-travel debugging; CrewAI: faster to prototype, role-based crews, harder to trace execution; LangGraph adopted by Klarna, Uber, LinkedIn. — https://agent.nexus/blog/langgraph-vs-crewai
- **Quantitative:** Google internal experiments on topology — 6× speedup (1 hour → 10 minutes) via multi-agent decomposition; AdaptOrch study — topology architecture beats model choice by 12–23% on task performance. — https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html

## Gotchas

- **Agents hallucinate their collaboration partners.** Give each agent an explicit, minimal description of who it hands off to and what they need — not just "the next agent will handle this."
- **Context accumulates asymmetrically.** Early agents in a chain have clean context; later agents get verbose, self-referential history. Put a summarization step before each handoff, not just at the end.
- **Failure modes shift at scale.** A 3-agent demo may work reliably; a 12-agent pipeline introduces failure modes (circular handoffs, priority conflicts, partial failures) that don't appear until you add the fifth agent.
- **Tool choice proliferation is a smell.** If an agent needs 6+ tools to do its job, it should probably be two agents. Broad goals with many tools cause wrong-tool selection, loop behavior, and inconsistent output.
- **The observability gap.** LangSmith, Langfuse, Arize Phoenix, or Braintrust trace every handoff in a multi-agent pipeline. Without this, you can't tell whether a failure was in agent A, the handoff, or agent B — you just see a bad final output.
