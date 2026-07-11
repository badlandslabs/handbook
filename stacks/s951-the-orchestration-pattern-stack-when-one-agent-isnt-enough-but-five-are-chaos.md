# S-951 · The Orchestration Pattern Stack — When One Agent Isn't Enough But Five Are Chaos

You've got a working single-agent system. Tasks that should be simple keep hitting its limits — it can research but can't write, it can draft but can't verify, it can execute but can't plan. The instinct is to give it more tools and a longer context window. The better move is to split the work across multiple specialized agents with a deliberate orchestration layer. But which pattern do you actually need? And how do you avoid spending all your budget on LLM calls?

## Forces

- Multi-agent systems amplify individual agent errors by ~17× without feedback loops and coordination — [LoopJar AI / Gartner data](https://loopjar.ai/fr/blog/agent-orchestration-feedback-loop)
- A 10-step process with 99% per-step success rates yields only 90.4% overall success — production systems need 99.9%+ — [LoopJar AI](https://loopjar.ai/fr/blog/agent-orchestration-feedback-loop)
- Anthropic reports multi-agent coordination improves task performance to 90.2% vs single-agent — but at ~15× the token cost — [LoopJar AI citing Anthropic research](https://loopjar.ai/fr/blog/agent-orchestration-feedback-loop)
- Most teams start with one framework (CrewAI, LangGraph) then rewrite in custom code when the framework's abstraction leaks under production load — [Hacker News, "Building Effective AI Agents" thread](https://news.ycombinator.com/item?id=44301809)
- The framework choice matters far less than model selection, observability, and error recovery design — [Presenc AI CTO analysis, May 2026](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026)
- LangGraph has the largest production deployment footprint in 2026; CrewAI leads on demo-to-prototype ergonomics; AutoGen leads in academic/research contexts — [Presenc AI Research, May 2026](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026)
- Production systems typically combine 2–3 orchestration patterns, not a single one — [Thinking Inc. AI Orchestration Patterns Guide, March 2026](https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns)

## The Move

Pick your orchestration pattern based on task shape, not framework popularity. Three patterns cover most production use cases:

**Supervisor routing** — One orchestrator decomposes a request, delegates to specialists, monitors results, and synthesizes the final output. Best for complex, multi-domain tasks where a single decision-maker should control the flow. The supervisor is the bottleneck and the safety valve.

**Sequential pipeline** — Each agent runs in order, passing output as input to the next. Best for tasks with strict dependency order (research → write → review → edit). Simple, traceable, and debuggable. The weakness is zero parallelism — slow steps block everything downstream.

**Parallel fan-out** — One agent dispatches multiple tasks simultaneously to independent agents, then aggregates results. Best for tasks where sub-problems are independent (analyze three documents, check five facts). The aggregation step is harder than it looks — conflicting results need a tiebreaker.

**Evaluator-optimizer loop** — An agent produces output, an evaluator grades it against criteria, and the producer revises. Repeats until the evaluator passes or a loop cap hits. Anthropic recommends this as the single most effective multi-agent pattern for quality-sensitive tasks — [Anthropic Engineering Blog](https://www.anthropic.com/engineering/building-effective-agents). The key design decision is the eval criteria: vague criteria produce vague passes.

**Router** — A classifier or LLM routes incoming requests to the appropriate agent or pipeline. Best when tasks have distinct types (support ticket vs. sales inquiry vs. refund request). Often combined with supervisor as the entry point.

Production systems don't pick one. A typical production stack: router at the edge → supervisor decomposes → parallel fan-out for independent sub-tasks → sequential pipeline for dependent steps → evaluator-optimizer loop for quality gates.

## Evidence

- **Framework comparison (primary):** LangGraph dominates enterprise production deployments; CrewAI dominates prototyping; AutoGen leads in research/academic settings; OpenAI Swarm is "experimental" and narrow. The Presenc AI CTO analysis also notes that for most teams, the framework is less consequential than model choice, observability, and error recovery. — [Presenc AI Research, May 2026](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026)

- **HN practitioner survey:** Interviews with 30+ startup founders and 40+ enterprise practitioners building agentic systems revealed that workflow integration challenges and organizational change management were the primary blockers — not technical capability. One HN commenter with a Java-based V0 product delivered it quickly with clean architecture, then spent months migrating to a Python framework without finishing. Conclusion: "Just use the API" for V0, frameworks add abstraction cost. — [Hacker News, "Building Effective AI Agents" discussion, June 2025](https://news.ycombinator.com/item?id=44301809)

- **Production observability repo:** The AccelateAI/multi-agent-orchestration GitHub repo (created May 2026) implements supervisor routing, sequential pipelines, and parallel fan-out as production-grade patterns with explicit error recovery and state persistence. Its README states: "The complexity isn't in the graph — it's in the nine production concerns around it." — [AccelateAI/multi-agent-orchestration on GitHub](https://github.com/AccelateAI/multi-agent-orchestration)

## Gotchas

- **LLM veto rates are high.** In multi-agent loops, the LLM judge vetoes ~25% of sessions even when the producer agent thought it succeeded. Build for veto-and-revise, not single-pass success. — [LoopJar AI citing production data](https://loopjar.ai/fr/blog/agent-orchestration-feedback-loop)
- **Token costs compound fast.** A single 2,000 USD/day compute bill is a reported real-world incident with a naive multi-agent setup. Budget per-session token limits and implement cost tracking as a first-class concern, not an afterthought.
- **Framework migrations are expensive.** Teams consistently underestimate the cost of migrating from a framework's abstractions to their own observability and internal systems. If starting a V0, use the raw API. If already on a framework, don't migrate until the abstraction genuinely costs more than the migration.
- **The aggregation step is underestimated.** Parallel fan-out looks easy until two agents return conflicting results. The tiebreaker agent — or a human-in-the-loop for high-stakes outputs — is not optional. Design it before you ship.
- **Determinism is a production requirement.** Multi-agent systems are non-deterministic by default. If your use case requires auditable, reproducible outputs (finance, compliance, legal), you need checkpointing, state persistence, and explicit rollback — not just better prompts.
