# S-1487 · The Supervisor / Fan-Out Stack

When a single LLM call cannot cover the skill surface your task requires — but spawning five agents and hoping they coordinate turns your pipeline into spaghetti.

## Forces

- **A single agent accumulates too many tools.** Adding every capability to one prompt causes decision paralysis and tool-call confusion, especially on frontier models that start second-guessing which tool to use.
- **Parallel subagents run faster than sequential chains**, but without a supervisor they return unstructured results that need a human to re-assemble — the speed gain evaporates.
- **Cost compounds in loops.** Multi-agent systems with unbounded turns can cost 3–5× more than a single-call LLM workflow. The fan-out has to be worth the token burn.
- **Supervisor becomes a bottleneck.** Routing every decision through one orchestrating agent creates a single point of failure and throttles throughput.

## The move

**Use a supervisor agent that owns task decomposition and result synthesis, paired with stateless parallel subagents that each own one capability.** Keep the supervisor lightweight and fast; keep subagents dumb and specific.

Specific techniques:

- **One supervisor, N stateless subagents.** The supervisor decomposes the user's goal into sub-tasks, assigns each to a dedicated subagent, then synthesizes their outputs into a final response. Subagents carry no cross-call state — they receive a task, return a result, and are done.
- **Supervisor as router, not executor.** The supervisor's only job after decomposition is to wait for results and merge them. It should not itself perform the research, code, or analysis — delegate that fully.
- **Capability-aligned subagent personas.** Give each subagent a narrow, consistent persona (e.g., "You are a financial analyst. You specialize in SEC filings and earnings calls.") rather than a generic "researcher" prompt. Narrow personas reduce hallucination on domain edge cases.
- **Cap the parallel fan-out with a difficulty classifier.** Before launching N agents, route the query through a lightweight classifier that estimates complexity. Simple queries get 1–2 subagents; complex ones get the full team. This delivers cost reductions without accuracy loss. (Zylos Research, 2026)
- **Dead-letter queue for subagent failures.** If a subagent times out or returns malformed output, put its result in a DLQ rather than failing the whole run. The supervisor can re-run just the failed subagent, retry with a fallback model, or surface the partial failure to the user.
- **Structured output from every subagent.** Require each subagent to return JSON with a `findings` field, `confidence` score, and `gaps` list. Unstructured text from parallel agents is the most common source of synthesis bugs.

## Evidence

- **Engineering post:** Anthropic's multi-agent research system (Jun 2025) uses a lead agent that decomposes queries and spawns parallel subagents, each with their own tool access and context window. They found that parallel subagents with separate context windows let the system "compress" research time because each subagent explores independently. — [anthropic.com/engineering/multi-agent-research-system](https://www.anthropic.com/engineering/multi-agent-research-system)
- **Industry survey:** Enterprise AutoGen deployments show two-agent supervisor patterns cover ~60% of production cases; group chat with more than four agents accounts for under 15%. The bottleneck is not the number of agents — it's the quality of the routing logic between them. — [secondtalent.com — How Enterprises Are Using AutoGen in 2026](https://www.secondtalent.com/resources/how-enterprises-are-using-autogen)
- **Research synthesis:** Zylos Research's 2026 orchestration analysis identifies three production-grade patterns (DAG, event-driven, actor model), with difficulty-aware dynamic routing emerging as a cost lever — routing simple queries to shallow chains and reserving deep pipelines for complex ones. They note dead-letter queues are now standard in production event-driven agent deployments handling thousands of concurrent tasks. — [zylos.ai — Agent Workflow Orchestration Patterns](https://zylos.ai/research/2026-04-14-agent-workflow-orchestration-patterns)
- **Architecture guide:** Thinking Inc's practitioner survey of 2026 enterprise agent deployments identifies the supervisor pattern (one orchestrator hands off to specialists) as the dominant architecture when workflow steps are known in advance and agents need structured handoffs. — [thinking.inc — Agent Orchestration Patterns](https://thinking.inc/en/blue-ocean/agentic/agent-orchestration-patterns)

## Gotchas

- **Subagent hallucinations don't fail loudly.** A subagent can return confident, plausible-but-wrong output as HTTP 200. Treat every subagent output as untrusted until validated. Add a verification step in the supervisor before synthesis.
- **Context window pressure moves, not disappears.** Sending large context to N parallel subagents multiplies token cost even if each subagent runs faster. Compress context before dispatch.
- **Supervisor prompt drift.** The orchestrator's system prompt must stay stable across sessions. If the supervisor starts making inconsistent routing decisions after 50+ queries, its prompt has drifted — rebuild from a clean template, don't patch.
- **Timeout orchestration is non-negotiable.** Without per-step timeouts and a max-turns cap, a stuck subagent blocks the entire pipeline. Set explicit limits for each subagent and an overall execution budget.
