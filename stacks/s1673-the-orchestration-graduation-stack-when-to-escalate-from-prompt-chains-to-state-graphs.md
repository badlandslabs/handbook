# S-1673 · The Orchestration Graduation Stack — When to Escalate from Prompt Chains to State Graphs

When your agent works fine in demos but you need fan-out, crash-resume, or typed handoffs — and you have to decide whether to reach for LangGraph, build a custom orchestrator, or just use the model API directly.

## Forces

- **"Start simple" and "be ready to migrate" are in tension.** Anthropic and LangChain's own founder both say start with the API directly — but the migration cost from a sprawling chain to a graph is real. Over-engineering from day one wastes time; under-engineering six months in costs a rewrite.
- **Frameworks solve the problem they were built for.** CrewAI gets you to a working multi-agent prototype fastest. LangGraph wins when you need state machines with branching and durability. AutoGen wins for multi-turn human-in-the-loop. Picking the wrong framework means fighting it instead of using it.
- **The escalation signal is specific, not vague.** It's not "when your agent gets complex." It's: parallel sub-agents, crash-resumable long-running tasks, or typed handoffs between stages. Teams that can't name the signal reach for orchestration before they need it.
- **Roll-your-own has a specific cost.** HN practitioners who built custom orchestrators in Node.js or Python report being happy with the control but rebuilding observability, retry logic, and state persistence from scratch every time.

## The Move

The key insight: orchestration is a ladder, not a menu. Each rung unlocks capabilities the previous one couldn't handle. Stay on the lowest rung that works.

**Rung 1 — Direct API calls (zero orchestration)**
- One LLM call per request. No state, no memory, no tools beyond what fits in context.
- Use when: single-turn completions, stateless transformations, simple classification.
- Typical tools: raw SDK, ~50 lines of code.

**Rung 2 — Prompt chains (sequential composition)**
- Output of LLM call N becomes input to LLM call N+1. Linear, no branching.
- Use when: multi-step but fully deterministic pipeline (extract → transform → validate → respond).
- Typical tools: LangChain LCEL, or 10-line Python loop.
- The red line: any step that needs to branch based on output value, or any step that might fail and need retry.

**Rung 3 — State graph (LangGraph-style)**
- Nodes = LLM calls or tool calls. Edges = transitions. State = shared dict passed between nodes. Supports conditional branching, parallel fan-out, crash-resume.
- Use when you need **any** of: branching on model output, parallel sub-agents, human-in-the-loop approval, resumable long-running tasks, step-by-step auditability.
- Typical tools: LangGraph, or custom state machine in ~200 lines.
- The red line: multiple agents that need typed message passing, not just shared state dict.

**Rung 4 — Multi-agent system (typed agent communication)**
- Agents are first-class entities with roles, owned tools, and explicit handoff protocols. A2A (Agent-to-Agent) or similar protocol handles routing.
- Use when: agents have different model backends, different tool sets, or need to be independently deployable.
- Typical tools: LangGraph's multi-agent patterns, CrewAI crew, AutoGen, or custom A2A implementation.

**The graduation signals (from Agentika production research):**

| Signal | Upgrade to |
|--------|-----------|
| Need to branch based on LLM output (e.g., "if confidence < 0.7 → escalate") | Rung 3 |
| Need two sub-agents to work in parallel, then merge | Rung 3 |
| Agent run must survive a crash/restart mid-workflow | Rung 3 |
| Compliance requires explaining which step produced which output | Rung 3 |
| Different agents have different tool sets or model backends | Rung 4 |
| Agents need to be independently deployed/scaled | Rung 4 |

## Evidence

- **Anthropic Engineering Blog ("Building Effective Agents", Dec 2024 — HN 543 pts, Jun 2025):** "We suggest that developers start by using LLM APIs directly — many patterns can be implemented in a few lines of code. The most successful implementations use simple, composable patterns rather than complex frameworks." Also defines the core distinction: Workflows = predefined code paths; Agents = dynamic, LLM-directed. — [URL](https://www.anthropic.com/engineering/building-effective-agents)

- **Agentika blog ("LLM Orchestration Patterns That Actually Work", Feb 2026):** LangChain's 2025 production survey: simple chains handle 80% of production use cases, yet teams consistently over-engineer with agents on first implementation. Harrison Chase (LangChain CEO): "Start with the simplest orchestration that could work. Most teams over-engineer with agents when a chain would do." — [URL](https://agentika.uk/blog/llm-orchestration-patterns.html)

- **Hacker News — Ask HN: Multi-agent orchestration in production (2026):** 11 practitioners, near-universal consensus: frameworks are useful for prototyping but production systems either build custom on top (LangGraph + custom orchestrator) or roll their own entirely. One respondent: "There's absolute 0 framework out there that's good enough for serious work." Others report success with lightweight abstractions over raw APIs (Express endpoints + MongoDB shared state). — [URL](https://news.ycombinator.com/item?id=47660705)

- **IdeaToMVP blog ("LangGraph Patterns, Production Gotchas & Reddit/X 2026", Jun 2026):** In 2026, the migration story is: CrewAI for speed → LangGraph when you need branching, crash-safe resume, or typed state. LangGraph wins specifically because it treats orchestration as a first-class state machine rather than a chat transcript. — [URL](https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026)

## Gotchas

- **Over-engineering from day one is the most common mistake.** Shipping a LangGraph state machine for a two-step extract-and-respond pipeline adds complexity without benefit. The chain works fine. You will debug the graph when you could have shipped.
- **"Multi-agent" is not automatically better.** Adding multiple agents when a single chain would solve the task adds: communication overhead, observability complexity, and failure modes at agent boundaries. Teams at Databricks reported 327% growth in multi-agent workflows (Jun–Oct 2025) — but the same report notes most teams building multi-agent systems are in tech, at 4× the rate of other industries, which suggests over-indexing on complexity in early-adopting sectors.
- **The migration cost from chain to graph is non-trivial.** If your chain uses unstructured text outputs at each step, retrofitting typed state machines means rewriting every boundary. Design for typed outputs (JSON/struct) from the start, even in chains.
- **Roll-your-own means owning observability from scratch.** Custom orchestrators (Express + MongoDB, raw Python loops) give you full control but require rebuilding the retry logic, state persistence, and step logging that LangGraph/LangSmith provide out of the box. The trade is real: flexibility vs. infrastructure debt.
