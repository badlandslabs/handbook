# S-2318 · The Orchestration Pattern Stack — When Your Agent Does the Right Thing the Wrong Way

You have a working prototype. The LLM calls tools, the loop runs, the output looks right. Then you scale it: latency explodes, costs multiply, and a slightly different input sends the agent into a spiral. The problem isn't the model — it's how you're chaining everything together.

## Forces

- **ReAct vs Plan-Execute is a real trade-off, not a preference** — interleaved reasoning wastes tokens on simple tasks; upfront planning fails when the environment changes mid-execution
- **Multi-agent parallelism offers huge speedups but compounds token cost** — Anthropic's own system uses ~15× more tokens than chat for multi-agent research, vs ~4× for single-agent
- **The framework is a trap** — teams adopt LangChain/CrewAI/AutoGen for prototyping, then discover the abstraction leaks at every production edge case
- **Tool description quality dominates agent performance** — Anthropic found it explained 40% of task completion time variance; most teams treat tool schemas as boilerplate

## The Move

Pick your orchestration pattern based on task predictability, not preference. Then stop optimizing the pattern and start optimizing the inputs.

**Choose by task shape:**
- **Sequential chain** — fully deterministic steps, no branching. Lowest latency, lowest cost, zero flexibility.
- **ReAct (Reason-Act-Observe)** — unpredictable environments, tool-heavy tasks. High adaptability but burns tokens per iteration. Best for exploratory research.
- **Plan-Execute** — predictable goals with uncertain paths. Plans upfront, executes in batches. Reduces re-planning overhead by ~15× vs ReAct.
- **Orchestrator-Worker (multi-agent)** — parallel decomposition of independent sub-tasks. Anthropic's research system achieved +90.2% over single-agent on complex research. Use when a task has natural parallelism.

**Then optimize the three inputs that explain 95% of performance variance (Anthropic internal eval on BrowseComp):**
1. **Tool descriptions** — write them like API docs, not natural language. Every parameter needs a type, range, and purpose. Ambiguous tool schemas are the #1 cause of tool call failures.
2. **Model selection** — a frontier model in a basic framework beats a weaker model in a sophisticated framework. Don't pay for orchestration complexity with a budget model.
3. **Parallelization** — if sub-tasks are independent, run them concurrently. Anthropic's parallel subagents cut research time by up to 90%.

**Guard the loop:**
- Hard cap on iterations *and* a convergence check. LoopGain (open source, 92.8% less spend vs naive max_iter=20) uses control-theoretic loop-gain bands — the agent stops when output actually stabilizes, not when a counter hits N.
- Set a total execution timeout (Anthropic recommends starting conservative on complex tasks).
- Roll back to best-so-far on degradation: a confused agent that has made partial progress will often make things worse before giving up.

**Keep the framework thin or skip it:**
- Anthropic's finding: "The most successful implementations use simple, composable patterns rather than complex frameworks."
- If you do use a framework (LangGraph, CrewAI, AutoGen), treat it as state management scaffolding, not reasoning logic. Extract and test your tool-calling and state-transition code independently.
- arXiv:2512.08769's production guide recommends single-responsibility agents and clean separation between workflow logic and tool servers — avoids the "god agent" that does everything and breaks everything.

## Evidence

- **Engineering blog / Primary research:** Anthropic's multi-agent research system — lead Claude Opus 4 orchestrator spawning parallel Sonnet 4 subagents outperformed single Opus 4 by +90.2% on internal evaluation. Tool description improvements reduced task completion time 40%. Token usage: ~15× vs chat for multi-agent. Three factors explained 95% of performance variance on BrowseComp. — [Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Primary research / Survey:** MMC Ventures interviewed 30+ agentic AI startup founders and 40+ enterprise practitioners. Found that blockers for production deployment are *not* technical — workflow integration complexity, employee trust, and data privacy dominate. Successful teams deploy incrementally with narrow, verifiable use cases before scaling. — [MMC Ventures State of Agentic AI](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)

- **Open source / Primary tool:** LoopGain — open-source cost controller for AI agent loops using control-theoretic convergence detection instead of fixed max_iteration caps. Benchmarked: 92.8% less API spend than naive max_iter=20 ($27.05 → $1.94), ~15× faster (median 30.9s → 2.1s), 0.678 weighted preference across 1,800 judge comparisons. — [GitHub loopgain-ai/loopgain](https://github.com/loopgain-ai/loopgain)

- **Academic / Framework guidance:** arXiv:2512.08769 — "A Practical Guide for Designing, Developing, and Deploying Production-Grade Agentic AI Workflows" (Dec 2025, CC BY 4.0). Nine best practices include: tool-first design over MCP abstraction, pure-function tool invocation, single-responsibility agents, externalized prompt management, KISS principle. Demonstrated via multimodal news-to-media generation case study. — [arXiv:2512.08769](https://arxiv.org/abs/2512.08769)

- **Engineering guidance / Canonical:** Anthropic's "Building Effective AI Agents" — distinguishing workflows (predefined code paths) from agents (LLM-directed, dynamic). Recommends starting with the simplest solution. — [Anthropic Engineering](https://www.anthropic.com/engineering/building-effective-agents)

## Gotchas

- **"We'll improve it later" on tool descriptions** — tool schemas are the interface your agent relies on. Bad schemas cause silent failures where the agent calls the wrong tool or the right tool with wrong params. Treat them like user-facing API docs.
- **Forgetting token cost compounds in multi-agent** — Anthropic's multi-agent uses ~15× tokens vs ~4× for single-agent. Before parallelizing, ask: does the speedup justify the cost for this use case?
- **Naive max_iter caps** — a fixed iteration limit stops the loop mechanically. LoopGain's research shows it stops too late (wasting compute) or too early (shipping degraded output). Convergence detection beats counters.
- **The "god agent" anti-pattern** — one agent with access to everything. A single-responsibility agent that does one thing well is easier to test, debug, and replace than a monolith.
- **Adopting a framework as an architecture** — frameworks solve state management, not reasoning quality. The teams with the best results (per Anthropic) use the framework as scaffolding and own the core logic themselves.
