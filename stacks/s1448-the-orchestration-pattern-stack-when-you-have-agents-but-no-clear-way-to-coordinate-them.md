# S-1448 · The Orchestration Pattern Stack — When You Have Agents but No Clear Way to Coordinate Them

You have tools. You have agents. You have memory. What you don't have is a coherent plan for how they flow into each other — so the LLM decides at runtime, context balloons, costs spiral, and nobody can trace what happened when something goes wrong.

## Forces

- **Naive chaining collapsed.** By 2025, "chain LLM calls together and hope" had produced deadlocks, silent failures, state corruption, and runaway costs at scale. Teams learned agent coordination requires the same engineering discipline as distributed systems generally.
- **Frameworks fragmented the community.** LangChain/LangGraph dominated with 126K+ GitHub stars and 57% production adoption, but the HN community largely agreed: the ability to swap APIs was less valuable than claimed, and framework overhead hurt debugging more than it helped. Direct API usage won for many teams.
- **Every pattern has a ceiling.** Sequential chains are simple but no parallelism. Routers are fast but require a good classifier. Parallel fan-out burns budget. Supervisors bottle-neck. Evaluator-optimizers are expensive but high-quality. No single pattern wins universally.
- **Multi-agent coordination is where projects die.** Anthropic's analysis of 200+ enterprise deployments found 57% of failures rooted in orchestration design, not individual agent capability. The agents were strong enough; the coordination wasn't.

## The Move

Choose orchestration patterns along a complexity spectrum. Start at the simplest viable level, measure, and advance only when evidence shows a ceiling.

### Level 1: Direct API calls with augmentation (start here)
- Use the LLM API directly with structured outputs and typed schemas rather than letting the model freely call tools
- Add tool use only when the task genuinely requires environmental interaction (browser, code execution, external API)
- Add memory only when the conversation genuinely benefits from prior context across turns
- Resist the pull to add multi-agent coordination until a specific failure mode demands it

### Level 2: The six core orchestration patterns (use one or combine)

| Pattern | What it does | Use when |
|--------|-------------|----------|
| **Sequential Chain** | Output of Model A feeds Model B | Simple pipelines: extract → classify → route |
| **Router / Classifier** | LLM or heuristic routes input to specialized handler | Task types differ enough to need distinct processing |
| **Parallel Fan-Out** | Same input sent to multiple agents, results merged | Redundancy or breadth matters (e.g., multi-perspective analysis) |
| **Supervisor / Hierarchical** | One agent directs others, manages their outputs | Complex workflows requiring a conductor with visibility |
| **Evaluator-Optimizer Loop** | One agent produces, another critiques, loop until quality | High-stakes outputs where iteration improves quality |
| **Difficulty-Aware Routing** | Classifier estimates task complexity, routes to appropriate depth | Cost-sensitive production systems with mixed workloads |

### Level 3: Choose an architectural model for coordination

- **DAG-Based (LangGraph, Temporal, Prefect, Airflow):** Explicit dependency graphs, deterministic execution order. Best for workflows where correctness of sequence matters. Latency is predictable. Failure modes are traceable.
- **Event-Driven (Kafka, pub/sub, MCP, A2A):** Agents react to events asynchronously. Best for high-throughput, loosely coupled systems. Requires careful schema design. Agents can process at different rates.
- **Actor Model (AutoGen, Microsoft Agent Framework):** Isolated state per agent, message-passing between agents, supervision hierarchies for failure recovery. Best for complex multi-agent conversations with natural dialog patterns.

### Level 4: Combine patterns in practice
- Production systems typically run 2-3 orchestration patterns in a single workflow
- Common combo: Router at the top level → Sequential or Parallel within each branch → Evaluator-Optimizer for critical outputs
- The "evaluator-optimizer" loop is increasingly common as a quality gate: generate → judge → regenerate, stopping when quality threshold is met

## Evidence

- **Anthropic Engineering Blog:** Recommends starting with LLM APIs directly — "most successful implementations use simple, composable patterns rather than complex frameworks." Documents four core workflow patterns (Prompt Chaining, Routing, Parallelization, Orchestrator-Workers) with decision criteria for each. — [URL](https://www.anthropic.com/engineering/building-effective-agents)
- **Camunda (50+ customer deployments, Oct 2025):** Found the root cause of most failed agentic projects is "orchestration design — the individual agents are strong enough, but coordination is weak." Introduced the "Agentic Value Trap": early pilots look promising, then agents make inconsistent decisions on the same case because nobody owns the end-to-end process. Recommends deterministic process logic governing known paths, with dynamic agents only for the unpredictable middle. — [URL](https://camunda.com/blog/2025/10/hype-to-impact-lessons-learned-making-agentic-orchestration-work)
- **Zylos Research (Apr 2026):** Traced three architectural schools (DAG, Event-Driven, Actor) to specific failure modes in 2025 — "by 2025 that approach had collapsed under its own complexity: deadlocks, state corruption, silent failures, and runaway costs." Identified difficulty-aware dynamic routing as a key 2026 pattern delivering cost reductions without accuracy loss. — [URL](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)
- **Microsoft Azure Architecture Center (2026):** Five-level complexity spectrum from Direct model call → Prompt chaining → Parallelization → Supervisor/Orchestrator → Multi-agent systems. Recommends starting at Level 1 and only advancing when requirements genuinely need it. — [URL](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- **Hacker News thread on "Building Effective Agents" (Jun 2025, 543 points):** Practitioners with production systems reported that framework lock-in hurt more than it helped. "Having built several systems serving massive user bases with LLMs — the ability to swap out APIs just isn't that important in practice." Direct API usage with simple orchestration code was preferred. — [URL](https://news.ycombinator.com/item?id=44301809)

## Gotchas

- **The multi-agent reflex.** Teams add a second agent when they should first fix their first agent's prompt, tool design, or evaluation loop. Multi-agent coordination adds overhead proportional to the product of agent complexity — don't multiply unsolved problems.
- **Synchronous coupling kills production.** Coupling the agent execution loop with the synchronous request-response path is the architectural choice that causes the most production incidents. Async execution, streaming intermediate states, and dead-letter queues for failure isolation are not optional at scale.
- **Framework hype vs. production reality.** LangChain has 126K+ stars but also widespread backlash from production engineers. Microsoft Agent Framework's RC (Jun 2026) merging Semantic Kernel and AutoGen is a sign the ecosystem is consolidating — pick frameworks with stable APIs and strong observability tooling, not just stars.
- **Routing classifiers can be the weakest link.** A router that misclassifies input sends the wrong task down the wrong pipeline — and unlike a slow chain, this fails silently and confidently. Validate routing accuracy before routing in production.
