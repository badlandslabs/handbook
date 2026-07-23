# S-1541 · The Orchestrator-Worker Stack — When Your Agent Team Is Smart but Poorly Wired

Your agents are individually capable. They call the right tools, reason through problems, produce coherent output. And yet the system fails: results are incomplete, context disappears mid-chain, two agents produce conflicting outputs, or the whole pipeline hangs because one step took too long. The agents aren't the problem. The wiring is.

## Forces

- **The orchestration tax is real.** Every hop — LLM → tool → result → LLM → next tool — adds latency, error surface, and context pressure. More agents mean more hops. Teams that chase "smarter agents" while ignoring coordination often end up with slower, less reliable systems.
- **The build-vs-buy line is genuinely unclear.** LangGraph, CrewAI, AutoGen, OpenAI Agents SDK, Google ADK, and custom orchestration all solve the same problem with wildly different trade-offs. The framework you choose shapes what's easy to change later. Production teams consistently report that custom orchestration wins for performance-critical paths; frameworks win for prototyping velocity.
- **When to go multi-agent is the hardest call.** Anthropic's own engineers spent the first 80% of their landmark "Building Effective Agents" post advising teams they probably don't need agents. The decision to decompose into multiple agents requires clear justification — and most teams justify it too quickly.
- **Error propagation dominates failure modes.** Research from Zhu et al. (2025) found that error propagation through chains is "the single biggest barrier to building dependable LLM agents." A tool returning malformed JSON in step 3 of 7 doesn't just fail step 3 — it can poison the LLM's state for the remaining steps, causing increasingly incoherent behavior.
- **Parallelism promises speed but demands coordination.** Subagents exploring different directions in parallel can reduce wall-clock time dramatically (Anthropic saw 15x token usage but near-identical wall-clock time vs. single-agent). But shared state, result synthesis, and duplicate-effort prevention require explicit design.

## The Move

Choose orchestration patterns from a structured decision tree, not from the framework you already know.

### Pattern 1: Supervisor (orchestrator-worker)

A single lead agent decomposes a request, delegates sub-tasks to specialized workers, monitors results, and synthesizes the final output. Use when:
- Tasks decompose cleanly into independent sub-tasks
- A single "boss" can reliably evaluate worker quality
- You need a clear handoff boundary for auditability

Anthropic uses this pattern in their production Research system. Their lead agent analyzes a query, plans a strategy, then spawns parallel subagents for different search directions. Workers return results to the lead; the lead synthesizes. Internal benchmarks improved 90.2% over single-agent, with 80% of the variance explained by increased token usage (more depth per sub-task).

### Pattern 2: Parallel fan-out / fan-in

A task is sent to N agents simultaneously, all produce results, then results are merged. Use when:
- Sub-tasks are truly independent (no shared state needed mid-execution)
- You want near-identical wall-clock time to a single agent despite more total computation
- Results are easy to merge (lists, rankings, structured summaries)

The key failure mode: agents duplicate effort or produce inconsistent formats. Mitigate with explicit output schema contracts (each agent must return a specific JSON shape) and a dedup/marge step before synthesis.

### Pattern 3: Router

A lightweight LLM or heuristic inspects the input and dispatches to the correct pipeline. Use when:
- Different input types need fundamentally different handling (code review vs. prose writing vs. data analysis)
- You want to avoid the cost and latency of a full orchestrator for simple cases
- A deterministic rule can handle the common 80% of cases without LLM involvement

### Pattern 4: Sequential pipeline with guardrails

Tasks flow through fixed steps — each step is a deterministic function, an LLM call, or a tool. Use when:
- The task path is predictable and the same for all inputs
- You need auditability and reproducibility
- You want to mix rule-based steps with LLM steps in the same pipeline

This is Anthropic's recommended default. The insight: most "agentic" tasks can be expressed as pipelines where an orchestrator routes between steps, rather than agents that dynamically figure out what to do next. Fixed pipelines are easier to test, debug, and observe.

### Pattern 5: Evaluator-optimizer loop

An agent produces output; a second agent (the evaluator) critiques it against criteria; the producer revises; repeat until the evaluator passes or iteration limit is hit. Use when:
- Quality is more important than speed
- A reliable evaluation signal exists (a rubric, a spec, a test suite)
- Cost per iteration is acceptable given the quality requirement

### Combining patterns

Real production systems stack 2-3 patterns. A common production topology: Router (classify input) → Supervisor (decompose into sub-tasks) → Parallel fan-out (workers handle sub-tasks) → Evaluator-optimizer (refine results) → Supervisor (synthesize). Each transition is an explicit boundary — useful for logging, retry, and human-in-the-loop intervention.

## Evidence

- **Anthropic engineering blog (June 2025):** Anthropic's production Research system uses an orchestrator-worker pattern with a lead agent decomposing queries and spawning parallel subagents. 90.2% internal benchmark improvement over single-agent. 80% of performance variance explained by increased token usage (more thorough exploration per sub-task). — [https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)

- **Hacker News discussion of Anthropic's "Building Effective Agents" (June 2025, 543 points, 88 comments):** HN consensus emphasized that "a large share of failures originate in orchestration design rather than individual agent capability — agents are individually capable but poorly coordinated." Commenter `gregorymichael` distilled the pattern: "an augmented LLM running in a loop is the best definition of an agent I've heard so far." — [https://news.ycombinator.com/item?id=44301809](https://news.ycombinator.com/item?id=44301809)

- **Future AGI research (March 2026):** Tool chaining — sequential multi-tool execution — consistently breaks in production. Four failure modes: context dilution (critical details pushed out of the context window mid-chain), partial failures (one tool fails but the chain continues with corrupted state), error propagation (a malformed tool response poisons downstream LLM reasoning), and context divergence (LLM misinterprets tool output, carrying the wrong assumption forward). Zhu et al. (2025) research confirms error propagation as "the single biggest barrier" to reliable agents. — [https://futureagi.substack.com/p/how-tool-chaining-fails-in-production](https://futureagi.substack.com/p/how-tool-chaining-fails-in-production)

- **Microsoft Azure Architecture Center:** Six-orchestration-pattern taxonomy (Supervisor, Sequential, Parallel Fan-Out/Fan-In, Router, Hierarchical Delegation, Evaluator-Optimizer) with explicit guidance on when each applies and the complexity trade-offs at each level of the complexity spectrum. — [https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns](https://learn.microsoft.com/en-us/azure/architecture/ai-ml/guide/ai-agent-design-patterns)

## Gotchas

- **Reaching for multi-agent when a pipeline suffices.** Anthropic's own engineers warn: 80% of use cases that "need agents" actually need a deterministic workflow with if-statements. Add agents when you need dynamic routing, parallel exploration, or autonomous multi-step reasoning — not because it feels more sophisticated.
- **No shared state between agents.** In parallel patterns, subagents operate in isolation. If they need to coordinate or avoid duplicate work, you must build that explicitly — through a shared message bus, a database, or a supervisor agent that assigns work before dispatch. "They'll figure it out" is not a design; it's a production incident waiting to happen.
- **Timeout and partial-result handling is the make-or-break.** A subagent that takes 10 minutes in a parallel fan-out blocks nothing (by design), but you need explicit logic for: what if only 3 of 5 agents return? What if one returns late? What if the synthesis step gets partial results? Tool-call-level timeouts, circuit breakers, and fallback strategies must be designed before production, not after.
- **Framework choice is sticky.** LangGraph (state graph as code), CrewAI (role-based), AutoGen (conversational), and custom (raw API calls) each have a different debugging model. LangGraph has the largest production deployment footprint in 2026 and the best observability story. But custom orchestration consistently wins for latency-critical paths because frameworks add 50-200ms of overhead per step. Choose based on where your system will spend its time, not where you're starting from.
