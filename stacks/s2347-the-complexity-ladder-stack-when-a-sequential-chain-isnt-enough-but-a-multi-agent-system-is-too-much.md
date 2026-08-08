# S-2347 · The Complexity Ladder Stack — When a Sequential Chain Isn't Enough but a Multi-Agent System Is Too Much

You've got one LLM call working. Then the business adds a second step, and you start chaining calls. Then branching. Then parallel sub-tasks. Suddenly you have a graph with no clear edges, an agent that loops, and no idea which pattern you should have started with. The six production orchestration patterns form a ladder — most teams skip rungs and pay for it.

## Forces

- **Frameworks make multi-agent feel cheap; production makes it expensive.** CrewAI gets you to a demo in an afternoon. LangGraph takes longer but actually survives a Thursday deploy. The fast path and the right path diverge quickly once costs, failures, and debugging enter the picture.
- **The complexity ceiling is predictable.** Sequential chains fail at branching. Routers fail at shared context. ReAct fails at long-horizon tasks. Map-reduce fails at cross-slice synthesis. Each pattern has a concrete ceiling, and hitting it while built on the wrong abstraction is expensive to fix.
- **Most teams over-architect on the first build.** Anthropic's production findings across dozens of deployment teams: "The most successful implementations use simple, composable patterns rather than complex frameworks." Starting at the top of the ladder is the most common and costly mistake.
- **LangGraph's graph paradigm earns its cost at a specific threshold.** When you need checkpointing, crash-safe resume, conditional branching with explicit state, or auditability — a state machine is the right tool. Before that threshold, it adds overhead without benefit. The Reddit/LangChain community consensus: "CrewAI gets you to demo; LangGraph gets you to a run you can resume after a deploy."

## The move

**Match the orchestration pattern to the actual failure mode of your current approach.** The six patterns are a ladder — move up only when the pattern below genuinely can't do the job.

### Pattern 01: Single LLM Call + Retrieval
Start here. Every other pattern adds overhead. If one model call with a good prompt and RAG can solve it, use one model call.
- Use retrieval to inject relevant context instead of prompting the model to "remember" everything
- Optimize prompt structure and few-shot examples before adding a second call

### Pattern 02: Sequential Chain
When output from one step must be the complete input to the next.
- Model A → Model B. Summarize → classify → route. Extract → validate → store.
- Latency compounds; errors cascade. Each step must succeed for the chain to proceed.
- Best for pipelines where each stage has a single, clear purpose and failure is unambiguous.

### Pattern 03: Router (If/Else Branching)
When the path through the pipeline depends on the content.
- Single orchestrator decides which specialized handler receives the request: a refund goes to the refund agent, a technical question to the support agent.
- The router is the most critical component — its errors route work to the wrong place silently.
- Prefer deterministic routing on structured signals (intent classification, tool selection schemas) over LLM-based routing until the routing logic is proven.

### Pattern 04: Map-Reduce
When the same operation can be applied independently to multiple inputs, then the results synthesized.
- Fan out: send N documents to N parallel extractors. Fan in: aggregate results through a summarizer.
- Each branch is isolated — failure in one doesn't corrupt others. But cross-slice synthesis (who summarizes the summarizers?) is where this pattern gets complex.
- Shopify Sidekick found that map-reduce was the natural fit for bulk operations (analyzing customer segments across thousands of records) where the agentic loop overhead would have been prohibitive.

### Pattern 05: ReAct (Think-Act-Observe Loop)
When the agent needs to interleave reasoning with tool use dynamically.
- Think: decide what to do next. Act: call a tool. Observe: incorporate the result. Repeat.
- Keeps the model grounded in actual tool outputs rather than hallucinated completions.
- Fails at long-horizon tasks: the model must hold the entire loop state in context, so cost and quality degrade with step count.
- The "thin" ReAct variant (short reasoning traces) is cheaper; the "extended" variant enables complex tool-use chains but burns tokens fast.

### Pattern 06: Plan-and-Execute (Hierarchical)
When a task has many steps across different domains and must survive partial failure.
- Separate planner (decomposes goal into steps) from executor (performs each step with tools).
- The planner runs once upfront, producing a task list. The executor works through it, replanning on failure.
- This is where LangGraph's state machine model pays off — checkpointing lets you resume from mid-plan after a crash.
- Production teams at Shopify using Claude Swarm found that a planning agent directing specialized execution agents cut task completion time from hours to minutes compared to monolithic prompts.
- **The key trade-off:** planning adds an LLM call overhead before execution. For tasks that need 3+ steps with conditional branches, this overhead pays for itself in error recovery.

## Evidence

- **Anthropic engineering blog:** "The most successful implementations use simple, composable patterns rather than complex frameworks. Consistently, optimizing single LLM calls with retrieval and few-shot examples outperforms adding orchestration complexity." — Erik S. & Barry Zhang, *Building Effective AI Agents*, December 2024 — https://www.anthropic.com/engineering/building-effective-agents

- **Shopify engineering (Sidekick):** Tool inventory growth follows predictable failure modes: 0–20 tools have clear boundaries and are easy to debug; 20–50 introduce coordination overhead; 50+ require hierarchical grouping to remain manageable. Sidekick implemented Anthropic's "agentic loop" (input → LLM decision → action → feedback → repeat) and found map-reduce natural for bulk merchant operations. — *Building production-ready agentic systems: Lessons from Shopify Sidekick*, August 2025 — https://shopify.engineering/building-production-ready-agentic-systems

- **Reddit r/LangChain community survey:** LangChain's own community survey found 51% of respondents were already using agents in production, with 78% having active plans to scale. Community consensus: LangGraph's graph-as-state-machine model outperforms role-based frameworks (CrewAI) specifically for "branching, approvals, and crash-safe resume." — *r/LangChain community analysis*, 2025 — https://agentsindex.ai/r-localllama

## Gotchas

- **Starting with multi-agent when sequential would suffice.** The agent-to-agent handoff problem (how does the research agent tell the coding agent what it found?) is non-trivial. Each handoff boundary is a potential context loss point. Anthropic's finding: for most applications, optimizing the single LLM call is the highest-ROI move.
- **Routing on LLM confidence instead of structured signals.** LLM-based routers hallucinate routing decisions under distributional shift. A classifier trained on actual intent labels is more reliable than asking the router model to "decide." Treat router accuracy as a first-class engineering problem.
- **ReAct loops that don't terminate.** Without explicit step limits or termination conditions, ReAct agents can loop indefinitely, especially with models that prefer action over "I'm done." Set hard max iterations and define explicit success signals.
- **Planning overhead that negates the benefit.** Plan-and-execute adds an upfront planning LLM call before any execution. For 1–2 step tasks, this doubles cost. Profile your actual task complexity before committing to the hierarchical pattern.
