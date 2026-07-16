# S-1195 · The Orchestration Spectrum Stack — When You're Not Sure If You Need a Chain, a Router, or a Loop

Every AI project starts with a prompt. The next decision — how to chain, route, and loop that prompt across multiple LLM calls — is where teams lose weeks of iteration. The choice isn't chains versus agents. It's how much autonomy the LLM needs per task, and picking a point on the orchestration spectrum that matches that need.

## Forces

- **Over-engineering is the default failure.** LangChain's 2025 production survey found simple chains handle ~80% of real production use cases, yet teams consistently reach for agent loops on first build.
- **Cost scales super-linearly with autonomy.** Agent-based systems cost 3–5× more in token usage than equivalent chains — every loop is another model call, another context pass.
- **Latency compounds in sequential chains.** Each step adds wall-clock time; parallelism helps but introduces fan-in aggregation complexity.
- **Framework ceilings are real.** 65% of teams hit an architectural wall within 12 months when they pick the wrong orchestration framework and face a painful rewrite.
- **Four canonical patterns cover ~90% of production cases.** Sequential chains, router/dispatch, parallel fan-out/fan-in, and hierarchical supervisor — knowing which one you need is the highest-leverage architecture decision.

## The Move

Start at the simplest pattern that could work. Move up the chain only when evidence forces it.

### The six-level orchestration spectrum

**Level 1 — Simple Chain**
Model A output feeds Model B input. No branching, no loops. Best for: summarize → classify → route, extract → validate → store.
- Deterministic, easy to debug, full audit trail per step
- Latency compounds; no parallelism; error in step 1 cascades

**Level 2 — Router / Classifier Dispatch**
A lightweight model classifies the input and routes it to a specialized handler. The router itself is a simple LLM call — fast, cheap.
- Enables ~30–45% better task completion vs. fixed pipeline routing
- Avoids over-processing simple queries; deep-paths complex ones
- Router accuracy is a hidden dependency — bad routing poisons everything downstream

**Level 3 — Parallel Fan-Out / Fan-In**
Break a task into independent subtasks, process them concurrently, aggregate results. Used for document segmentation (split → process sections → reassemble), multi-source research, parallel API calls.
- Fan-out delegates to parallel units: functions, containers, or agents on Step Functions, Kubernetes, Ray, or LangGraph
- Fan-in aggregates, de-duplicates, validates, or re-ranks outputs
- Natural fit for DAG-based workflows; deadlocks possible if aggregation has hidden dependencies

**Level 4 — Sequential Multi-Agent (Supervisor Pattern)**
A supervisor agent decomposes a task and delegates sub-tasks to specialized agents. Microsoft ISE documented this pattern for a leading e-commerce voice assistant handling order tracking, returns, product recommendations, and FAQs in any order.
- Supervisor routes to specialist agents; handles the conversation orchestration
- Works well when task types are known but order is unpredictable
- Requires explicit role definitions and communication protocols between agents

**Level 5 — Hierarchical / Tree-of-Thought**
Agents spawn sub-agents that spawn sub-agents. Used for complex reasoning, deep research, or multi-layer code generation.
- Maximum expressiveness for open-ended problems
- Cost grows exponentially with depth; context bloat is a real operational problem
- Tree pruning (killing branches that aren't converging) is essential

**Level 6 — Event-Driven / Reactive**
Agents respond to system events rather than a predefined sequence. Inputs are unpredictable; agents must adapt.
- Best for monitoring, incident response, real-time customer-facing automation
- Most complex to reason about; debugging is hard
- Requires mature observability before this is viable

### Picking the right framework

| Framework | Best For | Orchestration Model | Maturity | Ceiling |
|-----------|----------|--------------------|----------|--------|
| **LangGraph** | Complex stateful workflows, DAGs, checkpointing | State machine / directed graph | Most mature (v1.0, 90K+ stars) | High |
| **CrewAI** | Rapid prototyping, role-based teams | Role-based agents with goals | Growing (20K+ stars) | Medium |
| **AutoGen** | Conversational AI, code generation | Agent-to-agent conversation | GA Q1 2026 (30K+ stars) | Medium |
| **Temporal** | Workflow orchestration with durability | Long-running workflows with saga patterns | High | Requires infra |
| **Custom (queues + LLM)** | Simple cases, cost-sensitive | Fully controlled | — | — |

Default to LangGraph unless you have strong reasons not to. The learning curve is steeper (2–4 weeks) but you won't hit a ceiling 6 months in.

### The autonomy decision tree

```
Does the task have a fixed, known sequence of steps?
  YES → Simple Chain
  NO  → Is it a single decision (classify → route)?
    YES → Router / Classifier Dispatch
    NO  → Are subtasks independent and parallelizable?
      YES → Fan-Out / Fan-In
      NO  → Does a supervisor need to decompose and delegate?
        YES → Hierarchical Supervisor
        NO  → Are inputs unpredictable, event-driven?
          YES → Event-Driven
          NO  → Agent Loop (Level 5)
```

## Evidence

- **LangChain production survey (2025):** Simple chains handle ~80% of production use cases; teams consistently over-engineer with agents on first build. — [Agentika citing LangChain 2025 survey](https://agentika.uk/blog/llm-orchestration-patterns.html)
- **Microsoft ISE e-commerce case study:** A supervisor orchestrator decomposed multi-intent voice queries (order tracking, returns, recommendations, FAQs) and routed to specialized agents — produced coherent multi-turn responses across unpredictable intent sequences. — [Microsoft ISE Developer Blog, November 2025](https://devblogs.microsoft.com/ise/multi-agent-systems-at-scale/)
- **Routing improvement data:** Router-based task dispatch delivers 30–45% better work completion rates versus fixed pipelines; semantic failure rates reduced by 65–80% with proper pattern-matched orchestration. — [C# Corner citing Liu et al. orchestration research, 2026](https://www.c-sharpcorner.com/article/llm-agent-orchestration-patterns-architectural-frameworks-for-managing-complex/)
- **Framework migration cost:** 65% of teams hit an architectural wall within 12 months when choosing the wrong orchestration framework. — [Gheware DevOps AI Blog, 2026](https://devops.gheware.com/blog/posts/langgraph-vs-crewai-vs-autogen-comparison-2026.html)
- **Fan-out/fan-in latency:** Async state serialization via background threads decouples agent execution from storage I/O, cutting p95 latency by 40%; transactional checkpointing with PostgresSaver reduces failure rate from 12% to <0.01%. — [MarkAICode LangGraph Memory Architecture, 2026](https://markaicode.com/architecture/langgraph-memory-architecture)

## Gotchas

- **Don't start with an agent loop.** Agent loops are powerful for open-ended research but cost 3–5× more than chains for the same result. If a simpler pattern could work, use it.
- **Router accuracy is a hidden single point of failure.** If the classifier dispatches to the wrong handler, the entire pipeline produces the wrong output. Invest in router eval before the downstream agents.
- **Fan-in is underrated.** Teams implement fan-out easily but treat aggregation as an afterthought. De-duplication, validation, and re-ranking at the fan-in stage determine output quality.
- **Framework lock-in is real.** LangGraph's graph-as-code model is more portable than CrewAI's role-based conventions, which are harder to migrate once you've built your agent taxonomy around them.
- **Checkpointing isn't optional for multi-step workflows.** Without checkpointing, a failure mid-workflow loses all progress. LangGraph's `PostgresSaver` with async write-ahead logging is the production standard; Redis works for cross-process communication but has consistency trade-offs at scale.
