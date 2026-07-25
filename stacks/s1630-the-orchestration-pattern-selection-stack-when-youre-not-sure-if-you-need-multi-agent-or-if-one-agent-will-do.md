# S-1630 · The Orchestration Pattern Selection Stack — When You're Not Sure If You Need Multi-Agent or If One Agent Will Do

You're staring at a greenfield agent build. A colleague says "obviously we need multiple agents." You almost reach for LangGraph because everyone does. But Princeton NLP's benchmark data says a single agent with the right tools matches or beats multi-agent on 64% of tasks, for roughly half the cost. Meanwhile, 40% of multi-agent pilots fail within six months of production deployment. You're trying to figure out which side of that divide your problem actually lives on.

## Forces

- **The multi-agent tax.** Multi-agent systems add coordination overhead, state management complexity, and failure modes that don't exist in single-agent designs. The accuracy gain is often marginal while cost nearly doubles.
- **The premature orchestration trap.** Teams reach for multi-agent frameworks before proving the workflow needs persistent state, retry logic, or handoff between agents. The "obvious" split (researcher + writer + reviewer) looks clean in a diagram and collapses in production.
- **The pattern mismatch problem.** Four canonical patterns exist — Orchestrator-Worker, Supervisor, Pipeline, and Router — and teams routinely pick the wrong one, then build elaborate workarounds for its structural weaknesses.
- **The framework seduction.** LangGraph dominates enterprise deployments (Presenc AI, May 2026), but on HN practitioners say "there's absolute 0 framework out there that's good enough for serious work" and roll their own. The real skill is knowing which to use when.

## The Move

### 1. Check if you need multi-agent at all.

Before any pattern: ask whether your task requires genuine specialization. If one agent can hold the full context, use one agent. Add agents only when: distinct tools/skill sets are required, different models make sense for different subtasks, or task independence allows parallel execution that saves time.

Princeton NLP's benchmark finding is the empirical anchor: **single agent outperforms multi-agent on 64% of tasks.** Multi-agent adds **+2.1 percentage points of accuracy at ~2x cost** (Beam.ai, July 2026). Treat multi-agent as an optimization, not a starting point.

### 2. Choose the canonical pattern by workflow shape.

**Orchestrator-Worker** — One central agent decomposes tasks and delegates to specialists, then assembles results. Best for: cross-functional workflows with clear decomposition (e.g., customer service routing to billing/tech/legal specialists). Trade-off: orchestrator bottleneck; workers are interchangeable.

**Supervisor** — One agent makes routing decisions between workers using LLM judgment. Best for: tasks requiring dynamic evaluation of intermediate outputs (e.g., research → draft → review → revise). Trade-off: supervisor adds an LLM call before workers start, creating latency. State accumulates across turns.

**Pipeline** — Sequential stages where each agent processes and passes output to the next. Best for: linear workflows with deterministic order (e.g., ingest → extract → transform → load). Trade-off: no dynamic routing; a slow stage blocks the pipeline.

**Router** — Incoming requests get classified and dispatched to a single appropriate agent. Best for: high-volume, low-complexity request distribution. Trade-off: the router is the single point of failure; misclassification sends work to the wrong agent.

### 3. Keep state lean regardless of pattern.

LangChain's 2026 State of Agent Engineering report ties **>60% of production incidents to state management issues** (Easton, April 2026). Every node transition in a LangGraph workflow serializes the full state object. Storing raw LLM responses with metadata ballooned one team's checkpoints to **180KB per step and 400ms Postgres writes** (r/LangChain). Keep state to primitives: IDs, summaries, flags. Store full outputs externally.

### 4. Add iteration limits and budgets upfront.

Runaway agents are a documented production failure mode. Build: max step limits per task, cumulative token budgets, timeout per agent, explicit deadlock detection. One documented case hit **$180 on a single request** due to missing limits (BuildMVPFast, 2026). This is not rare.

### 5. Use the right framework for the pattern's needs.

| Framework | Strength | Weakness |
|-----------|----------|----------|
| LangGraph | Production observability, checkpointing, enterprise tooling | Verbose; easy to bloat state |
| CrewAI | Fastest demo-to-prototype | Trails on production observability and error recovery |
| AutoGen | Mature debate and verification patterns | Smaller production adoption |
| Roll your own | Full control | Re-invents checkpointing, retry logic, observability |
| Botctl / process manager | Long-lived agent services | Not an orchestration framework |

LangGraph has the largest production deployment footprint in 2026. The Presenc AI framework comparison (May 2026) notes: "for most enterprise deployments, the framework choice is less consequential than the underlying model selection, evaluation, and state management."

### 6. Instrument before you need to debug.

Multi-agent systems behave like distributed systems, not chat interfaces. GitHub's AI team (February 2026) puts it plainly: "Without explicit instructions, data formats, and interfaces, things won't go the way you planned." Every agent handoff should have a structured contract: what it receives, what it produces, what it does on failure. Tool call failures that are silently hallucinated as results are a top production failure mode.

## Evidence

- **Research benchmark:** Single agent matches or outperforms multi-agent on 64% of tasks; multi-agent adds +2.1 percentage points of accuracy at ~2x cost — [Beam.ai, July 2026](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **Enterprise deployment data:** LangGraph has the largest production footprint; CrewAI leads on prototype speed; "roll your own" still dominant at the high end — [Presenc AI CTO comparison, May 2026](https://presenc.ai/research/multi-agent-orchestration-frameworks-2026)
- **Practitioner HN thread:** "There's absolute 0 framework out there that's good enough for serious work" — production teams using shared MongoDB, Redis scratchpads, and SQLite-structured JSON for agent-to-agent data passing — [Hacker News Ask HN #47660705](https://news.ycombinator.com/item?id=47660705)
- **State failure data:** >60% of LangChain production incidents tied to state management; checkpoint bloat at 180KB/step documented on r/LangChain — [Easton blog, April 2026](https://eastondev.com/blog/en/posts/ai/20260424-langgraph-agent-architecture)
- **Failure rate:** 40% of multi-agent pilots fail within six months of production deployment; 40% of enterprise apps will embed agents by end of 2026 (Gartner 1,445% inquiry surge) — [Beam.ai, July 2026](https://beam.ai/agentic-insights/multi-agent-orchestration-patterns-production)
- **Distributed systems analogy:** Multi-agent failures (agent closes what another opened, change ships that fails a downstream check) stem from missing structure, not model capability — [GitHub Blog, February 2026](https://github.blog/ai-and-ml/generative-ai/multi-agent-workflows-often-fail-heres-how-to-engineer-ones-that-dont/)

## Gotchas

- **The "supervisor makes an LLM call before workers start" trap.** Every routing decision costs latency and tokens. Optimize conditional edges that skip the supervisor for deterministic cases.
- **Skipping the framework skepticism question.** Ask: should this workflow use a framework at all? A narrow workflow with one or two tools often does better with direct code and explicit tests than with a full agent stack. HN practitioners warn against adding orchestration layers before proving the workflow needs them.
- **No iteration limits until production shows runaway costs.** Then it's too late. Build step limits, token budgets, and explicit deadlock detection from day one.
- **Treating state as infinite.** Every serialized LLM response in checkpoint state is a silent cost multiplier. Store summaries, not raw outputs.
