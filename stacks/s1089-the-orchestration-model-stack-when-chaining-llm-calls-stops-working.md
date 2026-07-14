# S-1089 · The Orchestration Model Stack — When Chaining LLM Calls Stops Working

Your two-agent demo worked perfectly. Then you added a third. Then you hit silent loops, cascading context corruption, and a $400 invoice you can't explain. The problem isn't your model. It's that you chose an orchestration architecture before understanding the autonomy demands of your workflow. Different tasks need radically different coordination models — and picking the wrong one compounds every other problem you have.

## Forces

- **Autonomy compounds cost and risk.** Every hop from one LLM call to the next adds latency, inference cost, and failure probability. A 4-agent orchestrator-worker workflow runs $5–8 per complex task. Teams that don't model the economics before committing to architecture get burned.
- **Context corruption cascades.** Downstream agents inherit upstream LLM outputs — which may be semantically valid but logically wrong. With chains of agents, this error compounds at each hop. A bad research agent pollutes the synthesis agent pollutes the writer.
- **The framework is a starting point, not a destination.** Multiple HN practitioners — including those running production multi-agent systems — report rolling their own orchestration because "there's absolute 0 framework out there that's good enough for serious work." Teams that treat their first framework choice as permanent rebuild 2–3 times.
- **The chains-vs-agents framing is a distraction.** The real question is how much autonomy the LLM needs for each specific task. LangChain's 2025 production data: 73% of production systems use chains, only 12% use full agents. The hype says agents; the reality says chains.

## The Move

Map your task's autonomy requirements to one of four coordination models. Move up the stack only when the lower model demonstrably fails.

**1. Simple chains for linear, bounded workflows.**
Sequential LLM calls with explicit input/output. No routing, no loops, no autonomous decisions. Best for: document transformation, summarization, classification, single-step API calls. Zero autonomy. Maximum predictability.

**2. Router patterns for task classification with specialized handlers.**
A single LLM classifies the incoming task and dispatches it to a fixed handler. The routing step decides; the handlers execute. Best for: customer triage, multi-format processing, request routing. Low autonomy at the router; handlers are chains.

**3. Orchestrator-worker for complex task decomposition.**
A central orchestrator plans, decomposes, delegates to specialized workers, and synthesizes results. Workers are usually chains or routers — not full agents. Best for: multi-step research, report generation, code review pipelines. High orchestrator autonomy; constrained worker autonomy.

**4. Peer-to-peer / event-driven for parallel, loosely-coupled agents.**
No central coordinator. Agents subscribe to events, act on relevant ones, and emit results. Each agent owns its own state and tools. Best for: monitoring systems, distributed research, newsroom-style workflows. Maximum parallelism; hardest to debug.

**Difficulty-aware dynamic routing (emerging 2026).**
Route based on estimated task complexity. Simple queries go to chains; complex multi-step tasks route to full agent loops. Discriminator is task complexity score, not human judgment. Reduces cost by 40–60% vs. routing everything through full agents.

## Evidence

- **LangChain 2025 production survey:** 73% of production systems use chains; only 12% use full agents. Simple chains handle 80% of production use cases — teams consistently over-engineer their first implementations. — [Agentika citing LangChain data](https://agentika.uk/blog/llm-orchestration-patterns.html)
- **HN Ask — production multi-agent orchestration:** Practitioners report rolling their own orchestration: Node.js + V8 isolates per agent with MongoDB-backed shared state (pablovarela); reputation-based gating for agent delegation (olegbk); "there's absolute 0 framework out there that's good enough for serious work" (segmondy). Primary pain points: untyped handoffs, cascading context corruption, circular delegation deadlocks, inference cost explosion. — [Hacker News Ask HN #47660705](https://news.ycombinator.com/item?id=47660705)
- **Gartner / RaftLabs market analysis:** 1,445% surge in multi-agent system inquiries Q1 2024 → Q2 2025; 57% of organizations running agents in production. Failure root causes: 49% cite inference costs as top blocker; 40% of agentic AI projects at risk of cancellation by 2027 (cost, unclear business value, inadequate risk management). — [RaftLabs citing Gartner](https://www.raftlabs.com/blog/multi-agent-systems-guide)
- **OpenAI Agents SDK (March 2025):** Made agent handoffs a first-class production primitive — `Handoff` as an explicit object type, not an implicit prompt instruction. Represents industry consensus that handoff reliability is a mandatory production requirement, not an implementation detail. — [TURION.AI deep dive](https://turion.ai/blog/framework-deep-dive-openai-agents-sdk)
- **Zylos Research (April 2026):** Three architectural schools crystallized for coordinating AI agents: DAG-based (explicit dependency graphs), event-driven (async pub/sub), actor model (isolated state + message-passing). Top failure categories: semantic failures (syntactically valid but logically wrong outputs), cascading context corruption, circular delegation deadlocks. — [Zylos Research](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)

## Gotchas

- **Model the economics before you commit.** Inference cost compounds across agents. A 4-agent workflow at $0.01–0.02 per call × 10+ iterations = $5–8 per task. Teams that don't build cost budgets into their architecture design get surprise invoices.
- **Typed handoff schemas are non-negotiable in production.** Untyped handoffs between agents kill multi-agent workflows faster than any other issue. Every agent-to-agent boundary needs a validated schema with version numbering. Semantic failures cascade and amplify at each hop — a schema catches them before they propagate.
- **Don't treat your first framework as permanent.** The right abstraction for a 2-agent demo is different from what's needed at 10 agents. Teams that choose LangGraph, CrewAI, oragno and freeze there rebuild when requirements hit real complexity. Plan for at least one architectural migration.
