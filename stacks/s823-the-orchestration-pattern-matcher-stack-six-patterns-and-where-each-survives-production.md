# S-823 · The Orchestration Pattern Matcher — Six Patterns and Where Each Survives Production

You built a multi-agent system. It works in demos. In production, costs spiral, agents loop, and you have no idea which one failed. The root cause: you picked the wrong orchestration pattern for your problem shape. Six patterns cover ~90% of production use cases — but teams reach for the complex ones before exhausting the simple ones.

## Forces

- **Fan-out vs. fan-in tension** — parallel work is fast but coordination cost grows nonlinearly with agent count
- **Determinism vs. adaptability** — code-driven flows are predictable but brittle; LLM-driven flows are flexible but expensive and opaque
- **Context window pressure** — single-agent context explodes on complex tasks; distributed context requires explicit state management
- **Cost ceiling uncertainty** — multi-agent systems are cost multipliers, not linear; teams underinvest in cost governors until the bill arrives
- **Debugging debt** — the more agents, the harder to trace a bad output to its source; observability is not optional at this scale

## The move

The six patterns are ordered by complexity. Start at the top. Move down only when evidence shows the simpler pattern genuinely can't hold.

### 1. Sequential Chain — when the task is a pipeline

Model A output feeds Model B input. No branching, no parallelism.

- Use for: Summarize → classify → route; Extract → validate → store; any fixed-step workflow
- Strength: Simple, predictable, easy to debug, low cost
- Trap: Latency compounds; a failure in step 1 cascades; no parallelism means no speedup
- Evidence it works: Used as the "fallback after hierarchical mode drifts" — CrewAI teams report switching from hierarchical to sequential after ~40 production runs when delegation patterns became unpredictable

### 2. Supervisor + Specialists — when one agent should own the work

A supervisor agent decomposes the task and routes subtasks to specialist agents. Specialists execute and return. Supervisor integrates the final answer.

- Use for: Tasks requiring different domain expertise (legal + financial + technical analysis); anything where you'd naturally hand off to a colleague
- Strength: Simple, debuggable, cost-predictable — this is what most production "multi-agent" systems actually are
- Trap: Supervisor becomes a bottleneck if it's also generating the final output; specialists can produce outputs the supervisor can't integrate cleanly
- Tooling: LangGraph supervisor pattern, CrewAI hierarchical mode (with drift monitoring), OpenAI Agents SDK handoffs

### 3. Parallel Fan-Out — when independent work can happen simultaneously

One agent spawns N specialists working on independent subtasks, then results are merged.

- Use for: Research tasks (explore N topics in parallel), document analysis (analyze N sections), comparison tasks
- Strength: Near-linear speedup with agent count; captures distributed context without context-window pressure
- Trap: Fan-out cost is N × single-agent cost; merge step can lose signal if not designed carefully; Anthropic measured 15x token usage vs. single-agent for their research system
- Evidence: Anthropic's research system uses this pattern — subagents explore in parallel with separate context windows, then compress results back to supervisor; achieved 90.2% on internal benchmarks vs. single-agent baseline

### 4. Router — when the system must decide which path to take

An LLM or heuristic classifier routes incoming requests to the appropriate agent, pipeline, or response path.

- Use for: Intent classification at scale, routing customer queries to specialists, dynamic tool selection
- Strength: Clean separation of routing logic from task execution; enables A/B testing of agent paths
- Trap: Router itself can misclassify, sending requests down wrong paths — the failure mode is invisible until you measure per-path accuracy
- Tooling: OpenAI Agents SDK structured outputs for classification, LangGraph conditional edges

### 5. Hierarchical — when nested delegation matters

A top-level agent manages a team of sub-agents, each potentially managing their own sub-teams. Control flows top-down, results flow bottom-up.

- Use for: Large-scale research (e.g., market analysis requiring regional + industry + regulatory sub-teams), complex project planning
- Strength: Models real organizational structure; can scale to very large problem spaces
- Trap: Anthropic observed that hierarchical modes "drift" after ~40 production runs as delegation patterns become harder to predict; deep hierarchies are nearly impossible to debug
- Evidence: Anthropic's Claude Code architecture independently converged on hierarchical + parallel patterns; the deeper lesson is that hierarchy works at 2 levels, not 5

### 6. Evaluator-Optimizer Loop — when quality requires iteration

An agent produces output, an evaluator scores it against criteria, and the agent迭代 (iterates) until quality threshold is met or loop limit is hit.

- Use for: Code generation with test requirements, writing with editorial standards, any output where quality is measurable
- Strength: Dramatically improves output quality on complex tasks (Anthropic: 90.2% improvement on research benchmarks)
- Trap: Without a hard loop limit and cost governor, this is where runaway costs happen; evaluation itself consumes tokens; some tasks don't converge
- Evidence: Anthropic's core pattern — interleaved thinking with continuous plan refinement; OpenAI Agents SDK: "run it in a loop and let it critique itself"

## Evidence

- **Anthropic engineering blog:** Multi-agent research system achieves 90.2% on internal benchmarks; 15x token usage vs. single-agent; uses orchestrator-worker + parallel subagent + evaluator loop; key lessons: persist critical context explicitly, design for dynamic adaptation, embed scaling heuristics — [https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

- **TURION.AI field note (March 2026):** Surveyed 12 production multi-agent deployments; supervisor + specialists is what "most production multi-agent systems actually are"; fan-out + merge is the second most common; hierarchy works at 2 levels not 5; cost and failure handling are the two hardest unsolved problems — [https://turion.ai/blog/multi-agent-orchestration-infrastructure-production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)

- **OpenAI Agents SDK documentation:** Documents two orchestration modes — LLM-driven (for open-ended tasks, unpredictable paths) and code-driven (for deterministic, predictable outcomes); recommends specialized agents over generalists; structured outputs for LLM-based routing decisions; handoffs for delegated ownership — [https://openai.github.io/openai-agents-python/multi_agent/](https://openai.github.io/openai-agents-python/multi_agent/)

- **Camunda blog — 50+ enterprise customers (October 2025):** Across banking, insurance, healthcare, telecom — "deterministic process + AI agents within bounded guardrails" delivers measurable ROI; agentic orchestration fails when agents operate without process boundaries; the process is the governor — [https://camunda.com/blog/2025/10/hype-to-impact-lessons-learned-making-agentic-orchestration-work](https://camunda.com/blog/2025/10/hype-to-impact-lessons-learned-making-agentic-orchestration-work)

- **Technspire — State of Agentic AI end-2025:** Agents shipped in 4 domains: developer tooling (tight feedback loops), customer service (high volume, scripted), data extraction (schema-defined), research synthesis (human-in-loop); the common thread: software engineering discipline, bounded scope, observable runtime — [https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons](https://technspire.com/en/blog/state-of-agentic-ai-end-2025-production-lessons)

- **r/LocalLLaMA — former Manus backend lead (March 2026):** After 2 years building agents at Manus, abandoned function calling entirely in favor of a single `run(command="...")` tool exposing Unix-style commands; argument: agent interfaces have become more complicated than the underlying tasks require; Unix philosophy (small tools, composition) beats large function catalogs — [https://www.reddit.com/r/LocalLLaMA/comments/1rrisqn/i_was_backend_lead_at_manus_after_building_agents/](https://www.reddit.com/r/LocalLLaMA/comments/1rrisqn/i_was_backend_lead_at_manus_after_building_agents/)

## Gotchas

- **Reaching for hierarchy when sequential suffices.** Most production systems use supervisor + specialists (pattern 2) and never need more. Add hierarchy only when you have evidence of delegation drift at scale.
- **No cost governor on evaluator-optimizer loops.** The loop will consume your entire budget on a hard task. Set hard token limits and a cost-per-run cap before running this pattern.
- **Fan-out cost is N×, not 1×.** Parallel subagents multiply your token budget. Budget for 15x vs. single-agent before going parallel.
- **Hierarchical mode drifts.** Anthropic, Turion, and CrewAI teams all report that deep hierarchies (3+ levels) produce unpredictable delegation patterns over time. Monitor per-path accuracy, not just final output quality.
- **Router misclassification is silent.** If the router sends 10% of requests down wrong paths, you won't notice until customers complain. Measure per-path accuracy from day one.
- **Framework choice ≠ orchestration pattern.** LangGraph, CrewAI, and AutoGen implement overlapping patterns — pick based on observability needs (LangGraph), development speed (CrewAI), or Azure integration (AutoGen) — not based on which "sounds more agentic."
