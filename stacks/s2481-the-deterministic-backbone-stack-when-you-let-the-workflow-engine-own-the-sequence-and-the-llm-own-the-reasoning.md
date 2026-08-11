# S-2481 · The Deterministic Backbone Stack — When You Let the Workflow Engine Own the Sequence and the LLM Own the Reasoning

Your multi-agent demo impresses everyone. Six agents, parallel execution, elegant handoffs. Then the first ambiguous input hits in production and agents deadlock, duplicate work, or silently drop context on floor. You blame the model. The real problem is architectural: you gave the LLM control of both sequencing and reasoning, and it was built for only one of those things. The fix is not better prompts — it is a structural separation of concerns where a deterministic engine owns what runs when, and agents own what happens inside each step.

## Forces

- **LLMs are good at reasoning within a step, unreliable at sequencing across steps.** A language model can decide what to do next given context. It cannot reliably track retries, manage timeouts, recover from partial failures, or guarantee that two parallel agents don't overwrite each other's output. Those are state machine problems.
- **The framework you choose encodes your autonomy budget.** Sequential pipelines (CrewAI) assume minimal autonomy — agents do their step and hand off. Graph-based systems (LangGraph) let you branch conditionally but still express the graph explicitly. Event-driven and actor-model approaches push more autonomy to agents at the cost of harder debugging.
- **37% of multi-agent failures trace to inter-agent coordination, not individual agent quality** — meaning even perfect agents fail if the glue is weak.
- **The biggest mistake teams make:** Using a flexible, agentic system (LangGraph with dynamic edges, or raw AutoGen) when a deterministic chain would have worked fine. Complexity compounds failure modes.

## The Move

The structural move is separating sequence ownership from reasoning ownership. A deterministic workflow engine — Temporal, Conductor, LangGraph's state machine, or even a well-scoped DAG — owns: ordering, retries, timeouts, failure recovery, and replay. LLM agents own: what to do inside each step, which tool to call, when to ask for clarification, and whether output is good enough to proceed.

### The four production-grade patterns in play

**Pipeline (Sequential):** Agents in fixed order. Each output feeds the next. Best for processes with a natural sequence and a clear final step — extract, validate, enrich, draft, send. No branching, no parallelism. CrewAI calls this "sequential process." LangGraph implements it as a linear StateGraph. Use when the steps are known ahead of time and the LLM's job is transformation, not navigation.

**Fan-Out / Fan-In (Map-Reduce):** One planner dispatches N independent tasks to N agents in parallel, then a reducer aggregates results. Best for batch operations — enrich 1,000 leads, review 50 documents, summarize 20 pages. The key design decision is granularity: too-coarse fan-out creates a bottleneck at the reducer; too-fine fan-out creates coordination overhead that eats the parallelism gain. The Conductor reference architecture models this with FORK/JOIN primitives.

**Supervisor / Worker:** A supervisor agent routes tasks to specialized workers and manages their lifecycle. The supervisor owns sequencing (which worker gets which task, when to escalate); workers own execution (do the thing, report back). This is the pattern behind CrewAI's hierarchical process and the dominant pattern for complex, open-ended tasks like research pipelines where the supervisor decides what to explore next. Gotcha: if the supervisor LLM is weak, it becomes a bottleneck; treat supervisor model selection as a first-class infrastructure decision.

**Critic / Refiner (Self-Correction Loop):** An executor produces output, a critic evaluates it against explicit criteria, and the loop runs until criteria pass or a max-iteration cap is hit. This is the pattern behind systems like Hephaestus that use trajectory analysis to detect when agents drift from goals. The critical implementation detail: the criteria must be machine-checkable. "Is this response good?" is not a criterion. "Does the response contain a code snippet AND a test AND fits under 500 tokens?" is.

### The Output.ai insight — filesystem-first, Temporal underneath

The GrowthX team extracted their Output.ai framework from 500+ production agents and made a revealing observation: the friction was not prompting, it was workflow reliability. They built Output as a TypeScript framework on Temporal's durable execution model — meaning every workflow step can fail, crash, or timeout and Temporal will replay it from exactly where it left off, with full state preserved. The LLM step is an opaque box inside a durable, retryable envelope.

### The Conductor reference architecture — mapping agent concerns to primitives

Conductor's production agent reference maps each agent concern to a specific execution primitive: LLM_CHAT_COMPLETE for planning, DYNAMIC task for runtime tool selection, CALL_MCP_TOOL/HTTP/SIMPLE for execution with retry policies, FORK/JOIN for parallelism, HUMAN_APPROVAL for human-in-the-loop gates, and WAIT for long-running steps. The pattern is explicit: no concern is handled by "the LLM figures it out" — every concern maps to an infrastructure primitive with defined behavior.

## Evidence

- **HN Show HN (81 points):** Hephaestus — autonomous multi-agent orchestration framework with semi-structured approach: define phase types (analysis, building, validation) and let agents spawn tasks across phases dynamically. Trajectory analysis runs LLM-powered coherence scoring on accumulated work. — [Hephaestus GitHub / HN](https://news.ycombinator.com/item?id=45796897)
- **GitHub / Framework README:** Output.ai — open-source TypeScript framework extracted from 500+ production agents by GrowthX team. Built on Temporal's durable execution model. Stars 431 (Apache-2.0). Core insight: "One framework. Prompts, evals, tracing, cost tracking, orchestration, credentials. No SaaS fragmentation." — [growthxai/output](https://github.com/growthxai/output)
- **Blog post / Primary research:** 37% of multi-agent failures trace to inter-agent coordination, not individual agent quality. Deterministic backbone + agentic steps pattern validated across pipeline, fan-out, supervisor-worker, and critic-loop implementations. — [Swarmsignal.net](https://swarmsignal.net/ai-agent-orchestration-patterns/), [Lowco.ai](https://lowco.ai/blog/ai-agent-orchestration-patterns)
- **GitHub / Reference architecture:** Conductor production agent architecture maps every agent concern (planning, tool selection, execution, retry, memory, human approval, long waits, reflection) to a specific Conductor primitive with defined retry logic and state management. — [conductor-oss/conductor](https://github.com/conductor-oss/conductor/blob/main/docs/devguide/ai/production-agent-architecture.md)
- **Framework comparison:** LangGraph (graph-based state machine for complex branching), CrewAI (role-based for rapid prototyping), AutoGen (conversation-driven). LangChain CEO Harrison Chase: "Start with the simplest orchestration that could work. Most teams over-engineer with agents when a chain would do." — [LangChain Blog](https://blog.langchain.com/on-agent-frameworks-and-agent-observability/), [YoungJu.dev comparison](https://www.youngju.dev/blog/llm/2026-03-09-llm-agent-framework-autogen-crewai-langgraph-comparison.en)

## Gotchas

- **"We'll add the workflow engine later" is a trap.** Without durable execution primitives, every agent failure requires either manual intervention or a retry that doesn't know where to resume. Add Temporal, Conductor, or LangGraph's checkpointing from the start — retrofitting is painful.
- **Supervisor becomes a bottleneck.** When one LLM routes all work, its latency and quality become the system ceiling. Profile supervisor round-trips in production before assuming parallelism is helping.
- **Fan-out granularity matters more than you think.** The reducer aggregating 50 parallel agent outputs is itself a fragile step if it wasn't designed for that input volume. Test at 3x expected scale.
- **Critic loops need explicit exit criteria.** Without a hard iteration cap or explicit pass/fail threshold, self-correction loops can oscillate between similar wrong answers indefinitely. Set a max-iterations budget and a machine-checkable minimum quality bar before the loop starts.
