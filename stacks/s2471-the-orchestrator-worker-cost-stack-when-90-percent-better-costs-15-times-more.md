# S-2471 · The Orchestrator-Worker Cost Stack — When 90% Better Costs 15× More

Your multi-agent research pipeline is producing substantially better results than a single-agent setup. It is also burning through tokens at 15× the rate, running 3× longer per task, and costing 15× more per query. The team celebrated the quality improvement. Nobody celebrated the compute bill. The question is not whether the pattern works — Anthropic's production data says it does, with >90% task quality improvement over single-agent on research tasks. The question is whether it earns that cost on your workload.

## Forces

- **Token cost scales with agent count and context windows.** Each subagent runs its own full context window. Eight parallel subagents × full context = multiplicative token growth, not linear. Anthropic measured ~15× more tokens compared to standard chat on their research pipeline.
- **Quality improvement correlates with independent exploration.** Multi-agent shines when subagents explore different facets in parallel and the orchestrator synthesizes. For tightly interdependent tasks — sequential code with shared state, multi-file refactors with cross-references — the same architecture degrades into coordination overhead with little quality gain.
- **Cost-per-task is the wrong unit.** Per-task cost matters less than cost-per-correct-answer. A pipeline that costs 15× more but succeeds on 3× more hard queries has a better cost-quality ratio than it appears.
- **The orchestrator is a single point of failure and bottleneck.** If the orchestrator degrades — wrong task decomposition, poor synthesis, tool prompt drift — the entire pipeline degrades. Subagent quality is necessary but not sufficient.

## The Move

The orchestrator-worker pattern works when the cost-quality ratio is right for the workload. Design it with this decision tree:

- **Use orchestrator-worker when:** research tasks where subagents explore independent facets, synthesis tasks with a clear aggregator, tasks where parallel exploration compresses a large search space faster than sequential reasoning.
- **Skip it when:** tasks are tightly sequential or interdependent, latency matters more than depth, the task fits in a single context window without degradation.
- **Size subagents for independence.** Each subagent should operate on a self-contained slice of the problem. If two subagents constantly need to read each other's outputs mid-task, merge them or reorder the pipeline.
- **Run Opus as orchestrator, Sonnet-class as workers.** Anthropic's production deployment uses Claude Opus 4 as lead (planning, synthesis, routing) and Claude Sonnet 4 as subagents (parallel search and retrieval). The asymmetry is deliberate: the router needs more reasoning depth; the workers need speed and volume.
- **Instrument token cost at the subagent level.** Track tokens-per-subagent and synthesize the cost breakdown per task. Without per-subagent visibility, you cannot identify which workers are expensive relative to their contribution.
- **Gate on cost-per-correct-answer, not per-task cost.** Measure the quality delta: does multi-agent solve X% more hard queries? If yes, the 15× multiplier may be justified. If the improvement is on easy queries the single-agent would have gotten right anyway, you are overpaying for everything.

## Evidence

- **Engineering blog (primary):** Anthropic's multi-agent research system delivers >90% improvement over single-agent on research tasks. Uses Claude Opus 4 as orchestrator, Sonnet 4 as subagents. Architecture: lead agent decomposes the query, dispatches parallel subagents to independent tool calls (web search, workspace access), synthesizes results. Published with internal evaluation data. — [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Practitioner validation:** Fountain City Tech validated Anthropic's multi-agent blueprint in production. Confirmed ~90% improvement with Opus 4 + Sonnet 4. Measured ~15× token cost multiplier vs. chat. Tool description rework on subagents reduced task completion time by 40%. — [fountaincity.tech/resources/blog/anthropic-multi-agent-blueprint-production](https://fountaincity.tech/resources/blog/anthropic-multi-agent-blueprint-production)
- **ByteByteGo architectural breakdown:** Orchestrator-worker pattern enables breadth-first exploration, compresses large search spaces, reduces risk of missing key information. Most effective for problems divisible into parallel strands. Less effective for tightly interdependent tasks. — [blog.bytebytego.com/p/how-anthropic-built-a-multi-agent](https://blog.bytebytego.com/p/how-anthropic-built-a-multi-agent)

## Gotchas

- **Parallel subagents with shared mutable state will race.** If subagents write to a shared resource — a document, a database, a shared memory block — implement a merge strategy or sequential write ordering. Do not assume subagent outputs are independent if they share an output target.
- **The 15× multiplier is not a ceiling.** Complex queries with many subagents, deep reasoning traces, and repeated synthesis can exceed this. Budget conservatively and instrument aggressively.
- **Tool description quality cascades to worker quality.** Fountain City Tech found that reworking subagent tool descriptions — clearer parameter names, explicit preconditions, examples of common failure modes — cut task completion time by 40%. The orchestrator's decomposition is only as good as the workers' ability to execute it.
- **Subagent tool calls do not automatically feed back into the orchestrator's context.** The synthesis step requires the orchestrator to receive and reason over subagent outputs. If the context window overflows during synthesis, you lose the quality gains of parallel exploration.
