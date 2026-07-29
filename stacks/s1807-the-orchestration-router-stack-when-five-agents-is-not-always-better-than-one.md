# S-1807 · The Orchestration Router Stack — When Five Agents Is Not Always Better Than One

Your product manager wants a multi-agent system. You spin up a supervisor, three workers, a critic, and a synthesizer. The demo looks impressive. Six weeks later, the 95%-reliable agents chain into a 77% reliable pipeline, a single LLM call now costs $0.18, and nobody can trace why the final output is wrong. The graph grew organically and nobody drew the map. You needed an orchestration router, not a crowd.

The dominant failure in agentic systems is not that agents fail individually — it is that teams reach for multi-agent architectures before understanding what orchestration pattern actually matches their failure budget, and then they wire them together without a clear routing contract.

## Forces

- **Reliability compounding destroys multi-agent gains.** Per Lusser's law, five 95%-reliable agents in a chain yield 77% system reliability. Ten chained agents yield 60%. Teams underestimate this until production traffic reveals it.
- **Framework choice shapes what you can express.** CrewAI ships fast and fits the team metaphor, but graph-as-chat breaks under branching, human-in-the-loop, and crash-safe resume. LangGraph ships slower but treats orchestration as a first-class state machine.
- **The "more agents" instinct is wrong half the time.** Anthropic's own evals showed orchestrator-worker outperforms single-agent by 90%+ on complex research tasks — but on simple classification, a single well-prompted call wins on cost and latency.
- **Context window pressure forces architectural decisions.** Agents that stuff everything into one context hit token limits and spend budget on retrieval. Anthropic's parallel subagent approach sidesteps this by giving each agent its own compressed context window, then aggregating.

## The move

**Route to the right orchestration pattern based on task complexity, failure tolerance, and budget — not team size or developer enthusiasm.**

1. **Start single-agent. Graduate only on evidence.** If a task can be done in one LLM call with a good system prompt and a tool definition, one call it is. The multi-agent tax — more latency, more cost, more failure surface — only pays when branching, parallelism, or role specialization demonstrably improves output quality.

2. **Use the Supervisor pattern for routing-heavy tasks.** A single orchestrator LLM routes tasks to specialized workers based on content classification. This is LangGraph's core primitive and the pattern behind Anthropic's Claude Opus 4.8 multi-agent results. The supervisor holds routing logic; workers hold domain logic. Routing is explicit, auditable, and replayable.

3. **Use parallel subagents when the task decomposes into independent explorations.** Anthropic's Research system spawns multiple agents with separate context windows that explore different aspects simultaneously, then aggregates results. Each subagent operates in a compressed context — the coordination overhead is worth it because the alternative is one agent hitting context limits while redundantly re-reading the same material.

4. **Treat the orchestration graph as a first-class artifact, not emergent behavior.** Document the routing rules, the edge conditions, and the termination criteria. Gambit (Bolt Foundry's agent harness) frames agents as TypeScript programs or markdown files with typed interfaces ("decks") between them — making the contract between orchestration and execution explicit.

5. **Implement the "stop micormanaging your AI" principle.** Sourcegraph's Amp Code team learned that prompt-as-puppeteer turns agents into expensive autocomplete. The inversion: give the agent a high-level goal, expose the right tools, and let it decide execution order. The human reviews output, not intermediate steps. This is what "inversion of control" means in practice — not no control, but deferred control at the right granularity.

6. **Flatten the chain where possible.** Sequential pipelines compound failure worst. Consensus patterns and hierarchical containment beat sequential for reliability. If you need a chain, keep it to three steps maximum and insert a quality gate between each.

## Evidence

- **Anthropic engineering post:** Multi-agent research system uses parallel subagents with separate context windows. "Once intelligence reaches a threshold, multi-agent coordination enables exponential capability gains." Supervisor pattern routes to specialists; parallel exploration compresses research time. — [https://www.anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Anthropic Claude Cookbook:** Async multi-agent orchestration pattern documented with the public Python SDK — fixed N-agent team with peer messaging through a shared hub, and dynamically spawned subagents with spawn/status/collect/kill lifecycle. — [https://platform.claude.com/cookbook/patterns-agents-async-multi-agent-orchestration](https://platform.claude.com/cookbook/patterns-agents-async-multi-agent-orchestration)
- **Sourcegraph / nibzard synthesis:** "CrewAI gets you to demo in an afternoon. LangGraph gets you to a run you can resume after a deploy on Thursday." Inversion of control documented as a pattern — agent drives execution, human reviews output. Sourcegraph's Amp Code achieved 30-60% developer productivity gains in enterprise deployments. — [https://www.nibzard.com/ampcode/](https://www.nibzard.com/ampcode/)
- **LangGraph community synthesis:** Supervisor/orchestrator-worker pattern is the default for routing-heavy workflows. Community consensus: start with single-agent, add LangGraph only when branching, parallelism, or crash-safe resume becomes a requirement. — [https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026](https://ideatomvp.ai/blog/langgraph-agent-orchestration-patterns-2026)
- **GrowthEngineer analysis:** MAST study (March 2025) found real multi-agent failure rates at 41%–86.7% depending on pattern. Sequential pipelines compound worst; consensus and hierarchical contain it best. — [https://growthengineer.ai/blog/multi-agent-orchestration-patterns](https://growthengineer.ai/blog/multi-agent-orchestration-patterns)
- **Bolt Foundry / Gambit:** Agent harness framing — orchestration is a TypeScript program or markdown file with typed interfaces ("decks") between agents, making routing contracts explicit and testable. — [https://github.com/bolt-foundry/gambit](https://github.com/bolt-foundry/gambit)

## Gotchas

- **Reaching for multi-agent before measuring single-agent ceiling.** Most tasks that "need" multiple agents actually need better tool definitions or a better system prompt. Measure where single-agent degrades before adding the coordination overhead.
- **Building an orchestration graph that only the author can read.** LangGraph's graph-as-code approach is powerful but the graph quickly becomes a liability without a visual representation and explicit routing rule documentation. Gambit's deck model forces explicit contracts.
- **Ignoring context pressure until the agent starts dropping files.** Anthropic's parallel subagent approach is partly a solution to context window limits — each subagent gets its own compressed window rather than stuffing everything into one. Design for context eviction from the start.
- **Chain depth outpaces reliability.** Five agents at 95% reliability = 77% system reliability. Add a quality gate after each step, or use a consensus pattern to catch failures before they propagate. A critic agent that checks output before the next stage in the chain pays for itself in reduced downstream waste.
