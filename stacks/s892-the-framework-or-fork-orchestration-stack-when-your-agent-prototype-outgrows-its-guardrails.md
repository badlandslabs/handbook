# S-892 · The Framework or Fork Orchestration Stack — When Your Agent Prototype Outgrows Its Guardrails

You built a working agent prototype with LangGraph (or CrewAI, or AutoGen). Demos pass. The moment you ship to production and traffic grows, you hit the walls: opaque retry logic, uninspectable state, memory leaks in long conversations, and a framework update that silently breaks your tool definitions. Now you're deciding: adapt your problem to the framework, or extract into custom orchestration.

## Forces

- **Prototype velocity vs. production control** — frameworks get you to a working agent fast, but their abstraction boundaries become prison walls when you need to introspect, retry, or modify agent behavior at the edges
- **Ecosystem lock-in vs. maintenance debt** — using LangGraph means riding its API changes; rolling your own means owning every retry, timeout, and observability concern yourself
- **The stochastic LLM sandwich** — between any two deterministic steps (tool call → structured output → next agent), the LLM call can hallucinate, loop, or refuse; frameworks abstract this but often hide the failure modes rather than solving them
- **State explosion** — conversation history grows unbounded; frameworks provide compaction strategies that often don't match your specific use case's information density
- **Parallel agents introduce coordination tax** — multiple agents on the same codebase (or shared task) create work overlap, stale context, and conflicting decisions that no framework handles automatically

## The Move

The move is a deliberate fork decision — not a default, but an explicit stage gate. Start on a framework to validate the pattern. Extract to custom orchestration when the framework's abstractions start costing more than they provide.

### Validate on a framework first
- Use LangGraph for stateful graph-based workflows (largest ecosystem, best tooling); use CrewAI for rapid multi-agent role prototyping; use AutoGen for multi-agent debate and research patterns
- Frameworks are not wrong — they accelerate discovery of what your orchestration actually needs to do
- Treat the prototype as a requirements document, not a production artifact

### Extract when these signals appear
- You need to inspect, replay, or fork agent state mid-execution — framework state objects are opaque
- Your retry logic needs to be aware of semantic state (which step failed, what was already committed), not just HTTP codes
- You need to share state across agent boundaries in ways the framework doesn't support (Redis scratchpad, SQLite, structured output passing)
- The framework's tool definition system (MCP, native tools) is becoming a bottleneck to your deployment velocity

### Build custom orchestration on async Python primitives
- Use asyncio with typed message queues instead of framework-specific abstractions
- Keep messages as an append-only list — makes execution traces easy to reason about and replay
- Treat the conversation thread itself as the primary state store, not a separate memory system
- Don't bother compacting histories until you must; summarize and spin up a fresh agent context instead

### Handle the parallel agent problem explicitly
- Use workspace isolation (separate git branches, separate file scopes) to prevent work collision
- Enforce a coordination layer that owns task dispatch, tracks what's in-flight, and prevents overlapping file edits
- Inject shared project memory (documentation decisions, architectural choices) into each agent's context, but don't rely on agents to discover it themselves

### Choose MCP as your tool interface standard
- MCP (Model Context Protocol) has crossed from Anthropic experiment to ecosystem standard: OpenAI (March 2025), Google Gemini (April 2025), Microsoft, AWS, Cloudflare, and Bloomberg all adopted it
- Build tools as MCP servers — this decouples your tool definitions from your orchestration layer
- A shared MCP layer acts as the state bus across multiple agents in a workflow: planner, executor, reviewer all read/write from the same tool context

## Evidence

- **HN Ask HN (multi-agent orchestration in production, 2025):** A thread asking "Do you use a framework or roll your own?" revealed strong practitioner consensus that custom orchestration dominates serious production deployments. One respondent (extasia): "I wrote my own agent state machine in pretty much pure async Python. Running successfully in prod with very few issues. Don't bother compacting histories imo. worst case just summarise and spin up a new agent with the context." — https://news.ycombinator.com/item?id=45502646
- **HN Ask HN (multi-agent AI workflows in production, 2025):** Multiple practitioners described rolling their own with JSON docs and Redis scratchpads for state passing, underestimated observability needs, and mixed execution triggers (webhooks, cron, manual). One respondent noted treating "the entire conversation thread as the context window, not just the latest message." — https://news.ycombinator.com/item?id=47660705
- **Presenc AI research (multi-agent orchestration frameworks 2026):** Framework landscape analysis found LangGraph has the largest enterprise deployment footprint in 2026, but "production deployments still favour custom orchestration at the upper end." Framework choice is "less consequential than underlying model selection, evaluation infrastructure, and human-checkpoint design." — https://presenc.ai/research/multi-agent-orchestration-frameworks-2026
- **E2B blog (CrewAI vs AutoGen code execution, 2025):** Detailed technical comparison found CrewAI allows agents to delegate to each other (vs. AutoGen's more rigid execution model), but both frameworks "look great in isolated demos and fall apart when you try to glue agents together into a real application." — https://e2b.dev/blog/crewai-vs-autogen-for-code-execution-ai-agents
- **Show HN (Stoneforge, parallel AI coding agents, 2025):** An open-source project orchestrating multiple Claude Code/Codex agents in parallel on the same codebase. The creator built it because manual coordination between terminal windows was burning hours. Stoneforge acts as a coordination layer preventing work overlap and context degradation across parallel agents. — https://news.ycombinator.com/item?id=47267105

## Gotchas

- **"The framework will handle it" is usually wrong in production.** Retry logic, timeout escalation, and error recovery need to be semantic — aware of which step you're in, what was already committed, and what the downstream agents expect. Generic framework retry often makes things worse by repeating irreversible actions.
- **MCP solves the tool interface problem but not the orchestration problem.** Having a standard way to call Brave Search or GitHub tools doesn't tell you when to call them, in what order, or how to handle partial results. MCP is infrastructure, not logic.
- **Multi-agent parallelism sounds like a multiplier but introduces coordination overhead that eats the gains.** Running 3-5 agents in parallel on the same codebase requires active work to prevent overlapping edits, stale context propagation, and conflicting decisions. The coordination cost is non-zero and often underestimated.
- **Framework upgrades silently break tool definitions.** LangChain and CrewAI change their tool schema format between versions; a routine upgrade can render your entire tool catalog unreadable at runtime with no crash, just degraded behavior.
- **LLM-as-judge evaluation requires careful scorer design or it regresss to noise.** Braintrust's guidance: target 0.80+ Spearman correlation with human judgment. Without calibration, "eval as a judge" simply amplifies model bias rather than catching regressions.
