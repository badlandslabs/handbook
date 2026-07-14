# S-1113 · The Orchestration Battlefield Stack — When Multiple Agents Can Do It, But None Know Who Should

You have three capable agents, two tools each, and a complex workflow that needs to go A → B → C. Every team hits the same wall: the individual agents are fine, but the coordination layer is where everything falls apart. Race conditions, infinite loops, silent failures, and context windows that silently overflow mid-run. The models are strong enough. The wiring isn't. This is the orchestration problem.

## Forces

- **57% of AI project failures trace to orchestration design**, not model capability — individual agents work, coordination doesn't — [AnhTu.dev, 2026](https://anhtu.dev/ai-agent-orchestration-6-patterns-for-production-2026-1121)
- **Multi-agent workflows grew 327% between June–October 2025**, with tech companies building them at 4× the rate of other industries — [MHTECHIN/MH Technologies, 2026](https://www.mhtechin.com/support/orchestration-frameworks-for-agentic-ai-langchain-autogen-crewai-the-complete-2026-guide)
- **Most multi-agent failures are distributed systems failures in disguise** — agents handle related tasks and make implicit assumptions about shared state, ordering, and validation that the system never enforces — [GitHub Blog, Feb 2026](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont)
- **The choice between frameworks is a choice about failure modes**, not features — each pattern encodes which class of failure you catch early and which you trade for

## The Move

Orchestration is not about choosing a framework — it is about choosing **where you want your failure modes**. The three dominant schools each own a different part of the tradeoff surface:

### Pattern 1: Supervisor / Router — Keep the Router Dumb, Keep the Specialists Sharp

A single supervisor agent classifies each incoming task and routes it to the appropriate specialist. The supervisor holds no domain knowledge — it only decides who handles the work. Think of it as an air traffic controller, not a pilot.

- Route by task type, not by LLM judgment — use a lightweight classifier or exact-match rules for the routing decision itself; reserve LLM reasoning for the specialist work
- Each specialist owns its tools exclusively — avoid tool overlap across workers to prevent race conditions
- The supervisor schema is a typed contract — define it in JSON Schema, validate inputs and outputs at every handoff
- Implement circuit-breaker routing — if a specialist fails twice consecutively, route to a fallback or alert a human

```python
# Supervisor routes; it does not execute
supervisor = SupervisorAgent(workers={
    "researcher": ResearcherAgent(),
    "writer": WriterAgent(),
})
result = await supervisor.execute(task)
```

*Used in production at enterprises requiring parallel intake triage (support, procurement, compliance) — [AccelateAI/multi-agent-orchestration](https://github.com/AccelateAI/multi-agent-orchestration)*

### Pattern 2: DAG / State Machine (LangGraph) — Explicit Control Flow, Durable State

When workflow correctness matters more than flexibility, build an explicit graph. Every node, edge, and state transition is visible in code. The LLM makes bounded decisions at designated nodes; the graph handles flow control deterministically.

- Define state as a typed Pydantic schema — not a dict — so schema violations surface as type errors, not silent bugs
- Use checkpointing from day one — LangGraph's built-in checkpointing lets you resume a graph from any saved state, recover from crashes mid-run, and fork execution for debugging
- Human-in-the-loop is a graph node, not an afterthought — pause at an Approval node, resume on external signal; the graph sits dormant consuming zero compute while waiting
- Deterministic routing via Python logic: `if confidence_score < 0.7: return "human_help"` enforces business rules that CrewAI can only request

Used in production by Klarna, Replit, Elastic, LinkedIn, and Uber — [LangGraph GitHub README](https://github.com/langchain-ai/langgraph), [AgentMarketCap, Apr 2026](https://agentmarketcap.ai/blog/2026/04/08/langgraph-fortune-500-production-stateful-multi-agent-workflows)

### Pattern 3: Role-Based Crews (CrewAI) — Fastest Path to a Working Team

When you need a multi-agent pipeline deployed in days and the workflow is well-defined, assign each agent a role, goal, and backstory. The agents figure out coordination through natural language negotiation. Best for content pipelines, research synthesis, and support ticket workflows.

- The Two-Pizza Rule: teams of 3–5 agents max, with a single manager who owns the outcome and delegates all tasks — [Reddit r/AI_Agents, 2025](https://www.reddit.com/r/AI_Agents/comments/1ic6myq/my_lessons_learned_designing_multiagent_teams_and/)
- Define agent roles precisely — "senior researcher who specializes in SQL query generation for data warehouses" beats "researcher" every time
- Use process=Process.hierarchical for complex workflows — the manager coordinates planning and execution, agents handle execution, results flow back through validation
- 30–60% cost reduction achievable by routing simple queries to fast models and complex ones to frontier models — [AnhTu.dev, 2026](https://anhtu.dev/ai-agent-orchestration-6-patterns-for-production-2026-1121)

### Pattern 4: Fan-Out / Fan-In — Parallelize Independent Work

When multiple sub-tasks have no dependencies on each other, dispatch them simultaneously and aggregate results. This is where orchestration pays off most: a 10-step workflow with 4 parallel branches can cut latency by 60%.

- Fan-out at natural boundaries — fetching data from independent sources, generating variations, running parallel validations
- Use a barrier/join node to aggregate — the DAG waits for all branches before proceeding; implement a timeout so a slow branch doesn't block the whole run
- Cost scales sub-linearly with parallelism if you're using token-metered APIs

## Evidence

- **GitHub Blog (2026):** Multi-agent failures are distributed systems failures. Missing structure — not model capability — causes most breakdowns. Three engineering patterns address this: explicit handoff protocols, shared state contracts, and deterministic routing — [URL](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont)
- **AnhTu.dev (Apr 2026):** 57% of failed projects fail on orchestration design. Framework comparison across LangGraph, CrewAI, and AutoGen with production trade-offs documented. AutoGen entered maintenance mode Oct 2025 (successor: Microsoft Agent Framework). LangGraph is the production default at 60% of enterprise deployments — [URL](https://anhtu.dev/ai-agent-orchestration-6-patterns-for-production-2026-1121)
- **LangGraph GitHub README (2026):** Trusted in production by Klarna, Replit, and Elastic. LinkedIn uses LangGraph for its English-to-SQL data warehouse query system. Uber uses it for multi-agent workflow orchestration. All Fortune 500 users cite checkpointing and human-in-the-loop as critical requirements — [URL](https://github.com/langchain-ai/langgraph)
- **AgentMarketCap (Apr 2026):** LinkedIn's production agent finds the right tables, writes SQL, detects and fixes its own errors, and enforces access permissions autonomously. The graph enforces the permission boundaries; the agent handles the reasoning within them — [URL](https://agentmarketcap.ai/blog/2026/04/08/langgraph-fortune-500-production-stateful-multi-agent-workflows)
- **MHTECHIN (2026):** Multi-agent workflows grew 327% June–Oct 2025. Tech companies build multi-agent systems at 4× the rate of other industries. LangChain/LangGraph: 126K+ GitHub stars, ~$0.18/query. AutoGen: 43K+ stars, ~$0.35/query (Azure ecosystem). CrewAI: 43K+ stars, ~$0.12–0.15/query — [URL](https://www.mhtechin.com/support/orchestration-frameworks-for-agentic-ai-langchain-autogen-crewai-the-complete-2026-guide)
- **Reddit r/AI_Agents (2025):** "The manager owns the outcome." Hierarchical Two-Pizza Team approach — manager agent delegates to 3–5 specialists, evaluates performance, coordinates the final outcome. Single-threaded manager prevents race conditions at the coordination layer — [URL](https://www.reddit.com/r/AI_Agents/comments/1ic6myq/my_lessons_learned_designing_multiagent_teams_and/)

## Gotchas

- **AutoGen entered maintenance mode in October 2025.** Microsoft's successor is the Azure Agent Framework (GA April 2026). If you're starting a new project on AutoGen, you're building on legacy infrastructure — [JetThoughts, 2025](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)
- **Framework loyalty is the wrong instinct.** BeyondScale reports 60% of their projects use LangGraph as the primary orchestrator, 25% use plain LangChain, and CrewAI handles content pipelines — the right answer is use-case dependent and teams that are framework-loyal tend to over-engineer simple problems and under-engineer complex ones — [BeyondScale, 2025](https://beyondscale.tech/blog/langchain-crewai-langgraph-comparison)
- **Fan-out without a timeout is a budget leak.** Parallel branches that never join silently consume compute and tokens. Always implement a timeout on the join node that triggers a partial-result fallback or alert.
- **CrewAI's natural language handoffs sound like agents talking to each other, but there's no enforced contract.** Two agents can misalign on output format mid-run and the error surfaces downstream. Always validate outputs at handoff boundaries, especially when using role-based processes.
- **"Human-in-the-loop" is often added as an afterthought but must be a first-class graph node.** If you bolt it on later, you'll spend a sprint retrofitting state management. Design the pause-and-resume boundary into the state schema from day one.
