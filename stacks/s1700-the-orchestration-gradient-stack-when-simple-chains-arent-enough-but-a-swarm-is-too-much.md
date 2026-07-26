# S-1700 · The Orchestration Gradient Stack — When Simple Chains Aren't Enough But a Swarm Is Too Much

Teams do not wake up and choose to build multi-agent systems. They start with a single LLM call, add a second for a slightly different task, and discover they have built an orchestration problem. The dominant finding across practitioner surveys and HN threads in 2025–2026 is not that one pattern wins — it is that teams pick the wrong point on the complexity gradient, and pay for it.

The **Orchestration Gradient Stack** maps where to enter: what the task actually demands, and what pattern matches that demand without adding unearned complexity.

## Forces

- **Most tasks are linear.** LangChain's 2026 survey (N=1,340 teams) found that simple chains — ordered sequences of LLM calls with no autonomous routing — handle 80% of production use cases. Yet teams consistently reach for agents too early.
- **The cost and latency penalty for full agents is severe.** Agent loops cost 3–5x more than chains and add 40%+ latency. The router pattern cuts that cost by 60% and latency by 40% by dispatching to specialists only when classification is needed.
- **Coordination overhead compounds.** Every additional agent in a workflow adds latency, cost, and a new failure surface. Multi-agent systems are harder to operate by roughly the order of their agent count.
- **Framework immaturity pushes teams custom.** Multiple HN respondents building production pipelines said "there's absolute zero framework out there that's good enough for serious work" — they built their own orchestration layers.

## The move

Match the orchestration pattern to the actual autonomy requirement of the task. Work up the gradient only when the previous level demonstrably fails.

1. **Start with a simple chain.** Ordered, deterministic LLM calls. No autonomous routing. 80% of production use cases end here. Frameworks: LangChain LCEL, DSPy pipelines.
2. **Add a router when you have distinct verticals.** A classifier (LLM or keyword) dispatches the query to the appropriate specialist. The router pattern cuts cost 60% and latency 40% versus running a full agent loop. Frameworks: LangGraph router, CrewAI routing.
3. **Reach for a supervisor + specialists when branching, approvals, or crash-safe resume are required.** One supervisor decomposes tasks and routes to specialist agents. Supervisors integrate the output. This is the most battle-tested multi-agent pattern in production. Frameworks: LangGraph supervisor, CrewAI hierarchical mode, OpenAI Agents SDK handoffs.
4. **Use event-driven fan-out when independent subtasks can run in parallel.** Fan out to N researchers or validators, collect responses, merge. Latency drops but merge logic and race conditions become the failure mode. Frameworks: LangGraph branches, Temporal with agent workers.
5. **Treat swarm/actor-model orchestration as a last resort.** Emergent collaboration across many loosely coupled agents. Maximum flexibility, maximum operational complexity. Only when the problem genuinely requires negotiation between equals, not delegation from a supervisor.

The decision heuristic from r/LangChain and TURION.AI's production post (2026): use multi-agent orchestration only when you have at least one of — branching logic based on output, parallelism with merge, or a need for crash-safe resume. If you just need more capability, improve the system prompt or add a tool.

## Evidence

- **LangChain State of Agent Engineering Survey (June 2026, N=1,340):** 57.3% of teams have agents in production, up from 51% YoY. 89% have observability. 52.4% run offline evaluations. Survey explicitly notes cost concerns have dropped while quality concerns (32%) remain the top production barrier. — [langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering)
- **HN Ask thread — "How are you orchestrating multi-agent AI workflows in production?" (2025, HN item #47660705):** 11 practitioner responses. Key findings: some teams roll their own (Node.js in V8 isolates, custom lightweight abstractions), others use LangGraph + custom on top, or AGNO for minimalistic isolation. One respondent noted their orchestration is "ironically managed by an agent." State management: MongoDB + JSON for shared state, session-scoped memories with importance scoring. — [hn.nuxt.dev/item/47660705](https://hn.nuxt.dev/item/47660705)
- **TURION.AI — "Multi-Agent Orchestration Infrastructure: Lessons from Production" (March 2026):** Surveyed a dozen production deployments. Finding: Supervisor + Specialists is the pattern with the best debuggability-to-effectiveness ratio. LangGraph's state machine model earns its keep over CrewAI when you need crash-safe resume and branching. — [turion.ai/blog/multi-agent-orchestration-infrastructure-production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Agentika — "LLM Orchestration Patterns That Actually Work" (February 2026):** Simple chains: 80% of production use cases, 73% of production systems use chains. Router pattern: 60% cost reduction, 40% latency reduction. Harrison Chase (LangChain CEO): "Start with the simplest orchestration that could work. Most teams over-engineer with agents when a chain would do." — [agentika.uk/blog/llm-orchestration-patterns.html](https://agentika.uk/blog/llm-orchestration-patterns.html)
- **Groovy Web — "Multi-Agent Orchestration Patterns 2026" (June 2026):** Sequential pipelines (low complexity, single failure point), parallel fan-out (merge logic is the new failure mode), hierarchical/supervisor (manager bottleneck risk), state-graph (LangGraph, most production-flexible), swarm (emergent, highest complexity). — [groovyweb.co/blog/multi-agent-orchestration-patterns-supervisor-router-pipeline-swarm-2026](https://www.groovyweb.co/blog/multi-agent-orchestration-patterns-supervisor-router-pipeline-swarm-2026)

## Gotchas

- **Over-engineering at entry.** The single most common mistake: reaching for LangGraph supervisor or CrewAI hierarchical mode when a sequential chain with a few extra tools would solve the problem. The 80% stat is not a coincidence — it's a signal about how much work simple chains can actually do.
- **Supervisor bottleneck.** In hierarchical patterns, the supervisor becomes the serialization point. Every task flows through it, meaning its prompt and model quality determine overall system quality. If the supervisor fails, the entire system fails — it just fails faster.
- **State explosion in state graphs.** LangGraph's state machine model is powerful but the graph definition itself can become unmaintainable. Multiple teams on r/LangChain have posted migration stories where the graph grew too complex to reason about, forcing architectural rewrites.
- **No observability for emergent failures.** In multi-agent systems, failures are often not agent failures but interaction failures — the output of one agent gets misinterpreted by another, or the merge logic doesn't handle an unexpected format. Individual agent tracing is necessary but not sufficient; you need trace correlation across agents.
