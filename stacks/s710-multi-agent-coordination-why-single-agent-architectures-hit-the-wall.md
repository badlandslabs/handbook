# S-710 · Multi-Agent Coordination: Why Single-Agent Architectures Hit the Wall

[Your agent handles a 200-page SEC filing alongside API docs and user feedback in one context window. Accuracy tanks on buried facts. Safety guardrails disappear under new messages. The "coder" persona bleeds into the "creative writer." You're not prompts away from a fix — you're at an architectural wall. The way forward is splitting work across specialized agents with the right coordination pattern.]

## Forces

- **"Lost in the middle" degrades accuracy by 73%.** Long context doesn't solve the problem — it makes it worse. Models perform dramatically worse on information buried in the middle of large contexts, regardless of context window size.
- **One agent, one persona — until it's not.** When a single agent handles multiple domains, persona bleed causes hallucinations (coding agent hallucinating non-existent libraries in a creative task) and guardrail burial (safety constraints get overwhelmed by recent messages).
- **Coordination overhead is real but bounded.** The cost of routing between agents is finite and observable. The cost of a degraded single-agent is invisible until it causes an incident.
- **Which coordination pattern to use is non-obvious.** Supervisor, peer-to-peer, and hierarchical patterns each have distinct failure modes and fit different task structures.

## The Move

Split the monolithic agent along domain boundaries and route work through a coordination layer matched to the task structure:

- **Use a Supervisor (hierarchical) pattern** when tasks decompose cleanly into independent subtasks with a single decision-maker needed at the end. The supervisor decomposes, assigns, and synthesizes. EvidionAI's research pipeline exemplifies this: Supervisor → Search → Code → Analysis → Skeptic → back to Supervisor.
- **Use peer-to-peer coordination** when agents must collaborate simultaneously on the same artifact (e.g., a code review requiring both security and performance perspectives running in parallel). Requires explicit routing logic or a shared blackboard.
- **Use hierarchical delegation** for complex organizational workflows where mid-level managers own a domain and escalate edge cases up. This mirrors how human companies scale — each layer has a bounded responsibility.
- **Distribute context to match agent responsibility.** Each agent gets only the context relevant to its role. A "Lost in the Middle" problem for one agent is a signal to add a retrieval or summarization step, not a signal to increase context window.
- **Add a Skeptic/Validator agent** that actively tries to break conclusions before the supervisor synthesizes. This is the highest-leverage investment in multi-agent reliability.
- **Bound each agent's max iterations and token budget.** Independent of the coordination pattern, every agent needs hard limits. The coordination pattern doesn't protect against cost overruns from a single runaway agent.

## Evidence

- **HN Show HN (EvidionAI):** Open-source research pipeline using LangGraph with a Supervisor orchestrating Search, Code, Analysis, and Skeptic agents — the Skeptic explicitly challenges conclusions before synthesis — [https://news.ycombinator.com/item?id=47510639](https://news.ycombinator.com/item?id=47510639)
- **Comet Blog (Multi-Agent Systems):** Documents the "Lost in the Middle" 73% performance degradation, persona bleed, and guardrail burial as core drivers for multi-agent decomposition, recommending distributed context management as the architectural fix — [https://www.comet.com/site/blog/multi-agent-systems](https://www.comet.com/site/blog/multi-agent-systems)
- **JetThoughts (Agent Framework Comparison):** Real-world production status: LangGraph at Klarna/Replit/Elastic (production, durable execution), CrewAI active at v0.98+ for content/support pipelines (fast prototyping), AutoGen in maintenance mode since Oct 2025 with successor being Microsoft Agent Framework — [https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025/](https://jetthoughts.com/blog/autogen-crewai-langgraph-ai-agent-frameworks-2025/)

## Gotchas

- **Don't split agents prematurely.** If a task fits in a single agent's context without degradation, adding coordination overhead for "best practices" reasons is unnecessary complexity. Measure context utilization before splitting.
- **Supervisor becomes a bottleneck.** A single supervisor making all routing decisions is itself a single point of failure. For high-throughput systems, the supervisor should delegate routing authority, not own it.
- **Inter-agent communication cost compounds.** Each hop between agents adds latency and token cost. Deep hierarchies (Supervisor → Manager → Worker → Sub-worker) can be slower than a well-prompted single agent. Two to three hops maximum.
- **Context routing is harder than it looks.** Passing the right context to the right agent without leaking irrelevant information requires explicit filtering. Don't just dump the full context on every agent.
