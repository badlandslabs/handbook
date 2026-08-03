# S-2053 · The Pattern-Match Stack — When You Reach for Multi-Agent Orchestration But Simple Would Work

You have a task that exceeds what a single LLM call can handle — too many steps, too many tools, or too many failure modes. The instinct is to reach for a multi-agent framework and start spawning agents. The problem: 88% of AI agents never make it to production, and the most common failure isn't the model — it's the harness layer around it. The teams that actually ship are the ones who treated orchestration as a last resort, not a first reflex.

## Forces

- **Complexity grows superlinearly with agents.** Each additional agent adds coordination overhead, observability cost, and failure surface — not just capability.
- **Framework lock-in is real and underreported.** LangGraph, CrewAI, and custom code have radically different debugging, testing, and deployment profiles. Switching mid-project is painful; switching in production is a rewrite.
- **The pattern determines the ceiling.** Supervisor routing handles branching logic but creates a single point of failure. Sequential pipelines are debuggable but collapse under non-linear tasks. Parallel fan-out scales well but multiplies cost and error surface.
- **AutoGen is effectively dead.** As of May 2026, Microsoft replaced AutoGen with Microsoft Agent Framework (MAF). CrewAI has 52,000 GitHub stars but zero publicly verified production case studies — all are anonymized. LangGraph has the only verifiable production record at scale: Klarna, LinkedIn, Uber, Elastic, and Replit.
- **95% of enterprise GenAI pilots deliver zero measurable ROI.** The problem isn't the model — it's integration, governance, and operational maturity.

## The move

Pick the lowest-complexity pattern that fits your actual need, not your anticipated one. Escalate only when the simpler pattern genuinely fails, not when it gets uncomfortable.

### The six core patterns (in order of complexity)

1. **Direct LLM calls** — single completion, no agents. Start here. Most tasks that "need" agents actually need better prompting or retrieval.
2. **Router pattern** — one LLM classifies input and routes to a fixed handler. Zero agent overhead; just conditional logic over function calls.
3. **Pipeline (sequential)** — task flows through fixed steps with clear contracts. Each step is independently testable. Best for linear decomposition: `research → draft → review → edit`.
4. **Supervisor + Specialists** — one "supervisor" agent decomposes tasks and routes to specialist agents. Supervisor integrates results. Simple, debuggable, effective. This is what most production "multi-agent" systems actually look like.
5. **Evaluator-Optimizer loop** — iterative cycle where an evaluator scores output and the generator refines. Strong for creative tasks: code, writing, SQL. Set explicit stopping criteria upfront (iteration cap, quality threshold).
6. **Fan-out / parallel execution** — same input dispatched to multiple agents, results aggregated. Best for parallel survey tasks. Expensive; verify aggregation logic is sound before scaling.

### When to actually reach for orchestration

Anthropic's engineering team distilled it: use **workflows** (predefined code paths) when steps can be predicted; use **agents** (dynamic tool use) when the model must direct its own process. Most teams use agents when workflows would suffice. The decision rule: if you can write the decision tree in `if/else`, you don't need an agent.

### The framework decision

| Framework | Production record | Best for | Watch out |
|-----------|-----------------|----------|-----------|
| **LangGraph** | Klarna, LinkedIn, Uber, Elastic, Replit | DAG-based workflows, checkpointing, production | Steeper learning curve than CrewAI |
| **CrewAI** | Unverifiable (anonymized case studies only) | Fast prototyping, developer experience | Production maturity unclear |
| **Custom code** | Common at scale | Full control, minimal dependencies | Reinventing wheel; no checkpointing |
| **Microsoft Agent Framework (MAF)** | Too new (replaced AutoGen) | Microsoft stack integration | Don't use in production yet |

## Evidence

- **Engineering blog:** Anthropic's "Building Effective Agents" (Dec 2024) — after working with dozens of teams, the finding is blunt: "the most successful implementations use simple, composable patterns rather than complex frameworks." Their five workflow patterns (Router, ReAct, Supervisor, Evaluator-Optimizer, Pipeline) cover most production use cases without agentic overhead. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents)
- **Production comparison:** ODSEA's CTO-level review (May 2026) of LangGraph vs CrewAI vs AutoGen finds LangGraph is the only framework with verified production deployments at scale (Klarna at 85M users, LinkedIn, Uber, Replit). AutoGen is "effectively dead — in maintenance mode, replaced by MAF." CrewAI has 52k stars but zero public non-anonymized case studies. — [odsea.com/blog/langgraph-vs-crewai-vs-autogen-production](https://odsea.com/blog/langgraph-vs-crewai-vs-autogen-production)
- **Field note:** TURION.AI's production deployment notes (March 2026) — "multi-agent systems are harder to operate than single agents by roughly the order of their agent count." The patterns that work: Supervisor + Specialists (most common production pattern), Pipeline (linear tasks), and Event-Driven (async, loosely coupled). — [turion.ai/blog/multi-agent-orchestration-infrastructure-production/](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production/)

## Gotchas

- **Reaching for orchestration too early is the #1 mistake.** Most tasks that "need" agents actually need better prompting, a RAG pipeline, or a router. Every agent you add multiplies failure surface and debugging cost. Reddit and HN practitioner consensus in 2025–2026 is unanimous: start simpler.
- **Failures happen at the harness layer, not the model layer.** Harness Engineering's production post-mortem (March 2026): "When an agent fails, the natural question is 'what did the model do wrong?' The answer is almost always: the orchestration logic, tool integration code, context management, or verification steps." Prompt optimization hits diminishing returns past ~85-90% task completion; the remaining gap requires infrastructure fixes.
- **No circuit breaker means runaway costs.** Without explicit caps on loop iterations, fan-out parallelism, or tool call counts, agents can spiral — producing $47,000 API bills from a single recursive loop. Set hard limits on every dimension: max iterations, max tool calls per step, cost ceiling per run.
- **Framework features ≠ architectural decision.** LangGraph supports hundreds of nodes in a graph. That doesn't mean you should use them. The question is always: what is the simplest pattern that handles my actual use case?
- **No observability at the agent level means no debugging.** Each agent in a multi-agent system needs traceable outputs, intermediate state, and decision logs. If you can't answer "what did each agent decide and why?" you can't debug failures. LangGraph's checkpointing is one solution; custom instrumentation is another — but you must have something.
