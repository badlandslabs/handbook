# S-897 · The Multi-Agent Default — When Your Second Agent Costs Double and Helps Little

Your team shipped an agent. It works. Someone proposes adding a research agent, a reviewer, an orchestrator. The demo is impressive. You build it. Six weeks later, the system is slower, more expensive, harder to debug, and the accuracy improvement is within noise. You added agents before proving one was insufficient. This is the multi-agent default: the reflexive reach for distributed agentic architecture when a well-designed single agent handles the problem just fine.

## Forces

- **Multi-agent hype drowns empirical evidence.** Gartner reported 1,445% growth in multi-agent inquiries (Q1 2024 → Q2 2025). Frameworks make multi-agent demos trivially easy to build. The baseline assumption has shifted from "prove you need multiple agents" to "multi-agent is the default."
- **The coordination tax is architectural, not incidental.** Every additional agent adds inter-agent communication, shared state management, and failure propagation. A single bad decision from one agent cascades through the system. Teams underestimate this because demos run clean — production runs messy.
- **Princeton NLP found single agents match multi-agent on 64% of tasks.** When given equivalent tools and context, a single capable agent matches or outperforms multi-agent systems on nearly two-thirds of benchmarked tasks. Multi-agent adds ~2.1 percentage points of accuracy at roughly double the cost. The gain does not justify the complexity for most tasks.
- **The MAST study found 41%–86.7% failure rates across 7 SOTA open-source MAS frameworks.** UC Berkeley (NeurIPS 2025) analyzed 1,642 execution traces across AutoGPT, BabyAGI, CrewAI, LangGraph, MetaGPT, CAMEL, and ChatDev. Every framework studied failed at high rates. The failure modes cluster around specification, execution, and coordination failures — not model capability.
- **Adding an agent is easy. Removing one is hard.** Once a multi-agent system is in production, each agent accumulates dependencies, consumers, and oversight requirements. The decision to add agents is reversible only with significant engineering cost.

## The move

**Require a burden of proof before multi-agent. Treat distributed agentic architecture as an optimization, not a starting point.**

- **Exhaust single-agent first.** Before adding a second agent, push the single agent harder: increase tool count, expand context, add reflection loops. Measure where it actually breaks down — not where you imagine it will.
- **Define the specific failure that requires distribution.** Multi-agent earns its cost when tasks genuinely need parallel execution, fundamentally different capability profiles, or strict separation of concerns that a single agent's context cannot maintain. If you cannot name the specific failure a second agent solves, you do not need one.
- **Separate orchestration from capability.** The orchestrator-worker pattern is legitimate, but only when work decomposition is clean and workers are cheap and stateless. If your "workers" need significant shared context, the orchestrator becomes a bottleneck, not a coordinator.
- **Budget the coordination cost explicitly.** Model the expected token count for inter-agent messages, the number of LLM calls per task, and the failure propagation paths. If the budget does not pencil out against a single-agent approach, single-agent wins.
- **Design for agent reduction, not just addition.** Build with explicit boundaries between agents so you can collapse them into a single agent when evidence shows it is sufficient. Monolithic agents that proved themselves are more valuable than distributed ones that "mostly work."

## Evidence

- **Research paper:** "Single-agent matched or outperformed multi-agent on 64% of benchmarked tasks when given the same tools and context, with multi-agent adding only ~2.1 percentage points of accuracy at roughly double the cost." — cited across Princeton NLP research, referenced in Apptitude analysis, 2026 — https://apptitude.io/blog/single-agent-vs-multi-agent-ai-decision-framework/
- **Research paper:** "41%–86.7% failure rates across 7 SOTA open-source MAS frameworks" from analysis of 1,642 annotated execution traces. MAST taxonomy identifies 14 distinct failure modes — UC Berkeley / NeurIPS 2025 — https://arxiv.org/html/2503.13657
- **Industry analysis:** "40% of multi-agent pilots fail within six months of production deployment — not because multi-agent systems don't work, but because teams pick the wrong orchestration pattern or pick the right one without understanding how it breaks." — Beam.ai Agentic Insights, July 2026 — https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production
- **Industry analysis:** "Teams pick the wrong orchestration pattern for their problem, or pick the right one without understanding how it breaks." Same finding — multi-agent failure is an architectural decision failure, not a technology failure. — Beam.ai, 2026

## Gotchas

- **The demo runs clean; production does not.** Multi-agent demos benefit from short task lengths, cooperative agents, and manual intervention on failures. Production introduces retries, cascading errors, and cost accumulation. The demo does not reveal the coordination tax.
- **"We can always collapse it later" is a lie.** Agent roles become entrenched. Downstream systems start routing based on agent identity. The coordination overhead of multi-agent creates implicit coupling that is hard to undo without a full rewrite.
- **More agents amplify errors, not just capabilities.** Google DeepMind research (2025) found multi-agent networks can amplify errors by up to 17x compared to a single agent. The amplification is non-linear — a 5% error rate per agent does not produce a 5% system error rate. It produces cascading, correlated failures.
