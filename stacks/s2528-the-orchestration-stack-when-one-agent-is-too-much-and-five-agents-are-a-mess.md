# S-2528 · The Orchestration Stack — When One Agent Is Too Much and Five Agents Are a Mess

You shipped a single agent and it works — until it doesn't. You tried adding more agents and the coordination overhead ate your latency gains, introduced mysterious failure modes, and turned debugging into archaeology. This is the orchestration problem: not how to build agents, but how to wire them together so the system exceeds the sum of its parts.

## Forces

- **A single \"god agent\" hits ceilings fast.** Context window limits, model fit (no single LLM is optimal for every task), and the impossibility of parallel subtask execution all hit at once.
- **Multi-agent adds coordination cost you can't see.** Token overhead from orchestration loops, inter-agent state passing, and routing logic are invisible in demos and brutal in production.
- **The framework is a means, not the answer.** HN practitioners report that the framework itself rarely determines success — the architecture-task alignment does.
- **The most common production patterns are the least exciting ones.** Sequential pipelines and supervisor routing dominate production deployments, not swarms or emergent topologies.

## The Move

Map the problem's complexity to the lowest orchestration tier that can handle it. Every level above your actual need adds cost, latency, and debugging surface area.

**The five-tier complexity ladder:**

1. **Direct model call** — single LLM, no tools, no agent logic. Use when a well-crafted prompt suffices.
2. **Single agent with tools** — one agent, its own toolset, loops until done. Use for moderate multi-step tasks with a fixed scope.
3. **Orchestrator-worker (supervisor pattern)** — a central LLM decomposes the task, dispatches to specialized workers, aggregates results. The dominant production pattern. Use when subtasks are parallelizable and workers are interchangeable.
4. **Multi-agent collaboration** — agents communicate directly, peer-to-peer, with shared state. Use when the task topology is dynamic and can't be predicted by a central planner.
5. **Hierarchical** — multi-level supervisor tree, like an org chart. Use when 15+ agents need to coordinate and a single supervisor becomes a bottleneck.

**Pattern picks by real-world use:**

- **Sequential pipeline** — document processing: summarization → translation → QA, each agent's output feeds the next. Deterministic, easy to trace.
- **Parallel fan-out** — research: orchestrator breaks the query into independent sub-research tasks, workers run concurrently, aggregator synthesizes. Anthropic's internal eval showed 90.2% improvement over single-agent Opus 4 using this shape with Opus 4 as lead + Sonnet 4 subagents.
- **Supervisor routing** — task routing: a classifier/manager agent decides which specialist handles each request. LangGraph's typed message contract between supervisor and workers enforces this cleanly.
- **Hierarchical** — enterprise-scale: IBM Watson AIOps uses a management tree for incident response, with a top-level orchestrator delegating to domain specialists, achieving 60% reduction in incident resolution time.
- **Swarm** — dynamic customer service: agents hand off directly to peers based on conversation state, no central coordinator. GitHub stars Swarms (6.8k stars, Apache 2.0) and OpenAI's Swarm are the canonical open-source references here.

## Evidence

- **Engineering blog:** Anthropic's multi-agent research system (June 2025) — orchestrator-worker pattern with Claude Opus 4 as supervisor + four Sonnet 4 subagents, 90.2% eval improvement over single-agent Opus 4. Key lesson: parallel compression (workers compress findings before returning to the orchestrator) was essential to managing token costs. — https://www.anthropic.com/engineering/multi-agent-research-system

- **HN thread:** "How are you orchestrating multi-agent AI workflows in production?" — real practitioners reporting: (1) "segmondy" — "There's absolute 0 framework out there that's good enough for serious work," builds in Node.js + Express in V8 isolates with MongoDB for shared state; (2) "pablovarel" — same Node.js/V8 isolate pattern; (3) "Chepko932" — uses LangGraph with a custom orchestrator layer on top; (4) "kathir05" — uses AGNO for "minimalistic design for isolation, decoupling and control plane architecture." — https://news.ycombinator.com/item?id=47660705

- **Engineering blog:** CyberArk Engineering on LangGraph production use (Oct 2024) — replaced a LangChain single-agent "god prompt" architecture with a LangGraph state machine dividing the process into focused prompts with the optimal LLM per node. Identified the core failure mode: "No single LLM is optimal for every task." — https://medium.com/cyberark-engineering/building-production-ready-ai-agents-with-langgraph-a-real-life-use-case-7bda34c7f4e4

- **Research synthesis:** Zylos Research (April 2026) — 40% of enterprise apps will include AI agents by end of 2026 (Gartner); multi-agent workflows grew 327% between June–October 2025 (Databricks State of AI Agents report). Three architectural schools: DAG-based (explicit dependencies, centralized control), event-driven (async pub/sub), actor model (message-passing, supervision hierarchies). — https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns

## Gotchas

- **Orchestration is not free.** An orchestrator-worker system adds at minimum one extra LLM call per round (the supervisor routing decision) on top of the worker calls. Anthropic's own post emphasizes parallel compression of worker outputs before returning to the orchestrator to stay within token budgets.
- **Roll-your-own vs. framework: the tradeoff is support vs. lock-in, not quality.** HN practitioners building in Node.js + V8 isolates report satisfaction with the control — but spend significant time on state management and observability that a framework would provide. The "no framework is production-ready" sentiment coexists with "LangGraph 1.0 GA (Oct 2025) is trusted by Klarna, Replit, Elastic" per its GitHub README.
- **CrewAI-to-LangGraph migrations are a documented pattern.** In early-to-mid 2025, teams shipped quickly with CrewAI's role-based crews. As they hit branching logic, approval gates, and crash-safe resume requirements, migration to LangGraph's graph-based state machine became the common escape hatch. This migration cost is real and should factor into framework choice.
- **AutoGen is in maintenance mode as of October 2025.** Microsoft's shift of focus to Semantic Kernel means new projects should be cautious about AutoGen for long-lived production systems. — https://markaicode.com/best/best-agent-framework-production-multi-agent
- **Inter-agent state passing is the underestimated problem.** HN practitioners report that data formats between agents (raw text, JSON, protobuf, embeddings) vary widely and have significant downstream effects on routing quality and error recovery. Building a shared schema is not optional at scale.
