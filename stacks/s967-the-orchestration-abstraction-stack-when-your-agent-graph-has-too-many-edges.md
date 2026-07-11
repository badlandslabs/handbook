# S-967 · The Orchestration Abstraction Stack — When Your Agent Graph Has Too Many Edges

Your agent system started as one loop calling an LLM. Now you have a coordinator, three specialist agents, two fallback paths, a memory layer, a retry queue, and something that might be a DAG but nobody's entirely sure. The orchestration code is now larger than the business logic. You need a way to describe agent coordination that doesn't collapse under its own weight — but you also don't want to swap one framework's opinions for another's.

## Forces

- **Frameworks add polish but subtract debuggability.** Every abstraction hides the actual LLM call, making it harder to trace why the agent chose a particular tool or took a particular path. The HN consensus from mid-2025 is blunt: teams who removed LangChain/LangGraph found the simplification worth it.
- **DAGs assume the shape of work is known at design time.** Traditional orchestration (Airflow, Prefect, LangGraph StateGraph) requires declaring every node and edge upfront. Agents that discover subtopics, encounter malformed data, or dynamically route based on content break this assumption — forcing conditional edges and state machines that erode the original clarity.
- **The 2026 production stack is split three ways.** Teams are choosing between DAG-based (explicit control, deterministic execution), event-driven (reactive, handles unknown shapes), and actor-model (isolated state, supervision hierarchies) — each suited to different task profiles.
- **Declarative IaC thinking is crossing into agents.** The Terraform/Kubernetes crowd wants to define agents as versioned infrastructure resources with desired state, permissions, and execution limits — not as imperative code.

## The move

Three distinct orchestration patterns are winning in production, each dominant in different conditions:

### 1. DAG-based (explicit control flow) — for deterministic pipelines
- Use when task shape is known, order matters, and auditability is non-negotiable
- Tools: LangGraph `StateGraph`, Temporal with LLM-assisted workflow generation, Orloj YAML manifests
- Key insight from Anthropic: workflows (predefined paths) beat agents (dynamic loops) when you know what needs to happen — default to workflow, reach for agents only when the LLM genuinely needs to decide next steps
- The DAG node is an LLM call with defined inputs and outputs. Edges are deterministic unless you explicitly add branching logic.

### 2. Event-driven (reactive, shape-unknown) — for open-ended agent tasks
- Use when the agent must discover its own path based on content
- Pub/sub topology: agents emit events, consumers subscribe, orchestration is implicit in the wiring
- Mentiko argues this fundamentally beats DAGs for AI agents because the workflow shape is not known at design time — agents encounter unexpected data quality, discover subtopics, and route around failures in ways that DAGs can't anticipate
- Handles thousands of concurrent tasks with per-consumer dead letter queues for failure isolation (Zylos, 2026)

### 3. Actor-model (isolated state, supervision) — for resilient multi-agent systems
- Each agent is an isolated process with its own state; communication is message-passing only
- Supervision hierarchies: parent actors restart failed children, creating self-healing topologies
- Best for systems where agent crashes should not cascade — financial trading agents, critical infrastructure automation
- Zylos notes this is gaining traction specifically for enterprise deployments requiring fault isolation

### The practical default: start direct, add abstraction only when you have to
- Anthropic's direct API call advice still holds: an LLM call is "essentially an array of strings to a web service" — frameworks add complexity before you need it
- HN practitioner `pablovarela`: "custom abstractions with Node.js/Express, 0 frameworks good enough for serious work"
- When you do need orchestration: prefer a thin layer (AGNO's minimalistic design for isolation) over a full framework
- When you need governance and multi-cloud: Agent Kernel (Yaala Labs, Apache 2.0) provides the platform layer — framework-agnostic, MCP-native, Terraform deployment

### Difficulty-aware dynamic routing (2026 emerging pattern)
- Classify query difficulty first, route to appropriate pipeline depth
- Simple queries → shallow chain (faster, cheaper)
- Complex queries → deep multi-agent pipeline
- Delivers cost reduction without accuracy loss — Zylos reports teams adopting this mid-2026

## Evidence

- **HN Ask HN (2025):** Multi-agent orchestration in production thread — practitioners reporting custom Node.js/Express stacks, LangGraph for parallel workers, AGNO for minimal isolation, and Swrl's distinction between persistent "agent" vs single-run "swirl" memory scopes. No consensus on a dominant framework; the common thread is keeping orchestration thin and explicit.
  — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)

- **Anthropic "Building Effective Agents" (Dec 2024):** Most successful implementations use simple, composable patterns rather than complex frameworks. Workflows (predefined paths) for known shapes; agents (dynamic loops) only when the LLM needs to decide. Direct API calls with retrieval outperform framework-wrapped equivalents. This was the highest-scoring HN post on agents in 2025 (543 points).
  — [anthropic.com/research/building-effective-agents](https://www.anthropic.com/research/building-effective-agents)

- **Orloj (Show HN, 2025):** Open-source runtime treating agents as infrastructure-as-code. Declarative YAML manifests declare model, tools, permissions, and execution limits. Composes agents into workflows via dependency declarations. Built by former Kubernetes/Terraform engineers. 107 stars, Apache 2.0.
  — [github.com/OrlojHQ/orloj](https://github.com/OrlojHQ/orloj)

- **Mentiko blog (2026):** Argues event-driven fundamentally beats DAG-based orchestration for AI agents because agents encounter unknown workflow shapes at runtime. DAGs require upfront node/edge declaration that works for ETL but not for probabilistic, context-dependent agent tasks.
  — [mentiko.com/blog/event-driven-vs-dag-orchestration](https://mentiko.com/blog/event-driven-vs-dag-orchestration)

- **Zylos Research (2026):** Three orchestration schools (DAG, event-driven, actor model) each dominant in different production conditions. Difficulty-aware dynamic routing emerging as cost-reduction pattern. Workflow-as-code with LLM-assisted generation (natural language → Temporal code) is early-stage but gaining tooling.
  — [zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)

## Gotchas

- **Abstraction leaks at the worst times.** LangChain/LangGraph's abstraction layers hide the actual prompts and tool schemas — when an agent misbehaves, you spend hours tracing through framework code before finding the real cause. HN practitioners who removed these frameworks report debugging time dropping significantly.
- **DAGs for agents are a category error.** Trying to force dynamic agent behavior into a graph with predefined nodes and edges produces conditional spaghetti — every "dynamic" edge is a hidden state machine that nobody tests.
- **The "orchestration framework" market is fragmented.** No single framework has the Terraform-like staying power of a category-defining tool. Picking one commits you to its evolution trajectory. The IaC crowd (Orloj) and the enterprise platform crowd (Agent Kernel) are both trying to solve this differently — neither is dominant yet.
- **Direct API calls are not production-ready by default.** The anti-framework consensus does not mean "write raw curl calls." It means: own your prompt templates, own your tool definitions, own your retry logic. The LLM call itself is simple; everything around it (observability, error recovery, context management) is where orchestration decisions live.
