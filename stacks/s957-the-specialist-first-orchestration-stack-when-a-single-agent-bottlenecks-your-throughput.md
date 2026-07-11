# S-957 · The Specialist-First Orchestration Stack — When a Single Agent Bottlenecks Your Throughput

When your agent pipeline is fast enough for demos but collapses under real load — context windows saturating, every query routed through the biggest model, parallelism impossible, and latency compounding step by step.

## Forces

- **Token cost vs. accuracy trade-off** — routing everything through Opus-class models is reliable but expensive; Haiku-class models are cheap but unreliable on hard tasks
- **Context saturation** — a single agent handling retrieval, coding, review, and routing fills its context window and degrades downstream reasoning
- **Serial execution tax** — one agent doing everything means total latency = sum of all steps; no concurrency possible
- **Single point of failure** — one error stalls the entire pipeline with no isolation
- **Static workflows are wrong-sized** — a 10-step pipeline on a trivial query wastes compute; a 2-step pipeline on a hard query produces wrong answers

## The Move

**Specialist-First Orchestration: route to the smallest capable model, distribute context across parallel agents, and reserve the largest model only for synthesis.**

The pattern has four layers:

- **Difficulty classifier (lightweight model)** — estimates query complexity before committing to a pipeline depth. Simple queries get 1–2 agent hops; hard queries get 5+. This is the highest-leverage architectural decision, consistently delivering 12–23% gains over model-upgrade-only approaches. (arXiv:2509.11079, WWW '26)
- **Specialized subagents (small/medium models)** — each agent handles one domain: retrieval, coding, review, routing. They run in parallel and maintain isolated context windows. Context is only merged at the synthesis step.
- **Lead orchestrator (large model)** — a single Opus/Claude-level agent owns planning, delegates work to subagents, and synthesizes final output. Anthropic's production system uses this exact topology and achieved **90.2% better performance than a single-agent Opus 4** (verified on their research evaluation suite).
- **Token-aware cost control** — token usage alone explains ~80% of performance variance in multi-agent research tasks (Anthropic engineering data). The lead agent monitors token budget per subagent and terminates paths that exceed thresholds.

Key implementation insight from DevOpsBoys: use LangGraph's conditional edges to model the orchestration as a **state machine** rather than a static chain. Agents write to shared state; routing decisions are explicit graph edges, not implicit LLM behavior.

## Evidence

- **Engineering blog + arXiv (cross-referenced):** Anthropic's multi-agent research system uses a lead Opus 4 + parallel Sonnet 4 subagents. Multi-agent outperforms single Opus 4 by 90.2% on research benchmarks. Token distribution accounts for 80% of performance variance. — [Anthropic Engineering](https://www.anthropic.com/engineering/multi-agent-research-system), [Plain English summary](https://ai.plainenglish.io/how-we-built-our-multi-agent-research-system-5f5e10b2a8d6)
- **Academic paper:** DAAO (Difficulty-Aware Agentic Orchestration) dynamically generates query-specific multi-agent workflows. Across HumanEval and GSM8K, difficulty routing delivers 12–23% gains over fixed-topology approaches at equivalent model quality. — [arXiv:2509.11079](https://arxiv.org/pdf/2509.11079), [GitHub repo](https://github.com/AutoAgents-ai/DAAO)
- **Engineering blog:** Google's internal experiments show distributed multi-agent pipelines reducing processing time from ~1 hour to ~10 minutes (6× speedup) compared to monolithic single-agent approaches on complex queries. — [MACGPU blog citing Google agent bake-off](https://macgpu.com/en/blog/2026-0622-multi-agent-ai-architecture-production-guide.html)

## Gotchas

- **Difficulty classifiers misfire on edge cases** — a classifier that routes incorrectly on ambiguous queries either wastes compute on simple queries or produces shallow answers on hard ones. Validate with a calibration set before deploying.
- **Subagent context isolation hides cross-cutting concerns** — if two subagents make conflicting assumptions about shared state, the lead agent's synthesis step may produce internally inconsistent output. Use a shared schema for subagent outputs, not freeform text.
- **The lead agent becomes the new bottleneck** — if the lead agent's context window saturates before subagents complete, planning degrades. Cap subagent outputs and route through a summarizer before returning to the lead.
- **Static pipelines still dominate in practice** — most production systems still use fixed sequential chains because dynamic orchestration adds complexity without obvious payoff until scale. The ROI only materializes past ~50 concurrent queries/day.
