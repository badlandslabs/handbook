# S-2567 · The Context Substrate Stack — When Your Agent Knows Everything and Understands Nothing

Your agent has a 200K-token context window. You've loaded it with your entire knowledge base, your recent Slack history, three years of ticket data, and the full contents of your wiki. The model can see everything. Your agent still deletes the production database, sends a contract amendment to the wrong client, and recommends a feature that violates your own documented policy. The problem is not the model. The problem is not the prompt. The problem is that your agent is drowning in data but starving for the right context at the right moment. This is the stack for building the governed data substrate that lets agents know what they can trust, what they don't know, and what they should act on.

## Forces

- **Teams build the data layer last, but it determines first whether the agent works.** Only 11% of organizations that claim AI agent adoption actually have agents in production (Atlan/IDC, 2026). The gap traces to ungoverned context — not model quality, not prompt engineering. The governed data substrate is the layer most teams build last, but it must come first.
- **Context failures are invisible until they bite.** The agent produces a plausible answer, so it looks correct. Only when traced does the failure surface: wrong document retrieved, stale data from 6 months ago, or "lost in the middle" — relevant facts buried 40,000 tokens deep where the model discounts them.
- **Retrieval quality compounds downstream.** A retrieval error doesn't just produce one bad output — it propagates into every subsequent reasoning step. An agent making 20 tool calls amplifies a single context error 20 times.
- **"Dump-truck" context is the dominant failure pattern in production.** Arize AI's field analysis of millions of production decision paths found that most teams treat context windows like dump trucks — indexing entire Salesforce instances, wikis, or database exports without scope, structure, or freshness constraints. Noise enters the context window faster than relevance can be preserved.
- **The 65/35 split redefines where to invest.** Gartner (2025) found the LLM itself is responsible for only 35% of production agent failures. The remaining 65% stem from context infrastructure, observability gaps, and retrieval quality — engineering problems, not model problems.

## The move

Context engineering — the practice of curating what enters the LLM's context window at each step — has become a core production discipline. The pattern that works:

- **Scope retrieval by query type, not by volume.** Different queries need different slices of context. Route intent to the right data domain (customer records, policy docs, support history) before retrieving. Blind retrieval against the full corpus produces the dump-truck failure.
- **Enforce deterministic context blocks, not document-level retrieval.** Retrieve at the section or fact level, not the document level. Document-level retrieval introduces irrelevant surrounding context and buries the relevant signal.
- **Rank for recency, relevance, and trust score.** Timestamps are a first-class signal for agents in production. A 3-year-old policy document should carry a freshness penalty. Assign trust scores to data sources — verified HR records vs. a stale Confluence page should be weighted differently.
- **Build a governed data substrate — not just a vector store.** The substrate includes: data freshness policies (how old is too old?), scope constraints (what domain does this agent's query actually need?), trust hierarchies (which sources override which?), and explicit "unknown" signals (what does the agent do when the right context isn't there?). This is governance, not just infrastructure.
- **Detect context failures at retrieval time, not at output time.** If retrieval returns empty results or below-threshold relevance, surface that signal to the agent explicitly. A "no relevant data found" signal is correct behavior. A confident hallucinated answer is not.
- **Design a three-layer context delivery stack.** From Redis's context engine model: (1) Protocol layer (MCP, tool interfaces) — how the agent accesses data. (2) Delivery layer (hybrid vector/keyword search, context graphs) — how relevance is ranked. (3) Governed data substrate (freshness, trust, scope, lineage) — what data the agent is allowed to use and under what conditions.

## Evidence

- **Research/Field Analysis:** Arize AI analyzed millions of production decision paths and found retrieval noise and context window overload the dominant failure pattern. "Teams index entire Salesforce instances or internal wikis without enforcing structure or scope. Retrieval operates at the document level rather than deterministic, trackable blocks." — [Why AI Agents Break: A Field Analysis of Production Failures](https://arize.com/blog/common-ai-agent-failures/), January 2026
- **Engineering Blog / Primary Research:** Atlan/IDC found only 11% of organizations claiming AI agent adoption actually have agents in production, despite 79% claiming adoption. The gap "traces to ungoverned context, not model quality." The governed data substrate — freshness policies, scope constraints, trust hierarchies, explicit "unknown" signals — is "the layer most teams build last, but it must come first for production success." — [Context Infrastructure for AI Agents: The Complete Guide](https://atlan.com/know/context-infrastructure-for-ai-agents/), April 2026
- **Platform Research / Primary:** Redis's analysis of production agent failures found that "most production agent failures aren't model failures. They're context failures: the data the agent needed was somewhere in the stack, just not where the agent could access it, not fresh, or not connected to what came before." — [What is a Context Engine?](https://redis.io/blog/what-is-a-context-engine/), May 2026

## Gotchas

- **Adding more context does not fix bad context.** Doubling the retrieval window when the top results are irrelevant just dilutes signal further. Scope and precision beat volume.
- **RAG alone is not a context engine.** RAG handles retrieval. A context engine handles freshness, trust, routing, and explicit "unknown" signals. Teams that treat their vector DB as their entire context strategy miss the governance layer entirely.
- **Context failures compound — retrieval errors don't stay contained.** A wrong document retrieved at step 3 of a 20-step agent task corrupts every subsequent reasoning step. Build error detection into retrieval, not just output validation.
