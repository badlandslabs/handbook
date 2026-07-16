# S-1205 · The Agent Orchestration Stack — When You're Not Sure If You Need One Agent or Twenty

You have a task that requires multiple steps. A single LLM call won't cut it. So you start adding components — a router here, a tool there, a second agent for the part the first one keeps getting wrong. Six months later your orchestration graph is 14 nodes deep, takes 40 seconds to run a task that should take 5, and nobody on the team can explain why it makes the decisions it does. This is the orchestration stack: choosing the right coordination pattern, not just adding more agents.

## Forces

- **More agents means more coordination debt, not more capability.** Every new agent adds a handoff point. Every handoff is a place where state gets lost, latency gets added, and a failure can cascade. Teams reach for multi-agent before exhausting what a single well-scoped agent can do.
- **Frameworks hide the hard parts until production exposes them.** CrewAI gets you to a working demo in an afternoon. LangGraph gets you to a graph you can resume after a Thursday deploy. The demo-speed vs. debuggability tradeoff only becomes visible under load.
- **The LLM-chain abstraction leaks.** What looks like a clean "step 1 → step 2 → step 3" in code becomes a system with branching, retries, partial failures, and state that the LLM has to track. Predefined paths only stay predefined until the first edge case.
- **The 80/20 of production is boring.** LangChain's 2025 production survey found simple chains handle 80% of production use cases. Only 12% of systems actually deploy full autonomous agents. The industry talks about agents; production runs chains.

## The Move

**Start at the simplest orchestration that could work. Add complexity only when a measured failure mode demands it.**

### The Three Patterns That Survive Production

1. **Simple chains** — predefined code paths, LLM calls in sequence, no dynamic routing. For: summarization, translation, formatting, any task with a known fixed sequence. Implementation: a `for` loop over prompt templates, or LangChain's `LCEL` chain syntax. No agents needed.

2. **Router patterns** — an LLM classifies the input and dispatches to the right handler. For: triage, routing between tool sets, filtering queries that need escalation vs. self-service. Implementation: a single classification prompt + `if/else` in code. The router is not an agent; it's a switch statement backed by an LLM.

3. **Agent loops** — the LLM dynamically decides next actions, calls tools, and loops until a termination condition. For: open-ended research, coding tasks, complex reasoning where the path cannot be predetermined. This is where LangGraph, AutoGen, and CrewAI compete. Choose based on the four questions: who runs next, what do they see, how is progress saved, when do we stop.

### The Four Questions Every Orchestration Must Answer

| Question | What It Determines |
|----------|-------------------|
| **Who runs next?** | Agent selection, routing logic, handoff protocol |
| **What do they see?** | Context shaping — what state, history, and instructions the next agent receives |
| **How is progress saved?** | Checkpointing — how to resume after crash, deploy, or approval delay |
| **When do we stop?** | Termination — budget caps, confidence thresholds, escalation paths |

### Choosing Your Framework

| Framework | Sweet Spot | Production Maturity | Best For |
|-----------|-----------|---------------------|----------|
| **Direct API calls** | Simple chains, routers | Highest (no abstraction) | Teams that want zero framework overhead |
| **LangGraph** | Branching DAGs, durable workflows | High — state machine primitives | Complex flows needing checkpointing and auditability |
| **CrewAI** | Multi-role agent teams | Medium — rapid prototyping | Fast demos, agent-native teams |
| **AutoGen (AG2)** | Custom multi-agent collaboration | Medium — active consolidation | Research-heavy, flexibility-first |
| **OpenAI Agents SDK** | Tool-use-heavy agents | Emerging | OpenAI-centric stacks |

### Escape the Multi-Agent Premature Optimization Trap

- Measure where single-agent caps out (accuracy, latency, cost) before adding a second
- If a single `create_agent` with 3–5 well-scoped tools beats a three-node graph, use the agent
- Multi-agent adds coordination overhead that only pays off for: true parallelism (fan-out/fan-in), role specialization (different system prompts), or cross-cutting concerns (one agent monitors another)
- "Swarm" and peer-to-peer patterns are research-stage; supervisor hierarchy is production-proven

### Production Operational Patterns

- **Circuit breaker** — when a tool or agent fails N times in a row, stop calling it and route to a fallback. Prevents cascading failures and runaway costs.
- **Checkpointing** — save state after every completed step, not just at the end. Enables resume after crash, approval delay, or deployment.
- **Human-in-the-loop (HITL) escalation** — route high-stakes decisions (payments, deletions, external sends) to human approval before executing. Never let a fully autonomous loop own irreversible actions.
- **Cost budget per run** — cap total tokens or dollars per workflow invocation. Agent loops can run for minutes; without a budget they can run for $200.

## Evidence

- **Anthropic engineering post:** After working with dozens of teams building LLM agents, the core finding: "Consistently, the most successful implementations use simple, composable patterns rather than complex frameworks." Recommends starting with direct API calls and only reaching for frameworks when the abstraction pays for itself. — [Anthropic — Building Effective AI Agents](https://www.anthropic.com/research/building-effective-agents)

- **Hacker News thread (543 points, 88 comments):** Community consensus mirrors Anthropic's advice. HN user `miki123211`: "You don't need a whole framework for this." Multiple contributors cite LangGraph's state machine primitives as the reason to adopt it over simpler approaches — not raw capability. Practical production experience: the debugging cost of framework abstraction often exceeds the prototyping speedup. — [HN — Building Effective AI Agents](https://news.ycombinator.com/item?id=44301809)

- **GitHub orchestration-playbook:** Battle-tested operational patterns distilled from months of running 5+ agents across multiple models. Covers File Blackboard (shared state via filesystem), Task Envelope (structured handoff format), Circuit Breaker, and HITL escalation. Explicitly not a framework — "no code to install." Used by teams running Claude Code with subagents. — [p3nchan/orchestration-playbook](https://github.com/p3nchan/orchestration-playbook)

- **LangChain 2025 production survey (via Agentika):** 73% of production systems use chains; only 12% use full agents. Simple chains handle 80% of production use cases. Harrison Chase (LangChain CEO): "Start with the simplest orchestration that could work. Most teams over-engineer with agents when a chain would do."

- **Databricks case study — BASF Coatings:** Supervisor agent pattern deployed at enterprise scale. Top-level supervisor decomposes tasks and routes to specialist agents. Demonstrates modularity and specialization at scale, with clear handoff protocols and failure isolation. — [Databricks — Supervisor Agent Architecture](https://www.databricks.com/blog/multi-agent-supervisor-architecture-orchestrating-enterprise-ai-scale)

## Gotchas

- **The latency tax compounds.** Five sequential LLM calls at 2s each = 10s minimum latency, plus network overhead. Parallelize with fan-out/fan-in where steps are independent. Measure latency at each step; the bottleneck is rarely where you expect.
- **Router patterns still need fallback logic.** A classifier that routes to "unknown" with no handler will silently drop the request or loop. Always define the boundary cases explicitly, even if the fallback is "escalate to human."
- **Checkpointing is not serialization.** Saving the graph state after each step is different from saving the full LLM context window. The former is cheap and fast; the latter is expensive and slow. Most frameworks checkpoint graph state, not context.
- **Framework upgrades break production silently.** LangChain v0.x to v1.0 had breaking changes in memory handling and chain abstractions. AutoGen rebranded to AG2 with API changes. Pin framework versions in production and treat upgrades as full regression events.
