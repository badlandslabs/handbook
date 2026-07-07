# S-770 · The Multi-Agent Orchestration Pattern Taxonomy: What Actually Works in Production

Multi-agent systems promise parallel speedup and specialized reasoning — but benchmarks reveal a brutal gap between demos and deployment. ChatDev achieves 33.3% correctness on real programming tasks. AppWorld hits 86.7% failure on cross-app workflows. Logistics systems deliver +27% throughput with -22% cost reduction. The variable is not model size — it is pattern choice.

## Forces

- **Multi-agent overhead compounds.** Each hop costs tokens, latency, and failure surface area. The coordination tax can wipe out parallelism gains if the pattern is wrong for the problem.
- **Agents are non-deterministic.** Same input → different output every run. Monitoring must detect *semantic drift*, not just value changes — making observability harder than traditional software.
- **Production breaks where demos don't.** Context limits, error propagation, runaway cost, and silent failures all surface in production but not in prototypes.
- **Pattern selection is architectural debt.** Choosing the wrong coordination strategy early means expensive rewrites 6-12 months in — the same window where CrewAI teams hit ceiling and LangGraph teams scale.

## The move

Match the orchestration pattern to the dependency structure of the work — not to the number of agents you want to use.

**Sequential (Pipeline) — for linear dependencies:**
- Fixed order, Unix-pipe equivalent. Agent N's output feeds Agent N+1.
- Best when each agent performs a distinct transformation with clear upstream/downstream ownership.
- Production example: PDF text extraction → document classification → structured field extraction → business-rule validation.
- Failure modes: bottleneck agent blocks entire pipeline; no mid-pipeline recovery; no dynamic branching.
- When to reach for it: the output of step A is a strict input to step B, every time.

**Supervisor (Hierarchical) — for delegation with oversight:**
- One supervisor agent decomposes a task and delegates sub-tasks to specialized workers, then synthesizes results.
- Supervisor retains full context; workers are scoped to their sub-task.
- Failure modes: supervisor becomes bottleneck; supervisor hallucination cascades to all workers; single point of failure.
- When to reach for it: one agent naturally coordinates others (e.g., a "Director" in an agency-model crew).

**Peer (Network) — for parallel independent work:**
- Agents coordinate as equals, typically via a shared message bus or blackboard system.
- No single coordinator; agents publish findings and consume others' outputs.
- Best when sub-problems are genuinely independent and can be solved concurrently.
- Failure modes: message explosion as N agents each talk to N-1 others; circular dependencies; race conditions on shared state.
- When to reach for it: multiple agents doing research or analysis in parallel before a merge point.

**Dynamic (LLM-Driven Routing) — for adaptive workflows:**
- The LLM itself decides which agent to invoke next based on intermediate state.
- Highest flexibility; lowest predictability.
- Production example: agentic RAG where the agent evaluates its own retrieval quality and re-queries if confidence is low.
- Failure modes: unpredictable execution paths; cost unbounded without aggressive gating; debugging nightmare.
- When to reach for it: genuinely exploratory or branching tasks where you cannot enumerate all paths upfront.

**The gateway control plane is non-negotiable in production.** Every multi-agent deployment — regardless of pattern — needs a unified entry point that enforces: per-agent rate limiting, cost ceilings, audit trails, and cross-agent trace correlation. Without it, individual agents appear to work but the system as a whole is ungovernable.

## Evidence

- **Benchmark data:** ChatDev achieves 33.3% correctness on real programming tasks; AppWorld fails 86.7% of cross-app workflows; logistics systems show +27% throughput / -22% cost reduction — demonstrating that pattern selection is the dominant variable. — [Thread Transfer — Multi-Agent System Design Patterns for Production (July 2025)](https://thread-transfer.com/blog/2025-07-06-multi-agent-system-patterns)
- **Production deployments:** LangGraph powers 400+ production deployments including Uber, LinkedIn, and Klarna. LangGraph's state-machine approach is explicitly preferred for complex, stateful multi-agent workflows requiring durable execution. — [Gheware DevOps — LangGraph vs CrewAI vs AutoGen Comparison 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Real engineering teams:** Netguru's Omega sales-automation agent uses AutoGen orchestration with Azure OpenAI GPT-4o, vector DB for memory, and explicit gateway-level guardrails. Enterprise teams at Deutsche Telekom (2M+ conversations, 89% acceptable answer rate) and Harvey AI (0.2% hallucination rate serving 700+ legal clients) both require a control plane layer for cost, safety, and audit. — [Netguru — The AI Agent Tech Stack in 2025](https://www.netguru.com/blog/ai-agent-tech-stack) and [Aliac EU — Agentic RAG in Production](https://aliac.eu/blog/agentic-rag-in-production)
- **Framework recommendation:** "Default to LangGraph unless you have strong reasons not to — the steeper learning curve prevents painful rewrites 6-12 months in." — [Gheware DevOps](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)

## Gotchas

- **Don't start with multi-agent.** Single-agent with tools wins on simplicity, cost, and debuggability. Multi-agent earns its overhead only when agent boundaries map to genuine capability or domain boundaries — not just because "more agents sounds better."
- **CrewAI hits a ceiling at 6-12 months.** Fastest path to working prototypes via role-based model, but teams consistently report needing to migrate to LangGraph for production scale. Plan for that migration on day one.
- **Silent failures propagate silently.** An agent returning empty responses will be "worked around" by downstream agents in ways that look like success. You need per-agent health signals, not just end-to-end success rates.
- **Token budgets compound non-linearly.** A 5-agent pipeline where each agent gets full conversation context can consume 10-50x the tokens of a well-scoped single-agent call. Gate context at every handoff.
