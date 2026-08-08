# S-2308 · The Specialization Split — When One Agent Is Not Enough

You have a complex task. A single agent handles it, but the results are shallow, brittle, or wrong in ways you can't predict. You reach for "more capable model" but that hits cost ceilings. The real answer is splitting work across multiple agents — but that raises harder questions: how do you divide the labor, who coordinates the pieces, and how do you stop one agent's errors from contaminating everyone else's?

## Forces

- **Single agents hit a quality ceiling on complex, multi-domain tasks.** Incident response data shows single-agent systems produce actionable recommendations 1.7% of the time versus 100% for multi-agent systems — not because the model is worse, but because one agent can't simultaneously specialize in triage, diagnosis, and resolution. — [arXiv 2511.15755 / MyAntFarm](https://arxiv.org/html/2511.15755)
- **Non-determinism compounds across hops.** Multi-agent success probability = p^n where p is per-step reliability and n is the number of hops. At 95% reliability over 20 hops, end-to-end success is ~36%. At 90%, it's ~12%. A single agent turn often contains multiple sub-steps (plan, call, parse, hand off), so visible hops undercount the real exposure. — [LatentEval / MAST Taxonomy](https://latenteval.ai/analysis/multi-agent-failure-modes)
- **Error propagation is faster than recovery.** In a 4-agent coding pipeline (architect → developer → reviewer → QA), a single false claim from the architect reached 100% adoption in 5 of 6 tested frameworks within 3 rounds. The error wasn't caught — it was treated as authoritative input. — [danilchenko.dev / arXiv 2603.04474](https://www.danilchenko.dev/posts/2026-04-01-error-cascades-multi-agent-llm-systems)
- **The coordination overhead tax is real.** Dynamic LLM-based routing at every decision point costs tokens, adds latency, and introduces unpredictability. Many workflows have known structure — forcing dynamic routing on them is wasted overhead.

## The Move

### Choose your orchestration topology before choosing your framework

The three canonical patterns have distinct failure profiles:

**1. Hierarchical / Lead-Subagent (Anthropic pattern)**
A lead agent plans and spawns parallel subagents, each with isolated context. The lead coordinates but doesn't execute. Used by Anthropic's Research feature (June 2025), Claude Orchestrator (Capozzi, Jan 2026), and the incident response study.

- Lead owns task decomposition and result synthesis
- Subagents run in parallel with separate context windows — no cross-contamination
- Subagents distill findings before returning to lead (parallel compression)
- Best for: open-ended research, parallel exploration, tasks where path is unknown at start

**2. Role-Based Crew (CrewAI pattern)**
Specialized agents with fixed roles (researcher, writer, reviewer) execute in a defined sequence or parallel, each with explicit goals and expected outputs. Roles are defined declaratively.

- Fastest to prototype — role definitions are short and readable
- Flow is either sequential (hierarchical) or consensual (agents vote/negotiate)
- Roles provide natural fault boundaries — a bad writer doesn't corrupt the researcher
- Best for: business workflows, content pipelines, tasks with known roles

**3. Graph-Based State Machine (LangGraph pattern)**
The workflow is a directed graph where nodes are agents and edges are transitions. Routing is explicit, conditional edges encode business logic, state is a typed object passed between nodes.

- Most production-ready for complex conditional logic
- Each node is a pure function: state in → state out
- Debugging is tractable — you can trace the exact path taken
- Best for: support tickets, multi-step forms, anything with branching logic

### Add a genealogy verification layer at the message-passing boundary

The single highest-leverage intervention for error propagation: verify claims before they become inputs. The "From Spark to Fire" research (arXiv 2603.04474, March 2026) shows that adding a lightweight claim-verification step at agent handoff boundaries raises defense from 32% to 89% without changing system architecture. Implement as middleware: each agent output is checked against ground truth before the next agent receives it.

### Prefer deterministic routing for known-structure workflows

For workflows with predictable structure, YAML-defined deterministic routing (Microsoft Conductor) eliminates token overhead at the orchestration layer, removes runtime routing unpredictability, and makes the workflow auditable. The tradeoff: you lose dynamic re-planning when the task genuinely requires it. Use dynamic routing (LLM decides next step) only where the path is genuinely unknown.

### Set per-agent circuit breakers, not just system-level ones

The MAST taxonomy (14 failure modes across 3 categories, grounded in 150 expert-annotated traces, kappa 0.88) shows that failures in multi-agent systems are propagation failures first. Circuit breakers at the agent level catch corruption before it spreads. System-level circuit breakers only fire after damage is done.

## Evidence

- **arXiv / Incident Response Study:** Single-agent (C2) achieved 1.7% actionable recommendation rate versus 100% for multi-agent (C3) orchestration in 115 incident response trials. Multi-agent showed zero quality variance (DQ variance = 0.000) versus 0.023 for single-agent — enabling SLA commitments. Both achieved ~40s comprehension latency; quality and determinism, not speed, were the differentiators. — [MyAntFarm.ai / arXiv 2511.15755](https://arxiv.org/abs/2511.15755)
- **Anthropic Engineering Blog:** Claude's Research feature uses a lead-subagent model. Key lessons: parallel compression (subagents distill before returning) prevents context overflow; isolation prevents error propagation; the lead's planning capability is the bottleneck. Published June 13, 2025. — [Anthropic](https://www.anthropic.com/engineering/multi-agent-research-system)
- **"From Spark to Fire" / arXiv 2603.04474:** Tested 6 multi-agent frameworks (AutoGen, CrewAI, LangChain, LangGraph, MetaGPT, Camel) with a false-claim injection. 5 of 6 reached 100% false-claim adoption within 3 rounds. A genealogy graph middleware raised defense from 32% to 89%. The verification layer must live at the message-passing boundary, not at the agent level. — [danilchenko.dev](https://www.danilchenko.dev/posts/2026-04-01-error-cascades-multi-agent-llm-systems)
- **Microsoft Open Source Blog:** Conductor CLI uses YAML-defined deterministic workflows with Jinja2 templating for agent input. Routing is predetermined — zero tokens consumed by the orchestration layer. The insight: many useful workflows have known structure; dynamic routing adds cost and unpredictability for no benefit in those cases. Published May 14, 2026. — [Microsoft Open Source Blog](https://opensource.microsoft.com/blog/2026/05/14/conductor-deterministic-orchestration-for-multi-agent-ai-workflows/)

## Gotchas

- **More agents ≠ better results.** Each agent hop multiplies failure probability. The incident response study used 3 specialized agents (C3) versus 1 generalist (C2) — the gain came from specialization, not from adding agents blindly. Profile your pipeline: identify where context isolation helps versus where it just adds hops.
- **Dynamic routing is seductive and expensive.** LLM-based orchestration ("the coordinator decides what to do next") is flexible but costs tokens on every decision and introduces unpredictability. Most production workflows are more structured than they appear. Default to deterministic; graduate to dynamic only where you can prove the path is genuinely unknown.
- **Context isolation is not the same as context management.** Spawning agents in parallel with isolated contexts prevents cross-contamination, but you still need the lead agent to synthesize results coherently. The synthesis step is where many multi-agent systems under-invest — a bag of good individual outputs is not a good result.
- **Latency multiplies with parallelism.** Running 5 agents in parallel sounds fast, but each agent still runs sequentially through its own tool-use loop. Parallelism helps when agents are I/O-bound (waiting on different external services), not when they're compute-bound (long model inference). Profile before assuming parallel = faster.
