# S-2745 · The Orchestration Topology Stack — When Your Agents All Connect but Nobody Planned the Shape

You have two agents working together. The wiring between them is an afterthought — a shared prompt instruction that says "delegate to the code reviewer." It works for a week, then silently fails when the delegation format changes. The shape of agent connections matters as much as the agents themselves.

## Forces

- **Complexity ceiling vs. capability floor** — Multi-agent topology unlocks capabilities that single agents can't reach, but each pattern adds latency, cost, and failure surface. Teams systematically over-topologize: 80% of production use cases are handled by simple chains (LangChain 2025 survey), yet most pilots start with fan-out architectures.
- **Explicit control vs. emergent coordination** — State machines (LangGraph) enforce a defined shape; role-based crews (CrewAI) let agents negotiate. The right choice depends on whether your workflow is more like a factory or more like a committee.
- **Quality vs. throughput** — The evaluator-optimizer loop catches more bugs than a single pass, but doubles latency and cost per iteration. The question is whether your error surface is worth the overhead.
- **57% of AI project failures trace to orchestration design** — individual agents are strong enough; the coordination layer breaks. Knowing which topology fits which workflow characteristic is the difference between a pilot that ships and one that stalls.

## The Move

Match your workflow shape to one of five proven topologies. Each has a clear entry condition and a clear "you've outgrown this" signal.

**1. Sequential chaining — for linear transformations**
- Tasks where output of agent A is input to agent B, with no branching and no back-and-forth
- Best for: document pipeline (scrape → extract → format → send), code lint → test → deploy
- Upgrades to: router when classification gates the path; evaluator-optimizer when quality gates the output

**2. Router pattern — for task classification gates**
- A lightweight classifier (rule-based or model-based) dispatches incoming requests to specialized agents
- Best for: multi-intent inboxes, systems where different request types need fundamentally different tools
- Production data: 30–60% cost reduction when cheap routing model filters before expensive downstream agents (AnhTu.dev, 2026)
- Implementation: pair a Haiku-class classifier with an explicit tool/agent whitelist per class; never let the router pass an unclassified intent downstream

**3. Fan-out / Fan-in — for parallel independent work**
- One coordinator spawns N parallel agents, waits for all, then aggregates results
- Best for: document batch processing, parallel research branches, map-reduce over a list
- Key constraint: latency = slowest agent + aggregation overhead; cost = N × per-agent cost
- Upgrades to: orchestrator-worker when workers share intermediate state; evaluator-optimizer when aggregation quality is inconsistent

**4. Orchestrator-worker — for complex tasks with shared context**
- A central agent plans, delegates sub-tasks to specialized workers, synthesizes results, and handles retries
- Best for: research pipelines, multi-step analysis, customer support flows where context must flow between stages
- Key advantage over fan-out: the orchestrator can make routing decisions mid-flight based on partial results
- LangGraph's `Pregel` compute model is purpose-built for this pattern; agents pass typed state through graph nodes rather than negotiating via chat

**5. Evaluator-optimizer loop — for iterative refinement with quality gates**
- Generator agent produces output; evaluator agent scores it against criteria; loop continues until pass or max iterations
- Best for: code generation with review, document drafting with editorial criteria, any output where "good enough" has a measurable definition
- Cross-model review: one provider generates, a different provider evaluates — each model has different blind spots, so cross-provider review catches more than self-review (heyuan110.com, 2026)
- Guard against: adversarial dynamics where evaluator becomes a nitpicker; define stopping criteria precisely and instrument the loop counter

## Evidence

- **LangChain 2025 Production Survey:** Simple chains handle 80% of production use cases — teams consistently over-engineer with multi-agent topology on first implementation. Start with the simplest pattern that meets requirements; upgrade only when metrics prove the current one doesn't scale.
- **Hacker News Discussion (128 pts):** Practitioners report highest value from "scripts that wrap a small handful of agent calls" — lightweight sequential chaining beats complex multi-agent choreography for boring B2B/B2E workflows. The bottleneck is rarely agent count; it's context management and failure handling within each agent.
- **Digits ML / MLOps World 2025 (Hannes Hapke):** A production agent is ~100 lines of code combining: an objective, an LLM, tools, and a retry loop. Framework choice matters far less than the plumbing: typed state, checkpoints, human-approval gates, and per-step traces. Renamed "agents" to "Process Daemons" in internal lexicon — sets the right expectation for what the system actually does.
- **AnhTu.dev (2026):** 57% of AI project failures have root cause in orchestration design. Multi-agent pilots fail within 6 months at 40% rate. Fan-out multiplies cost by N but latency equals slowest agent + aggregation — only worth it when latency is the top priority AND chunks are truly independent.
- **arXiv 2607.19297 (Pearson et al., 2026):** LangGraph's graph-based workflow makes workflows easier to *inspect, repair, pause, resume, and govern* — the useful question is not whether a graph makes an LLM smarter, but whether it makes a workflow easier to operate. Three executable recipes: SQL analytics with repair loops, agentic RAG with evidence gating, human-in-the-loop policy review with interrupt/checkpoint recovery.
- **Sim Studio HN Discussion (196 pts):** Founders explicitly disagree with OpenAI's "single multi-step agent" guidance — argue that explicit, declarative workflow graphs are the key to reliable, maintainable agentic applications. Built a drag-and-drop GUI for LangGraph-style directed graph construction.
- **TokenMix Research (2026):** Four frameworks dominate production: LangGraph (stateful graph, high production reliability), CrewAI (role-based crews, fastest prototyping), AutoGen/AG2 (multi-agent conversations, research), OpenAI Agents SDK (opinionated handoffs, OpenAI-native). Not competing for the same niche.

## Gotchas

- **The graph becomes unmaintainable** — LangGraph's graph-of-nodes approach scales well, but practitioner HN reports (r/LangChain, 2026) show that once a workflow exceeds ~10 nodes, the graph itself becomes a debugging surface. Plan node boundaries deliberately; a node per conceptual step, not per LLM call.
- **CrewAI's process abstraction hides the topology** — fine for prototyping; dangerous when you need to trace a specific failure through a multi-agent handoff. When you hit the 6-12 month ceiling, you're rewriting topology assumptions baked into the role definitions.
- **Fan-out assumes independence; it often doesn't hold** — parallel agents frequently discover they need shared context established after the fact. Model fan-out around independent chunks only; use orchestrator-worker when agents need to build on each other's results.
- **Evaluator-optimizer loops need explicit stop criteria** — without a numeric quality threshold or iteration cap, adversarial evaluator-agent dynamics produce infinite loops. Instrument the loop counter and alert on approach to cap.
