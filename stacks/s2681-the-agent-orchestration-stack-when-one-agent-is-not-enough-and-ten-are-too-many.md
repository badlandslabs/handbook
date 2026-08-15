# [S-2681] · The Agent Orchestration Stack

When one agent can't finish the job but ten agents become unmanageable — and you need to figure out the right coordination structure before you ship.

## Situation

You shipped a single-agent system. It handles straightforward cases well but degrades on complex, multi-domain tasks. You consider going multi-agent, then realize you don't know whether to use a central orchestrator, a peer network, a supervisor hierarchy, or something else entirely. The choice isn't academic — it determines latency, cost, failure modes, and whether you can debug what went wrong at 2am.

This is the **orchestration pattern decision**: the structural choice of how agents coordinate, communicate, and hand off work. Get it right and you get parallelism, specialization, and graceful degradation. Get it wrong and you get cascading failures, silent deadlocks, and runaway token costs.

## Forces

- **Cost vs. quality tradeoff** — capable models orchestrate better; cheaper models specialize better. You need both, which means model tiering — but tiering adds latency and coordination overhead.
- **Coordination overhead scales non-linearly** — a peer network of 10 agents has 45 potential channels; a supervisor/worker tree has 10. Observability tooling like LangSmith works well with hierarchical trees but struggles with concurrent peer graphs.
- **Teams adopt multi-agent too early** — Reddit consensus on r/LangChain is blunt: a single agent with 3–5 well-scoped tools beats a three-node graph with extra latency. The threshold is real and often missed.
- **Pattern choice determines failure mode shape** — a sequential pipeline's failure is localized; a peer mesh can cascade silently; an event-driven system can deadlock via circular delegation.
- **Ad-hoc chaining collapses in production** — by 2025, teams that naively chained LLM calls discovered semantic failures (logically wrong parameters), context corruption, unlimited retry loops, and silent state loss. Structured patterns emerged from this pain.

## The move

The core decision tree:

1. **Start with a single agent and tools.** Only move to multi-agent when you have real evidence: distinct security boundaries, independent parallel work, or multi-domain expertise that genuinely can't fit in one context. The burden of proof is on orchestration, not on simplicity.

2. **Choose topology by dependency shape.** Three patterns cover most cases:
   - **Orchestrator-Worker (supervisor pattern):** One capable lead agent plans and delegates; specialist workers handle subtasks; lead assembles results. Best for: structured tasks with known subtask decomposition. The lead model is expensive; workers are cheap. Anthropic's production Research system uses this with Opus 4 as lead and Sonnet 4 subagents, achieving +90.2% quality improvement over single Opus 4.
   - **Sequential Pipeline:** Strict linear handoff where each agent's output feeds the next. Best for: batch workflows, content pipelines, ETL with AI stages. Simple, predictable, easy to audit — but the slowest step sets overall latency.
   - **Peer Network (mesh):** Agents communicate directly with each other, sharing context without a central coordinator. Best for: collaborative reasoning, debate patterns, multi-perspective analysis. Most flexible but hardest to debug — communication channels grow quadratically.

3. **Model tier the lead.** The most impactful cost decision: use a capable model (Opus 4, o3, GPT-4 class) only for orchestration, planning, and synthesis. Delegate tool execution and domain tasks to smaller, cheaper models. This is how Anthropic achieved 4× token reduction while improving output quality.

4. **Make the control flow explicit — use a framework, not raw API calls.** LangGraph (state machine model), CrewAI (role-based agents), and AutoGen (conversational agents) are the three dominant open-source choices. LangGraph earns its keep when branching, durability, or auditability is required — it treats orchestration as a first-class state machine rather than a chat transcript. CrewAI wins for speed and clarity when roles are well-defined. AutoGen is the choice when human-in-the-loop or conversational workflows are central. Teams that started with CrewAI and hit complex branching are migrating to LangGraph.

5. **Bound the loop.** Every agent needs a maximum step count, a termination condition, and explicit cost limits. Unbounded loops are the leading cause of runaway token bills in production. Set `max_iterations`, `timeout`, and `budget` at the orchestration level — not per-agent.

6. **Add observability from day one.** LangSmith, Langfuse, or similar trace-level instrumentation is not optional. Multi-agent systems generate complex execution trees; debugging without traces means reading raw API logs and reconstructing the call graph manually.

## Evidence

- **Anthropic's production multi-agent research system (June 2025):** Uses a lead agent (Opus 4) that plans research and spawns parallel subagents (Sonnet 4) that search simultaneously. Achieved +90.2% improvement on BrowseComp vs single Opus 4. Multi-agent uses ~15× more tokens than chat, but token usage explains 80% of variance in performance. Multi-agent completes tasks in ~70% less time than single-agent traversal. — [Anthropic Engineering Blog](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Microsoft ISE retail customer case study (June 2026):** Evolved from a modular monolith with a router pattern (single-agent routing per query) to a supervisor-worker microservices architecture enabling agent reuse across teams. Key lesson: peer-to-peer meshes of 10+ agents create 45+ communication channels; supervisor/worker topology has 10. The architectural choice has direct cost, reliability, and latency consequences. Coordination overhead scales non-linearly with topology complexity. — [Microsoft ISE Developer Blog](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

- **Reddit r/LangChain community pattern (2025–2026):** Community consensus: most teams adopt multi-agent orchestration too early. Rule of thumb: use a single agent with 3–5 well-scoped tools before reaching for a graph. LangGraph became the de facto answer for teams that outgrew CrewAI — specifically when they needed branching, crash-safe resume, or audit trails. The migration pattern (CrewAI → LangGraph) appears consistently in community discussion threads. — [r/LangChain via IdeaToMVP](https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026)

- **HN "Ask HN: What's your multi-agent orchestration setup?" (2025):** Practitioners discussing personal multi-agent setups cited Scion (Google Cloud's agent orchestration framework), direct model-as-coordinator patterns, and role-separated agents for coding/design/testing/supervision. The conversation reflects real adoption tension between tooling maturity and architectural simplicity. — [Hacker News](https://news.ycombinator.com/item?id=48559933)

- **Gartner / Princeton NLP data:** Organizations average 12 agents in use, projected to grow 67% within two years. Princeton NLP found single-agent matches multi-agent on 64% of tasks; multi-agent adds only 2.1 percentage points of accuracy at roughly double the cost. Rule of thumb from practitioners: start with the simplest pattern. — [Beam.ai](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)

- **GitHub trending frameworks (2026):** LangGraph (~30K+ stars), CrewAI, and AutoGen dominate open-source agent orchestration. Agentic-Orchestra on PyPI offers profile-based agent pooling with race-safe creation. Scion (Google Cloud) provides harness/env + agent provider + agent definition separation for production fleets. — [GitHub Topics: ai-orchestration](https://github.com/topics/ai-orchestration)

## Gotchas

- **Don't build a peer mesh until you've tried a supervisor tree.** The flexibility of peer networks looks appealing but the debugging cost is real. Start hierarchical; go mesh only when you have concrete evidence the supervisor is a bottleneck.
- **Tool design is orchestration design.** How you define tools determines how cleanly agents can delegate. If your orchestrator's "tools" are actually doing multi-step work, you've hidden orchestration complexity — badly.
- **Context window is a topology constraint.** Sequential pipelines consume more tokens (each agent passes full context forward). Supervisor-worker with focused subagents conserves tokens. Peer meshes with shared context explode it. Model your token budget before choosing.
- **Human-in-the-loop isn't a pattern — it's a safety layer.** If you need human approval at decision points, add it as a guard on the orchestration edge, not as a special agent type. AutoGen's strength here is the conversational approval interface; don't replicate it ad-hoc.
- **Observability before optimization.** Trace every agent call from day one, even if the graph is simple. Retrofitting traces into a multi-agent system is painful; starting with LangSmith/Langfuse costs nothing and saves hours of debugging.
