# S-1251 · The Orchestration Patterns Stack: When Your Agent Chains Calls but Nobody Knows What Runs Next

Your single-prompt agent worked. Your multi-step workflow fell apart. Planner calls Executor calls Planner. Nobody routed anything. The state got lost between tool calls. You shipped it with a note that said "it works in the demo." Three months later the trace is a 400-step spaghetti graph and nobody can explain why step 47 always goes wrong.

## Forces

- **The orchestration layer is where reliability actually lives in 2026.** Most agent quality work is no longer about model choice — it is about how steps are sequenced, routed, and recovered. The model does the thinking; the orchestrator decides what runs next.
- **Graph beats chain as complexity grows.** Linear chains (`prompt → tool → prompt → answer`) cannot express cycles, branches, or parallel fan-out. Once a workflow has a retry loop, a human approval gate, or two agents running simultaneously, you need a graph, not a pipeline.
- **Teams reach for multi-agent orchestration too early.** A single agent with 3–5 well-scoped tools beats a three-node graph with extra latency for most use cases. Orchestration adds overhead; only reach for it when you genuinely need branching, parallelism, durability, or auditability.
- **State is the hard part.** Passing context between agents, maintaining it across crashes, and making it recoverable is where most orchestration pain lives — not in the LLM calls themselves.

## The Move

Model your agent workflow as an explicit directed graph with typed state. Every pattern below is a specific graph topology with a specific routing mechanism.

**1. Planner–Executor–Evaluator (three-node linear graph)**
The foundational production pattern. A Planner agent converts natural language requests into structured execution plans with risk assessment. An Executor runs plans step-by-step (tool calls, API calls, shell commands). An Evaluator validates results, checks for errors, and decides whether to proceed, retry, or rollback. Conditional edges route between states based on evaluator output.
Concrete: DevOps Boys' production LangGraph implementation uses this for infrastructure changes — the Planner assesses Terraform risk before the Executor touches anything.
Source: [devopsboys.com — LLM Multi-Agent Orchestration with LangGraph in Production](https://devopsboys.com/blog/llm-multi-agent-orchestration-langgraph-production-2026) (2026)

**2. Supervisor routing (star graph with a router node)**
A central supervisor agent classifies incoming requests and routes to specialized agents. The supervisor does NOT do the work — it decides who does. This is the most common pattern for customer-facing agents where the first step determines the entire downstream path.
Concrete: Gravity describes this as the dominant 2026 pattern — the supervisor holds a routing table of agents and makes a classification decision before any tool is called.
Source: [gravity.fast — AI Agent Orchestration Explained: Planner, Executor, Evaluator](https://gravity.fast/blog/ai-agent-orchestration-explained/) (May 2026)

**3. Conductor–Expert (dedicated routing node)**
A specialized Conductor model evaluates every query and routes it to a pool of expert models — each trained or prompted for a specific domain. The Conductor is NOT an LLM doing work; it is a lightweight classifier that minimizes latency and cost by keeping heavy work on the right expert.
Concrete: Orchestra (Reddit r/LocalLLaMA, open source) implements this with Ollama — the Conductor routes between 18+ local expert models. The team reports 5x cost reduction vs. a single frontier model handling everything.
Source: [reddit.com/r/LocalLLaMA — Orchestra: Multi-model AI orchestration system](https://www.reddit.com/r/LocalLLaMA/comments/1qg06zg/orchestra_multimodel_ai_orchestration_system_with/) (2025)
Source: [github.com/ericvarney87-collab/Orchestra-Multi-Model-AI-System](https://github.com/ericvarney87-collab/Orchestra-Multi-Model-AI-System)

**4. Parallel fan-out with merge (fork-join graph)**
A parent node spawns multiple sub-agents simultaneously, each working on a partition of the task. A join node collects and synthesizes results. Critical for research, document processing, and any task where independent subtasks dominate total time.
Source: [iterathon.tech — Agent Orchestration 2026: LangGraph, CrewAI & AutoGen Guide](https://iterathon.tech/blog/ai-agent-orchestration-frameworks-2026) (December 2025)

**5. Hierarchical orchestration (two-tier cost model)**
A high-capability agent (frontier model: Claude Opus, GPT-5) handles planning and decision nodes. Lower-capability agents (Haiku-class, GPT-4-mini) handle execution of routine steps. The tier boundary is enforced by the graph, not by prompts. Blended cost drops 5x vs. routing everything through a frontier model.
Concrete: AgentMarketCap reports organizations using hierarchical routing achieve 3x higher data integration rates and 2.4x greater cost savings vs. isolated single-model agents.
Source: [agentmarketcap.ai — Why Hierarchical Agent Orchestration Is Winning Production in 2026](https://agentmarketcap.ai/blog/2026/04/12/hierarchical-agent-orchestration-pattern-production-2026) (April 2026)

**6. Cross-model verification (parallel heterogeneous agents)**
Run two different model families (e.g., Claude + Codex) on the same task simultaneously and compare outputs. The graph routes outputs to a verifier node that checks agreement before proceeding. Designed to catch model-specific hallucinations that a single model will never catch in itself.
Concrete: Zenflow (Show HN, Zencoder) implements this — their production users report that cross-model disagreement on code correctness is a reliable signal for human review. Runs in "YOLO" mode for cheap/simple tasks and "human-in-the-loop" mode for complex ones.
Source: [news.ycombinator.com — Show HN: Zenflow – orchestrate coding agents without "you're right" loops](https://news.ycombinator.com/item?id=46290617) (2025)

## Evidence

- **Engineering blog:** LLM Multi-Agent Orchestration with LangGraph in Production — demonstrates a full 3-agent (Planner/Executor/Reviewer) architecture with LangGraph code, conditional edges, and LangSmith observability — [devopsboys.com](https://devopsboys.com/blog/llm-multi-agent-orchestration-langgraph-production-2026)
- **Research synthesis:** Graph-Based Agent Workflow Orchestration in Production: The 2026 Landscape — traces the shift from linear chains to explicit directed graphs with typed state, checkpointed execution, and layered observability; notes LangGraph 1.0 (Oct 2025), Mastra 1.0 (Jan 2026), Microsoft Agent Framework 1.0 (April 2026, merging AutoGen + Semantic Kernel) — [zylos.ai](https://zylos.ai/research/2026-04-14-graph-based-agent-workflow-orchestration-production/)
- **HN primary:** "Ask HN: How did you set up a multi-agent orchestration for personal use?" — cromka asks about tooling for role-based agents (coding, design, testing, supervision) with a human in the loop. Community responses discuss Scion (Google Cloud Platform), model-as-coordinator patterns, and the tradeoffs between framework-level orchestration vs. custom scripting — [news.ycombinator.com](https://news.ycombinator.com/item?id=48680842)
- **HN primary:** "Show HN: Agent Orchestrator" — Composio HQ builds an agent orchestrator using the agents it orchestrates (meta-design). The system uses agents to define and manage other agents — [news.ycombinator.com](https://news.ycombinator.com/item?id=47219229)
- **Framework comparison:** CrewAI vs AutoGen (agent.nexus, 2026) — CrewAI leads production deployments via role-based agent collaboration; AutoGen entered maintenance mode and merged into Microsoft Agent Framework (April 2026). Key finding: >70% of new AI projects use orchestration frameworks in 2026 — [agent.nexus](https://agent.nexus/blog/crewai-vs-autogen)
- **Production gotchas:** LangGraph Agent Orchestration Patterns (ideatomvp.ai, 2026) — community consensus: add `interrupt_before` on any node that spends money, sends external communication, or mutates production data. Set `recursion_limit` explicitly. Wire LangSmith tracing before optimizing. The winning teams start simple and add graph nodes only when branching or durability demands it — [ideatomvp.ai](https://ideatomvp.ai/en/blog/langgraph-agent-orchestration-patterns-2026)

## Gotchas

- **Default to a single agent with well-scoped tools.** Most "orchestration" projects are over-engineered chains that would run faster, cheaper, and more reliably as one agent with better tool definitions. Add graph structure only when you hit branching, parallelism, durability, or auditability requirements.
- **State leakage between agents silently corrupts output.** If Agent B inherits context from Agent A without a schema, you will eventually get a tool call with wrong parameter types, stale references, or hallucinated field names. Use typed state channels, not implicit context passing.
- **`thread_id` plus checkpointing is non-negotiable for production.** Without it, a deploy or crash mid-workflow loses everything. LangGraph's `MemorySaver` checkpointing is the community's default; Temporal is the enterprise-grade alternative for workflows that must survive infrastructure failures.
- **Loops are the most dangerous graph construct.** Without an explicit `recursion_limit`, an agent stuck in a retry loop will burn through your entire API budget before producing output. Cap it. The DevOps Boys pattern sets max_evaluator_iterations explicitly at the graph level.
- **Tool descriptions are the most impactful optimization in the orchestration layer.** The model selects tools based on descriptions. Vague descriptions → wrong tool → wrong path → cascade failure. Every tool in your graph needs a one-sentence description that distinguishes it from similar tools.
