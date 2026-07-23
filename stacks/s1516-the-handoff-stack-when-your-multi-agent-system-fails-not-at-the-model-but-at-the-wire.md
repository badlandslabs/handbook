# S-1516 · The Handoff Stack — When Your Multi-Agent System Fails at the Wire, Not the Model

You built a pipeline of five specialized agents. Each agent's prompts are tight, its tools are correct, its outputs look right in isolation. But the end-to-end result is wrong — confidently, plausibly wrong — and nobody can trace why. The model did its job. The failure is in the handoff: the context transfer between agents, the coordination boundary, the implicit contract between two LLM calls that was never made explicit. This is where multi-agent systems actually break in production.

## Forces

- **More agents compound failure probability.** Five agents at 95% reliability each yield ~77% end-to-end success. Adding agents doesn't make a system more robust — it adds probabilistic handoffs. The reliability math works against you unless each handoff is a first-class design problem.
- **The wiring is not the product.** Teams spend weeks tuning individual agent prompts, then treat the inter-agent context transfer as an afterthought. The research is unambiguous: 79% of multi-agent failures trace to coordination problems — specification ambiguity, unstructured context passing, role drift — not model capability failures.
- **Decomposition pressure and composition pressure pull in opposite directions.** You decompose tasks into specialized agents to get focus. But each decomposition creates a handoff boundary where context can silently degrade. The more specialized the agents, the more brittle the wiring between them.
- **Topology matters more than model choice.** AdaptOrch (2026) demonstrated that selecting the right orchestration topology (parallel, sequential, hierarchical, hybrid) delivers 12–23% performance gains over static baselines — using the same underlying models. How you connect agents matters as much as which models you use.
- **The baseline rule.** Google Research found that single agents with 45%+ baseline accuracy get diminishing returns from adding more agents. Tool-heavy tasks suffer a 2–6× efficiency penalty in multi-agent setups versus a well-prompted single agent. Decomposition is not free.

## The Move

Multi-agent coordination fails at handoff boundaries unless you treat them as explicit, structured interfaces rather than implicit context concatenations. The stack below covers the five canonical topology patterns, the two handoff mechanisms, and the three failure modes that kill systems in production.

### Topology Patterns (choose based on task type)

- **Orchestrator/Worker** — One lead agent decomposes the task and dispatches to parallel specialized subagents. Subagents operate independently with their own context windows; lead agent synthesizes results. Best for: open-ended research, parallel exploration, tasks where different agents need different tool sets. (Anthropic's Research feature uses this pattern — the orchestrator plans, subagents search in parallel.)
- **Sequential Pipeline** — Agents process a task in ordered stages. Each agent's output feeds the next. Best for: deterministic content pipelines (crawl → parse → validate → store), cases where order is semantically meaningful.
- **Peer-to-Peer / Debate** — Agents negotiate or critique as equals. Best for: reasoning tasks where adversarial review improves output quality, complex analysis requiring multiple perspectives without a predetermined order.
- **Hierarchical** — Multi-level management: a strategic orchestrator delegates to tactical sub-managers who manage worker agents. Best for: enterprise-scale operations, complex workflows with nested sub-tasks.
- **Marketplace / Auction** — Task broadcast to multiple candidate agents; best response wins. Best for: tasks where parallel proposals can be objectively compared.

### Two Handoff Mechanisms

- **Structured Handoff** (preferred) — An agent explicitly calls a named handoff tool (`transfer_to_refund_agent`) and passes a structured summary. OpenAI Agents SDK implements this as a first-class LLM tool: the model sees the handoff as a callable function, making delegation an explicit reasoning step rather than a context concatenation accident. Include: task summary, relevant findings, explicit next-step instructions, success criteria for the receiving agent.
- **Agent-as-Tool** — One agent calls another as a tool within its own loop. The calling agent retains control and reasoning. Best for: tight coupling where the orchestrator needs to remain in the loop, not true delegation.

### Three Failure Modes to Guard Against

- **Cascading error propagation** — One agent's degraded output becomes another's degraded input. Fix: add a lightweight verification step before each handoff (structured output validation, a critic agent, or a schema check).
- **Silent failure with confident output** — Multi-agent systems rarely throw clean exceptions; they return plausible wrong answers built on broken sub-tasks. Fix: validate at handoff boundaries; make agents fail loudly, not subtly.
- **Cost and loop runaway** — Unbounded agent cycles burn token budgets in minutes. Fix: set explicit termination conditions, max-iteration guards, and per-agent budget caps.

## Evidence

- **Anthropic Engineering Blog (Jun 2025):** Described their multi-agent research system's orchestrator-worker pattern — the lead agent plans research processes and spawns parallel subagents with distinct tools and exploration trajectories. Key lesson: subagent separation enables parallel context windows that distill insights before condensing back to the lead, reducing path dependency in open-ended research. — [https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **arxiv:2503.13657 (MAST, NeurIPS 2025):** Systematic failure taxonomy for multi-agent LLM systems. Found that inter-agent misalignment — specification ambiguity, unstructured context passing, and role drift — accounts for the majority of failures. Published a labeled dataset of 1,600+ execution traces mapping 14 failure modes. — [https://arxiv.org/abs/2503.13657](https://arxiv.org/abs/2503.13657)
- **AdaptOrch (arxiv:2602.16873, 2026):** Formal framework showing orchestration topology selection delivers 12–23% performance gains over static baselines using identical models, validated on SWE-bench, GPQA, and RAG tasks. Introduced a performance convergence scaling law formalizing conditions under which orchestration design outweighs model selection. — [https://arxiv.org/html/2602.16873](https://arxiv.org/html/2602.16873)
- **Google internal "Agent Bake-Off"** (referenced in MACGPU analysis, Jun 2026): Distributed multi-agent topology cut processing time from 1 hour to 10 minutes (6× speedup) compared to single-agent serial execution on the same task. — [https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)
- **Google Developers Blog (Dec 2025):** Described five multi-agent patterns in ADK — Supervisor/Worker, Peer-to-Peer, Hierarchical, Pipeline, and Marketplace — with decision guidance for when each applies. — [https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk)
- **Qurtoo (Mar 2026):** Reported that a 2025 analysis found 79% of multi-agent failures trace to coordination problems at handoff boundaries, not model capability. Structured handoff protocols — explicit role definitions, structured context summaries, success criteria — reduce this. — [https://qurtoo.com/blog/agent-handoff-protocols-how-to-transfer-state-between-specialized-agents-without](https://qurtoo.com/blog/agent-handoff-protocols-how-to-transfer-state-between-specialized-agents-without)
- **OpenAI Agents SDK:** Implemented handoffs as first-class LLM tools (`transfer_to_<agent>`) — the model reasons about delegation explicitly rather than implicitly managing context concatenation. — [https://openai.github.io/openai-agents-python/handoffs/](https://openai.github.io/openai-agents-python/handoffs/)
- **Connylazo blog (Feb 2026):** Practitioner account of hitting multi-agent scaling walls: adding agents to a translation pipeline (five specialized agents) and research pipeline (sub-agent decomposition) introduced coordination failures that single-agent baselines didn't have. Corroborated independently by arxiv:2512.08296 "Towards a Science of Scaling Agent Systems." — [https://connylazo.com/blog/2026-02-19-more-agents-worse-results](https://connylazo.com/blog/2026-02-19-more-agents-worse-results)

## Gotchas

- **Don't decompose until you have to.** If a single agent with good prompting and tools handles a task at 45%+ accuracy, adding agents adds coordination cost without proportional benefit. Decompose when distinct, separable capabilities genuinely justify separate agents — not for organizational tidiness.
- **Unstructured context passing is the default failure mode.** Simply concatenating Agent A's output into Agent B's prompt is not a handoff — it's a context dump. The receiving agent must parse, re-interpret, and re-prioritize. Use structured summaries with explicit next-step instructions.
- **Verification at handoffs is not optional.** Every inter-agent boundary is a trust boundary. Add output validation, schema checks, or a lightweight critic step before passing work downstream. Five 95%-reliable agents in a chain without verification is a 77%-reliable system in practice.
- **Loop guards are a first-class requirement.** Multi-agent systems can enter non-terminating cycles where agents pass work back and forth or re-dispatch without progress. Set explicit max-iteration limits and budget caps from day one.
- **Debugging requires tracing, not logs.** Standard logging shows you what each agent output — not how context degraded across a handoff. Invest in structured trace visualization (e.g., OpenTelemetry spans per agent step) before going to production.
