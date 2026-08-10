# S-2430 · The Reliability Compounding Stack — When 95% Per-Step Still Fails Half Your Runs

Your agent nails 95% of its tool calls. Your demo works flawlessly. Then you ship a 20-step enterprise workflow and it fails on every fifth run. The math isn't broken — your expectations are. Welcome to the compound reliability problem, the single biggest gap between agent benchmarks and production reality in 2026.

## Forces

- **The formula is unforgiving:** If each step in a multi-step agent succeeds at rate p, a workflow of N steps succeeds at probability p^N. At 95% per-step accuracy across 20 steps: 0.95^20 = 36%. Not 95%.
- **MAST study quantified reality:** A 2025 analysis of 1,642 annotated execution traces across 7 production frameworks found failure rates of 41%–86.7% in real systems — not adversarial test conditions, not toy benchmarks.
- **68% of practitioners cap agent chains at ≤10 steps** before requiring human review, citing reliability as the reason. The industry has learned this the hard way.
- **40% of multi-agent pilots fail within six months of production deployment.** Root cause: teams pick the wrong orchestration pattern, or pick the right pattern without understanding how it breaks.
- **Token duplication kills economics:** MetaGPT wastes 72% of tokens on duplicated context, CAMEL wastes 86%, AgentVerse wastes 53% — compounding the cost of every retry.

## The Move

Design for failure containment, not failure elimination. Every architectural choice should answer: when a step fails, how far does the blast radius reach?

- **Shorten the critical path.** Every added step multiplies your failure rate. Audit whether each step earns its failure probability. Steps that don't parallelize or independently justify their existence are candidates for merging.
- **Build retry budgets into the harness, not the agent.** Agents that retry indefinitely produce longer failure modes (looping, cost spiral). Set explicit per-step retry budgets (1–3 attempts) with circuit-breaker escalation.
- **Isolate agents behind deterministic checkpoints.** Use a deterministic controller or supervisor to own canonical state. Workers fail; the controller decides whether to continue, retry, or abort. Never let a failing subagent corrupt shared state.
- **Instrument every step boundary.** Every tool call, every subagent handoff, every state mutation should emit a trace event. Full transcripts (outputs, tool calls, reasoning traces) are essential for post-mortem. You cannot fix what you cannot see.
- **Route governance-critical paths to deterministic controllers.** Policy decisions, billing operations, staged deployments — tasks where correctness outweighs creativity — belong in explicit state machines, not agent loops.
- **Use tiered model strategy to cut cost-per-retry.** A capable orchestrator with cheaper task-specific workers reduces cost per step by 40–60% vs running everything on the most capable model. When retries happen (and they will), you pay less per failure.

## Evidence

- **Research study:** The MAST study analyzed 1,642 annotated execution traces across 7 production frameworks in 2025, finding 41–86.7% failure rates in production multi-agent systems — a 2025 study cited by LayerLens. — [LayerLens: Compounding Agent Failure Math Engineers Miss](https://layerlens.ai/blog/compounding-failure-math-agents)

- **Enterprise engineering:** Microsoft ISE documented a real retail customer migrating from a modular monolith router pattern (single-agent-per-query) to a microservices coordinator pattern. The new architecture enabled agent reuse across teams, independent deployment, and parallel subagent execution — directly addressing the failure isolation problem. — [Microsoft ISE: Orchestration Patterns for Multi-Agent Systems](https://devblogs.microsoft.com/ise/coordinator-patterns-multi-agent-systems)

- **Enterprise survey:** MMC Ventures surveyed 30+ European agentic AI startup founders and interviewed 40+ enterprise practitioners in 2025. 90%+ of startups achieved ≥70% accuracy, but the primary deployment challenge cited was human and workflow integration — not model capability. — [MMC Ventures: State of Agentic AI — Founder's Edition](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)

- **Industry metric:** Gartner tracked a 1,445% surge in multi-agent system inquiries from Q1 2024 to Q2 2025. Organizations average 12 agents in production. 40% of pilots fail within six months of production deployment. — [Beam.ai: 6 Multi-Agent Orchestration Patterns That Actually Work in Production](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)

- **Production field note:** TURION.AI's field notes from 2025–2026 production deployments: "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count." Four patterns cover most use cases: hierarchical, pipeline, orchestrator-worker, and peer-to-peer. Inference costs compound to $5–8 per complex task. — [TURION.AI: Multi-Agent Orchestration Infrastructure: Lessons from Production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)

## Gotchas

- **Don't improve individual agents to solve system-level reliability.** Once errors are allowed to propagate, improving the model does very little. You need architectural containment, not better models.
- **Demo benchmarks lie about production reliability.** A benchmark where every task succeeds in one pass through the pipeline doesn't tell you what happens when a step fails mid-trajectory and the agent loops.
- **Capping step count without architectural support just hides the problem.** If you hard-cap agents at 10 steps, a 12-step workflow either fails silently or returns an incomplete result. The cap must be paired with graceful degradation — explicit abort, escalation, or checkpoint save.
- **Token duplication is a hidden cost multiplier.** Each retry re-sends the full context to every involved agent. Systems with high token duplication (CAMEL at 86%) pay dramatically more for every failure recovery.
