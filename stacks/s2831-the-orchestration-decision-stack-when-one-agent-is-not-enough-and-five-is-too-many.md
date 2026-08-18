# S-2831 · The Orchestration Decision Stack — When One Agent Is Not Enough and Five Is Too Many

When your single-agent system starts failing on complex tasks, and someone suggests "just add more agents" — this is where you need a framework for making that call.

## Forces

- **The tool-count cliff:** Up to 20 tools is manageable; 20–50 blurs boundaries; 50+ creates a combinatorial explosion the LLM cannot reliably navigate.
- **Framework vs. custom overhead:** Full frameworks (LangChain, CrewAI) add abstractions that help early but become constraints at scale; many teams roll lightweight orchestration instead.
- **Latency vs. capability:** Every hop to a sub-agent costs 200–500ms+; parallelizing agents helps but adds coordination cost.
- **The 40% pilot failure rate:** Gartner tracked 1,445% growth in multi-agent inquiries (Q1 2024 → Q2 2025), but 40% of pilots fail within six months — usually from over-engineering the architecture before understanding actual task requirements.
- **Cost scaling:** Multi-agent setups typically cost ~2x a single-agent approach for only ~2.1 percentage points of accuracy gain (production benchmarks).

## The Move

Start at the lowest complexity level that reliably meets requirements. Add agents only when a specific failure mode demands it. Every level adds coordination overhead, latency, and cost.

### The 5-level complexity spectrum (Microsoft Azure Architecture Center)

| Level | Pattern | When to use |
|-------|---------|-------------|
| 1 | **Direct model call** | Single-step: classification, summarization, translation |
| 2 | **Single agent + tools** | Multi-step with tools, no sub-agent needed |
| 3 | **Multi-agent coordination** | 2–5 agents sharing state for a single goal |
| 4 | **Hierarchical agents** | Supervisor decomposes tasks, dispatches to specialists |
| 5 | **Open-ended ecosystem** | Multiple independent agent teams, cross-organization |

### Choose your level by failure mode

- **Single agent fails because tools are too many?** → Move tools to a menu shown contextually (JIT), don't add agents.
- **Single agent fails because it lacks domain expertise?** → Add one specialist sub-agent, not three.
- **Specialist agents need to share state?** → Use Orchestrator-Worker pattern (one supervisor, stateless workers).
- **Tasks are independent and parallelizable?** → Fan-out/Fan-in: split → process in parallel → aggregate.
- **Tasks have sequential dependencies?** → Pipeline pattern with explicit output passing between agents.
- **Different agents need different trust/permission levels?** → Hierarchical pattern with security boundaries at each level.

### The tool-count scaling playbook (Shopify Sidekick)

- **0–20 tools:** Clear boundaries, easy to debug, straightforward.
- **20–50 tools:** Boundaries blur, tool combinations cause unexpected outcomes. Introduce JIT tool instructions (deliver tool descriptions and usage context at call time, not in the system prompt).
- **50+ tools:** Multiple ways to accomplish the same task. Split into agent teams with domain-scoped tool access, not one god-agent with all tools.

### The LLM-first inversion (Gambit agent harness)

Traditional orchestration: `compute → compute → compute → LLM → compute → compute → LLM`

Agent harness: `LLM → LLM → LLM → compute → LLM → LLM → compute → LLM`

Let the LLM drive decisions and sequence compute as supporting tasks — not the reverse. This shifts from a pipeline mindset to an agent mindset.

## Evidence

- **Engineering blog:** Shopify Sidekick scaled from simple tool-calling to 50+ tools using JIT instructions — delivered alongside tool data instead of bloating the system prompt. Authored by Andrew McNamara, Ben Lafferty, Michael Garner (ICML 2025 talk). — [https://shopify.engineering/building-production-ready-agentic-systems](https://shopify.engineering/building-production-ready-agentic-systems)
- **Architecture guide:** Microsoft Azure's 5-level complexity spectrum for agentic systems, with specific guidance on when to escalate to multi-agent patterns. — [https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)
- **Community discussion:** Hacker News "Ask HN: How are you orchestrating multi-agent AI workflows in production?" — practitioners report rolling lightweight custom orchestration, treating conversation threads as stateful units, and using simple Postgres + JSON for cross-agent data passing. — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **Open-source harness:** Gambit (Bolt Foundry) — explicit paradigm shift from orchestration pipelines to agent harnesses where the LLM drives sequencing. — [https://github.com/bolt-foundry/gambit](https://github.com/bolt-foundry/gambit)
- **Production benchmarks:** Beam.ai analysis of 6 multi-agent patterns — Orchestrator-Worker reduces costs 40–60% by routing to task-specific cheaper models; 64% of benchmarked tasks show no improvement from multi-agent over single-agent. — [https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)

## Gotchas

- **Don't add agents to solve a tool problem.** If your single agent fails because it has too many tools, the fix is better tool design (JIT delivery, semantic grouping), not more agents.
- **Multi-agent has a floor on cost reduction.** Even the most efficient orchestrator pattern adds ~2x cost over a single-agent approach. Make sure the accuracy or capability gain justifies it.
- **State across sessions is unsolved for most teams.** Practitioners on HN report handling "human replies days apart" as the hardest state problem — simple vector DB + conversation thread replay is the common approach, not a framework solution.
- **Framework lock-in is real.** Teams that adopted CrewAI or LangChain early are now rebuilding their orchestration logic as those frameworks hit architectural walls at 50+ tools. Evaluate framework fitness at your target scale, not at prototype scale.
