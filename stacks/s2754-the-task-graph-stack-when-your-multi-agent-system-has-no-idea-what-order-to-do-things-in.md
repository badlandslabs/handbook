# S-2754 · The Task-Graph Stack — When Your Multi-Agent System Has No Idea What Order To Do Things In

When two agents argue over who goes first. When outputs get lost between pipeline stages. When your "multi-agent" system is really just one agent doing everything serially with extra steps.

## Forces

- **Orchestration overhead vs. parallelization gains.** Multi-agent systems add 2x cost on average (Princeton benchmark) but only 2.1 percentage points of accuracy — you must be deliberate about where the parallelism actually earns its keep.
- **The who-decides problem.** Agents that can spawn their own subtasks are hard to debug and hard to predict; agents that only handle leaf nodes are predictable but need a smarter coordinator above them.
- **Data handoffs are the failure point.** Inter-agent communication — passing context, outputs, and state between agents — is where details get dropped, not inside any individual agent.
- **40% of multi-agent pilots fail within six months** (Gartner) not because individual agents break, but because the coordination layer between them does.

## The move

Structure the task graph before runtime, and keep agents at the leaf nodes.

**Define the graph yourself; agents own the leaves.**
> *"Don't let agents pick their own subtasks. Define the task graph yourself: agents only handle the leaf nodes."* — HN practitioner `Chepko932`

**Pick the orchestration pattern that fits the branching structure of your work:**

1. **Orchestrator-Worker** — One central agent decomposes a task and dispatches to specialized workers, then synthesizes results. Best for tasks with variable subtask structure (e.g., research with unknown scope). Single point of failure but simple to reason about.

2. **Supervisor-Worker** — A supervisor agent routes to domain-specific workers without doing the work itself. Workers return outputs; supervisor decides next step. Good for routing-heavy tasks (triage, classification pipelines).

3. **Plurality / Network** — All agents are peers; each can call any other. Maximum flexibility, maximum chaos. Best for research or ideation where you want emergent synthesis.

4. **Supervisor-Plus** — Supervisor + a separate feedback/verifier agent that checks worker outputs before synthesis. The verifier is the quality gate — add it when errors are costly.

5. **Planner → Executor → Verifier** — Three distinct phases. Planner decomposes goals into steps. Executor runs them. Verifier checks outputs against requirements before the next step. Most robust for compliance or accuracy-sensitive pipelines.

6. **Hierarchical** — Two-plus tiers of supervisors. Senior supervisor owns the top-level goal; junior supervisors own sub-domains. Scales to large, complex workflows.

**Pass data explicitly, not via context inference.**
- MongoDB shared-state documents with pipeline-ID linking (HN `pablovarela`: each agent reads/writes its own state document; simple and debuggable)
- SQLite-structured JSON per task output, read by a central coordinator (HN `Chepko932`)
- Avoid implicit context-passing where Agent B has to infer what Agent A produced — the inference fails more than you'd expect

**Keep shared state schema-stable.** Document what each agent writes at each stage. Schema drift between agents is the silent corrupter.

## Evidence

- **Ask HN thread:** Practitioners report rolling their own orchestrators because "there's absolute 0 framework out there that's good enough for serious work" (`segmondy`). Those using frameworks (LangGraph, Agno) build custom coordinator layers on top. Data passing via MongoDB JSON docs or SQLite-structured outputs was the most common production pattern. — [HN Ask: How are you orchestrating multi-agent AI workflows in production?](https://news.ycombinator.com/item?id=47660705)
- **Production GitHub repo:** A Planner → Executor → Verifier pipeline with shared memory, automatic retry, and evaluation metrics, built with Google Gemini. The README explicitly calls out shared memory between stages as the state mechanism and retry logic as a first-class concern. — [bhavani-gbs/Multi-Agent-LLM-System](https://github.com/bhavani-gbs/Multi-Agent-LLM-System)
- **YC QM harness:** Y Combinator open-sourced its internal multi-agent harness (QM, MIT license, July 2026) after running it across accounting, legal, events, and engineering — including building QM itself. Key design: triggers (crons, webhooks), shared context, per-employee agent provisioning. — [QM — Open-Source Agent Harness from YC](https://qm.ycombinator.com/)

## Gotchas

- **Adding agents doesn't automatically add parallelism.** If your agents all run sequentially, you've added overhead without latency reduction. Profile whether agents actually run in parallel in your graph.
- **The synthesizer is the hardest agent to get right.** Combining outputs from multiple specialized agents into a coherent result requires more context and instruction than any single agent needs. Budget development time for it.
- **Roll-your-own vs. framework trade-offs.** Frameworks (LangGraph, Agno, AutoGen, CrewAI) accelerate initial development but add abstraction cost when debugging or customizing. HN consensus: most serious production systems eventually add custom coordinator logic regardless of framework choice.
- **The 40% pilot failure rate is mostly a coordination failure**, not an agent quality failure. Invest in your orchestration layer proportionally to the number of agents you're running.
