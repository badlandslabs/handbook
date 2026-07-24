# S-1576 · The Orchestration Taxonomy Stack — When Your Agents Know Too Much About Each Other

Multi-agent systems promise to divide complex work across specialized agents that coordinate to solve problems. In 2023, demos looked great. In 2024, production deployments mostly looked cursed. In 2025–2026, a handful of patterns emerged that actually work — and a lot of patterns that don't. The failure isn't usually in the agents themselves; it's in how you wired them together.

## Forces

- **The over-architecting trap** — Teams spend months debugging agent coordination before they've proven the underlying workflow works. The most common mistake is adding multi-agent complexity on day one instead of building a single-agent system first and identifying actual bottlenecks.
- **The topology choice is load-bearing** — A supervisor pattern behaves nothing like a fan-out, yet teams pick patterns by familiarity rather than by task shape. Each topology has specific failure modes that don't show up until production.
- **Control flow is the hard part** — Individual agents are generally capable. Across 200+ production traces analyzed by Berkeley researchers, most failures originated in orchestration design: task routing, state passing, and error propagation between agents — not in agent reasoning.
- **The 40% pilot failure rate** — 40% of multi-agent pilots fail within six months of production deployment, not because multi-agent systems don't work, but because teams pick the wrong orchestration pattern or pick the right one without understanding how it breaks.

## The Move

Choose your orchestration topology based on task shape, not framework familiarity. Six patterns cover the majority of production cases; most systems combine two or three within a single workflow.

**1. Supervisor (Orchestrator-Worker)**
- One central agent receives the task, decomposes it into subtasks, routes to specialist workers, and assembles the final result.
- Workers use cheaper, task-specific models; the supervisor uses a capable model.
- Cut costs 40–60% by routing to cheaper models for specialists (Beam.ai, 2026).
- Best for: heterogeneous, cross-functional workflows with clear task decomposition. Scales to 3–8 agents.

**2. Sequential Pipeline**
- Fixed sequence: researcher → analyst → writer → reviewer. Each stage's output is the next stage's input.
- Each stage emits a clean, scoped output — not the accumulated context plus the new output.
- The anti-pattern: stages that pass through all accumulated context instead of their specific output. This bloats context windows and degrades downstream agent performance (Thinking.inc, 2026).
- Best for: deterministic workflows where order matters and each stage is a defined transformation.

**3. Parallel Fan-Out / Fan-In**
- One task gets dispatched across N parallel workers, results are aggregated.
- Critical: every stage must validate its inputs. When one worker produces malformed output, downstream aggregation produces plausible-looking garbage.
- Best for: independent sub-tasks that can be executed concurrently — processing multiple documents, running the same analysis on different data sources.

**4. Router**
- A central agent classifies incoming requests and routes them to the appropriate agent or pipeline.
- No execution happens at the router — routing only.
- Best for: high-volume, diverse request types where you need to pick the right specialist without running all of them.

**5. Hierarchical Delegation**
- Multi-level management tree: a top-level manager delegates to team leads who manage specialist agents.
- Scales to 10–50+ agents where a single supervisor would become a bottleneck.
- Best for: enterprise-scale systems with complex organizational structures.

**6. Evaluator-Optimizer Loop**
- An agent produces output; a separate evaluator agent critiques it; the optimizer revises.
- Repeat until the evaluator approves or a loop limit is hit.
- Best for: creative or analytical tasks where quality matters more than single-pass speed.

## Evidence

- **Blog post (TURION.AI, March 2026):** "Multi-agent systems are harder to operate than single agents by roughly the order of their agent count. In 2023, demos looked great. In 2024, production deployments mostly looked cursed. In 2025–2026, a handful of patterns emerged that actually work." — [turion.ai/blog/multi-agent-orchestration-infrastructure-production](https://turion.ai/blog/multi-agent-orchestration-infrastructure-production)

- **Research paper (Cemri et al., UC Berkeley, arXiv:2503.13657, 2025):** MAST taxonomy analyzing 7 MAS frameworks across 200+ production traces. Found that 14 distinct failure modes cluster into 3 categories: system design issues, inter-agent misalignment, and task verification. "ChatDev achieves only 33.33% correctness on ProgramDev" — performance gains from multi-agent systems often remain minimal compared to single-agent frameworks. — [arxiv.org/abs/2503.13657](https://arxiv.org/abs/2503.13657)

- **Industry report (Beam.ai / Gartner, July 2026):** Gartner reported a 1,445% surge in multi-agent system inquiries between Q1 2024 and Q2 2025. Organizations use an average of 12 agents, projected to climb 67% within two years. 40% of multi-agent pilots fail within six months of production deployment. — [beam.ai/agentic-insights/multi-agent-orchestration-patterns-production](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)

- **Consulting analysis (Thinking.inc, 2026):** "The orchestration layer is where most enterprise agent projects succeed or fail. Across the deployments we have observed, a large share of failures originate in orchestration design rather than individual agent capability — agents are individually capable but poorly coordinated." — [thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns](https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns/)

- **Field report (Data-Gate, 2026):** "The most common mistake is over-engineering from day one. Teams spend months debugging agent coordination instead of solving user problems." — [data-gate.ch/multi-agent-systems-production-lessons](https://data-gate.ch/multi-agent-systems-production-lessons)

- **Startup research (MMC Ventures, November 2025):** Surveyed 30+ European agentic AI startup founders and 40+ enterprise practitioners. Key finding: the biggest challenges are workflow integration, employee resistance, and human-agent interface design — not technical capability. — [mmc.vc/research/state-of-agentic-ai-founders-edition](https://mmc.vc/research/state-of-agentic-ai-founders-edition/)

## Gotchas

- **Adding agents doesn't fix broken workflows.** If a single-agent system can't do the task, adding a second agent and hoping they'll collaborate won't help. Decompose the task first, then add agents only where specialization genuinely helps.
- **The supervisor becomes a bottleneck at 8+ agents.** Beyond that, switch to hierarchical delegation or the system starts failing in new ways (context overload on the supervisor, cascading delays).
- **Fan-out without timeout limits burns budget fast.** Each parallel worker runs independently, so a hung worker wastes an entire slot. Set per-worker timeouts and aggregate partial results.
- **Every inter-agent handoff is a failure surface.** Context loss (agent doesn't know what another did and re-does the work) and error cascade (upstream error propagates and amplifies downstream) are the two most common failure modes from the MAST taxonomy. Design explicit state-passing contracts between agents.
- **Hybrid patterns outperform pure patterns in production.** Most real systems use 2–3 orchestration patterns in sequence — a router picks the pipeline, a sequential pipeline executes, an evaluator loop refines the output.
