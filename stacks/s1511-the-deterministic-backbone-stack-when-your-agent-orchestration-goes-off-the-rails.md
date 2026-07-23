# S-1511 · The Deterministic Backbone Stack — When Your Agent Orchestration Goes Off the Rails

When your agent starts doing three things at once, looping on the same mistake, and no one can explain why — it's not a model problem. It's an orchestration problem.

## Forces

- **Flexibility vs. control** — agents that own their own execution paths are powerful but unpredictable; agents locked into rigid scripts are safe but fragile
- **Framework enthusiasm vs. production reality** — 2024 was full of elaborate multi-agent frameworks; 2025 taught teams that complexity is the enemy of reliability
- **State explosion** — the more agents you add, the harder it becomes to know where a workflow is, whether it recovered correctly, and what actually happened on failure
- **The latency/cost tradeoff** — agentic loops give better task performance but cost more and take longer than a single LLM call

## The Move

Layer a **deterministic state machine** as the orchestrator, with agents confined to reasoning within their assigned step. The engine owns sequence, retries, timeouts, and state. The agent owns what happens inside the step.

### The six production patterns (pick the simplest that works)

- **Pipeline (sequential specialists):** `extract → validate → enrich → draft → send`. Each step is a separate agent with a narrow role. Failure at step 3 rolls back or re-runs from step 3 — the state machine knows exactly where it is. Best for linear, well-defined workflows.
- **Router (intent dispatch):** A lightweight classifier (often a simple prompt or small model) routes incoming requests to the right specialist agent. Fast, low-cost, avoids the overhead of full agentic loops for queries that don't need them.
- **Planner-Worker:** A planning agent decomposes a complex goal into sub-tasks, then spawns or assigns worker agents. Workers report back; the planner synthesizes. Best for open-ended research and multi-domain problems.
- **Critic Loop:** A specialist agent produces output; a separate critic agent evaluates it against criteria. Iterates until the critic passes it. Expensive but catches quality regressions that would otherwise ship.
- **Human-Gate:** The deterministic engine pauses at a defined step and surfaces a decision to a human operator. The agent resumes from that checkpoint. Non-negotiable for high-stakes actions (payments, deletions, external sends).
- **Saga / Compensation:** For multi-step workflows where each step has a counterpart (commit/rollback). If step 3 fails, the saga runs compensating actions for steps 1-2. Used in financial and data pipelines.

### The three architectural schools

| School | Philosophy | Right tools |
|--------|-----------|-------------|
| **DAG-based** | Explicit dependency graphs, deterministic execution | LangGraph, Temporal, Airflow, Dagster |
| **Event-driven** | Async pub/sub, agents as reactive consumers | Kafka + A2A protocol + MCP |
| **Actor model** | Isolated state, message-passing, supervision hierarchies | AutoGen/MAF, Akka |

Most production systems **blend all three**: Temporal provides durable execution substrate, LangGraph handles agent reasoning, Kafka + MCP handles inter-service coordination.

### The framework decision

LangGraph has the largest production deployment footprint in 2026 — dominant for enterprise multi-agent systems. CrewAI has the strongest demo-to-prototype ergonomics but trails on production observability and error recovery. Microsoft AutoGen leads research adoption. OpenAI Swarm is light and opinionated, suitable for narrow use cases — not a full orchestration framework.

**The honest insight:** for most enterprise deployments, the framework choice is less consequential than model selection, evaluation infrastructure, and human-checkpoint design.

## Evidence

- **Anthropic engineering guide (Dec 2024, updated 2025):** Most successful agent implementations use simple composable patterns — not complex frameworks. Recommends starting with the simplest solution (optimized single LLM calls with retrieval and in-context examples) and only adding agentic complexity when data shows it's needed. Defines workflows (predefined code paths) vs. agents (LLMs dynamically direct their own processes). — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Microsoft ISE Developer Blog (June 2026):** Documented evolving a production retail chatbot from a modular monolith router pattern (single agent per query, no synthesis) to a microservices architecture enabling agent reuse across teams. Found that coordinator-based patterns with typed state schemas and PostgreSQL checkpointing let agents survive pod restarts — all production failures traced to state management failures. — [devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)
- **LangGraph case studies (40+ companies, 2025-2026):** Production deployments span Uber, LinkedIn, Replit, Klarna, and others. Real production patterns documented: typed state + checkpointing for multi-agent state that survives failures, interrupt-and-resume for human-in-the-loop approval without blocking threads, parallel subgraphs reducing research agent latency by 60–70%. — [docs.langchain.com/oss/python/langgraph/case-studies](https://docs.langchain.com/oss/python/langgraph/case-studies)
- **HN discussion on "Building Effective AI Agents" (543 points, June 2025):** Practitioner consensus: "The ability to swap out APIs just isn't the bottleneck. It is always behavioral issues or capability differences between models. Frameworks just add complexity, obscurity, and API misalignment." Contrast: teams with 10+ agents in production needed frameworks for coordination; teams with 1-3 agents preferred direct API calls. — [news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)
- **Presenc AI Research (May 2026):** Framework comparison across LangGraph, CrewAI, AutoGen, Swarm, Google ADK, Anthropic Skills. Finding: "the framework choice is less consequential than model selection, evaluation infrastructure, and human-checkpoint design." — [presenc.ai/research/multi-agent-orchestration-frameworks-2026](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026)

## Gotchas

- **Activity ≠ progress.** Agents in stuck loops still make API calls and edit files. Activity signals can't distinguish stuck from slowly converging — you need progress-metric-flat detection (has the output quality improved in the last N steps?).
- **Naive retries amplify outages.** At 500 jobs/minute with naive exponential backoff, retry storms can multiply failures 10–50x. Use circuit breakers at the infrastructure layer, not just retry logic in the agent layer.
- **Soft loops are harder than hard loops.** Hard loops (exact repetition) are trivial to detect. Soft loops (slight variations each iteration) need semantic similarity detection. Both are easier than semantic loops (plausible variation with no convergence), which require progress-metric detection.
- **Coordinator agents become bottlenecks.** A single central planner routing all tasks creates a single point of failure and a scaling ceiling. Use fan-out/fan-in parallelism with typed state for horizontal scaling.
- **Agent frameworks hide state.** Many framework abstractions make it opaque where a workflow actually is when it fails. The fix is a typed state schema with explicit checkpointing — not just in-memory dicts.
