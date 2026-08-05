# S-2157 · The Orchestration Topology Stack — When Dynamic Routing Costs More Than It's Worth

You have a multi-agent pipeline: research → analyze → write → review. The obvious approach is to let an LLM decide when to route between stages. It works. But you're paying token costs on every routing decision, debugging nondeterministic execution paths, and watching your observability tooling struggle to explain why the same input sometimes takes a different route. The question is whether that flexibility is earning its keep — or whether a static, YAML-defined topology would give you the same result with a fraction of the cost and a lot more predictability.

## Forces

- **LLM-driven routing adds cost on every decision.** An orchestrator model burning tokens to decide "should I call the writer now?" is overhead that compounds at scale. Microsoft Conductor's team explicitly measured this: YAML-based routing eliminates all token overhead on the orchestration layer itself.
- **Dynamic routing is genuinely valuable for open-ended problems.** When the agent faces genuine branching — user input is ambiguous, task type is unknown, the right tool isn't predetermined — an LLM planner earns its cost. The problem is using the same model for both reasoning and routing, which creates cognitive overload.
- **Observability is the #1 barrier to production multi-agent adoption** (corroborated across Zylos Research 2026, Beam.ai 2026). Static topology is trivially observable: you know the path before it runs. Dynamic topology requires runtime tracing to understand what happened and why.
- **40% of multi-agent pilots fail within 6 months of production deployment** (Beam.ai citing Gartner, 2026). The dominant failure mode is not that multi-agent systems don't work — it's that teams pick the wrong orchestration pattern or use the right one without understanding how it breaks.
- **72% of enterprise AI projects now involve multi-agent systems**, up from 23% in 2024 (Zylos Research). The tooling is maturing, but the decision framework for *which pattern to use when* is still immature in most teams.

## The Move

The core move: **treat orchestration topology as an explicit architectural choice, not a default**. Pick dynamic routing only where the branching genuinely can't be predetermined. Use deterministic routing everywhere else.

### Specific techniques:

- **Define known workflows in YAML with static routing.** Microsoft's Conductor (MIT, May 2026) uses Jinja2 expression evaluation in YAML: first matching condition wins, no LLM in the loop. Conductor's own README frames this as "same inputs follow the same path through the same agents, run identically locally and in CI." This maps well to code review pipelines, research-then-synthesize, plan-then-implement, and any pipeline with a fixed sequence of stages.

- **Use a supervisor LLM only for the decisions that actually need it.** Beam.ai's 2026 production guide identifies the supervisor pattern as best for complex workflows requiring governance — but flags single point of failure risk. The supervisor should own high-stakes routing that requires semantic understanding, not routine stage transitions.

- **Isolate routing from reasoning.** The HN thread on production orchestration (Ask HN "How are you orchestrating multi-agent AI workflows in production?", ID 47660705) surfaced a recurring failure: teams use the same model for both planning jobs and deciding transitions, creating cognitive overload. One practitioner solved this by using Express endpoints in V8 isolates with MongoDB for state — keeping the LLM isolated to its reasoning job, not mixing it into infrastructure concerns.

- **Build a router pattern before a coordinator pattern.** Microsoft's ISE blog (June 2026, Lily Jia) documents the evolution from a modular monolith with deterministic routing to a full microservices coordinator pattern. The key insight: a simple router — where each query routes to exactly one agent based on intent detection — is the right starting point. It can evolve into a coordinator (orchestrating multiple agents in parallel) only when the use cases demand it. Premature microservices-style coordination adds coordination overhead before the problem requires it.

- **Version-control your topology.** One practitioner in the HN thread reported building a "lightweight abstraction for running and managing agents, ironically managed by an agent" — and versioning the abstraction in git. Static YAML topologies are trivially diffable in pull requests, making workflow changes auditable and reversible.

- **Separate state from routing.** The HN thread identified Redis and MongoDB as common choices for agent state management in production, with the critical insight that state should be passed between agents as structured data, not as LLM-generated natural language summaries. This keeps the token-per-step cost bounded and makes state transitions inspectable.

## Evidence

- **Engineering blog:** Microsoft Open Source Blog (Jason Robert, Principal Software Engineer, May 14 2026) — Conductor: deterministic orchestration using YAML with Jinja2 expression evaluation, zero LLM token overhead on routing. Workflows are source-controlled, diffable in PRs, run identically locally and in CI. MIT license. — [Microsoft Open Source Blog: Conductor](https://opensource.microsoft.com/blog/2026/05/14/conductor-deterministic-orchestration-for-multi-agent-ai-workflows/)
- **Industry research:** Beam.ai (Fredrik Falk, August 2026) — 40% of multi-agent pilots fail within 6 months. Supervisor-worker pattern has single point of failure risk. Coordinator pattern enables parallel execution but adds coordination overhead. Swarms are for robotics and optimization (50+ agents), not general-purpose pipelines. — [Beam.ai: 6 Multi-Agent Orchestration Patterns for Production (2026)](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **Primary source discussion:** Hacker News (swrly, Ask HN ID 47660705, ~3 months ago, 11 comments) — Real production practitioners: custom Node.js/Express with MongoDB, AGNO ("minimalistic design for isolation, decoupling and control plane architecture"), LangGraph with custom orchestrator built on top. One practitioner's summary: "There's absolute 0 framework out there that's good enough for serious work." Consensus on treating full conversation history as context, not just latest message. — [HN: Multi-Agent AI Workflow Orchestration in Production](https://news.ycombinator.com/item?id=47660705)
- **Engineering blog:** Microsoft ISE Developer Blog (Lily Jia, June 12, 2026) — Evolution from router pattern (modular monolith, deterministic routing, one agent per query) to coordinator pattern (microservices, multiple agents in parallel, cross-team reuse). Key finding: start with a simple router before evolving to a coordinator; coordination overhead must be justified by use-case demands. — [Microsoft ISE: Orchestration Patterns for Multi-Agent Systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

## Gotchas

- **Don't use dynamic routing as a default because it feels more "AI-native."** This is the most common mistake. If your workflow has a known sequence, dynamic routing adds cost and nondeterminism without adding value. Measure the token overhead of your routing decisions — it's almost certainly higher than you think.
- **Don't evolve to a coordinator/microservices pattern before you have cross-team reuse demand.** The ISE case study shows that premature microservices coordination creates coordination overhead that hurts performance. A well-designed modular monolith with clear agent boundaries often runs 20–40% faster than an equivalent microservices topology for single-query workflows.
- **Don't pass state between agents as natural language.** Multiple HN practitioners flagged this: when agents communicate via LLM-generated summaries instead of structured data, token costs explode and observability collapses. Treat state as typed data, not prose.
