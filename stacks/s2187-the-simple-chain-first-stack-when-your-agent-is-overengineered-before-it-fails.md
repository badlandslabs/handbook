# S-2187 · The Simple-Chain-First Stack — When Your Agent Is Overengineered Before It Fails

When you reach for a full autonomous agent with tool loops and multi-agent orchestration — but a pipeline of three constrained LLM calls would do the job faster, cheaper, and more reliably.

## Forces

- **The framework draw** — CrewAI, LangGraph, AutoGen, and every vendor pitch agents as the default solution. The tutorials are all multi-agent. Starting simple feels like you're missing out.
- **The autonomy temptation** — giving the LLM full control feels more "AI-native," but every degree of freedom is a new failure mode in production.
- **The cost curve** — a single autonomous agent loop with 20 tool calls costs 10–40× more than a five-step prompt chain with the same output quality. The gap only widens with retry budgets.
- **The debugging cliff** — tracing a multi-agent system where three agents are arguing over schema is fundamentally harder than reading a sequential pipeline log. The difference shows up at 2 AM.
- **Production data says so** — 73% of production LLM systems use chains; only 12% use full agents. The majority of teams don't need the complexity they're adopting.

## The Move

The core principle from Anthropic's systematic work with dozens of production teams: **find the simplest orchestration pattern first, and only add complexity when empirical evidence demands it.** The four patterns in increasing order of complexity:

- **Augmented LLM** (baseline) — give the model tools, memory, and context. Most tasks stop here.
- **Prompt chaining** — sequential LLM calls where each output feeds the next. Linear, predictable, debuggable. For 80% of enterprise workflows.
- **Parallelization** — split a task into independent sub-tasks, run them simultaneously, merge results. Reduces latency, not complexity.
- **Orchestrator-workers** — a central LLM decomposes a task, assigns sub-tasks to specialized workers, synthesizes results. Use when task shapes vary.
- **Evaluator-optimizer** — a loop where one LLM generates, another critiques, and the first revises until quality thresholds are met.
- **Agents** — give an LLM tools and let it loop until it decides it's done. Reserve for genuinely open-ended tasks where you cannot enumerate steps.

**Practical decision tree:**

```
Can you write down the exact steps?
  → YES → prompt chain (or even a single well-crafted call)
  → NO  → is the task exploratory with one clear output?
           → YES → single agent with bounded max_iter
           → NO  → orchestrator-workers or evaluator-optimizer
```

**Framework choice follows architecture, not the other way around.** CrewAI's role-based crews excel at parallel task delegation with shared memory; LangGraph's directed graphs give explicit state management and checkpointing for long-running workflows; AutoGen shines for multi-turn code generation pipelines. None of them are the default answer — the chain is.

## Evidence

- **Anthropic engineering post (Dec 2024):** After working with dozens of production teams, the most successful implementations used "simple, composable patterns rather than complex frameworks." Introduced the canonical augmentation → workflow → agent hierarchy. — [anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents) — discussed on HN (763 pts, Dec 2024; 543 pts, June 2025)

- **Agentika production survey (Feb 2026):** 73% of production LLM systems use chains; only 12% use full agents. Harrison Chase (LangChain CEO): "Start with the simplest orchestration that could work. Most teams over-engineer with agents when a chain would do." — [agentika.uk/blog/llm-orchestration-patterns](https://agentika.uk/blog/llm-orchestration-patterns)

- **CrewAI production deployment lessons (Jun 2026):** Teams discover that tutorials work for single agents; composition breaks in production. Key findings: `max_iter` defaults to 25 (set to 5–8 per agent or one bad run burns 5–10× token budget); sequential pipelines beat hierarchical ones for reliability; structured output (`output_pydantic`) prevents fragile string parsing; a 3-agent pipeline at 100 runs/day costs ~$900/month — halving that with model tiering per agent. — [agilesoftlabs.com/blog/2026/06/crewai-in-production-2026-real-lessons](https://www.agilesoftlabs.com/blog/2026/06/crewai-in-production-2026-real-lessons)

- **LangChain State of AI Agents report (Jun 2026):** 57% of surveyed organizations have agents in production (up from 51% prior year). 89% have implemented observability; 52% use evals. Multi-model usage is the norm. — [langchain.com/state-of-agent-engineering](https://www.langchain.com/state-of-agent-engineering)

## Gotchas

- **Over-engineering on day one** — the most common mistake. Ship the chain, measure where it fails, then graduate to agents only for the specific failure mode. Not the other way around.
- **Blowing past token budgets with unbounded agent loops** — `max_iter` is not a formality. Set it per-agent, not globally, and track cost per task. A single 20-step agent run with a frontier model can cost more than a week's worth of equivalent chain calls.
- **Choosing a framework before understanding your orchestration pattern** — the framework follows the architecture decision. If you don't know whether you need sequential steps or parallel workers, picking LangGraph vs. CrewAI is guessing. Solve the pattern first.
- **Fragile output parsing** — when chain steps pass data through unstructured strings, a single format drift breaks the entire pipeline. Use structured output (Pydantic, JSON mode, or OpenAI's `response_format`) from step one, not as a later patch.
- **The observability gap** — multi-agent systems need trace-level instrumentation (LangSmith, AgentOps, OpenTelemetry). A pipeline that "seems to work" in dev will become undebuggable in production without it.
