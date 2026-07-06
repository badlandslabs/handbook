# S-675 · The Multi-Agent Tax: When Decomposition Costs More Than It Saves

[The appeal of splitting one agent into five is obvious on a whiteboard. Each agent gets a focused role, a small context, and a clean interface. But in production, the inference bill arrives before the quality gains do. Multi-agent architectures cost 4–20× more than equivalent single-agent workflows — and most teams don't find out until they're already committed.]

## Forces

- **The decomposition dividend is real but narrow.** Splitting agents does improve per-step quality when tasks genuinely require different reasoning modes, tool sets, or context windows. It does not improve quality when the bottleneck is the model's own reasoning, not the context size.
- **The cost is front-loaded, the benefit is tail-loaded.** Every multi-agent call adds latency and token cost on the orchestration path. Quality gains often manifest only after you've built eval infrastructure to measure them — which most teams don't have at decision time.
- **The orchestrator is the hidden load-bearing wall.** In orchestrator-worker patterns, one LLM routes everything. Its cost and latency sit on the critical path. "Parallel" workers reduce wall-clock time but multiply the inference bill.
- **Context window ≠ memory architecture.** Giving each agent a clean context window doesn't solve long-term memory — it just defers the problem. Agents that need continuity need a three-tier memory system (episodic, semantic, procedural), not just a shared message bus.

## The move

Before splitting an agent, run the cost model backward from the inference budget:

- **Default to a single agent with tool decomposition.** Use tool-calling to hand off to functions rather than to sub-agents. A single LLM with 10 tools is often cheaper and more reliable than 5 agents with 2 tools each.
- **Split only on genuine capability boundaries.** If two agents need different models (e.g., a fast classifier + a slow reasoner), that is a valid reason. If they need different tools with different latency profiles, that is a valid reason. "They do different things" is not — a well-prompted single agent can context-switch.
- **Account for the orchestrator tax explicitly.** In orchestrator-worker, every worker call includes: (1) the orchestrator's routing call, (2) the worker's execution call, (3) the orchestrator's synthesis call. A 4-step pipeline that looks like 4 calls is actually 8+ calls.
- **For long-lived agents, build three-tier memory before splitting.** Episodic (what happened), semantic (what I know), procedural (how I act). CrewAI's lessons from 2B workflows confirm that trust and memory — not intelligence — separate demo from production.
- **If parallelizing, actually parallelize.** Use async worker dispatch where agents don't need each other's outputs. The General Compute analysis found that sequential multi-agent pipelines have the worst cost/latency ratio: high cost from multiple calls, high latency from no parallelism.
- **Measure before and after.** Run a baseline eval with the single agent on your target task. Only add agents if the eval improves and the cost delta is within budget.

## Evidence

- **General Compute blog:** Multi-agent architectures are 4–20× more expensive than equivalent single-agent systems. Orchestrator-worker patterns are the most expensive multi-agent pattern per task because the orchestrator sits on the critical path for every sub-task, and synthesis calls add further overhead. — https://www.generalcompute.com/blog/multi-agent-architectures-and-the-inference-cost-explosion
- **CrewAI (2B workflow retrospective):** After ~2 billion agentic executions across PepsiCo, AB InBev, DocuSign, US DoD, and others, CrewAI identifies Agent Operations — trust, observability, and memory — as the real production barrier, not model intelligence. One enterprise achieved 14× less code vs. their previous graph-based framework. — https://crewai.com/blog/lessons-from-2-billion-agentic-workflows
- **Ondřej Popelka (production build log):** Built a real CrewAI system over ~$414 in Gemini costs. Key lesson: role definitions are brittle in practice — agents frequently misidentify which role should handle a task, requiring explicit handoff logic. — https://ondrej-popelka.medium.com/crewai-practical-lessons-learned-b696baa67242
- **AppScale (three-tier memory):** A local-first agent memory system using SQLite + an 060MB embedding model outperformed cloud-dependent memory systems. Key finding: "the performance ceiling for agent memory is not gated by model size or cloud compute." — https://appscale.blog/en/blog/agent-memory-architecture-episodic-semantic-procedural-the-three-tier-pattern-2026
- **Madrona (AI agent infrastructure, 2025):** AI agents are creating databases at 4× the rate of human developers (Neon data). When Create.xyz launched its developer agent, 20,000 new databases were created in 36 hours. — https://www.madrona.com/ai-agent-infrastructure-three-layers-tools-data-orchestration
- **Arion Research (2025 year-end check):** 60–89% of enterprises experimented with agentic AI in 2025; only 15–47% deployed to production workflows touching real customers. Quote: "You can't drop an agent into existing processes and expect results." — https://www.arionresearch.com/blog/the-state-of-agentic-ai-in-2025-a-year-end-reality-check

## Gotchas

- **"We'll parallelize it" doesn't save cost, only latency.** Each parallel arm still requires an orchestrator call + synthesis call. You cut wall-clock time; the invoice is unchanged.
- **Agent-level observability is not the same as step-level tracing.** LangSmith and Phoenix can trace individual LLM calls, but correlating those traces to business outcomes requires custom instrumentation most teams skip.
- **Context window size is not the same as useful context.** A 200K-context agent and a 32K-context agent with better retrieval will often produce equivalent outputs — at a fraction of the cost.
- **The swarm pattern is not a cost optimization.** Open-source agent swarms (e.g., Agent Swarm on HN) are compelling for task breadth, but the self-learning overhead — agents writing their own memory files — adds unpredictable cost that doesn't scale linearly.
- **Memory is infrastructure, not a feature.** Teams that bolt on vector storage after the fact discover that retrieval quality is inconsistent, staleness is invisible (the agent confidently misapplies old facts), and the "fix" requires rebuilding the memory layer from scratch.
