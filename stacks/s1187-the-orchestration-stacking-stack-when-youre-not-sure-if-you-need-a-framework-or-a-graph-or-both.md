# S-1187 · The Orchestration Stacking Stack — When You're Not Sure If You Need a Framework, a Graph, or Both

You're building an AI system that needs more than one step. You know a simple prompt won't cut it. But you're staring at a menu of options — raw API chains, LangGraph, CrewAI, AutoGen, Mastra, Temporal, event buses — and every option seems to come with a new vocabulary: DAG, supervisor pattern, actor model, fan-out/fan-in. This is the orchestration stacking problem: choosing not just *what* your agents do, but *how* they connect, and at what cost.

## Forces

- **Simplicity bias vs. flexibility debt.** LangChain's 2025 production survey found simple chains handle 80% of production use cases — yet teams consistently over-engineer their first implementations, reaching for multi-agent orchestration when a single agent with well-scoped tools would outperform it.
- **Framework abstraction hides non-determinism, making it harder to debug.** Anthropic's engineering guidance (June 2025, cited on HN with 543 points) explicitly recommends starting with direct API calls: "Many frameworks make agentic systems easier to implement. However, they often create extra layers of abstraction that can obscure the underlying prompts and responses, making them harder to debug." A thread commenter put it bluntly: "It's insane that people use whole frameworks when you can just do it with the API."
- **Agent loops burn money silently.** Without explicit gating, a ReAct-style loop will re-call the LLM on every step with no termination guarantee. One practitioner described watching a multi-agent pipeline accumulate $400 in API costs on a single input.
- **Graph-based orchestration has become production infrastructure** — not experimental. Zylos Research (April 2026) notes that by 2025, naive chaining "collapsed under its own complexity: deadlocks, state corruption, silent failures, and runaway costs." The industry shifted to explicit directed graphs with typed state, conditional routing, and checkpointed execution.
- **Routing itself becomes the new bottleneck.** As teams add difficulty-aware routing, they discover the router itself needs evaluation — it can misclassify complexity and send trivial queries down expensive pipelines or vice versa.

## The Move

**Start at the bottom of the stack and move up only when you hit a concrete wall. The three patterns that survive production are a ladder, not a menu.**

1. **Single agent first.** A single `create_agent` call with 3–5 well-scoped tools beats a three-node graph for most use cases. You only need orchestration when you hit branching (different next steps based on classification), parallelism (fan-out to multiple workers), checkpoint/resume (need to recover mid-task after failure or human approval), or genuinely distinct roles that need separate context windows.

2. **Three canonical orchestration patterns, in order of increasing cost:**
   - **Simple chains** for linear, fixed-step workflows (summarize → extract → format). Zero autonomy needed. One failure stops everything downstream — plan for it.
   - **Router patterns** for task classification and cost-tiered dispatch. A classifier estimates query difficulty and routes to the appropriate depth. Weights & Biases (2025) documented 60% cost reduction and 40% latency reduction from tiered routing. Anthropic's own guidance is essentially a router: agents that "dynamically direct their own processes" are just routers with a model-in-the-loop.
   - **Agent loops (ReAct-style)** for open-ended problems requiring hypothesis formation, search, and iterative evaluation. Add explicit step limits, token budgets, or confidence thresholds — or set a hard cost ceiling per session.

3. **If you need a framework, match it to the production horizon:** CrewAI for demos (Reddit consensus: "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday"), LangGraph for production with checkpointing and interrupt support (the `interrupt()` feature is what separates toy demos from finance/ops deployments — teams describe it as "first-class"), Mastra if you're in the TypeScript/Node ecosystem (22K GitHub stars, YC W25, 300K weekly npm downloads as of January 2026 — "batteries-included" for TypeScript devs).

4. **Production architecture for multi-agent at scale** (per Markaicode's AWS EKS stress testing of CrewAI): stateless agent workers in separate containers, each agent isolated to prevent failure cascade, Redis stream as task queue (one stream per crew, coordinator is stateless), S3-compatible object store for results, at-least-once delivery with idempotent handlers, P50 orchestration overhead budgeted under 500ms to preserve agent response budget.

5. **Treat the execution graph as the specification.** Zylos Research frames this precisely: "The graph is not just a control flow mechanism — it is the specification of what the system is allowed to do, expressed as code." This makes the graph testable, auditable, and reviewable — critical for regulated industries.

## Evidence

- **Hacker News (543 points, June 2025):** Anthropic published "Building Effective Agents" — core guidance was that simple patterns beat complex orchestration, and that starting with direct API calls beats frameworks. Thread consensus agreed: frameworks "obscure underlying prompts and responses." HN commenter: "It's insane that people use whole frameworks when you can just do it with the API." — [HN #44301809](https://news.ycombinator.com/item?id=44301809)
- **ACM WWW '26 paper (April 2026):** "Difficulty-Aware Agentic Orchestration for Query-Specific Multi-Agent Workflows" (Su et al.) documented 64% cost reduction via difficulty-aware dynamic routing without accuracy loss — a multi-model pipeline that routes simple queries to small models and complex ones to larger ones. Validates the router pattern empirically. — [ACM DL #3774904.3792240](https://dl.acm.org/doi/10.1145/3774904.3792240)
- **Markaicode (May 2026):** CrewAI production architecture stress-tested on AWS EKS (m5.xlarge, 4 vCPU) — P95 latencies hit 10+ seconds before 50 concurrent requests without Redis-backed stateless workers. Published concrete deployment checklist. — [markaicode.com](https://markaicode.com/architecture/crewai-system-design-architecture-1048)
- **Agentika blog (February 2026):** LangChain's 2025 production survey cited — 80% of production use cases handled by simple chains. Router patterns documented as delivering 60% cost / 40% latency reduction. — [agentika.uk](https://agentika.uk/blog/llm-orchestration-patterns.html)
- **Zylos Research (April 2026):** Two-part deep dive on orchestration — DAG-based, event-driven, and actor-model schools documented. LangGraph 1.0 GA (October 2025), Mastra 1.0 (January 2026, 22K stars), OpenAI Agents SDK (March 2025), Microsoft Agent Framework 1.0 (April 2026). "Difficulty-aware dynamic routing" as the key emerging 2026 pattern. — [zylos.ai/research](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns/)

## Gotchas

- **Reaching for multi-agent when single-agent suffices** is the #1 over-engineering mistake. A single agent with well-scoped tools and a good system prompt outperforms a poorly coordinated crew on most tasks.
- **Event-driven and actor-model patterns are production-grade but add significant operational complexity.** Teams with Kafka/Flink backgrounds use them to handle thousands of concurrent agent tasks with dead-letter queues — but for teams without that infrastructure, it's the wrong starting point.
- **Difficulty-aware routing can be wrong at the router level.** If the classifier misjudges complexity, trivial queries get expensive pipelines and complex ones get inadequate treatment. Test the router separately from the downstream agents.
- **Framework versions break in ways the documentation doesn't warn about.** LangGraph's checkpointing and interrupt APIs had breaking changes between 0.x versions; CrewAI's async agent behavior diverges from its sync behavior in subtle ways. Pin versions and test the full flow, not just individual nodes.
