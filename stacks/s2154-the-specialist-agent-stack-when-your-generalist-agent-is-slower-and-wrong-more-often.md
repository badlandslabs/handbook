# S-2154 · The Specialist Agent Stack

When a single agent handles an entire multi-step workflow and produces slow, inconsistent results — but the instinct to "reduce API calls" keeps teams from fixing it.

## Forces

- **Fewer calls feels cheaper; more calls actually is.** The intuitive assumption: consolidate into one agent, one context, fewer API calls. In practice, this produces the opposite — slower responses, higher error rates, and context that saturates before the task is done.
- **Generalist prompts drift; specialist prompts hold.** A single prompt that must cover "get data, decide what to do, format output, check quality" degrades at each step boundary. Narrower prompts stay on-task longer.
- **Orchestration overhead vs. coordination cost.** Adding more agents means more infrastructure. But the cost of that infrastructure is paid once; the cost of a wrong answer from an over-loaded generalist is paid every time it runs.

## The move

Split one generalist agent into a pipeline of narrower, single-purpose agents, each with a small, stable prompt and a defined input/output schema.

- **Break on task boundaries, not arbitrary steps.** Identify where the workflow has distinct concerns — data fetch, decision, formatting, validation — and make each a separate agent.
- **Keep prompts under 500 tokens.** Smaller prompts are faster to tokenize, cheaper to run, and less prone to drift. If a prompt exceeds 500 tokens, that's a sign the agent has grown beyond its scope.
- **Use typed schemas for all inter-agent communication.** Define Pydantic or JSON schemas for what each agent receives and returns. This eliminates the "agent loses track of what it already did" failure mode.
- **Route errors to a recovery agent, not back to the generalist.** A dedicated fallback handler that can re-prompt or re-run only the failing step is cheaper than re-executing the whole pipeline.
- **Instrument at the call level, not the session level.** Track latency and cost per agent, not just end-to-end. This reveals which specialists are worth the overhead.

## Evidence

- **Engineering blog (HockeyStack):** After 1+ year running multi-agent pipelines in production, splitting tasks into smaller, simpler, more narrowly-scoped LLM calls "reliably improved latency, cost, and reliability" — directly contradicting their initial assumption that fewer API calls were better. Their initial single-agent lead-ranking approach produced >30 second latency; splitting into specialized agents brought it down significantly. — [https://www.hockeystack.com/applied-ai/optimizing-latency-and-cost-in-multi-agent-systems](https://www.hockeystack.com/applied-ai/optimizing-latency-and-cost-in-multi-agent-systems)
- **Hacker News thread (Ask HN, 2025):** Multiple practitioners echoed the same pattern. One commenter: "treating the entire conversation thread as the context window, not just the latest message" was the key insight. Another: a single generalist agent's prompt grew to cover too many concerns, and splitting it was the fix. — [https://news.ycombinator.com/item?id=47660705](https://news.ycombinator.com/item?id=47660705)
- **Framework analysis (Pharos Production, 2026):** LangGraph (stateful graph, slower but rigorous) is preferred for critical infrastructure; CrewAI (role-based, 5.7x faster deployment) for ROI-focused workflows; AutoGen for software engineering tasks. Each reflects a different tradeoff on the specialist vs. generalist spectrum. — [https://pharosproduction.com/insights/engineering/langchain-vs-crewai-vs-autogen/](https://pharosproduction.com/insights/engineering/langchain-vs-crewai-vs-autogen/)

## Gotchas

- **Not every split is worth it.** If two tasks are tightly coupled and one never changes without the other, splitting just adds latency with no reliability gain. Split at genuine decision boundaries.
- **The "fewer calls" trap is seductive.** Engineers optimize for API call count because it has a direct cost. But if 3 calls at 95% accuracy beats 1 call at 70%, the math is obvious when you track cost-per-correct-output, not cost-per-call.
- **Specialists still need a coordinator.** A pipeline of specialists without a routing agent that can decide "this input needs steps A and C but not B" will over-call. Build the router first.
- **Specialist prompts still drift in long chains.** Even narrow prompts degrade after 10+ steps of context accumulation. Compact state between agents, not within them.
