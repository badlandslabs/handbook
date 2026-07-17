# S-1238 · The Chain-First Stack — When Your First Instinct Is to Build an Agent Constellation

You have a complex task. Your gut says: build a team of specialized agents, each with a role, an LLM powering it, and a coordinator gluing them together. A researcher, a writer, an editor, maybe a fact-checker. It feels like the right answer to "how do you scale intelligence?" But the pattern that survives production is often none of that — it's a single chain with a router at the front and a circuit breaker at the back.

## Forces

- **Complexity vs. capability tension.** Multi-agent systems unlock genuinely new capabilities (parallel exploration, distributed context, role specialization). They also multiply failure modes, cost, and debugging burden by roughly the number of agents. Most teams reach for the former before exhausting the latter.
- **The 80% rule.** LangChain's production survey found that simple chains handle 80% of production use cases. Teams consistently over-engineer with agents when a chain would do — Harrison Chase, LangChain CEO: "Start with the simplest orchestration that could work."
- **Cost scaling.** Agent loops cost 3–5× more than chains per task. The question isn't "can we do this with agents?" but "is the extra capability worth the cost?"
- **Debuggability cliff.** A chain of 3 deterministic steps is trivially traceable. A swarm of 5 autonomous agents with message-passing and shared state is a distributed systems problem you didn't sign up for.

## The Move

**Start with a chain. Add agents only when you hit a concrete ceiling.**

1. **Classify first, architect second.** Route every request through a cheap model (e.g., GPT-4o-mini) that estimates task difficulty. Simple tasks go through a 2-step chain. Complex tasks go through a multi-agent pipeline. This delivers significant cost reductions without accuracy loss — per Zylos Research's 2026 field report.
2. **Three patterns survive production.** Supervisor + Specialists (one coordinator agent routes subtasks to specialists and integrates results — the most common real-world "multi-agent" setup), Sequential Pipeline (fixed order: researcher → writer → editor — predictable cost, step-level eval, low coordination overhead), and Parallel Fan-out (one agent spawns independent subagents for independent subtasks, then merges — Anthropic's research system uses this to 15× token spend).
3. **Use a state machine framework for anything non-linear.** LangGraph earns its keep when you need branching (different next steps based on classification or tool output), durability (resume after crash or human approval), or auditability (step-by-step explainability for compliance). LangGraph is used in production at Klarna, Replit, and Elastic. AutoGen entered maintenance mode October 2025 (Microsoft's successor is the Microsoft Agent Framework). CrewAI is actively developed and popular for content pipelines. Pick based on your production needs, not community hype.
4. **Build in human checkpoints for high-stakes loops.** LangGraph's `interrupt()` halts the graph at approval points (e.g., payment execution, external API writes). The graph persists to Postgres and waits indefinitely. Resume with `Command(resume=...)` and the same `thread_id`. This separates toy demos from finance and operations deployments.
5. **Composite graphs for scale.** A compiled LangGraph subgraph becomes a single node in a parent graph. Teams on r/LangChain describe a hybrid pattern: CrewAI or a simple chain for the overall workflow, with LangGraph subgraphs embedded for the steps that need durability and state management.

## Evidence

- **Anthropic Engineering Blog:** Anthropic's multi-agent Research feature uses an orchestrator-worker pattern — a lead agent decomposes tasks, spawns parallel subagents, synthesizes results, and iterates dynamically. 90.2% improvement over single-agent Opus 4 on internal benchmarks. Key insight: "Multi-agent systems work mainly because they help spend enough tokens to solve the problem." LeadResearcher saves its plan to Memory to avoid context truncation above 200K tokens. — [URL](https://www.anthropic.com/engineering/multi-agent-research-system)
- **LangChain production survey:** Simple chains handle 80% of production use cases. Teams consistently over-engineer with agents when a chain would do. — [URL](https://agentika.uk/blog/llm-orchestration-patterns.html) (citing LangChain survey, February 2026)
- **TURION.AI field report:** "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count. In 2023 demos looked great. In 2024 production deployments mostly looked cursed. In 2025–2026, a handful of patterns emerged that actually work." Three surviving patterns: Supervisor + Specialists (most common in production), Sequential Pipeline (predictable cost, step-level eval), and Parallel Fan-out (high-value tasks where parallel token spend is justified). — [URL](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)
- **Zylos Research (April 2026):** Difficulty-aware dynamic routing — a cheap classifier estimates task difficulty and allocates compute proportionally. Simple queries get shallow chains; complex queries get deep multi-agent pipelines. Delivers cost reductions without accuracy loss. — [URL](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/)
- **JetThoughts 2025 framework comparison:** LangGraph (state-machine, production, used at Klarna/Replit/Elastic), CrewAI (role-based, active v0.98+), AutoGen (maintenance mode Oct 2025, Microsoft Agent Framework is successor). — [URL](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025)

## Gotchas

- **Over-orchestrating a simple problem.** If your workflow is "retrieve context, generate answer, return," you need a chain, not a supervisor + 3 specialists. Adding agents because it feels sophisticated is the most common production mistake.
- **Forgetting the circuit breaker.** Agent loops can run indefinitely when the agent keeps deciding it needs one more step. Set explicit step limits, token budgets, or loop-count guards. Without them, high-value tasks burn compute; low-value tasks burn money.
- **Context truncation in long-running agents.** Anthropic's system saves the research plan to Memory specifically because exceeding 200K tokens truncates context. If your agent persists state across many turns, design for context management from day one, not as an afterthought.
- **Treating multi-agent as a scaling solution when it's a complexity solution.** Adding agents doesn't scale a broken single-agent workflow — it multiplies its failure modes. Fix the single-agent loop before distributing it.
