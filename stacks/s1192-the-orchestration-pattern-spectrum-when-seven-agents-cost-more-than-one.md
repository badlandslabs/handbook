# S-1192 · The Orchestration Pattern Spectrum — When Seven Agents Cost More Than One

You have a task that needs multiple agents. Planner, researcher, writer, critic, fact-checker. Five agents, five tokens per step, five chances for something to drift. You ship it. Three weeks later you discover the single-agent version with better prompting was 40% cheaper and 2 points less accurate — which nobody noticed because the task didn't need those 2 points. You picked orchestration before diagnosing whether you needed it.

The pattern you choose — orchestrator-worker, sequential pipeline, parallel fan-out, evaluator-optimizer loop, or router — determines your cost, latency ceiling, failure surface, and the complexity ceiling your system can handle. Most teams pick one framework and inherit its default pattern. That works until it doesn't.

## Forces

- **Multi-agent gains are narrower than advertised.** Princeton NLP benchmarks found single agents match multi-agent on 64% of tasks; the accuracy delta is +2.1 percentage points at 2x the cost. Gartner found 40% of multi-agent pilots fail within six months of production deployment — not because the agents don't work, but because the wrong pattern was chosen.
- **The pattern choice is architectural and irreversible.** Sequential pipelines are cheap and simple but can't parallelize; orchestrator-worker scales team coordination but the orchestrator becomes a single point of failure; evaluator-optimizer loops produce quality but multiply token costs.
- **Framework defaults constrain your pattern.** LangGraph defaults to state-machine graphs (great for conditional branching and crash-safe resume). CrewAI defaults to role-based task delegation (fastest for prototyping). AutoGen/AG2 defaults to conversation-driven negotiation (best for research). Rolling your own gives you pattern freedom but re-invents observability, retries, and state management from scratch.
- **State coordination is the underappreciated failure mode.** Individual agent capabilities are well-handled by every framework. What they don't handle: preventing multiple agents from overwriting each other's state, cascading errors through shared context, or deadlocking on conflicting goals. Frameworks solve the fun part; teams discover the coordination tax in production.

## The Move

Match the orchestration pattern to the workflow shape, not the other way around.

**Six patterns cover the vast majority of use cases:**

- **Sequential pipeline** — Tasks with strict dependency order. Each agent's output feeds the next. Simple, cheap, traceable. Breaks when any step can run independently.
- **Orchestrator-worker** — One central agent decomposes a task and delegates to specialists. The orchestrator uses a capable model; workers use cheaper, task-specific models. Best for cross-functional workflows. The orchestrator is a critical path — if it misdecomposes, all sub-agents produce wrong outputs.
- **Parallel fan-out/fan-in** — Independent subtasks run simultaneously, results merge at a join point. Best for batch operations, report generation from independent sections. The merge point is the failure surface — what if two agents produce conflicting facts?
- **Router/supervisor** — A single agent classifies incoming requests and routes to the right handler. Simple, fast, low cost. Best for intent classification and initial triage. Fragile if the router misses edge cases.
- **Hierarchical** — A chain of escalating authority. Junior agents handle routine cases; escalate to senior agents on uncertainty. Natural fit for customer support and triage workflows.
- **Evaluator-optimizer loop** — An agent produces output, a critic grades it, the original agent revises. Repeat until the critic passes. Best for high-stakes outputs (code review, legal drafts, technical writing). Expensive — each loop doubles token spend. The break condition is the design challenge.

**On framework choice:**
- LangGraph for production systems needing fine-grained control, branching, approvals, and crash-safe resume (the graph is the feature).
- CrewAI for fast prototyping with role-based agent teams (accept that you'll migrate when you need branching).
- AG2 (AutoGen) for research-heavy conversational negotiation between agents.
- Custom/roll-your-own when you need a pattern none of the above support cleanly — but budget 3x the time for observability and error recovery you would have gotten for free.

## Evidence

- **HN Ask HN (16 pts, ~4 months ago):** A 13-agent production system (PAI Family) running specialized agents for research, finance, content, strategy, critique, psychology — agents collaborate, argue, and bet against each other via a prediction market. Key practitioner finding: "The biggest underappreciated problem is state coordination. Frameworks handle individual agent capabilities well. What they don't handle: preventing multiple agents from overwriting each other's state." — [HN Ask HN: Multi-agent AI in daily workflow](https://news.ycombinator.com/item?id=47270020)
- **HN Ask HN (8 pts, ~3 months ago):** Practitioners reporting production stacks: roll-your-own ("0 framework good enough for serious work"), LangGraph + custom, AGNO (minimalistic, isolation, decoupling, control plane architecture), custom Node.js in V8 isolates with MongoDB shared state. Data passing: JSON documents via MongoDB, shared filesystem, message queues (SQS/SNS). — [HN Ask HN: Multi-agent orchestration in production](https://news.ycombinator.com/item?id=47660705)
- **Cognition AI blog + HN discussion (123 pts, 89 comments, ~10 months ago):** Argues simpler single-agent approaches outperform complex multi-agent systems. Key finding: context management problems emerge well before context windows fill. Multi-agent coordination overhead often negates the specialization benefit. Counter-thesis: subagents can share context efficiently without bloating. HN commentators pointed to cases where multi-agent works (diverse tool access, genuine role specialization, parallel independent work). — [HN: Don't Build Multi-Agents](https://news.ycombinator.com/item?id=45096962) | [Original Cognition post](https://cognition.ai/blog/dont-build-multi-agents)
- **Beam.ai (Jul 14, 2026):** Production deployment data — 1,445% growth in multi-agent inquiries (Gartner, Q1 2024 → Q2 2025). Average 12 agents per organization. Multi-agent pilots failing at 40% within 6 months. Single agent matches multi-agent on 64% of benchmarked tasks. +2.1 percentage points accuracy at ~2x cost. — [Beam.ai: 6 Multi-Agent Orchestration Patterns for Production](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **Tacavar benchmarks (Apr 2026):** LangGraph best for stateful graph-based workflows with fine-grained control. AutoGen best for research-heavy conversational multi-agent. CrewAI best for rapid prototyping and role-based teams. — [Tacavar: LangGraph vs AutoGen vs CrewAI 2026](https://tacavar.com/blog/ai-agent-frameworks-compared-2026/)

## Gotchas

- **Reaching for multi-agent before diagnosing the workflow shape.** If your task is a linear transformation, a sequential pipeline with one agent and a good system prompt beats five agents. Profile first.
- **The orchestrator becomes a critical path.** When you use orchestrator-worker, the orchestrator's misdecomposition cascades to every worker. Invest in the orchestrator's quality gate — a bad decomposer poisons the whole pipeline.
- **Merge point conflicts in parallel fan-out.** When two agents produce different facts about the same entity, the merge point needs a conflict resolution strategy you designed before shipping, not during an incident.
- **The loop termination problem in evaluator-optimizer.** Without a well-defined break condition, the loop can run indefinitely or terminate too early. Define exit criteria in terms of critic scores, iteration counts, or cost limits before the first run.
- **Framework migration is expensive.** Teams that start in CrewAI for speed and migrate to LangGraph for control (or custom for flexibility) pay a 2-3x rewrite tax. Pick the pattern first; the framework is second.
