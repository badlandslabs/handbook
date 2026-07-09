# S-886 · The Multi-Agent Orchestration Stack — When One Agent Is Too Much and Zero Is Too Little

Your single agent started degrading the moment you added a tenth tool. Now it hallucinates calls, ignores context, and blocks on timeouts while your users wait. You could strip tools back — but the use case needs them. The real move is splitting into multiple agents, each owning a narrow slice, with a coordinator routing work between them.

In 2026, the most reliable production AI systems are networks of specialized agents, not one model doing everything. LangGraph (36k+ stars, v1.0 stable), CrewAI (49k+ stars, 100k+ certified devs), and Microsoft AutoGen are the primary tooling layers — but the patterns predate the frameworks.

## Forces

- **One agent = one reasoning bottleneck.** A single LLM reasoning about context, planning, tool selection, error handling, and output formatting simultaneously degrades on every dimension.
- **Token budget cascades.** Intermediate tool outputs accumulate in context, starving later pipeline steps of clean inputs — the agent at step 10 gets degraded context from steps 1–9.
- **Parallelism is impossible to retrofit.** Sequential single-agent execution wastes wall-clock time on tasks that could run independently.
- **Tool count and quality trade off.** Adding more tools to one agent doesn't make it more capable — it makes tool selection noisier.
- **No isolation.** A bug or degradation in one capability affects everything the agent does.

## The move

Split work across specialized agents coordinated by a lightweight orchestrator. Three patterns cover most cases:

### Pattern 1: Supervisor (router)
A single coordinator agent classifies the incoming task and dispatches to the right specialist. The specialist returns its output; the supervisor formats the final response.

- Best for: Intent classification + task routing, customer service triage, mixed query types
- Tools: LangGraph's `StateGraph` with conditional edges, or CrewAI's hierarchical structure
- Example: Classifier agent → Account Agent (CRM lookups) OR Knowledge Agent (RAG retrieval) → Response Agent (natural language output)

### Pattern 2: Handoff (relay)
Specialized agents pass control explicitly — agent A completes its task and explicitly hands off to agent B with accumulated state.

- Best for: Linear pipelines where each stage must complete before the next starts (e.g., research → analysis → report)
- Tools: LangGraph checkpointing for state persistence across handoffs; AutoGen's conversation-based handoff protocol
- Key requirement: State from agent A must be serializable and passed cleanly to agent B without context pollution

### Pattern 3: Swarm (peer-to-peer)
Agents operate concurrently, communicating via shared state or message passing. No central coordinator; agents negotiate roles dynamically.

- Best for: Complex, multi-dimensional tasks where different perspectives are needed simultaneously (e.g., a coding agent and a security-review agent working in parallel on the same codebase)
- Tools: CrewAI's agent-to-agent delegation, LangGraph's broadcast patterns
- Risk: Without a supervisor, race conditions and contradictory outputs must be explicitly handled

### The right number of agents
Start with two. Add a third only when: (a) a distinct capability domain exists with its own tool set, and (b) the coordinator's routing logic for that domain is complex enough to justify isolation. Three to five agents covers 90% of real production cases. Beyond five, coordination overhead exceeds the quality gains.

## Evidence

- **GitHub README:** LangGraph (langchain-ai/langgraph) — "Low-level orchestration framework for building stateful agents. Build resilient agents." — [https://github.com/langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) — 36,856 stars, 6,191 forks, v1.0 stable (late 2025). Supports cycles, state persistence, and human-in-the-loop interventions via checkpointing.
- **Engineering blog:** Anthropic's "Building Effective Agents" — "The most successful implementations use simple, composable patterns rather than complex frameworks." — [https://www.anthropic.com/engineering/building-effective-agents](https://www.anthropic.com/engineering/building-effective-agents) — recommends starting with LLM APIs directly and understanding the underlying code before reaching for orchestration frameworks.
- **Technical guide:** Agentbrisk "Multi-Agent Orchestration in 2026" — "A single LLM agent with ten tools isn't the same as ten agents with one tool each. The problem isn't the number of tools, it's that one agent has to reason about context, planning, tool selection, error handling, and output formatting all at once." — [https://agentbrisk.com/blog/multi-agent-orchestration-guide-2026](https://agentbrisk.com/blog/multi-agent-orchestration-guide-2026)
- **Technical guide:** SourceBae "Multi-Agent LLM Systems" — "In 2026, production-grade AI systems are built on collaboration rather than a single all-knowing model." — [https://sourcebae.com/blog/multi-agent-llm](https://sourcebae.com/blog/multi-agent-llm) — covers parallel execution benefits and framework comparison.

## Gotchas

- **State pollution across handoffs.** Agent A's accumulated tool outputs pollute Agent B's context if not explicitly summarized or filtered. Always run a "context compaction" step before each handoff — pass a distilled summary, not the raw transcript.
- **Routing loops.** Without an explicit max-hops limit, a supervisor agent can enter a cycle of re-classifying the same output. Set a hard `max_iterations` bound and route to a fallback agent or human escalation on loop detection.
- **Silent degradation at scale.** A specialist agent can quietly degrade (worse tool calls, lower quality outputs) without the supervisor noticing. Pair multi-agent architectures with per-agent eval sampling — evaluate each agent's outputs independently, not just the final result.
- **Framework abstraction leaks.** "Start with LLM APIs directly" (Anthropic) is still good advice even when using LangGraph or CrewAI. The frameworks add useful primitives but also add layers that obscure failures. Know what your framework is doing under the hood before debugging production issues.
- **Credential scoping.** Each specialist agent needs only the permissions required for its domain. A knowledge agent that only reads RAG doesn't need write access to the CRM. Least-privilege tool access limits blast radius when an agent isprompt-injected or misbehaves.
