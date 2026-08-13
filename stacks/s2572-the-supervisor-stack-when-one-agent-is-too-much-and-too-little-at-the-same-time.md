# S-2572 · The Supervisor Stack — When One Agent Is Too Much and Too Little at the Same Time

{One-sentence situation — where this bites, when you reach for it}

A single agent tasked with too many domains, too many tools, or too long a context starts failing silently — degrading mid-task with no signal, or hallucinating tool invocations that were never real. The supervisor stack decomposes one brittle generalist into a central router and a team of specialists, each owning a narrow slice.

## Forces

- **Long-context collapse:** Retrieval accuracy in a single agent degrades by up to 73% when critical information is buried in the middle — even with large context windows. A supervisor routes each sub-task with fresh context, sidestepping this entirely.
- **Tool proliferation penalty:** LangChain's benchmarks show significant performance decline once a single agent handles 5+ tools across distractor domains. Each added tool degrades the agent's ability to pick the right one.
- **Evaluation paralysis:** A single monolithic agent is opaque to measure. When it fails, you don't know if it was the reasoning, the retrieval, the domain knowledge, or the tool selection. Specialist agents are independently testable.
- **Team ownership friction:** Different teams own different capabilities. A single agent requires concatenating all domain knowledge into one prompt. A supervisor team lets each team own their agent independently.
- **Cost and latency compounding:** More agents mean more LLM calls per turn. The supervisor stack must balance specialization against the cost/latency tax of coordination overhead.

## The move

The supervisor stack uses a central orchestrator agent to **decompose** incoming tasks and **route** sub-tasks to specialized agents, then **integrate** their outputs. The key design decisions:

- **Define specialist agents with narrow, non-overlapping tool sets.** A researcher agent gets search + read. A code agent gets bash + file ops. A reviewer gets evaluation criteria only. Overlap is the enemy — it creates routing ambiguity that compounds down the chain.
- **Route by task type, not by LLM.** The supervisor's job is classification and delegation — it does not need the most expensive model. It needs reliable structured output (tool calls or JSON) so the routing is deterministic.
- **Use fresh context per specialist call.** Pass only the relevant task and supporting context to each specialist, not the full conversation history. This eliminates the "lost in the middle" degradation that kills single-agent performance.
- **Aggregate results through a synthesis step.** Specialists return outputs; the supervisor (or a dedicated synthesis agent) integrates them. The synthesis step is where quality control happens — check outputs against the original task before returning.
- **Set per-agent timeout and retry budgets.** LangChain's supervisor benchmark (τ-bench) showed that bounding specialist execution time prevents cascading failures from one stuck agent taking down the whole pipeline.
- **Design the handoff protocol explicitly.** Define what each specialist receives as input schema and what it must return as output schema. Ambiguity in handoff contracts is the primary failure mode in production multi-agent systems.
- **Instrument at agent boundaries.** Because failures are localized in the supervisor stack, you can measure per-agent success rate, latency, and cost independently. This is the primary operational advantage over a monolith.

## Evidence

- **arXiv (Philip Drammeh, 2025):** Multi-agent orchestration for incident response achieved 100% actionable recommendation rate vs 1.7% for single-agent across 348 controlled trials — an 80x improvement in action specificity and 140x in solution correctness. Multi-agent also produced zero quality variance across all trials, enabling production SLA commitments impossible with inconsistent single-agent outputs. — [arXiv:2511.15755](https://arxiv.org/abs/2511.15755)
- **LangChain Blog (Will Fu-Hinthorn, June 2025):** Benchmarking on τ-bench showed single agents fail sharply when 2+ distractor domains are present. Supervisor + specialists was the most generic and debuggable pattern; improvements to the supervisor routing yielded ~50% performance increase. LangChain open-sourced the implementation at [github.com/langchain-ai/langgraph-supervisor-py](https://github.com/langchain-ai/langgraph-supervisor-py). — [LangChain Blog](https://www.langchain.com/blog/benchmarking-multi-agent-architectures)
- **Databricks Engineering (October 2025):** Production deployment at BASF Coatings used supervisor architecture to orchestrate Marketmind — an agent system handling market intelligence across 11,000+ employees and 70+ global sites. The supervisor decomposed unstructured field interactions and routed to specialist agents for follow-up generation, opportunity surfacing, and peer matching. — [Databricks Blog](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)
- **TURION.AI (March 2026):** Field notes from production deployments identified three battle-tested patterns — supervisor + specialists, sequential pipeline, and parallel fan-out — with error recovery and state persistence as critical production requirements. — [TURION.AI](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **AccelateAI/multi-agent-orchestration (GitHub, 2026):** Production-grade reference implementation demonstrating supervisor routing, sequential pipeline, and parallel fan-out patterns with SQLite and Redis state persistence. — [GitHub](https://github.com/AccelateAI/multi-agent-orchestration)

## Gotchas

- **Supervisor hallucination bleeds into routing.** If the supervisor hallucinates a task decomposition (assigning work to the wrong specialist or inventing a non-existent domain), the error compounds downstream. Mitigate with explicit routing criteria — either structured tool-calling schemas or a simple decision tree — rather than letting the supervisor decide purely by generation.
- **"Telephone game" quality loss in deep chains.** Each agent-to-agent handoff loses nuance. Limit supervisor chains to 2 hops max; deeper hierarchies require a synthesis step at each level. LangChain's Swarm benchmark showed this explicitly — less translation between agents correlated with better outcomes.
- **Cost scales with agent count per turn.** Parallel fan-out helps latency but multiplies cost. Profile the cost per task type and set a budget: for simple tasks, a sequential pipeline may be cheaper than a parallel fan-out that fires 5 agents.
- **State management is an afterthought.** Most supervisor stack tutorials omit how specialists share state across turns. Production implementations (Redis, Postgres, or SQLite store) are required for any session with more than one user turn. LangGraph's `MemorySaver` or AccelateAI's `state/` module are starting points.
- **Tool overlap creates infinite loops.** If two specialists both have access to a web search tool and neither is designated to terminate, the supervisor may oscillate between them. Define a termination agent or an explicit end-of-task signal that requires no further specialist calls.
