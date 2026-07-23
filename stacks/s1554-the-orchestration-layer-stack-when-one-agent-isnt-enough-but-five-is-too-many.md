# S-1554 · The Orchestration Layer Stack — When One Agent Isn't Enough But Five Is Too Many

You need a task that exceeds what a single agent can reliably handle — too many tools, too many steps, or too many failure modes. Reaching for a multi-agent framework feels like the right move, but the choice between supervisor routing, sequential pipelines, parallel fan-out, and evaluator loops is not obvious. The wrong pattern at the wrong time creates more problems than it solves. Teams that over-orchestrate early end up debugging a graph instead of shipping a feature.

## Forces

- **Complexity grows superlinearly with agents.** Each additional agent adds coordination overhead, observability cost, and failure surface — not just capability.
- **Framework lock-in is real.** LangGraph, CrewAI, and custom code have radically different debugging, testing, and deployment profiles. Migrating mid-project is painful.
- **The pattern determines the ceiling.** Sequential chains work for linear pipelines but collapse under branching logic. Supervisors are simple but become single points of failure at scale.
- **Multi-agent too early is the most common mistake.** Reddit and HN consensus in 2025–2026 is blunt: most teams reach for orchestration before they need it.

## The Move

Orchestration is a spectrum. Pick the lowest-complexity pattern that fits your actual need, not your anticipated one.

### The six core patterns (in order of complexity)

1. **Sequential Chain** — Agent A output feeds Agent B input. No branching. Use for linear pipelines: extract → validate → store → notify. Dead simple, fully predictable, trivially debuggable. Breaks down when latency compounds or branching is needed.

2. **Router** — A single dispatcher agent classifies the input and routes it to the correct handler. The simplest branching pattern. Best for request classification, routing to specialists, or filtering out-of-scope queries before they enter the main pipeline. From Anthropic's "Building Effective Agents" patterns.

3. **Supervisor** — A single orchestrator agent manages task delegation, monitors progress, and aggregates results. Agents remain "dumb" executors; the supervisor handles all routing decisions. Works well for moderate complexity (3–6 agents) where a single decision-maker pattern fits naturally. Becomes a bottleneck as agent count grows.

4. **Parallel Fan-Out / Fan-In** — A coordinator breaks a task into independent subtasks, dispatches them to parallel agents, then aggregates results. The MapReduce of AI agents. Strong for embarrassingly parallel work: summarize N documents, query N data sources, validate N test cases. The aggregation step is the hardest part — getting a coherent result from parallel agents takes careful prompt design.

5. **Evaluator-Optimizer Loop** — Two agents in a refinement cycle: a generator produces output, an evaluator critiques it against explicit criteria, and the generator revises. Iterates until quality threshold or iteration cap. SWE-Bench-style code generation uses this natively (generate → test → feedback → revise). Cost scales linearly with iteration count; set a hard cap to prevent runaway loops. Self-Refine (Madaan et al., 2023) documented gains across math reasoning, code generation, and dialogue.

6. **Hierarchical Delegation** — A tree of supervisor agents where mid-level supervisors coordinate sub-teams. Necessary only at enterprise scale (20+ agents). Coordination overhead is significant; most teams never need this.

### Framework decision guide

| Framework | Best for | Key constraint |
|-----------|----------|---------------|
| **Custom (Node.js/Python + function calling)** | Teams with strong engineering, need zero framework overhead | Full maintenance burden; no built-in observability |
| **LangGraph** | Complex stateful workflows, branching, checkpointing, human-in-the-loop | Steeper learning curve; graph can become hard to read |
| **CrewAI** | Role-based multi-agent teams, fast prototyping | Python-only; opinionated abstractions |
| **AGNO** | Minimalistic design, clean agent isolation | Smaller community, fewer integrations |
| **MCP-based (e.g., mcp-agent)** | Tool-centric workflows where MCP servers are the primary abstraction | Newer ecosystem; MCP adoption still maturing |

## Evidence

- **HN Ask Thread (2025):** "Ask HN: How are you orchestrating multi-agent AI workflows in production?" — real production teams reported rolling their own (Node.js/Express + MongoDB) because "0 frameworks [were] good enough for serious work," while others adopted LangGraph for its state machine model and AGNO for minimalistic agent isolation. Key takeaway on observability: structured logging of agent-to-agent data passing with thread IDs for correlation. — [news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **Microsoft Azure Architecture Center (2025):** Documents five orchestration patterns (sequential, supervisor, hierarchical, peer-to-peer, swarm) with a complexity spectrum that warns against multi-agent adoption before single-agent optimization. Notes that 60% of enterprise agentic AI pilots fail due to orchestration design flaws, not agent capability gaps. — [learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- **r/LangChain + X community synthesis (2026):** LangGraph has become the default answer for teams that outgrew simple agent loops — specifically when they need branching, approval gates, or crash-safe resume. Reddit consensus: "most teams reach for multi-agent orchestration too early." The evaluator-optimizer pattern is consistently cited as the highest-quality approach for code generation and structured content refinement, with SWE-Bench and LangGraph's reflection tutorial as canonical implementations. — [ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026](https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026)
- **AIAnytime Multi-Agent Patterns Playground (GitHub, 2025):** Implements all five patterns with code — sequential pipeline (report generation), MapReduce fan-out (parallel document summarization), consensus (redundant review), supervisor routing, and hierarchical delegation — as a Streamlit playground for engineers learning the patterns. — [github.com/AIAnytime/Multi-Agents-Orchestration-Design-Patterns](https://github.com/AIAnytime/Multi-Agents-Orchestration-Design-Patterns/blob/main/README.md)

## Gotchas

- **Start with one agent.** Add orchestration only when a single agent consistently fails at specific steps — then split those steps into a specialist and connect them. This is the incremental build rule from the HN and Reddit community.
- **Parallel fan-out is only as good as your aggregation step.** Dispatching to parallel agents is easy; getting a coherent combined result requires careful prompt design for the aggregator. Under-investing in the aggregator is the most common fan-out failure.
- **Hard cap your evaluator-optimizer loops.** Without an iteration limit, a low-quality evaluator will drive the generator into a local minimum spiral, compounding errors with each revision. Set a maximum iteration count and a confidence threshold for early exit.
- **Thread IDs and trace IDs are not optional.** When agents pass data to each other, every message needs a trace ID that persists across agent boundaries. Without this, debugging a failing multi-agent workflow means reading unstructured logs and guessing at causation. MongoDB or a dedicated trace store (e.g., LangSmith, Phoenix) are the minimum viable observability stack.
- **Framework migration is expensive once you commit.** CrewAI's opinionated role-based abstractions are fast to start with but painful to escape when you need branching or non-role-based logic. LangGraph's graph-as-code model is harder to learn but maps more naturally to complex state machines. Choose for where you'll end up, not where you're starting.
