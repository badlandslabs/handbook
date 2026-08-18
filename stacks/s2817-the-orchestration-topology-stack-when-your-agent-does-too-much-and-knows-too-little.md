# S-2817 · The Orchestration Topology Stack — When Your Agent Does Too Much and Knows Too Little

When a single agent accumulates too many tools, roles, and objectives — it stops being reliable. Tool calls degrade, context windows exhaust, and the agent "hallucinates" capabilities it doesn't have. The fix isn't a better model; it's topology: decomposing one overloaded agent into a structure of specialized agents that coordinate.

## Forces

- **The "God Agent" anti-pattern** — one agent handling research, analysis, drafting, review, and validation simultaneously suffers from context window exhaustion, confused reasoning across cognitive modes, no parallelism on independent tasks, and single-point debugging nightmares. A single 2000-line prompt to troubleshoot is the tell.
- **Framework inertia is real** — CrewAI gets teams to a first working prototype fast, but teams that need branching, human approvals, or crash-safe resume hit a wall and migrate to LangGraph. The migration cost is non-trivial once the graph is non-trivial.
- **State machine vs. chat transcript** — the core architectural divide. Frameworks that model orchestration as a state machine (LangGraph) support durable execution, checkpointing, and replay. Frameworks that model it as a chat transcript support fast iteration but become un-debuggable under production load.
- **Orchestration cost compounds** — each LLM call in a multi-agent flow is a budget event. Per-node model routing (routing cheap tasks to cheap models) is the most practical lever for cutting LLM cost without degrading quality, but it requires the topology to be designed for it upfront.

## The Move

Decompose by cognitive mode, not by topic. Route through a supervisor. Enforce state machine semantics. Add per-node routing as a first-class concern.

**The supervisor + specialists pattern works because:**
- The supervisor owns goal decomposition and result synthesis — it does no domain work
- Specialists execute in narrow, well-scoped contexts — smaller prompts, fewer tools, predictable failures
- Parallel fan-out to independent specialists reduces wall-clock time significantly
- Isolated failures — one specialist crashing doesn't kill the whole workflow
- Each agent can use a different model tier based on task complexity

**Topology patterns that have emerged as production-viable:**

1. **Sequential pipeline** — A → B → C → D. Simple, debuggable, linear audit trail. Use when order is strict and there are no branches.
2. **Parallel fan-out / merge** — Supervisor spawns N specialists simultaneously, waits for all results, then synthesizes. Use for independent research tasks, multi-source analysis.
3. **Hierarchical supervisor** — Supervisor spawns sub-supervisors, which each manage their own specialist pools. Use at enterprise scale (like BASF Coatings with Databricks) where domains are naturally siloed.
4. **Tool-router only** — A single agent with routing logic that delegates to tools rather than spawning sub-agents. Use for simpler workflows; avoids the complexity of true multi-agent.

**State machine essentials for production:**
- Checkpoint every completed step to durable storage (Postgres, Redis, object storage)
- Treat the SDK/process session as ephemeral — conversation log is the source of truth
- Design crash-safe resume: if the process dies mid-flow, restart from last checkpoint
- Use circuit breakers per agent — isolate runaway loops on any single specialist

**Per-node model routing:**
- Classify/route nodes → cheap model (Haiku, GPT-4o-mini)
- Research/retrieval nodes → medium model (GPT-4o, Claude 3.5 Sonnet)
- Synthesis/validation nodes → premium model (o1, Opus 3.5, Claude 3.7)
- This alone can cut LLM costs 40-60% with minimal quality degradation

## Evidence

- **Databricks + BASF Coatings production deployment:** Implemented a supervisor agent architecture at one of the world's largest chemical companies to coordinate cross-team enterprise AI. The supervisor decomposed goals and routed to specialist agents with domain-specific data access permissions. Cited "modularity, specialization, and control" as the core driver — exactly the forces the supervisor pattern addresses. — [Databricks Blog, October 2025](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)
- **Industry field notes from a dozen production deployments:** Turion.ai's March 2026 postmortem on multi-agent orchestration notes the shift from "2023 demos looked great → 2024 production mostly cursed → 2025-2026 patterns that actually work emerged." The supervisor + specialists pattern is explicitly cited as working, with LangGraph as the dominant implementation vehicle for state machine semantics. — [TURION.AI, March 2026](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Community migration pattern documented:** Builder migration from CrewAI → LangGraph documented on r/LangChain and X (2026): teams that shipped with CrewAI for speed post migration stories once they need branching, approvals, or crash-safe resume. LangGraph identified as the default because it's "the only mainstream framework that treats orchestration as a first-class state machine instead of a chat transcript." — [IdeaToMVP, June 2026](https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026)

## Gotchas

- **Decomposing by topic instead of cognitive mode** — splitting agents by "research agent" and "drafting agent" still leaves each agent doing mixed cognitive work. Split by cognitive mode: a classifier, a retriever, a synthesizer, a validator. Each has one job and one toolset.
- **No circuit breakers** — a specialist agent in a loop with no timeout will burn budget indefinitely on a task it cannot complete. Every agent needs a max iterations config and a dead-letter handler.
- **State assumed ephemeral** — teams building on the Claude Agent SDK or similar frameworks often treat session state as durable. It isn't. The conversation log (written to Postgres or equivalent) is the source of truth. The SDK session is a transient compute context.
- **Over-engineering the topology for simple tasks** — a sequential two-step agent doesn't need a supervisor + specialists structure. Add topology only when you have branching, parallelism, or durability requirements. The complexity of the graph must match the complexity of the problem.
- **Per-node routing added as an afterthought** — routing decisions embedded deep in agent prompts are hard to audit and harder to change. Model routing belongs in the orchestration graph definition, not in the system prompts of individual agents.
