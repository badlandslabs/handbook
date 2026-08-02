# S-2019 · The Orchestration Pattern Stack — When You Reach for LangGraph Before You Know What Pattern You Need

You have a multi-step AI task. Your first instinct is to scaffold a LangGraph project. You spend two days building a beautiful directed graph with conditional edges, custom state classes, and structured outputs — and then realize your use case was a four-step linear pipeline that would have worked fine as a sequential chain. This is the orchestration mistake: conflating the framework with the pattern. The pattern determines the cost, latency, failure surface, and debuggability. The framework is an implementation detail.

## Forces

- **Most teams over-architect their first multi-agent build.** LangChain's 2025 production survey found that simple chains handle 80% of production use cases, yet teams consistently reach for the full agentic stack on day one.
- **The wrong pattern amplifies cost by 5–10×.** Token duplication in open multi-agent frameworks is severe: MetaGPT wastes 72% of tokens, CAMEL 86%, AgentVerse 53%. Running a MapReduce pattern where a Sequential chain would suffice means paying for parallel agents to do work that didn't need parallelism.
- **Pattern choice is irreversible.** Switching from a supervisor pattern to a hierarchical one, or from a god agent to a fan-out, requires rewriting the core control flow — not a config change.
- **The blocker is rarely technical.** MMC.vc's 2025 survey of 30+ agentic AI founders found that the main barriers are workflow integration (60%), employee resistance (50%), and data privacy (50%) — not model capability or framework maturity.

## The Move

Start with the simplest pattern. Move down the complexity ladder only when the simpler pattern genuinely cannot work.

**The six patterns, in order of complexity:**

1. **Sequential Chain** — LLM A output feeds LLM B input. Predictable, debuggable, no parallelism. Best for pipelines where each step has a single clear purpose: extract → validate → store. Tradeoff: latency compounds, errors in step 1 cascade, no parallelism possible.

2. **Router / Classifier Dispatch** — A lightweight model (often a smaller one, or even keyword matching) classifies the input and routes to the right agent or pipeline. Best for handling heterogeneous input types where a single agent would need too many tools to stay coherent.

3. **Parallel Fan-out / Fan-in (MapReduce)** — A task is split across multiple agents working simultaneously, then results are aggregated. Best for document processing at scale, multi-perspective analysis, or sentiment analysis across large datasets. Think: 10 documents → 10 agents → 1 aggregator.

4. **Supervisor / Single-leader** — One orchestrator agent decides which sub-agents to call, in what order, and synthesizes the final output. Best for complex workflows where governance matters — you want one agent accountable. Limitation: single point of failure if the supervisor goes off-track.

5. **Hierarchical** — A supervisor delegates to sub-supervisors, which delegate to agents. Best for enterprise-scale systems with 20+ agents across multiple domains. Tradeoff: coordination overhead grows quadratically with depth.

6. **Peer-to-Peer / Swarm** — Agents communicate directly, negotiate, and form consensus without a central coordinator. Best for fault tolerance and distributed optimization. Tradeoff: slower consensus, emergent behavior hard to debug.

**Choosing the right framework per pattern:**

| Pattern | Framework | Notes |
|---------|-----------|-------|
| Sequential Chain | PydanticAI, raw API calls | No framework needed |
| Router | LangChain routers, FastAPI | Lightweight is fine |
| MapReduce / Fan-out | LangGraph, CrewAI Flows | Structured state key |
| Supervisor | LangGraph, AutoGen | Supervisor as a LangGraph node |
| Hierarchical | LangGraph (nested graphs), AutoGen | Complexity scales with depth |
| Peer-to-Peer / Swarm | Custom, Temporal, Kafka | Most framework-independent |

**Rule of thumb from production teams:** Agents as leaf nodes only. The supervisor/orchestrator should route, not execute. Every agent should have 2–5 tools max and a narrow role — not 15 tools and a broad mandate. The "god agent" anti-pattern (one agent doing everything) causes context window exhaustion, confused reasoning chains, and no parallelism.

## Evidence

- **Framework benchmark:** The Microsoft Azure Architecture Center (2026) formalizes this six-level complexity spectrum, noting that each level introduces coordination overhead, latency, and cost — and recommending teams "use the lowest level of complexity that reliably meets requirements." — [Microsoft Learn](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

- **Enterprise adoption data:** 72% of enterprise AI projects now involve multi-agent systems, up from 23% in 2024 (Zylos Research, 2026). Real-world results cited: 80% reduction in insurance claims processing time; $18.7M annual savings in banking fraud detection. Token duplication is the dominant cost concern. — [Zylos Research](https://zylos.ai/research/multi-agent-orchestration-2025)

- **Production failure patterns:** "LangChain tutorials make everything look easy. String together some prompts, add memory, ship it. Then you hit production and realize that 'simple chain' fails in seventeen different ways." Real teams report that sequential beats hierarchical for reliability; `max_iter` defaults to 25 (CrewAI's default) — the biggest cost driver — and should be set to 5–8 per agent. — [Agentika](https://agentika.uk/blog/llm-orchestration-patterns.html)

- **Real-world case study:** Cisco Outshift built a LangGraph-based agentic AI platform engineer that achieved a 10x productivity boost by routing tasks to specialized sub-agents rather than using a monolithic agent. Architecture: supervisor as a LangGraph node, specialized agents as leaf nodes, structured state passed between nodes. — [LangChain Blog](https://langchain.com/blog/cisco-outshift)

- **HN production reality:** In a 2025 HN thread on multi-agent orchestration in production, multiple practitioners reported abandoning LangChain/CrewAI entirely for custom Node.js + V8 isolate solutions or lightweight custom abstractions. Primary reasons: too much abstraction, poor debugging, framework not suited for the specific pattern needed. — [Hacker News](https://news.ycombinator.com/item?id=47660705)

## Gotchas

- **Reaching for the framework before the pattern.** The first question is not "LangGraph or CrewAI?" — it is "sequential, fan-out, or supervisor?" Framework choice follows pattern choice.
- **`max_iter` default blindsides you.** In CrewAI, default max iterations per agent is 25. One bad run with 3 agents can burn 5–10× the token budget of a well-bounded run. Set per-agent iteration caps before anything else.
- **Token duplication kills cost efficiency.** Running a multi-agent setup where every agent re-reads the full conversation history (a common LangChain memory pattern) compounds token costs dramatically. Externalize shared state rather than relying on context inheritance.
- **Supervisor as single point of failure.** A supervisor that goes off-track propagates bad decisions to all sub-agents. Add output validation at the supervisor level and a circuit breaker on the supervisor's authority to escalate to human review.
- **Sequential is not always slower.** Teams assume parallel = faster. But parallel fan-out introduces the aggregation step, which itself may require another LLM call to synthesize. For 3 or fewer steps with dependencies, sequential is simpler, cheaper, and more debuggable.
